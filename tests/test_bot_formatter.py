from bot.formatter import BotFormatter


def test_format_signal_missing_fields_does_not_crash():
    # Minimal / malformed payload should still render a message.
    msg = BotFormatter.format_signal({})
    assert isinstance(msg, str)
    assert "TRADE" in msg


def test_format_signal_legs_missing_is_handled():
    msg = BotFormatter.format_signal({"confidence": 80, "index": "NIFTY", "regime": "RANGE"})
    assert "No legs available" in msg

