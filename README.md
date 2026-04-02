# PCPrime — Sleep Schedule Bot

A grumpy porteño Discord bot that kicks everyone off voice channels at 1:00 AM ART and won't let them back in until 6:00 AM.

---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and fill in:

| Variable | Description |
|---|---|
| `DISCORD_TOKEN` | Your bot token from the Discord Developer Portal |
| `ANNOUNCE_CHANNEL_ID` | ID of the text channel for nightly messages |
| `GUILD_ID` | *(Optional)* Restrict to one server. Leave blank for all. |

To get a channel or guild ID: enable **Developer Mode** in Discord settings (`Settings → Advanced → Developer Mode`), then right-click the channel/server → **Copy ID**.

### 3. Discord Developer Portal — Required Intents

Go to [https://discord.com/developers/applications](https://discord.com/developers/applications) → your app → **Bot** tab → scroll to **Privileged Gateway Intents** and enable:

- **Server Members Intent** — needed to read guild ownership and member info
- **Message Content Intent** — needed to send messages in channels

`Voice State` intent is non-privileged and enabled by default.

### 4. Bot Permissions (Invite URL)

When generating your invite URL, the bot needs these OAuth2 scopes and permissions:

- **Scopes:** `bot`
- **Bot Permissions:**
  - `Move Members`
  - `Send Messages`
  - `View Channels`

### 5. Run

```bash
python bot.py
```

---

## How It Works

**The Sweep** — Every night at exactly 01:00 AM ART (`America/Argentina/Buenos_Aires`), the bot:
1. Scans all voice channels in the server
2. Disconnects every user (skips itself and the server owner)
3. Posts a snarky message in your designated announce channel

**The Guard** — Between 01:00 AM and 06:00 AM ART, any user who joins a voice channel is immediately disconnected.

---

## Testing

To test the sweep without waiting until 1 AM, temporarily change the `CronTrigger` in `bot.py` to fire a minute from now:

```python
# Temporary test trigger — fires 1 minute after bot starts
from datetime import datetime, timedelta
from apscheduler.triggers.date import DateTrigger

scheduler.add_job(
    nightly_sweep,
    DateTrigger(run_date=datetime.now(ART) + timedelta(minutes=1)),
    id="nightly_sweep",
    replace_existing=True,
)
```

To test the guard: set `is_quiet_hours()` to always return `True`, join a voice channel, and confirm you're instantly kicked.

---

## Timezone Note

The scheduler uses `America/Argentina/Buenos_Aires` explicitly via `pytz`, so the bot fires at the correct local time regardless of where it's hosted (UK VPS, Glasgow machine, etc.). Never rely on `datetime.now()` without a timezone.
