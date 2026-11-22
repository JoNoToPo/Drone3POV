// All the text the user sees in the client.
const MESSAGES = {
  appTitle: "Drone3POV",
  tagline: "A drone that follows you from behind and films you in third person, like a video game camera.",

  navHome: "Home",
  navLogin: "Log in",
  navRegister: "Register",
  navAccount: "My account",
  navAdmin: "Admin",
  navLogout: "Log out",

  landingIntro:
    "Start a follow session through our API and the drone locks onto you, keeps a set distance behind you and records the flight.",
  landingHowTitle: "How it works",
  landingSteps: [
    "Create an account and log in.",
    "Upload a photo to try our self-hosted person detection model.",
    "Start a follow session and the drone follows you at a set distance.",
  ],
  landingCta: "Get started",

  loginTitle: "Log in",
  registerTitle: "Create an account",
  emailLabel: "Email",
  passwordLabel: "Password",
  loginButton: "Log in",
  registerButton: "Register",
  noAccount: "Don't have an account?",
  haveAccount: "Already have an account?",
  registered: "Account created. You can log in now.",
  working: "Please wait...",

  accountTitle: "My account",
  loggedInAs: "Logged in as",
  roleLabel: "Role",
  callsUsed: "API calls used",
  of: "of",
  freeCalls: "free calls",

  detectTitle: "Find people in a photo",
  detectHelp: "Upload a JPEG or PNG. Our own YOLOv10n model, running on our server, finds the people in it.",
  detectButton: "Detect people",
  detectPick: "Choose a photo first.",
  detectResult: (count, ms) => `Found ${count} ${count === 1 ? "person" : "people"} in ${ms} ms.`,

  adminTitle: "Admin",
  usersTitle: "Users",
  endpointsTitle: "Requests per endpoint",
  colId: "ID",
  colEmail: "Email",
  colRole: "Role",
  colCreated: "Created",
  colRequests: "Total requests",
  colMethod: "Method",
  colEndpoint: "Endpoint",

  networkError: "Could not reach the server. Check your connection and try again.",
  unknownError: "Something went wrong. Try again.",
  notLoggedIn: "You need to log in to see this page.",
};
