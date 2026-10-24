"""Подключение к SQLite.

Используем встроенный модуль sqlite3 и обычный SQL: для сайта с заявками
этого хватает с запасом, а каждый запрос видно глазами (см. app/repo.py).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from flask import Flask, current_app, g

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def connect(path: str) -> sqlite3.Connection:
    """Открывает базу. Папку для файла создаёт сама."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)  # ждём до 10 секунд, если база занята
    conn.row_factory = sqlite3.Row  # строки как словари: row["name"]
    conn.execute("PRAGMA foreign_keys = ON")  # включаем связи между таблицами
    conn.execute("PRAGMA journal_mode = WAL")  # чтение не мешает записи (сайт + фоновые задачи)
    return conn


def get_db() -> sqlite3.Connection:
    """Одно подключение на один запрос к сайту (хранится в flask.g)."""
    if "db" not in g:
        g.db = connect(current_app.config["DATABASE_PATH"])
    return g.db


def close_db(_error: BaseException | None = None) -> None:
    """Закрывает подключение в конце запроса."""
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db(path: str) -> None:
    """Создаёт таблицы, если их ещё нет. Безопасно запускать сколько угодно раз."""
    conn = connect(path)
    with conn:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.close()


def init_app(app: Flask) -> None:
    """Подключает базу к приложению и сразу создаёт таблицы."""
    app.teardown_appcontext(close_db)
    init_db(app.config["DATABASE_PATH"])
