-- Схема базы данных. Выполняется командой: flask init-db
-- Время храним в UTC в формате ISO 8601: 2026-10-24T12:30:00+00:00

CREATE TABLE IF NOT EXISTS leads (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL,
    status          TEXT    NOT NULL DEFAULT 'new',   -- new | in_progress | quoted | won | lost
    name            TEXT    NOT NULL,
    phone           TEXT    NOT NULL,                 -- +79991234567
    email           TEXT    NOT NULL DEFAULT '',
    telegram        TEXT    NOT NULL DEFAULT '',      -- @username
    channel         TEXT    NOT NULL DEFAULT 'phone', -- phone | telegram | email
    call_time       TEXT    NOT NULL DEFAULT 'asap',
    message         TEXT    NOT NULL DEFAULT '',
    -- Снимок сметы на момент заявки: цены потом могут измениться
    has_estimate    INTEGER NOT NULL DEFAULT 0,
    format_id       TEXT,
    level_id        TEXT,
    guests          INTEGER,
    hours           INTEGER,
    estimate_total  INTEGER,
    estimate_low    INTEGER,
    estimate_high   INTEGER,
    estimate_json   TEXT,
    -- Откуда пришёл клиент (метки из рекламной ссылки)
    utm_source      TEXT    NOT NULL DEFAULT '',
    utm_medium      TEXT    NOT NULL DEFAULT '',
    utm_campaign    TEXT    NOT NULL DEFAULT '',
    source          TEXT    NOT NULL DEFAULT 'site',  -- site | sample (тестовые данные)
    tg_message_id   INTEGER                           -- сообщение в чате менеджеров
);

CREATE INDEX IF NOT EXISTS idx_leads_status  ON leads (status);
CREATE INDEX IF NOT EXISTS idx_leads_created ON leads (created_at);

-- История заявки: создание, смена статуса, заметки менеджеров
CREATE TABLE IF NOT EXISTS lead_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id     INTEGER NOT NULL REFERENCES leads (id) ON DELETE CASCADE,
    created_at  TEXT    NOT NULL,
    kind        TEXT    NOT NULL,                     -- created | status | note
    actor       TEXT    NOT NULL DEFAULT '',          -- кто сделал: «CRM», «Иван (Telegram)»
    old_status  TEXT,
    new_status  TEXT,
    text        TEXT    NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_events_lead ON lead_events (lead_id);

-- Настройки, которые меняются из админки (например, правки цен)
CREATE TABLE IF NOT EXISTS settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,                        -- JSON
    updated_at  TEXT NOT NULL
);
