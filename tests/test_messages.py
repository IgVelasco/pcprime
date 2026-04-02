"""
Tests for src/messages.py

Sanity checks that the message lists are valid and non-empty.
"""
from src.messages import GUARD_MESSAGES, SWEEP_MESSAGES


def test_sweep_messages_not_empty():
    assert len(SWEEP_MESSAGES) > 0


def test_guard_messages_not_empty():
    assert len(GUARD_MESSAGES) > 0


def test_all_sweep_messages_are_strings():
    assert all(isinstance(m, str) for m in SWEEP_MESSAGES)


def test_all_guard_messages_are_strings():
    assert all(isinstance(m, str) for m in GUARD_MESSAGES)


def test_no_empty_messages():
    for msg in SWEEP_MESSAGES + GUARD_MESSAGES:
        assert msg.strip(), f"Empty or whitespace-only message found: {msg!r}"
