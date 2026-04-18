# register-me

A minimal user registration service built with **FastAPI**, backed by **PostgreSQL** for durable user state and **Redis** for short-lived verification codes and rate-limiting counters. Emails are delivered through a pluggable HTTP email provider (mocked locally by **Mailpit**). A nightly cron, driven by **Ofelia**, purges unverified accounts.

---

## Architecture

![Architecture diagram](architecture.svg)

The source of the diagram lives in [`architecture.mmd`](architecture.mmd) (Mermaid).

High-level flow:

- The **api** container exposes `POST /api/users`, `POST /api/users/verify`, `POST /api/users/code` and `GET /health`.
- User rows (`id`, `email`, `password_hash`, `verified`, `created_at`) live in **PostgreSQL 16**.
- 4-digit verification codes live in **Redis 7** under `verification_code:{email}` with a 60-second TTL. Redis also stores the moving-window rate-limit counters.
- Verification emails are sent via an HTTP POST to `/api/v1/send` on the email provider. In the dev stack that provider is **Mailpit** (SMTP-compatible mock with a web UI on port 8025).
- The **scheduler** container (`mcuadros/ofelia`) reads Docker labels on the `api` service and runs `src.jobs.cleanup_unverified` inside it every day at 02:00.

---

## Tech stack

| Concern               | Choice                                                   |
| --------------------- | -------------------------------------------------------- |
| Language / runtime    | Python 3.13                                              |
| Web framework         | FastAPI + Uvicorn                                        |
| Dependency manager    | [`uv`](https://docs.astral.sh/uv/) (lockfile `uv.lock`)  |
| Database driver       | `asyncpg` (pooled, one transaction per request)          |
| Cache / TTL store     | `redis.asyncio`                                          |
| Password hashing      | `argon2-cffi` (offloaded to a thread via `anyio`)        |
| Auth on private routes| HTTP Basic (credentials checked against `password_hash`) |
| Rate limiter          | `limits` with `MovingWindowRateLimiter` + Redis storage  |
| HTTP client           | `httpx.AsyncClient` (reused from `app.state`)            |
| Validation / settings | `pydantic` + `pydantic-settings`                         |
| Scheduler             | Ofelia (Docker-label driven)                             |
| Tests                 | `pytest`, `pytest-asyncio`, `testcontainers`             |

---

## Getting started

Only prerequisite: **Docker** with Docker Compose v2 (`docker compose`).

```bash
docker compose up --build
```

This starts five containers (`api`, `db`, `redis`, `email`, `scheduler`). Once the `api` container is healthy, Swagger UI is available at [http://localhost:8000/docs](http://localhost:8000/docs) and the Mailpit inbox at [http://localhost:8025](http://localhost:8025).

For the full walkthrough — happy path, code resend, brute-force / rate-limit demo, and manually triggering the nightly cleanup cron — see **[INSTRUCTIONS.md](INSTRUCTIONS.md)**.

---

## Technical details

### Project layout

```
src/
├── api.py              # Public + private FastAPI routers
├── main.py             # App factory + lifespan (pool, redis, limiter, email provider)
├── config.py           # Pydantic Settings (env-driven)
├── constants.py        # Redis key templates + email templates
├── helpers.py          # issue_verification_code, require_unverified_user
├── logging.py          # configure_logging / get_logger
├── models.py           # User, InternalUser, OutboundEmail (pydantic)
├── jobs/
│   └── cleanup_unverified.py
└── services/
    ├── auth.py         # HTTP Basic + Argon2 verification, get_user
    ├── cache.py        # Redis pool init + FastAPI dependency
    ├── db/
    │   ├── __init__.py # asyncpg pool, get_db dependency (tx per request)
    │   └── schema.py   # Raw DDL for `users`
    ├── email.py        # EmailProvider ABC + MailpitEmailProvider impl
    └── security.py     # limit_rate(rate) dependency factory
tests/                  # pytest + testcontainers integration suite
```

### Request lifecycle

1. `lifespan` (`src/main.py`) wires singletons onto `app.state`: an `asyncpg` pool, a `redis.asyncio` client, an `EmailProvider` (currently `MailpitEmailProvider`, wrapping an `httpx.AsyncClient`), and a `MovingWindowRateLimiter` backed by the same Redis.
2. On startup the app also runs `create_tables()` to create the `users` table if it does not exist — this is intentionally *not* a migration system, see limitations below.
3. Every request that needs the DB opens a transaction via `get_db` so that any raised exception automatically rolls back writes.
4. Passwords are hashed with Argon2. Hashing is CPU-bound, so it is dispatched to a thread with `anyio.to_thread.run_sync` to avoid blocking the event loop.
5. Private routes depend on `get_user`, which parses HTTP Basic credentials, looks up the user, and verifies the hash. `require_unverified_user` adds the "must not be verified yet" constraint.

### Configuration

All settings come from environment variables and are validated by `pydantic-settings` (`src/config.py`):

| Variable                         | Default                       | Description                                  |
| -------------------------------- | ----------------------------- | -------------------------------------------- |
| `DB_URL`                         | *(required)*                  | PostgreSQL DSN, e.g. `postgresql://...`      |
| `REDIS_URL`                      | *(required)*                  | Redis DSN, e.g. `redis://redis:6379/0`       |
| `EMAIL_API_URL`                  | *(required)*                  | Base URL of the email provider               |
| `EMAIL_FROM`                     | `no-reply@example.com`        | Sender address                               |
| `VERIFICATION_CODE_TTL_SECONDS`  | `60`                          | Redis TTL of verification codes              |
| `API_LOG_LEVEL`                  | `INFO`                        | Logging level                                |
| `API_LOG_FORMAT`                 | standard format               | `logging` format string                      |

### Data model

```sql
CREATE TABLE users (
    id            INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    verified      BOOLEAN NOT NULL DEFAULT FALSE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### Redis keys

| Key pattern                     | Value     | TTL  | Purpose                      |
| ------------------------------- | --------- | ---- | ---------------------------- |
| `verification_code:{email}`     | 4-digit   | 60 s | Email verification challenge |
| `LIMITS:*` (managed by `limits`)| counters  | var. | Moving-window rate limiter   |

### Email provider abstraction

The app depends on the abstract `EmailProvider` interface (`src/services/email.py`), not on a specific vendor:

```python
class EmailProvider(ABC):
    @abstractmethod
    async def send(self, to_email: str, subject: str, body: str) -> None: ...
    async def aclose(self) -> None: ...
```

The default implementation, `MailpitEmailProvider`, POSTs a Mailjet-style JSON payload to `/api/v1/send` and is compatible with Mailpit (local dev) as well as any Mailjet-shaped transactional relay. To integrate a different backend (SES, SendGrid, SMTP, a testing double, ...), subclass `EmailProvider`, implement `send` / `aclose`, and return it from `init_email_provider()`. Nothing else in the codebase needs to change — `src/helpers.py`, `src/api.py`, and the tests only see the interface.

### Rate limits

| Endpoint                 | Limit      | Key                    |
| ------------------------ | ---------- | ---------------------- |
| `POST /api/users`        | `1/hour`   | client IP + path       |
| `POST /api/users/verify` | `1/minute` | client IP + path       |
| `POST /api/users/code`   | `1/minute` | client IP + path       |

### Local development without Docker

```bash
uv sync
export DB_URL=postgresql://user:password@localhost:5432/registry
export REDIS_URL=redis://localhost:6379/0
export EMAIL_API_URL=http://localhost:8025
uv run uvicorn src.main:app --reload
```

### Tests

```bash
uv run pytest
```

The test suite spins up ephemeral PostgreSQL and Redis containers via `testcontainers`, so Docker must be running. CI runs the same command (see `.github/workflows/test_api.yml`).

---

## Limitations & known trade-offs

This project is intentionally scoped as a take-home / reference implementation. The following shortcuts were taken deliberately and would need to be addressed before any production deployment:

- **No migration tooling.** Schema is created on startup with raw `CREATE TABLE IF NOT EXISTS` in `src/services/db/schema.py`. There is no Alembic, no versioning, no rollback, and no way to evolve the schema safely once data exists in production. Any non-trivial change requires manual SQL.
- **Secrets in plaintext.** DB credentials (`user` / `password`) live directly in `docker-compose.yml`. In production they would need to come from a secret manager (Docker/K8s secrets, Vault, SSM, etc.).
- **Rate limiting is per-IP only.** The limiter keys on `request.client.host`, which is the socket peer. Behind a reverse proxy or CDN every user looks like the same IP (or, worse, the wrong one). A real deployment needs `X-Forwarded-For` parsing with a trusted-proxy list, plus ideally per-account or per-email limits to complement per-IP.
- **No HTTPS / TLS termination.** The API speaks plain HTTP on `:8000`. HTTP Basic credentials over plain HTTP are unsafe; production traffic must go through a TLS-terminating proxy.
- **HTTP Basic on every private call.** Each `verify` / `code` request re-hashes and checks the password. That is simple but expensive (Argon2 is intentionally slow) and exposes the password on every hit. A short-lived verification token — e.g. returned by `POST /api/users` and consumed by `/verify` — would be a better UX and security story.
- **4-digit codes.** 10 000 combinations only. The 60s TTL and `1/minute` rate limit mitigate the risk (see §4) but a 6-digit code would give 100× more entropy for little UX cost.
- **No outbox / retry for email.** If the email provider is temporarily down, `issue_verification_code` deletes the Redis key and returns `502`. The user has to retry manually. A transactional outbox or background retry queue would make delivery reliable.
- **No structured audit log.** Events are plain `logging` lines. There is no audit trail table, no correlation ID, no tracing.
- **Single-writer registration table.** `users` has no sharding, no soft-delete, no GDPR "right to be forgotten" tooling. Cleanup is a hard `DELETE`.
- **Cron runs via Docker socket.** The `scheduler` container mounts `/var/run/docker.sock` to `docker exec` into the api. That is convenient locally but gives the scheduler root-equivalent power on the host; production would use a real scheduler (K8s `CronJob`, systemd timer, cloud scheduler) running the job as a separate one-shot container.
- **Healthcheck is shallow.** `/health` returns `{"status": "ok"}` unconditionally; it does not probe the DB, Redis, or the email provider. Readiness vs. liveness is not distinguished.
- **No CSRF, no CORS policy, no security headers.** The API assumes non-browser callers. Any browser-facing deployment needs at least `CORS`, `Strict-Transport-Security`, `X-Content-Type-Options`, and friends.
- **Argon2 parameters are library defaults.** They are fine for a demo but should be tuned against real hardware and reviewed periodically.
- **Verification lookup is not constant-time.** `redis.get(...) != code` leaks timing in principle. In practice the per-IP rate limit makes a timing attack impractical, but `hmac.compare_digest` would be trivial to add.

PRs that address any of the above are welcome.
