# INSTRUCTIONS

Minimal guide to run and exercise the User Registration API.

Only prerequisite: **Docker** with Docker Compose v2 (`docker compose`).

---

## 1. Run the application

From the project root:

```bash
docker compose up --build
```

This starts four containers:

| Service     | Purpose                                           | Port (host) |
| ----------- | ------------------------------------------------- | ----------- |
| `api`       | FastAPI app (Swagger UI + endpoints)              | `8000`      |
| `db`        | PostgreSQL 16 (users table)                       | `5432`      |
| `redis`     | Redis 7 (verification codes + rate limiter state) | `6379`      |
| `email`     | Mailpit — mock third-party email HTTP API + inbox | `8025`      |
| `scheduler` | Ofelia — runs the cleanup cron inside the api     | —           |

Wait until the `api` container becomes healthy (it runs a `/health` check every 5s).

Stop everything with:

```bash
docker compose down -v
```

(`-v` also wipes the Postgres volume so you restart from a clean DB.)

---

## 2. Standard user flow (happy path)

All API calls below can be done directly from the Swagger UI. The rate limiter is keyed by client IP + path, so running these flows locally on your machine counts as a single client.

### 2.1 Open Swagger UI

Browse to [http://localhost:8000/docs](http://localhost:8000/docs).

You will see three endpoints under `/api`:

- `POST /api/users` — public, create a user
- `POST /api/users/verify` — requires Basic Auth
- `POST /api/users/code` — requires Basic Auth (resend code)

### 2.2 Create a user

On `POST /api/users`, click *Try it out* and send:

```json
{
  "email": "alice@example.com",
  "password": "supersecret"
}
```

Expected response: `200 OK` with empty body. A 4-digit verification code is generated, stored in Redis with a 60-second TTL, and sent through the mock email provider.

> Rate limit: `1/hour` per client IP on this endpoint. Use a different email for retries within the hour, or `docker compose restart redis` to reset the limiter state.

### 2.3 Open the mailbox and read the code

Browse to Mailpit: [http://localhost:8025](http://localhost:8025).

You will see the incoming email "User Registration Email Verification" containing something like:

```
Your verification code is 7421.
```

### 2.4 Verify the account

On `POST /api/users/verify`, click the lock icon and authenticate with Basic Auth using the credentials you just registered (`alice@example.com` / `supersecret`).

Submit the form with the 4-digit `code` from the email.

Expected response: `200 OK`. The `users.verified` column is now `TRUE` in Postgres.

Calling `verify` again returns `400 User already verified`.

---

## 3. Flow with code resend (expired code)

Codes expire after **60 seconds** (`VERIFICATION_CODE_TTL_SECONDS`). If the user is too slow:

1. Register a new user via `POST /api/users` and wait > 60s.
2. Try `POST /api/users/verify` with the original code → `400 Invalid verification code` (the Redis key has expired).
3. Call `POST /api/users/code` with Basic Auth on the same account. A fresh code is issued, the Redis TTL is reset to 60s, and a new email is delivered to Mailpit.
4. Submit the new code to `POST /api/users/verify` → `200 OK`.

> Rate limit: `1/minute` on both `/users/verify` and `/users/code`, each per client IP. After a failed verification you may need to wait ~60s before calling resend again from the same IP.

---

## 4. Brute-force attempt (rate limiting)

The verify endpoint accepts a 4-digit code, so a naive attacker would have a 1-in-10 000 chance per try. Two layers block this:

- **Short code TTL**: the code only lives 60 seconds in Redis; after that any attempt returns `400 Invalid verification code` regardless of input.
- **Per-IP rate limit** on `POST /api/users/verify`: `1/minute` using a moving-window limiter backed by Redis.

To observe it:

1. Register a user and grab the code from Mailpit.
2. From Swagger (or curl) send a wrong code to `POST /api/users/verify`:
   ```bash
   curl -u alice@example.com:supersecret \
        -X POST http://localhost:8000/api/users/verify \
        -d code=0000
   ```
   → `400 Invalid verification code`.
3. Immediately retry with another guess (`0001`, `0002`, …):
   → `429 Rate limit exceeded`.
4. At best an attacker gets 1 guess per minute per IP = **60 attempts per hour**, well below the 10 000 combinations, and they only have 60 seconds before the code rotates anyway.

The same `1/minute` limit applies to `/api/users/code` to prevent email-bombing, and `1/hour` to `/api/users` to prevent registration flooding.

---

## 5. Background cron job (cleanup of unverified users)

Unverified accounts should not accumulate in the DB. A scheduled job deletes them.

- **What it does**: runs `python -m src.jobs.cleanup_unverified`, which executes
  ```sql
  DELETE FROM users
  WHERE verified = FALSE
    AND created_at < NOW() - INTERVAL '1 day';
  ```
- **Where it runs**: inside the `api` container (reusing its Python env and DB credentials), triggered by the `scheduler` container.
- **How it is scheduled**: via [Ofelia](https://github.com/mcuadros/ofelia) reading Docker labels on the `api` service (see `docker-compose.yml`):
  ```yaml
  ofelia.job-exec.cleanup-unverified.schedule: "0 0 2 * * *"
  ofelia.job-exec.cleanup-unverified.command:  "uv run python -m src.jobs.cleanup_unverified"
  ```
  Cron expression `0 0 2 * * *` = every day at **02:00** (server time).

### Trigger it manually (for testing)

```bash
docker compose exec api uv run python -m src.jobs.cleanup_unverified
```

You should see a log line like:

```
Starting unverified user cleanup
Unverified user cleanup finished (DELETE 3)
```

### Watch the scheduler

```bash
docker compose logs -f scheduler
```

Ofelia logs each execution (start, finish, exit code) so you can confirm the nightly run happened.
