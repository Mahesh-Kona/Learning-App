Flask Learning Backend
======================

Quick start (Docker)
---------------------

1. Copy `.env.example` to `.env` and adjust values if needed.
2. Start services with Docker Compose (this will start MySQL and Redis):

```powershell
docker-compose up --build
```

3. In a new terminal, after the DB is ready, run migrations:

```powershell
$env:FLASK_APP = 'wsgi.py'; flask db migrate -m "create schema"; flask db upgrade
```

4. Test register/login with curl:

Register:
```powershell
curl -X POST http://localhost:5000/api/v1/auth/register -H "Content-Type: application/json" -d '{"email":"test@example.com","password":"secret"}'
```

Login:
```powershell
curl -X POST http://localhost:5000/api/v1/auth/login -H "Content-Type: application/json" -d '{"email":"test@example.com","password":"secret"}'
```

Email (credentials / notifications)
----------------------------------

When creating a student from the admin UI, if **Send email notification** is checked, the backend will attempt to send a credentials email.

- Copy `.env.example` to `.env` and set your email settings.
- Supported env vars: either `SMTP_*` or `MAIL_*` (Flask-Mail style). For example: `MAIL_SERVER`, `MAIL_PORT`, `MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_USE_SSL`, `MAIL_USE_TLS`.
- For port `465`, use `MAIL_USE_SSL=True` and `MAIL_USE_TLS=False`.
- Optionally set `APP_PUBLIC_LOGIN_URL` to your frontend login URL (so the email contains the correct link).

What this repo provides (implemented so far)
-------------------------------------------
- Environment loading via `.env` (python-dotenv)
- SQLAlchemy configured to use `DATABASE_URL` with utf8mb4 charset
- Models: `User`, `Course`, `Lesson`, `Topic`, `Asset`, `Progress` (SQLAlchemy)
- Auth endpoints: `POST /api/v1/auth/register` and `POST /api/v1/auth/login` returning JWT access tokens
- Role decorator `@require_roles(...)` in `app/decorators.py`
- Global JSON error handler returning `{ success: false, error, code }`
- CORS enabled and configurable via `CORS_ORIGINS`
- Caching and rate-limiting extensions wired up (Flask-Caching, Flask-Limiter)
- API read endpoints: courses, lessons, content (with caching)
- Uploads endpoint for multipart uploads (saves to `UPLOAD_PATH` and creates `Asset` records)

Next steps you should run locally
---------------------------------
- Ensure Docker Compose completes startup (MySQL container finishes initialization).
- Run the migration commands shown above to populate the database schema.
- After migrations, test the endpoints with curl or Postman.

Docker & local CI
-----------------
Install Docker Desktop (Windows):

1. Download and install from: https://docs.docker.com/desktop/install/windows-install/
2. Enable WSL2 if prompted and follow Docker Desktop prompts.
3. After installation, open PowerShell and verify:

```powershell
docker --version
docker compose version
```

If both commands print versions, run the local CI helper script from the repo root in PowerShell:

```powershell
.\scripts\run_ci_locally.ps1
```

If you prefer not to use Docker, you can run basic local checks without containers:

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install pytest flake8
flake8
pytest -q
```

Migration squash helper
-----------------------
I included a helper script `scripts\squash_migrations.ps1` that drafts a safe process for squashing Alembic migrations. It will archive existing `migrations/versions` files and print the commands you should run to generate a single baseline migration against a fresh/test DB.

Important: DO NOT run the squash steps directly on production. Backup your DB and verify on a staging copy.

MySQL tuning notes (recommended in production)
---------------------------------------------
- Configure `innodb_buffer_pool_size` to a large fraction of available RAM.
- Adjust `max_connections` according to expected concurrency.
- Use connection pooling settings in `.env` (POOL_SIZE, MAX_OVERFLOW, POOL_RECYCLE) to avoid stale connections.

Backlog (next sprint)
---------------------
- Write endpoints for creating/updating lessons with jsonschema validation and content_version bump.
- Add unit tests for auth and read endpoints.
- Export Postman collection and API docs.
- Integrate S3 uploads option and signed URLs.
- Add analytics and badges engine.

If you want, I can now:
- run the migration commands in your terminal (I need permission to execute them), or
- add unit tests for the auth endpoints and run them locally.

Additional documentation
------------------------
- `docs/API.md` — API summary and endpoints.
- `docs/DOCKER_FRONTEND.md` — docker-compose and frontend integration notes.
- `docs/POSTMAN.md` — import instructions for the included Postman collection (`postman_collection.json`).
- `docs/RUN_THROUGH.md` — a quick run-through for frontend developers.

Redis & CI notes

	REDIS_URL=redis://redis:6379/0
	CACHE_TYPE=RedisCache
	CACHE_REDIS_URL=redis://redis:6379/1
	RATELIMIT_STORAGE_URL=redis://redis:6379/2


Security & linting
------------------
- Basic security response headers are enabled (X-Frame-Options, X-Content-Type-Options, X-XSS-Protection, Referrer-Policy, Content-Security-Policy). Adjust `CONTENT_SECURITY_POLICY` in `.env` for production needs.
- A flake8 configuration file `.flake8` is included. CI now runs `flake8` before tests. Add any linter rules you need.

Operational notes (expanded)
----------------------------

- MySQL tuning: for production, increase `innodb_buffer_pool_size` (e.g. 50-75% of RAM), tune `max_connections`, and set `innodb_log_file_size` appropriately. Example MySQL config snippet:

```
innodb_buffer_pool_size = 1G
max_connections = 200
innodb_flush_log_at_trx_commit = 2
```

-- Connection pooling: SQLAlchemy engine options are available via `POOL_SIZE`, `MAX_OVERFLOW`, and `POOL_RECYCLE` environment variables. `pool_recycle` helps avoid stale connections in long-running workers.

Note about pool recycling and environment variables:

The app exposes a few environment variables you can tune for production database reliability:

- `POOL_SIZE` (default 10) — number of connections in the pool.
- `MAX_OVERFLOW` (default 20) — additional connections beyond the pool when needed.
- `POOL_RECYCLE` (seconds) — recycle connections older than this to avoid "MySQL server has gone away" issues; set to a value smaller than your DB's wait_timeout (e.g. 1800).

Set these in your `.env` or container environment. Example:

```
POOL_SIZE=20
MAX_OVERFLOW=30
POOL_RECYCLE=1800
```

Rate limiting:

Login and upload endpoints are rate-limited by default (configured via Flask-Limiter). To change or disable limits, set the `RATELIMIT_STORAGE_URL` (for Redis) or configure limits per-route in the code. The defaults help prevent credential stuffing and abusive uploads in demo environments.

- Migrations: If deploying to production from scratch it's often helpful to squash historic Alembic migrations into a single baseline migration (backup first). This repo currently contains historical migration files; consider regenerating a clean single migration for easier deployments.

- Redis verification: To ensure the app uses Redis for caching and rate-limiting at runtime, set `CACHE_TYPE=RedisCache`, `CACHE_REDIS_URL` and `RATELIMIT_STORAGE_URL` in the environment. The app will pick these values at startup.


