import logging
import os

import pytz
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("PCPrime")

TOKEN = os.getenv("DISCORD_TOKEN")
ANNOUNCE_CHANNEL_ID = int(os.getenv("ANNOUNCE_CHANNEL_ID", "0") or "0")
GUILD_ID = os.getenv("GUILD_ID")  # optional — leave blank to cover all servers

ART = pytz.timezone("America/Argentina/Buenos_Aires")
