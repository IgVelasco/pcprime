import asyncio
import json
import logging
import re
import urllib.request
from datetime import datetime
from pathlib import Path

from config import ART

log = logging.getLogger("PCPrime")

HOLIDAYS_FILE = Path(__file__).parent / "holidays.json"

# Keyed by year — only hits the network once per calendar year.
_holiday_cache: dict[int, set[tuple[int, int]]] = {}


def _load_holidays_from_file(year: int) -> set[tuple[int, int]] | None:
    """Reads holidays for `year` from the local holidays.json fallback file."""
    try:
        data = json.loads(HOLIDAYS_FILE.read_text())
        entries = data.get(str(year), [])
        return {(m, d) for m, d in entries}
    except Exception as exc:
        log.error("Could not read holidays.json: %s", exc)
        return None


async def fetch_argentina_holidays(year: int) -> tuple[set[tuple[int, int]], bool]:
    """
    Scrapes holiday dates for `year` from argentina.gob.ar.
    The page embeds all holidays as inline JSON:
      { "date": "DD/MM/YYYY", "label": "...", "type": "..." }

    Returns (holidays, scrape_failed).
    On scrape failure, falls back to holidays.json.
    The caller is responsible for alerting the channel when scrape_failed is True.
    """
    if year in _holiday_cache:
        return _holiday_cache[year], False

    url = f"https://www.argentina.gob.ar/jefatura/feriados-nacionales-{year}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        response = await asyncio.to_thread(urllib.request.urlopen, req, timeout=10)
        html = response.read().decode("utf-8")
        raw_dates = re.findall(r'"date":\s*"(\d{1,2}/\d{2}/\d{4})"', html)
        holidays: set[tuple[int, int]] = set()
        for raw in raw_dates:
            day, month, yr = raw.split("/")
            if int(yr) == year:
                holidays.add((int(month), int(day)))
        _holiday_cache[year] = holidays
        log.info("Loaded %d Argentine holidays for %d.", len(holidays), year)
        return holidays, False
    except Exception as exc:
        log.warning("Holiday scraping failed: %s. Falling back to holidays.json.", exc)
        fallback = _load_holidays_from_file(year)
        if fallback is not None:
            log.info("Using holidays.json fallback: %d entries for %d.", len(fallback), year)
            return fallback, True
        log.error("holidays.json fallback also failed. Assuming no holidays.")
        return set(), True


async def should_enforce_tonight() -> tuple[bool, bool]:
    """
    Returns (should_enforce, scrape_failed).
    should_enforce is False when today (in ART) is a weekend or a public holiday.
    scrape_failed signals the caller to post the alert message.
    """
    today = datetime.now(ART).date()

    # weekday(): Mon=0 … Fri=4, Sat=5, Sun=6
    if today.weekday() >= 5:
        log.info("Skipping enforcement: %s is a weekend.", today.strftime("%A"))
        return False, False

    holidays, scrape_failed = await fetch_argentina_holidays(today.year)
    if (today.month, today.day) in holidays:
        log.info("Skipping enforcement: %s is an Argentine public holiday.", today)
        return False, scrape_failed

    return True, scrape_failed
