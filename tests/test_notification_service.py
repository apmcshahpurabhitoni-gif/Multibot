from telegram import TelegramMessage
import notification_service


class _AuditFailDatabase:
    def __init__(self):
        self.calls = 0

    def record_delivery(self, *args, **kwargs):
        self.calls += 1
        raise RuntimeError("audit unavailable")


def test_telegram_send_survives_delivery_audit_failure(monkeypatch):
    db = _AuditFailDatabase()
    service = notification_service.NotificationService(db)
    sent = []

    monkeypatch.setattr(
        notification_service,
        "send_message",
        lambda message, config: sent.append(message.text),
    )
    monkeypatch.setattr(
        service,
        "_config",
        lambda: object(),
    )

    result = service.deliver(
        signal_id="sig-1",
        message=TelegramMessage("MSG-TEST-V1", "hello"),
    )

    assert result is True
    assert sent == ["hello"]
    assert db.calls >= 1
