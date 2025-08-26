# Kodachrome

Welcome to the kodachrome project!

## Setting up environment variables

In order to run the kinfer-evals service, you need to set some environment variables. This repo uses a local .env file for secrets and config (loaded via python-dotenv).

Create it in the repo root as follows:

```bash
cd /path/to/kodachrome

# Create .env with your secrets and optional overrides
cat > .env <<'EOF'
# --- REQUIRED ---
BOT_TOKEN=your_discord_bot_token

# --- OPTIONAL (Notion logging) ---
# If set, eval results will be pushed to your Notion DB.
NOTION_API_KEY=your_notion_integration_token
NOTION_DB_ID=your_notion_database_id

# --- OPTIONAL (eval behavior overrides) ---
# Defaults shown; override only if you want different behavior.
EVAL_ROBOT=kbot-headless
EVAL_NAME=walk_forward_right
EVAL_OUT_DIR=runs
EVAL_MAX_CONCURRENCY=1       # how many evals to run in parallel
EVAL_TIMEOUT_S=1800          # kill evals that exceed this many seconds
EOF

# Keep it private and out of git
chmod 600 .env
echo ".env" >> .gitignore
```

### Notes

- Values are plain text (no quotes), one per line: `KEY=value`.
- After changing `.env`, restart the service so it picks up updates:

```bash
systemctl --user restart kodachrome-bot.service
```

- Not using Notion? Leave `NOTION_API_KEY`/`NOTION_DB_ID` unset; the bot will still run.


## Setting up systemd service

You can manage the Kodachrome Discord bot using a **systemd user service**.  

⚠️ **Note:** The environment variables (`.env`) must be set up before this service will run.

Create the service file at:

```bash
mkdir -p ~/.config/systemd/user
# create systemd unit file ~/.config/systemd/user/kodachrome-bot.service
[Unit]
Description=Kodachrome Discord bot (kinfer-evals)
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
# Run from the repo so load_dotenv() sees .env
WorkingDirectory=/home/dpsh/kodachrome

# Use your conda env's Python
ExecStart=/home/dpsh/miniconda3/envs/klog/bin/python -u kchrome/discord/bot.py

# Make sure the bot's subprocess can find kinfer-eval-osmesa
Environment=PATH=/home/dpsh/miniconda3/envs/klog/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin

# Be resilient
Restart=always
RestartSec=5
UMask=0077

[Install]
WantedBy=default.target
EOF
```

### Managing the service

```bash
# Reload systemd to pick up the new service
systemctl --user daemon-reload

# Enable service to start on login
systemctl --user enable kodachrome-bot.service

# Start the service now
systemctl --user start kodachrome-bot.service

# Check service status
systemctl --user status kodachrome-bot.service
```

---

That’s it — the bot will now start automatically with your user session and restart if it crashes.
