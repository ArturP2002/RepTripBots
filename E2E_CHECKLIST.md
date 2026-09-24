# E2E чеклист пилота RepTrip

- [ ] `.env` заполнен (TG token, OWNER ids, Google files, Postgres)
- [ ] `python scripts/google_oauth_setup.py` выполнен
- [ ] `docker compose up -d` (или свой Postgres)
- [ ] `python main.py` стартует без ошибок в логах
- [ ] Владелец `/new_trip` создаёт Trip и получает ссылки (RU)
- [ ] Агент по TG deep-link видит карточку (EN), Yes → регистрация → слот
- [ ] Владелец получает заявку, Confirm → event в Google Calendar
- [ ] Агент получает confirmation (EN), может Cancel
- [ ] Второй агент на тот же слот: Confirm блокируется
- [ ] Suggest another time → агент Yes / Choose another time
- [ ] Decline → нейтральное EN-сообщение агенту
- [ ] Повторный вход зарегистрированного агента — без регистрации
- [ ] `/go/{token}` открывает выбор Telegram / WhatsApp
- [ ] При `WHATSAPP_ENABLED=true`: JOIN token → тот же agent flow

Критерии готовности — см. README и reptrip_tz_essence.txt §4.
