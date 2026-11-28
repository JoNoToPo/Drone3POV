# Drone3POV

A follow-me drone service: an API call starts a session, and a DJI Mini 2 follows one consenting person from behind and records the flight.

Task board: [Trello](https://trello.com/b/CMNrwg89/drone3pov)

## Live

| What | URL | Hosted on |
| --- | --- | --- |
| Client (login, user and admin pages) | https://drone3pov.netlify.app | Netlify |
| API | https://drone3pov-production.up.railway.app | Railway, with Postgres |
| API docs (Swagger) | https://drone3pov-production.up.railway.app/doc/ | Railway |

Demo accounts: `john@john.com` / `123` (user) and `admin@admin.com` / `111` (admin).

## Folders

| Folder | What it is | Language |
| --- | --- | --- |
| [`api/`](api/) | Cloud API: follow sessions, safety limits, drone adapters | Python, FastAPI |
| [`edge/`](edge/) | Laptop beside the flight area: person detection, follow controller, recording | Python |
| [`bridge/`](bridge/) | Android app that flies the Mini 2 through DJI's Mobile SDK | Kotlin |
| [`web/`](web/) | Console: login, landing page, session controls | Web frontend |
| [`docs/`](docs/) | Feasibility study, architecture, test logs | Markdown |

## How the parts connect

```
web console ──HTTPS──▶ api ──WebSocket──▶ edge laptop ──LAN──▶ bridge (Android phone) ──RC link──▶ Mini 2
```

The control loop runs on the edge laptop. The cloud API sets goals and limits and is never inside the loop.

## Getting started

```bash
py -3.13 -m venv .venv
.venv\Scripts\python.exe -m pip install -r api/requirements.txt
cd api && ..\.venv\Scripts\python.exe -m pytest -q
```

Python 3.14 alpha doesn't work with the current FastAPI and pydantic versions, so use 3.13.
