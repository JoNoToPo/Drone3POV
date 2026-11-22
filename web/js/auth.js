// Used by both login.html and register.html. register.html sets data-mode="register" on <body>.
const isRegister = document.body.dataset.mode === "register";

text("heading", isRegister ? MESSAGES.registerTitle : MESSAGES.loginTitle);
text("email-label", MESSAGES.emailLabel);
text("password-label", MESSAGES.passwordLabel);
text("submit", isRegister ? MESSAGES.registerButton : MESSAGES.loginButton);
text("switch-text", isRegister ? MESSAGES.haveAccount : MESSAGES.noAccount);
text("switch-link", isRegister ? MESSAGES.navLogin : MESSAGES.navRegister);
renderNav(null);

const form = document.getElementById("form");
const submit = document.getElementById("submit");

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const email = document.getElementById("email").value.trim();
  const password = document.getElementById("password").value;

  showMessage("message", "");
  submit.disabled = true;
  submit.textContent = MESSAGES.working;

  try {
    if (isRegister) {
      await Api.register(email, password);
      showMessage("message", MESSAGES.registered, false);
      form.reset();
    } else {
      const user = await Api.login(email, password);
      location.href = user.role === "admin" ? "admin.html" : "user.html";
    }
  } catch (err) {
    showMessage("message", err.message);
  } finally {
    submit.disabled = false;
    submit.textContent = isRegister ? MESSAGES.registerButton : MESSAGES.loginButton;
  }
});
