import discord
from discord.ext import commands
import os
from pathlib import Path
import logging
from dotenv import load_dotenv
import traceback
import sys
import asyncio
import shlex
import re

from kchrome.discord.names_generator import get_random_name

# Configuration
load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN')
SAVE_DIR = Path('policies')
MAX_FILE_SIZE_MB = 8  # Discord default limit (8 MB)
ALLOWED_EXTENSIONS = {'.kinfer'}  # Optional extension filter

# Eval configuration (can be overridden via environment variables)
EVAL_ROBOT = os.getenv('EVAL_ROBOT', 'kbot-headless')
EVAL_NAME = os.getenv('EVAL_NAME', 'walk_forward_right')
EVAL_OUT_DIR = Path(os.getenv('EVAL_OUT_DIR', 'runs'))
EVAL_PYTHON = os.getenv('EVAL_PYTHON', sys.executable)
EVAL_GL = os.getenv('EVAL_GL', 'egl')  # 'egl' or 'osmesa'
EVAL_USE_SOFTWARE = os.getenv('EVAL_USE_SOFTWARE', '1')  # '1' to force llvmpipe with EGL

# Setup
SAVE_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Intents
intents = discord.Intents.default()
intents.message_content = True
intents.messages = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    print("Connected to servers:")
    for guild in bot.guilds:
        print(f"- {guild.name} (ID: {guild.id})")

async def save_policy(attachment: discord.Attachment) -> str | None:
    print("request")
    try:
        # Validate extension (optional)
        ext = Path(attachment.filename).suffix
        if ext not in ALLOWED_EXTENSIONS:
            return f"Invalid file type: must be one of {', '.join(ALLOWED_EXTENSIONS)}"

        file_bytes = await attachment.read()
        if not file_bytes:
            return "File is empty"

        # Generate unique name
        for _ in range(100):  # fail-safe loop cap
            nickname = get_random_name(retry=False)
            target_path = SAVE_DIR / f"{nickname}.kinfer"
            if not target_path.exists():
                break
        else:
            return "Failed to generate a unique policy name"

        # Write file
        with open(target_path, 'wb') as f:
            f.write(file_bytes)

        return nickname

    except Exception as e:
        logger.error(f"Failed to save policy: {e}")
        traceback.print_exc()
        return None

async def run_eval_subprocess(kinfer_path: Path, robot: str, eval_name: str, out_dir: Path) -> tuple[int, str, str]:
    """Run kinfer-evals via subprocess and capture stdout/stderr.

    Returns (returncode, stdout, stderr).
    """
    cmd = [
        EVAL_PYTHON,
        "-m",
        "kinfer_evals.core.eval_runner",
        str(kinfer_path),
        robot,
        eval_name,
        "--out",
        str(out_dir),
    ]

    env = os.environ.copy()
    if EVAL_GL.lower() == "osmesa":
        env["MUJOCO_GL"] = "osmesa"
        # OSMesa generally needs no other vars
    else:
        env["MUJOCO_GL"] = "egl"
        # Prefer surfaceless software EGL for VMs/headless
        env.setdefault("EGL_PLATFORM", "surfaceless")
        if EVAL_USE_SOFTWARE == "1":
            env.setdefault("LIBGL_ALWAYS_SOFTWARE", "1")
            env.setdefault("MESA_LOADER_DRIVER_OVERRIDE", "llvmpipe")

    logger.info("Launching eval: %s", shlex.join(cmd))
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    out_b, err_b = await proc.communicate()
    return proc.returncode, out_b.decode(errors="replace"), err_b.decode(errors="replace")

def extract_url(text: str) -> str | None:
    m = re.search(r"https?://\S+", text)
    return m.group(0) if m else None

@bot.command(name='policy')
async def upload_file(ctx):
    try:
        attachments = ctx.message.attachments
        if not attachments:
            await ctx.reply("❌ Please attach a file with the `!policy` command.")
            return

        if len(attachments) > 1:
            await ctx.reply("❌ Please attach only **one** file at a time.")
            return

        result = await save_policy(attachments[0])

        if result is None:
            await ctx.reply("❌ An internal error occurred while saving the file.")
        elif result.startswith("File too large"):
            await ctx.reply(f"❌ {result} (max {MAX_FILE_SIZE_MB} MB).")
        elif result.startswith("Invalid file type"):
            await ctx.reply(f"❌ {result}.")
        elif result.startswith("File is empty"):
            await ctx.reply("❌ The uploaded file is empty.")
        elif result.startswith("Failed to generate"):
            await ctx.reply("❌ Could not generate a unique name. Try again.")
        else:
            await ctx.reply(
                f"✅ Your policy has been added to the queue. Its nickname is `{result}`"
            )

            # Run the eval and report back with the Notion URL when done
            async def _run_and_report(nickname: str) -> None:
                try:
                    kinfer_path = SAVE_DIR / f"{nickname}.kinfer"
                    if not kinfer_path.exists():
                        await ctx.reply(
                            f"⚠️ Could not find saved file for `{nickname}` at `{kinfer_path}`"
                        )
                        return

                    await ctx.reply(
                        f"▶️ Running eval `{EVAL_NAME}` on robot `{EVAL_ROBOT}` for `{nickname}`…"
                    )

                    rc, out, err = await run_eval_subprocess(kinfer_path, EVAL_ROBOT, EVAL_NAME, EVAL_OUT_DIR)
                    url = extract_url(out) or extract_url(err)
                    if rc == 0 and url:
                        await ctx.reply(f"📄 Notion log: {url}")
                    elif rc == 0:
                        await ctx.reply(
                            "ℹ️ Eval completed, but Notion link was not detected in output. Check server logs."
                        )
                    else:
                        await ctx.reply(
                            f"❌ Eval failed (rc={rc}).\nstdout:\n```{out.strip()[:1500]}```\nstderr:\n```{err.strip()[:1500]}```"
                        )
                except Exception as exc:
                    logger.error("Eval run failed: %s", exc)
                    await ctx.reply("❌ Eval failed. Check server logs.")

            asyncio.create_task(_run_and_report(result))

    except Exception as e:
        logger.error(f"Unhandled exception: {e}")
        traceback.print_exc()
        await ctx.send("⚠️ Something went wrong while processing your request.")

def main():
    bot.run(BOT_TOKEN)

if __name__ == "__main__":
    main()

