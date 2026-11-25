# Testing the API with Swagger

Swagger UI is served by the API itself:

- **Live:** https://drone3pov-production.up.railway.app/doc/
- **Local:** http://localhost:8000/doc/ (start the API as described in `api/README.md`, with `COOKIE_SECURE=false`)

`/doc` without the slash redirects there.

## Log in once, then test anything

1. Open **auth → POST /api/v1/auth/login**. **Try it out** is already on and the body is pre-filled:
   ```json
   { "email": "john@john.com", "password": "123" }
   ```
   Change it to `admin@admin.com` / `111` to test as an administrator.
2. Click **Execute**. A 200 response sets an HttpOnly `access_token` cookie in your browser.
3. Every other **Execute** on the page now sends that cookie. Endpoints with a lock icon need it.
   You don't need the **Authorize** button for this.
4. **POST /api/v1/auth/logout** clears the cookie. Protected endpoints then return 401.

The **Authorize** button is for a pasted Bearer token (`bearerAuth`). Use it only when testing with a token
copied from somewhere else, as you would in Postman.

## Things worth showing in a lab

| Try | Expected |
| --- | --- |
| `GET /api/v1/users/me` before logging in | 401, `"Log in to use this service."` |
| Log in as john, then `GET /api/v1/users/me` twice | 200; `api_calls_used` goes up by one each time |
| Response headers of any counted call | `x-free-calls-used`, `x-free-calls-limit`, `x-free-calls-exceeded` |
| `POST /api/v1/vision/detect` with a photo of people | 200 with a box per person (the self-hosted AI) |
| `POST /api/v1/vision/detect` with a `.txt` file | 415 |
| As john, `GET /api/v1/admin/users` | 403, `"Only administrators can do this."` |
| As admin, `GET /api/v1/admin/stats/endpoints` | 200, request counts per endpoint |
| `POST /api/v1/auth/register` with an existing email | 409 |
| `POST /api/v1/auth/register` with an extra `"role": "admin"` field | 422 (mass assignment blocked) |
| `POST /api/v1/follow-sessions` with `"distance_m": 9` | 422 (outside the 1.5–3 m safety limit) |

Swagger's **Curl** box under each response shows the exact request it sent, which is useful for the
"sample HTTP requests" part of the Learning Hub post.

## Notes

- Testing counts toward the account's 20 free calls, like any other use. After 20, responses keep working
  and `x-free-calls-exceeded` becomes `true`.
- Swagger on the live site and the API share one origin, so the cookie works in every browser,
  including Safari.
