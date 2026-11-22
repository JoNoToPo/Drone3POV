# web

The client for Milestone 1: landing page, register, login, user page and admin page. Plain HTML, CSS and JavaScript, no build step.

| Page | What it does |
| --- | --- |
| `index.html` | Landing page with the project title |
| `register.html` / `login.html` | Calls `/api/v1/auth/register` and `/api/v1/auth/login`, shows the API's error messages |
| `user.html` | Email, role and API calls used from `/api/v1/users/me`, the free-call warning, and a photo upload that calls `/api/v1/vision/detect` and draws boxes around the people |
| `admin.html` | Users table and requests per endpoint. A normal user gets the API's 403 message |

All the text the user sees is in `js/messages.js`. The API's address is in `js/config.js`.

Every request uses `credentials: "include"` so the login cookie is sent to the API, which is on a different origin.

## Run locally

Start the API from `api/` with `COOKIE_SECURE=false` (see `api/README.md`), then serve this folder on port 5173, which the API allows by default:

```bash
cd web
python -m http.server 5173
```

Open http://localhost:5173. Demo accounts: `john@john.com` / `123` and `admin@admin.com` / `111`.

## Hosting

Any static host works (Netlify, Vercel, Cloudflare Pages, GitHub Pages). Point it at the `web/` folder with no build command.

After it is up, add the client's URL to `CLIENT_ORIGINS` on the API's Railway service, or the browser will block the requests.
