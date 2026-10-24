# ACM — TikTok Login Kit (Web) skeleton

Слоистая архитектура, зависимости направлены строго вниз:

```
api (routers, deps, templates)  →  services  →  repositories / integrations  →  models / db  →  core
```

| Слой | Путь | Ответственность |
|---|---|---|
| core | `src/acm/core` | конфиг, исключения, время, security-хелперы |
| db / models | `src/acm/db`, `src/acm/models` | Base, сессия, Unit of Work, ORM-модели |
| repositories | `src/acm/repositories` | доступ к данным (Repository pattern) |
| integrations | `src/acm/integrations/tiktok` | HTTP-клиент TikTok (Gateway/Adapter), без знания про БД |
| services | `src/acm/services` | use-case'ы (AuthService), не знают про HTTP/сессии |
| api | `src/acm/api` | роутеры, DI (`deps.py`), обработчики ошибок, шаблоны |

## Запуск (docker compose)

```bash
cp .env.example .env     # заполни SECRET_KEY, TIKTOK_CLIENT_KEY/SECRET, TIKTOK_REDIRECT_URI
docker compose up --build
```

Поднимется Postgres, применятся миграции (`alembic upgrade head`), стартует приложение на
http://localhost:8000 с автоперезагрузкой (`./src` примонтирован в контейнер).

```bash
docker compose exec app pytest                                   # тесты
docker compose exec app alembic revision --autogenerate -m "x"   # новая миграция
docker compose exec app ruff check .                             # линтер
docker compose down            # остановить; `down -v` — ещё и стереть БД
```

После добавления зависимости в `pyproject.toml` пересобери образ: `docker compose up --build`.

## TikTok

1. developers.tiktok.com → Manage apps → твой app → добавь продукт **Login Kit**, включи **Configure for Web**.
2. Добавь Redirect URI (тот же, что в `TIKTOK_REDIRECT_URI`): `https://<твой-хост>/auth/tiktok/callback`.
   TikTok принимает только HTTPS, поэтому локально нужен туннель (`cloudflared tunnel --url http://localhost:8000` или `ngrok http 8000`).
3. Scopes в `.env` должны быть добавлены в приложение в портале (`user.info.basic` по умолчанию).
4. Если app в Sandbox — добавь свой аккаунт в Target Users.
5. Открой `https://<твой-хост>/` → «Continue with TikTok».

## Флоу

`/auth/tiktok/login` (state в сессию → redirect на TikTok) → `/auth/tiktok/callback` (проверка state,
обмен `code` на токены, `GET /v2/user/info/`, upsert в БД, новая сессия) → `/dashboard`.
Также: refresh токена, revoke + удаление аккаунта, logout.

## Разработка

```bash
uv run pytest
uv run ruff check . && uv run ruff format .
uv run mypy src
uv run alembic revision --autogenerate -m "message"
```

## TODO перед продом

- шифровать токены в БД (сейчас plain text);
- фоновое обновление токенов до истечения (`is_access_token_expired` уже есть в модели);
- CSRF-токены для POST-форм (сейчас защищает SameSite=Lax).
