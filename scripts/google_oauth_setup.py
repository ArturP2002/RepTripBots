"""Одноразовый OAuth Google Calendar — сохраняет token в secrets/."""

from __future__ import annotations

import sys
from pathlib import Path

# корень проекта в PYTHONPATH
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import get_settings  # noqa: E402


def main() -> None:
    """Запускает браузерный OAuth и пишет google_token.json."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    settings = get_settings()
    creds_path = Path(settings.google_credentials_file)
    token_path = Path(settings.google_token_file)
    scopes = ["https://www.googleapis.com/auth/calendar"]

    if not creds_path.exists():
        print(
            f"Не найден {creds_path}. Скачайте OAuth Desktop credentials "
            "из Google Cloud Console и положите файл сюда."
        )
        raise SystemExit(1)

    flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), scopes)
    creds = flow.run_local_server(port=0)
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json(), encoding="utf-8")
    print(f"Готово. Token сохранён в {token_path}")
    print(f"Укажите GOOGLE_CALENDAR_ID в .env (сейчас: {settings.google_calendar_id})")


if __name__ == "__main__":
    main()
