"""
Tests for bot command logic in bot.py
"""
from unittest.mock import MagicMock

from bot import is_nico


def _make_message(author_name: str, mentions: list | None = None) -> MagicMock:
    msg = MagicMock()
    msg.author.bot = False
    msg.author.name = author_name
    msg.mentions = mentions or []
    return msg


def _make_member(name: str) -> MagicMock:
    m = MagicMock()
    m.name = name
    return m


def test_is_nico_author_exact():
    assert is_nico(_make_message("nico_1607")) is True


def test_is_nico_author_case_insensitive():
    assert is_nico(_make_message("Nico_1607")) is True
    assert is_nico(_make_message("NICO_1607")) is True


def test_is_nico_author_other_user():
    assert is_nico(_make_message("nacho")) is False


def test_is_nico_mentioned():
    nico = _make_member("nico_1607")
    assert is_nico(_make_message("nacho", mentions=[nico])) is True


def test_is_nico_mentioned_case_insensitive():
    nico = _make_member("Nico_1607")
    assert is_nico(_make_message("nacho", mentions=[nico])) is True


def test_is_nico_other_user_mentioned():
    other = _make_member("mel8402")
    assert is_nico(_make_message("nacho", mentions=[other])) is False


def test_is_nico_bot_author_ignored():
    msg = _make_message("nico_1607")
    msg.author.bot = True
    # bot messages are filtered before is_nico is called, but the helper
    # itself doesn't filter bots — that's the caller's responsibility
    assert is_nico(msg) is True
