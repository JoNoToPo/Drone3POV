# api

The Drone3POV REST API (FastAPI). Docs are served at `/doc/` and the OpenAPI spec at `/api/v1/openapi.json`.

## Endpoints (v1)

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| POST | `/api/v1/auth/register` | none | Create a user account (always role `user`) |
| POST | `/api/v1/auth/login` | none | Check password, set JWT in an HttpOnly cookie |
| POST | `/api/v1/auth/logout` | none | Clear the cookie |
| GET | `/api/v1/users/me` | user | Email, role, API calls used, free-call warning |
| POST | `/api/v1/vision/detect` | user | **AI:** find people in an uploaded photo (self-hosted YOLOv10n) |
| POST | `/api/v1/follow-sessions` | user | Start a follow session |
| GET | `/api/v1/follow-sessions/{session_id}` | owner or admin | Session state |
| POST | `/api/v1/follow-sessions/{session_id}/stop` | owner or admin | Stop and land |
| GET | `/api/v1/drone/status` | user | Battery, height, link |
| POST | `/api/v1/drone/emergency-stop` | user | Stop the motors now |
| GET | `/api/v1/admin/users` | admin | All users with total requests (Table B) |
| GET | `/api/v1/admin/stats/endpoints` | admin | Requests per endpoint (Table A) |

Every counted response carries `X-Free-Calls-Used`, `X-Free-Calls-Limit` and `X-Free-Calls-Exceeded`. Auth endpoints, docs and CORS preflights are not counted. Service continues after the 20 free calls.

## Self-hosted AI model

- Model: [onnx-community/yolov10n](https://huggingface.co/onnx-community/yolov10n), COCO object detection, ONNX, 9.4 MB.
- Downloaded by `scripts/download_model.py` into `api/models/yolov10n/onnx/model.onnx` and run with ONNX Runtime on the API server. No third-party AI API is used.
- Bonus demonstration: rename or delete `model.onnx`, and `POST /api/v1/vision/detect` returns 503 at once. Put it back and it works again.
- `api/models/` is git-ignored, so run the download script on every machine and in the host's build step.

## Run locally

From this `api/` folder, with the venv at the repo root:

```bash
py -3.13 -m venv ..\.venv
..\.venv\Scripts\python.exe -m pip install -r requirements.txt
..\.venv\Scripts\python.exe scripts\download_model.py
..\.venv\Scripts\python.exe -m pytest -q
```

Then start the server (PowerShell). Local HTTP needs `COOKIE_SECURE=false`, because browsers won't send a Secure cookie over plain HTTP:

```bash
$env:COOKIE_SECURE="false"; ..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

The demo accounts `john@john.com` / `123` (user) and `admin@admin.com` / `111` (admin) are created on startup, with bcrypt-hashed passwords.

## Environment variables

| Variable | Default | Notes |
| --- | --- | --- |
| `JWT_SECRET` | development value | **Set a long random value in production.** |
| `DATABASE_URL` | SQLite file `api/drone3pov.db` | Use Postgres when hosted; `postgres://` URLs are accepted. |
| `CLIENT_ORIGINS` | `http://localhost:5173` | Comma-separated client origins allowed by CORS. |
| `COOKIE_SECURE` | `true` | `false` only for local HTTP. |
| `COOKIE_SAMESITE` | `none` (or `lax` when not secure) | `none` is required when client and API are on different sites. |
| `JWT_MINUTES` | `60` | Token and cookie lifetime. |
| `FREE_CALLS` | `20` | |
| `MODEL_PATH` | `api/models/yolov10n/onnx/model.onnx` | |
| `SEED_DEMO_USERS` | `true` | Creates the two demo accounts. |
| `DRONE` / `BRIDGE_URL` | `sim` | `DRONE=mini2` with the bridge app's URL flies the real drone. |

## Deploying (e.g. Render)

- Root directory: `api`
- Build: `pip install -r requirements.txt && python scripts/download_model.py`
- Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Add a Postgres database and set `DATABASE_URL`, `JWT_SECRET` and `CLIENT_ORIGINS`.

**Cookie warning:** if the client and API are on different *sites* (for example two `*.onrender.com` apps, which count as different sites), Safari and some privacy settings block the cookie. Putting both on subdomains of one domain you own (`app.example.com` and `api.example.com`) keeps the origins separate, as the course requires, while the cookie stays first-party. Test login in Chrome and Safari before submitting.

## DJI Mini 2

- `app/mini2.py` calls an Android **bridge app** over HTTP (see `bridge/README.md`). The Mini 2 has no forward obstacle sensor, so telemetry reports `tof_mm = None`.
- Whether DJI's Mobile SDK velocity virtual sticks work on the Mini 2 is still unverified.

## Not yet built

- Follow sessions are kept in memory. Milestone 2 needs them (and recordings) in the database with full CRUD, including PATCH and DELETE.
- Edge WebSocket hub, recordings, and the Android bridge app.
