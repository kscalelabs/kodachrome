"""Discord bot for running kinfer-evals on policies."""

import asyncio
import json
import logging
import os
import re
import shlex
import sys
import traceback
from pathlib import Path

import discord
from discord.ext import commands
from dotenv import load_dotenv

from kchrome.discord.names_generator import get_random_name

# Configuration
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
SAVE_DIR = Path("policies")
ALLOWED_EXTENSIONS = {".kinfer"}  # case-insensitive check applied below

# Eval configuration (can be overridden via environment variables)
EVAL_ROBOT = os.getenv("EVAL_ROBOT", "kbot-headless")
MOTION_NAME = os.getenv("MOTION_NAME", "walking_and_standing_unittest")  # kmotions motion name
EVAL_OUT_DIR = Path(os.getenv("EVAL_OUT_DIR", "runs"))
LOCAL_MODEL_DIR = Path(os.getenv("LOCAL_MODEL_DIR", "/home/dpsh/kscale_asset_files/kbot-headless"))

# Optional: cap concurrent evals (1 = simple guard). 0/negatives are treated as 1.
_conc = max(1, int(os.getenv("EVAL_MAX_CONCURRENCY", "1")))
EVAL_SEM = asyncio.Semaphore(_conc)

# Optional: kill runaway evals
EVAL_TIMEOUT_S = float(os.getenv("EVAL_TIMEOUT_S", "1800"))  # 30 minutes default

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
async def on_ready() -> None:
    logger.info("Logged in as %s", bot.user)
    logger.info("Connected to servers:")
    for guild in bot.guilds:
        logger.info("- %s (ID: %s)", guild.name, guild.id)


async def save_policy(attachment: discord.Attachment) -> str | None:
    try:
        # Validate extension (optional)
        ext = Path(attachment.filename).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            return f"Invalid file type: must be one of {', '.join(ALLOWED_EXTENSIONS)}"

        # Generate unique name
        for _ in range(100):  # fail-safe loop cap
            nickname = get_random_name(retry=False)
            target_path = SAVE_DIR / f"{nickname}{ext}"
            if not target_path.exists():
                break
        else:
            return "Failed to generate a unique policy name"

        # Stream to disk (avoids loading large files into memory)
        await attachment.save(fp=target_path)

        return nickname

    except Exception as e:
        logger.error("Failed to save policy: %s", e)
        traceback.print_exc()
        return None


async def run_eval_subprocess(kinfer_path: Path, robot: str, motion_name: str, out_dir: Path) -> tuple[int, str, str]:
    """Run kinfer-evals via OSMesa CLI entry point and capture stdout/stderr.

    Args:
        motion_name: Motion name from kmotions (e.g., 'salute', 'wave', 'walking_and_standing_unittest')
    
    Returns (returncode, stdout, stderr).
    """
    # Use the osmesa CLI entry point which sets up proper headless rendering environment
    cmd = [
        "kinfer-eval-osmesa",
        str(kinfer_path),
        robot,
        motion_name,  # Changed: now a kmotions motion name, not eval name
        "--out",
        str(out_dir),
    ]
    # Thread through local model dir if needed
    if LOCAL_MODEL_DIR:
        cmd += ["--local-model-dir", str(LOCAL_MODEL_DIR)]

    env = os.environ.copy()
    logger.info("Launching eval with OSMesa CLI: %s", shlex.join(cmd))
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    try:
        out_b, err_b = await asyncio.wait_for(proc.communicate(), timeout=EVAL_TIMEOUT_S)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return 124, "", "Timed out (EVAL_TIMEOUT_S)"
    rc = await proc.wait()
    return rc, out_b.decode(errors="replace"), err_b.decode(errors="replace")

def extract_url(text: str) -> str | None:
    m = re.search(r"https?://\S+", text)
    return m.group(0) if m else None


def _latest_run_dir(base_out_dir: Path, motion_name: str) -> Path | None:
    root = base_out_dir / motion_name
    if not root.exists():
        return None
    subdirs = [d for d in root.iterdir() if d.is_dir()]
    return max(subdirs, key=lambda d: d.stat().st_mtime) if subdirs else None


def _notion_url_from_summary(base_out_dir: Path, motion_name: str, kinfer_path: Path) -> str | None:
    """Scan run_summary.json files for this kinfer path and return notion_url if present."""
    root = base_out_dir / motion_name
    if not root.exists():
        return None
    kinfer_abs = str(kinfer_path.resolve())
    # Iterate newest-first
    for d in sorted([p for p in root.iterdir() if p.is_dir()], key=lambda p: p.stat().st_mtime, reverse=True):
        f = d / "run_summary.json"
        if not f.exists():
            continue
        try:
            obj = json.loads(f.read_text())
            if obj.get("kinfer_file") == kinfer_abs:
                url = obj.get("notion_url")
                if url:
                    return url
        except Exception:
            continue
    return None


@bot.command(name="policy")
async def upload_file(ctx: commands.Context) -> None:
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
        elif result.startswith("Invalid file type"):
            await ctx.reply(f"❌ {result}.")
        elif result.startswith("Failed to generate"):
            await ctx.reply("❌ Could not generate a unique name. Try again.")
        else:
            await ctx.reply(f"✅ Your policy has been added to the queue. Its nickname is `{result}`")

            # Run the eval and report back with the Notion URL when done
            async def _run_and_report(nickname: str) -> None:
                try:
                    kinfer_path = SAVE_DIR / f"{nickname}.kinfer"
                    if not kinfer_path.exists():
                        await ctx.reply(f"⚠️ Could not find saved file for `{nickname}` at `{kinfer_path}`")
                        return

                    await ctx.reply(f"▶️ Running eval with motion `{MOTION_NAME}` on robot `{EVAL_ROBOT}` for `{nickname}`…")

                    async with EVAL_SEM:  # simple concurrency guard
                        rc, out, err = await run_eval_subprocess(kinfer_path, EVAL_ROBOT, MOTION_NAME, EVAL_OUT_DIR)

                    # Prefer artifacts written by kinfer-evals; fallback to regex
                    url = _notion_url_from_summary(EVAL_OUT_DIR, MOTION_NAME, kinfer_path)
                    if not url:
                        latest = _latest_run_dir(EVAL_OUT_DIR, MOTION_NAME)
                        if latest and (latest / "notion_url.txt").exists():
                            try:
                                url = (latest / "notion_url.txt").read_text().strip()
                            except Exception:
                                url = None
                    if not url:
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
        logger.error("Unhandled exception: %s", e)
        traceback.print_exc()
        await ctx.send("⚠️ Something went wrong while processing your request.")


def main() -> None:
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN is not set")
        sys.exit(1)
    bot.run(BOT_TOKEN)


if __name__ == "__main__":
    main()
