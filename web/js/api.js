// Small wrapper around fetch for talking to the API.
// credentials: "include" sends the login cookie to the API, which is on another origin.

class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

// FastAPI puts the message in "detail". Validation errors give a list instead of a string.
function errorMessage(body) {
  if (!body || !body.detail) return MESSAGES.unknownError;
  if (typeof body.detail === "string") return body.detail;
  if (Array.isArray(body.detail)) {
    return body.detail.map((e) => (e.msg || "").replace(/^Value error, /, "")).join(" ");
  }
  return MESSAGES.unknownError;
}

async function api(path, options = {}) {
  const init = { method: options.method || "GET", credentials: "include", headers: {} };

  if (options.json !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(options.json);
  } else if (options.form) {
    init.body = options.form;
  }

  let res;
  try {
    res = await fetch(API_BASE + path, init);
  } catch (e) {
    throw new ApiError(0, MESSAGES.networkError);
  }

  let body = null;
  try {
    body = await res.json();
  } catch (e) {
    body = null;
  }

  if (!res.ok) throw new ApiError(res.status, errorMessage(body));
  return body;
}

const Api = {
  register: (email, password) => api("/api/v1/auth/register", { method: "POST", json: { email, password } }),
  login: (email, password) => api("/api/v1/auth/login", { method: "POST", json: { email, password } }),
  logout: () => api("/api/v1/auth/logout", { method: "POST" }),
  me: () => api("/api/v1/users/me"),
  detect: (file) => {
    const form = new FormData();
    form.append("image", file);
    return api("/api/v1/vision/detect", { method: "POST", form });
  },
  adminUsers: () => api("/api/v1/admin/users"),
  adminEndpoints: () => api("/api/v1/admin/stats/endpoints"),
};
