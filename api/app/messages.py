"""Every user-facing message the API returns, kept in one place."""

# Auth
EMAIL_INVALID = "Enter a valid email address."
PASSWORD_LENGTH = "Password must be between 3 and 72 characters."
EMAIL_TAKEN = "An account with that email already exists."
LOGIN_FAILED = "Email or password is incorrect."
NOT_LOGGED_IN = "Log in to use this service."
SESSION_EXPIRED = "Your session has expired. Log in again."
TOKEN_INVALID = "Your login is not valid. Log in again."
ADMIN_ONLY = "Only administrators can do this."
LOGGED_OUT = "You are logged out."

# Usage
FREE_CALLS_EXHAUSTED = (
    "You have used all {limit} free API calls. Your service will continue, "
    "but your free allowance has been exhausted."
)

# Follow sessions and drone
SESSION_NOT_FOUND = "Follow session not found."
SESSION_NOT_YOURS = "You can only control your own follow sessions."
DRONE_BUSY = "Another follow session already controls the drone."
DRONE_STOPPED = "Emergency stop sent. The motors are stopped."

# Vision
IMAGE_REQUIRED = "Upload an image file (JPEG or PNG)."
IMAGE_TOO_LARGE = "The image is too large. The limit is {limit_mb} MB."
IMAGE_UNREADABLE = "That file could not be read as an image."
MODEL_UNAVAILABLE = "The person-detection model is not available on the server."

# Generic
SERVER_ERROR = "Something went wrong on the server. Try again."
