"""HTTP API: WhatsApp webhook и страница выбора канала /go/{token}."""

from __future__ import annotations

import logging
from urllib.parse import quote

from fastapi import APIRouter, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, PlainTextResponse

from app.config import get_settings
from app.db.base import get_session_factory
from app.domain.trips import TripService
from app.i18n import t

logger = logging.getLogger(__name__)


def create_api_app(whatsapp_handler=None) -> FastAPI:
    """
    Создаёт FastAPI-приложение.

    :param whatsapp_handler: async callable(payload dict) для inbound WA
    """
    app = FastAPI(title="RepTrip API", version="0.1.0")
    router = APIRouter()
    settings = get_settings()

    @router.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @router.get("/webhooks/whatsapp")
    async def wa_verify(
        hub_mode: str = Query(alias="hub.mode", default=""),
        hub_verify_token: str = Query(alias="hub.verify_token", default=""),
        hub_challenge: str = Query(alias="hub.challenge", default=""),
    ):
        """Верификация webhook Meta."""
        if (
            hub_mode == "subscribe"
            and hub_verify_token == settings.whatsapp_verify_token
        ):
            logger.info("WhatsApp webhook верифицирован")
            return PlainTextResponse(hub_challenge)
        logger.warning("Неудачная верификация WhatsApp webhook")
        raise HTTPException(status_code=403, detail="Forbidden")

    @router.post("/webhooks/whatsapp")
    async def wa_inbound(request: Request) -> dict[str, str]:
        if not settings.whatsapp_enabled:
            logger.warning("Получен WA webhook, но WHATSAPP_ENABLED=false")
            return {"status": "disabled"}
        data = await request.json()
        logger.debug("WhatsApp webhook payload keys=%s", list(data.keys()))
        if whatsapp_handler:
            await whatsapp_handler(data)
        return {"status": "ok"}

    @router.get("/go/{token}", response_class=HTMLResponse)
    async def go_page(token: str) -> HTMLResponse:
        """Страница Continue in Telegram / WhatsApp."""
        factory = get_session_factory()
        async with factory() as session:
            trip = await TripService(session, settings).get_by_token(token)
        if trip is None:
            raise HTTPException(status_code=404, detail="Trip not found")

        tg_user = settings.telegram_bot_username.strip().lstrip("@")
        tg_url = (
            f"https://t.me/{tg_user}?start={token}"
            if tg_user
            else "#"
        )
        # WhatsApp: пользователь пишет JOIN token на номер бизнеса —
        # в пилоте ведём на wa.me с предзаполненным текстом, если задан номер в PUBLIC
        wa_text = quote(f"JOIN {token}")
        # Номер для wa.me лучше задавать отдельно; используем deep link через тот же /go hint
        wa_url = f"https://wa.me/?text={wa_text}"

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{t("en", "go_page_title")}</title>
  <style>
    body {{ font-family: system-ui, sans-serif; max-width: 420px; margin: 3rem auto; padding: 0 1rem; }}
    a.btn {{ display:block; margin: .75rem 0; padding: 1rem; text-align:center;
             background:#111; color:#fff; text-decoration:none; border-radius:8px; }}
    a.btn.wa {{ background:#128C7E; }}
    p.meta {{ color:#555; }}
  </style>
</head>
<body>
  <h1>RepTrip</h1>
  <p class="meta">{trip.representative.name} · {trip.city}</p>
  <p>{t("en", "go_page_body")}</p>
  <a class="btn" href="{tg_url}">{t("en", "btn_continue_tg")}</a>
  <a class="btn wa" href="{wa_url}">{t("en", "btn_continue_wa")}</a>
</body>
</html>"""
        return HTMLResponse(html)

    app.include_router(router)
    return app
