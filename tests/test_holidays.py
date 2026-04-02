"""
Tests for src/holidays.py

Covers:
- _load_holidays_from_file: valid data, missing year, corrupt file, missing file
- fetch_argentina_holidays: successful scrape, HTTP failure with fallback, scrape failure flag
- should_enforce_tonight: weekend skip, holiday skip, normal weekday enforcement
- next_enforcement_datetime: skips weekends, skips holidays, finds next valid slot
"""
import json
import re
from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import src.holidays as holidays_module
from src.holidays import _load_holidays_from_file, next_enforcement_datetime, should_enforce_tonight


# ── _load_holidays_from_file ──────────────────────────────────────────────────

def test_load_holidays_valid(tmp_path):
    f = tmp_path / "holidays.json"
    f.write_text(json.dumps({"2026": [[1, 1], [5, 25], [12, 25]]}))
    with patch.object(holidays_module, "HOLIDAYS_FILE", f):
        result = _load_holidays_from_file(2026)
    assert result == {(1, 1), (5, 25), (12, 25)}


def test_load_holidays_missing_year(tmp_path):
    f = tmp_path / "holidays.json"
    f.write_text(json.dumps({"2025": [[1, 1]]}))
    with patch.object(holidays_module, "HOLIDAYS_FILE", f):
        result = _load_holidays_from_file(2026)
    assert result == set()


def test_load_holidays_file_not_found(tmp_path):
    with patch.object(holidays_module, "HOLIDAYS_FILE", tmp_path / "nonexistent.json"):
        result = _load_holidays_from_file(2026)
    assert result is None


def test_load_holidays_corrupt_json(tmp_path):
    f = tmp_path / "holidays.json"
    f.write_text("this is not json {{")
    with patch.object(holidays_module, "HOLIDAYS_FILE", f):
        result = _load_holidays_from_file(2026)
    assert result is None


# ── HTML date parsing (logic extracted for unit testing) ─────────────────────

def _parse_dates_from_html(html: str, year: int) -> set[tuple[int, int]]:
    """Mirrors the parsing logic inside fetch_argentina_holidays."""
    raw_dates = re.findall(r'"date":\s*"(\d{1,2}/\d{2}/\d{4})"', html)
    holidays: set[tuple[int, int]] = set()
    for raw in raw_dates:
        day, month, yr = raw.split("/")
        if int(yr) == year:
            holidays.add((int(month), int(day)))
    return holidays


def test_parse_dates_standard():
    html = '{ "date": "25/05/2026", "label": "Revolución de Mayo", "type": "inamovible" }'
    assert _parse_dates_from_html(html, 2026) == {(5, 25)}


def test_parse_dates_deduplicates():
    html = """
        { "date": "01/01/2026", "label": "Año Nuevo", "type": "inamovible" },
        { "date": "1/01/2026", "label": "New Year", "type": "inamovible" },
    """
    result = _parse_dates_from_html(html, 2026)
    assert result == {(1, 1)}


def test_parse_dates_excludes_other_years():
    html = """
        { "date": "25/12/2026", "label": "Navidad", "type": "inamovible" },
        { "date": "01/01/2027", "label": "Año nuevo", "type": "inamovible" },
    """
    result = _parse_dates_from_html(html, 2026)
    assert result == {(12, 25)}
    assert (1, 1) not in result


def test_parse_dates_empty_html():
    assert _parse_dates_from_html("no dates here", 2026) == set()


# ── fetch_argentina_holidays ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fetch_uses_cache():
    """Second call for the same year should not hit the network."""
    holidays_module._holiday_cache[2026] = {(1, 1)}
    result, failed = await holidays_module.fetch_argentina_holidays(2026)
    assert result == {(1, 1)}
    assert failed is False
    del holidays_module._holiday_cache[2026]


@pytest.mark.asyncio
async def test_fetch_scrape_failure_falls_back_to_file(tmp_path):
    f = tmp_path / "holidays.json"
    f.write_text(json.dumps({"2026": [[12, 25]]}))

    with patch.object(holidays_module, "HOLIDAYS_FILE", f), \
         patch("src.holidays.asyncio.to_thread", side_effect=Exception("network error")), \
         patch.dict(holidays_module._holiday_cache, {}, clear=True):
        result, failed = await holidays_module.fetch_argentina_holidays(2026)

    assert (12, 25) in result
    assert failed is True


@pytest.mark.asyncio
async def test_fetch_scrape_and_file_both_fail(tmp_path):
    with patch.object(holidays_module, "HOLIDAYS_FILE", tmp_path / "missing.json"), \
         patch("src.holidays.asyncio.to_thread", side_effect=Exception("network error")), \
         patch.dict(holidays_module._holiday_cache, {}, clear=True):
        result, failed = await holidays_module.fetch_argentina_holidays(2026)

    assert result == set()
    assert failed is True


