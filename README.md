# RepTrip — пилот (Telegram + WhatsApp)

Чат-боты для организации встреч Representative с education agents во время поездок.
Один backend, PostgreSQL, Google Calendar. Владелец подтверждает заявки в Telegram (RU);
агенты общаются на английском в Telegram / WhatsApp.

## Быстрый старт (локально)

### 1. PostgreSQL

```bash
docker compose up -d
```

Если Docker недоступен — поднимите Postgres 16 вручную и поправьте `DATABASE_URL` в `.env`.

### 2. Python

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Заполните в `.env` минимум:

- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_BOT_USERNAME`, `OWNER_TELEGRAM_IDS`
- `TELEGRAM_ENABLED=true`
- `WHATSAPP_ENABLED=false` (пока нет credentials)
- `DATABASE_URL`

### 3. Google Calendar (сразу)

1. Google Cloud Console → проект → включить **Google Calendar API**
2. OAuth consent screen + OAuth Client ID (**Desktop**)
3. Скачать JSON → `secrets/google_credentials.json`
4. Выполнить:

```bash
python scripts/google_oauth_setup.py
```

5. Указать `GOOGLE_CALENDAR_ID` (календарь поездки владельца продукта)

### 4. Таблицы БД

При старте `main.py` вызывает `create_all`. Либо миграции:

```bash
alembic upgrade head
```

### 5. Запуск

```bash
python main.py
```

Переключатели каналов в `.env`:

| TELEGRAM_ENABLED | WHATSAPP_ENABLED | Поведение |
|---|---|---|
| true | true | Оба канала |
| true | false | Только Telegram (+ API `/go`) |
| false | true | Только WhatsApp + API |
| false | false | Ошибка старта |

### 6. Демо Trip

```bash
python scripts/seed_demo.py
```

Владелец также может создать Trip в Telegram: `/new_trip`.

## E2E чеклист

1. Владелец: `/new_trip` → получить ссылки TG и `/go/{token}`
2. Email со ссылкой — вручную
3. Агент открывает TG или WA → видит встречу (EN)
4. Yes → регистрация (или skip для известных) → слот → MeetingRequest
5. Владелец в TG: Подтвердить / Другое время / Отклонить
6. Confirm → free/busy Google → Booking + event → confirmation агенту
7. Второй Confirm на тот же слот — отказ
8. Агент может Cancel → событие удаляется
9. Повторный вход того же агента — без новой регистрации

## WhatsApp

Когда есть Meta Business + Cloud API:

1. Заполнить `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_VERIFY_TOKEN`
2. `WHATSAPP_ENABLED=true`
3. Публичный HTTPS URL (`PUBLIC_BASE_URL`) → webhook `POST/GET /webhooks/whatsapp`
4. Локально: ngrok/cloudflared на `API_PORT`
5. Агент пишет боту `JOIN <token>` или открывает `/go/{token}`

## Часовые пояса

- `DEFAULT_TIMEZONE=Europe/Moscow` — системный дефолт
- `TIMEZONE_KZ=Asia/Almaty`, `TIMEZONE_UZ=Asia/Tashkent` — на Trip по стране

## Структура

См. `app/` — domain, adapters (telegram, whatsapp, calendar), i18n (ru/en), api.
Логи: `logs/reptrip.log` (сообщения на русском).

## VPS

1. Скопировать код, `.env`, `secrets/`
2. Postgres + `alembic upgrade head` (или авто `create_all` при старте)
3. systemd/docker: `python main.py`
4. Nginx HTTPS → `API_PORT` (webhook WA + `/go`)
5. Оба флага каналов `true`, Google token уже получен локально

## Тесты

```bash
pytest -q
```
