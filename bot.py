import argparse
import random
from datetime import datetime, timedelta

import discord
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

from src.config import TOKEN, ANNOUNCE_CHANNEL_ID, GUILD_ID, ART, log
from src.holidays import should_enforce_tonight, next_enforcement_datetime
from src.messages import SWEEP_MESSAGES, GUARD_MESSAGES

# ── Bot & scheduler ───────────────────────────────────────────────────────────

intents = discord.Intents.default()
intents.voice_states = True    # GUILD_VOICE_STATES — see who joins/leaves voice
intents.message_content = True  # GUILD_MESSAGES — send messages in channels
intents.members = True          # needed to read guild.owner_id on members

bot = discord.Client(intents=intents)
scheduler = AsyncIOScheduler(timezone=ART)


# ── Helpers ───────────────────────────────────────────────────────────────────

def is_quiet_hours() -> bool:
    """Returns True if current ART time is between 01:00 and 06:00."""
    now = datetime.now(ART)
    return 1 <= now.hour < 6


def is_nico(message: discord.Message) -> bool:
    """Returns True if the message is from nico_1607 or mentions them."""
    if message.author.name.lower() == "nico_1607":
        return True
    return any(m.name.lower() == "nico_1607" for m in message.mentions)


def should_skip(member: discord.Member) -> bool:
    """Returns True for the bot itself and the server owner."""
    if member.bot:
        return True
    if member.id == member.guild.owner_id:
        return True
    return False


def resolve_announce_channel(guild: discord.Guild) -> discord.TextChannel | None:
    """
    Returns the channel to post announcements in, in priority order:
    1. ANNOUNCE_CHANNEL_ID from .env (explicit override)
    2. guild.system_channel (the server's System Messages channel)
    3. First text channel the bot can write to (last resort)
    """
    if ANNOUNCE_CHANNEL_ID:
        ch = guild.get_channel(ANNOUNCE_CHANNEL_ID)
        if ch:
            return ch
        log.warning("ANNOUNCE_CHANNEL_ID %d not found in %s, falling back", ANNOUNCE_CHANNEL_ID, guild.name)

    if guild.system_channel and guild.system_channel.permissions_for(guild.me).send_messages:
        return guild.system_channel

    for ch in guild.text_channels:
        if ch.permissions_for(guild.me).send_messages:
            return ch

    return None


async def send_announcement(guild: discord.Guild, message: str) -> None:
    channel = resolve_announce_channel(guild)
    if channel is None:
        log.warning("No writable text channel found in guild %s", guild.name)
        return
    try:
        await channel.send(message)
    except discord.Forbidden:
        log.warning("No permission to send message in #%s", channel.name)
    except discord.HTTPException as exc:
        log.error("Failed to send announcement: %s", exc)


async def alert_scraping_failure() -> None:
    guilds = [bot.get_guild(int(GUILD_ID))] if GUILD_ID else list(bot.guilds)
    guilds = [g for g in guilds if g is not None]
    for guild in guilds:
        await send_announcement(guild, "Che el scraping de feriados no funca, arreglenme vagos..")


# ── The Sweep ─────────────────────────────────────────────────────────────────

async def nightly_sweep() -> None:
    """Disconnect every non-exempt user from every voice channel, then announce."""
    enforce, scrape_failed = await should_enforce_tonight()

    if scrape_failed:
        await alert_scraping_failure()

    if not enforce:
        log.info("Nightly sweep skipped.")
        return

    log.info("Nightly sweep started.")

    guilds = [bot.get_guild(int(GUILD_ID))] if GUILD_ID else list(bot.guilds)
    guilds = [g for g in guilds if g is not None]

    for guild in guilds:
        kicked = 0
        for vc in guild.voice_channels:
            for member in list(vc.members):
                if should_skip(member):
                    continue
                try:
                    await member.move_to(None)
                    kicked += 1
                    log.info("Swept %s from %s", member.display_name, vc.name)
                except discord.Forbidden:
                    log.warning("No permission to move %s", member.display_name)
                except discord.HTTPException as exc:
                    log.error("Error moving %s: %s", member.display_name, exc)

        msg = random.choice(SWEEP_MESSAGES)
        if kicked > 0:
            msg += f" ({kicked} vago{'s' if kicked != 1 else ''} echado{'s' if kicked != 1 else ''})"
        await send_announcement(guild, msg)

    log.info("Nightly sweep complete.")


# ── The Guard ─────────────────────────────────────────────────────────────────

@bot.event
async def on_voice_state_update(
    member: discord.Member,
    before: discord.VoiceState,
    after: discord.VoiceState,
) -> None:
    """Instantly disconnect anyone who joins a voice channel during quiet hours."""
    joined_channel = after.channel is not None and (
        before.channel is None or before.channel.id != after.channel.id
    )
    if not joined_channel:
        return

    if not is_quiet_hours():
        return

    enforce, scrape_failed = await should_enforce_tonight()

    if scrape_failed:
        await alert_scraping_failure()

    if not enforce:
        return

    if should_skip(member):
        return

    log.info("Guard: disconnecting %s who joined %s", member.display_name, after.channel.name)

    try:
        await member.move_to(None)
    except discord.Forbidden:
        log.warning("Guard: no permission to move %s", member.display_name)
        return
    except discord.HTTPException as exc:
        log.error("Guard: error moving %s: %s", member.display_name, exc)
        return

    await send_announcement(member.guild, random.choice(GUARD_MESSAGES))


# ── Commands ──────────────────────────────────────────────────────────────────

_DAYS_ES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
_MONTHS_ES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


@bot.event
async def on_message(message: discord.Message) -> None:
    if message.author.bot:
        return

    content = message.content.strip().lower()
    bot_mentioned = bot.user in message.mentions

    if is_nico(message):
        await message.channel.send("_PARALIZADO_")
        return

    if content == "$p":
        await message.channel.send("$pelotudo")
        return

    is_next_command = content.startswith("$next") or bot_mentioned

    if not is_next_command:
        return

    next_dt = await next_enforcement_datetime()
    day_name = _DAYS_ES[next_dt.weekday()]
    month_name = _MONTHS_ES[next_dt.month - 1]
    response = (
        f"La próxima patada es el **{day_name} {next_dt.day} de {month_name}** a la **01:00 AM**. "
        f"Aprovechen hasta entonces."
    )
    await message.channel.send(response)


# ── Bot lifecycle ─────────────────────────────────────────────────────────────

@bot.event
async def on_ready() -> None:
    log.info("PCPrime online as %s (id=%d)", bot.user, bot.user.id)

    if args.test_sweep:
        delay = args.test_sweep
        run_at = datetime.now(ART) + timedelta(seconds=delay)
        scheduler.add_job(
            nightly_sweep,
            DateTrigger(run_date=run_at),
            id="nightly_sweep",
            replace_existing=True,
        )
        log.info("TEST MODE: sweep will fire in %d seconds.", delay)
    else:
        scheduler.add_job(
            nightly_sweep,
            CronTrigger(hour=1, minute=0, timezone=ART),
            id="nightly_sweep",
            replace_existing=True,
        )
        log.info("Scheduler started. Sweep fires at 01:00 ART.")

    scheduler.start()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PCPrime sleep-schedule bot")
    parser.add_argument(
        "--test-sweep",
        metavar="SECONDS",
        type=int,
        nargs="?",
        const=10,
        default=None,
        help="Trigger the nightly sweep after SECONDS seconds (default: 10). For testing only.",
    )
    args = parser.parse_args()

    if not TOKEN:
        raise RuntimeError("DISCORD_TOKEN is not set. Check your .env file.")
    bot.run(TOKEN)