# ── should_enforce_tonight ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_no_enforcement_on_saturday():
    saturday = date(2026, 4, 4)
    mock_now = MagicMock()
    mock_now.date.return_value = saturday
    with patch("src.holidays.datetime") as mock_dt:
        mock_dt.now.return_value = mock_now
        enforce, scrape_failed = await should_enforce_tonight()
    assert enforce is False
    assert scrape_failed is False


@pytest.mark.asyncio
async def test_no_enforcement_on_sunday():
    sunday = date(2026, 4, 5)
    mock_now = MagicMock()
    mock_now.date.return_value = sunday
    with patch("src.holidays.datetime") as mock_dt:
        mock_dt.now.return_value = mock_now
        enforce, scrape_failed = await should_enforce_tonight()
    assert enforce is False
    assert scrape_failed is False


@pytest.mark.asyncio
async def test_enforcement_on_regular_weekday():
    monday = date(2026, 4, 6)  # Monday, not a holiday
    mock_now = MagicMock()
    mock_now.date.return_value = monday
    with patch("src.holidays.datetime") as mock_dt, \
         patch("src.holidays.fetch_argentina_holidays", new_callable=AsyncMock) as mock_fetch:
        mock_dt.now.return_value = mock_now
        mock_fetch.return_value = (set(), False)
        enforce, scrape_failed = await should_enforce_tonight()
    assert enforce is True
    assert scrape_failed is False


@pytest.mark.asyncio
async def test_no_enforcement_on_public_holiday():
    # 25 May is Día de la Revolución de Mayo
    holiday = date(2026, 5, 25)
    mock_now = MagicMock()
    mock_now.date.return_value = holiday
    with patch("src.holidays.datetime") as mock_dt, \
         patch("src.holidays.fetch_argentina_holidays", new_callable=AsyncMock) as mock_fetch:
        mock_dt.now.return_value = mock_now
        mock_fetch.return_value = ({(5, 25)}, False)
        enforce, scrape_failed = await should_enforce_tonight()
    assert enforce is False


@pytest.mark.asyncio
async def test_scrape_failed_flag_propagates():
    wednesday = date(2026, 4, 8)  # weekday, not a holiday
    mock_now = MagicMock()
    mock_now.date.return_value = wednesday
    with patch("src.holidays.datetime") as mock_dt, \
         patch("src.holidays.fetch_argentina_holidays", new_callable=AsyncMock) as mock_fetch:
        mock_dt.now.return_value = mock_now
        mock_fetch.return_value = (set(), True)  # scrape failed but no holiday
        enforce, scrape_failed = await should_enforce_tonight()
    assert enforce is True
    assert scrape_failed is True


# ── next_enforcement_datetime ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_next_enforcement_is_tonight_before_1am():
    """If it's before 1 AM on a valid weekday, next kick is tonight."""
    # Wednesday 2026-04-08 at 22:00 ART — next slot is Thu 09 at 01:00
    # (Wed night → Thu morning, so we check Thursday)
    from src.config import ART
    now = datetime(2026, 4, 8, 22, 0, 0, tzinfo=ART)
    with patch("src.holidays.datetime") as mock_dt, \
         patch("src.holidays.fetch_argentina_holidays", new_callable=AsyncMock) as mock_fetch:
        mock_dt.now.return_value = now
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        mock_fetch.return_value = (set(), False)
        result = await next_enforcement_datetime()
    assert result.day == 9
    assert result.month == 4
    assert result.hour == 1


@pytest.mark.asyncio
async def test_next_enforcement_skips_weekend():
    """A Friday night should skip Saturday and Sunday, landing on Monday."""
    from src.config import ART
    # Friday 2026-04-10 at 22:00 — next valid slot is Monday 13 at 01:00
    now = datetime(2026, 4, 10, 22, 0, 0, tzinfo=ART)
    with patch("src.holidays.datetime") as mock_dt, \
         patch("src.holidays.fetch_argentina_holidays", new_callable=AsyncMock) as mock_fetch:
        mock_dt.now.return_value = now
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        mock_fetch.return_value = (set(), False)
        result = await next_enforcement_datetime()
    assert result.weekday() == 0  # Monday
    assert result.day == 13


@pytest.mark.asyncio
async def test_next_enforcement_skips_holiday():
    """Should skip over a public holiday and return the next valid day."""
    from src.config import ART
    # Monday 2026-05-25 (Revolución de Mayo) at 22:00 — should skip to Tuesday
    now = datetime(2026, 5, 25, 22, 0, 0, tzinfo=ART)
    holidays = {(5, 26)}  # pretend Tue is also a holiday, so we skip to Wed
    with patch("src.holidays.datetime") as mock_dt, \
         patch("src.holidays.fetch_argentina_holidays", new_callable=AsyncMock) as mock_fetch:
        mock_dt.now.return_value = now
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        mock_fetch.return_value = (holidays, False)
        result = await next_enforcement_datetime()
    assert result.day == 27  # Wednesday
    assert result.month == 5
