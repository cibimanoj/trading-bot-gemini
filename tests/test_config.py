import config


def test_telegram_chat_ids_parses_comma_separated(monkeypatch):
    monkeypatch.setattr(config.settings, "TELEGRAM_CHAT_ID", " 123 , 456 ")
    assert config.telegram_chat_ids() == [123, 456]


def test_telegram_chat_ids_empty(monkeypatch):
    monkeypatch.setattr(config.settings, "TELEGRAM_CHAT_ID", "")
    assert config.telegram_chat_ids() == []


def test_telegram_chat_ids_skips_invalid_tokens(monkeypatch):
    monkeypatch.setattr(config.settings, "TELEGRAM_CHAT_ID", "123, not_a_number, 456")
    assert config.telegram_chat_ids() == [123, 456]
