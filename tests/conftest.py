"""Общие заготовки для тестов: приложение с временной базой и «фальшивый» Telegram."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import create_app  # noqa: E402
from app import db as dbmod  # noqa: E402

ADMIN_PASSWORD = "test-password"
INTERNAL_TOKEN = "test-internal-token"


class FakeResponse:
    def __init__(self, payload: dict, status: int = 200) -> None:
        self._payload = payload
        self.status_code = status

    def json(self) -> dict:
        return self._payload


class FakeTelegram:
    """Подменяет requests в TelegramNotifier: запоминает запросы и отвечает как Bot API."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.next_message_id = 100
        self.fail_with: str | None = None

    def post(self, url: str, json: dict, timeout: float) -> FakeResponse:
        method = url.rsplit("/", 1)[-1]
        self.calls.append((method, json))
        if self.fail_with:
            return FakeResponse({"ok": False, "description": self.fail_with}, 400)
        self.next_message_id += 1
        return FakeResponse({"ok": True, "result": {"message_id": self.next_message_id}})

    def methods(self) -> list[str]:
        return [m for m, _ in self.calls]


@pytest.fixture
def telegram() -> FakeTelegram:
    return FakeTelegram()


@pytest.fixture
def app(tmp_path, telegram):
    application = create_app(
        {
            "TESTING": True,
            "DATABASE_PATH": str(tmp_path / "test.db"),
            "SECRET_KEY": "test-secret",
            "ADMIN_PASSWORD": ADMIN_PASSWORD,
            "INTERNAL_API_TOKEN": INTERNAL_TOKEN,
            "TELEGRAM_BOT_TOKEN": "123:TEST",
            "TELEGRAM_CHAT_ID": "-1001",
            "TELEGRAM_ASYNC": False,  # в тестах отправляем сразу, без фонового потока
            "LEAD_MIN_SECONDS": 3,
            "SITE_URL": "https://smeta.example.ru",
        }
    )
    application.extensions["notifier"].http = telegram
    return application


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def db(app):
    conn = dbmod.connect(app.config["DATABASE_PATH"])
    yield conn
    conn.close()


@pytest.fixture
def admin(client):
    """Клиент, уже вошедший в CRM. csrf — токен для форм."""
    client.get("/admin/login")
    with client.session_transaction() as sess:
        token = sess["csrf"]
    response = client.post("/admin/login", data={"password": ADMIN_PASSWORD, "csrf_token": token})
    assert response.status_code == 302
    with client.session_transaction() as sess:
        client.csrf = sess["csrf"]
    return client


def lead_payload(**overrides) -> dict:
    """Правильная заявка, как её отправляет сайт."""
    data = {
        "name": "Анна",
        "phone": "+7 (999) 123-45-67",
        "email": "",
        "telegram": "",
        "channel": "phone",
        "call_time": "asap",
        "message": "Дата 20 декабря",
        "consent": True,
        "attach_estimate": True,
        "website": "",
        "elapsed_ms": 15000,
        "estimate": {
            "format": "corporate",
            "guests": 80,
            "hours": 4,
            "level": "standard",
            "addons": ["host", "show", "av", "catering", "gifts"],
        },
    }
    data.update(overrides)
    return data
