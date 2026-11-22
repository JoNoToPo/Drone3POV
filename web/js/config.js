// Where the API lives. Running locally, the API is on port 8000.
const API_BASE =
  location.hostname === "localhost" || location.hostname === "127.0.0.1"
    ? "http://localhost:8000"
    : "https://drone3pov-production.up.railway.app";
