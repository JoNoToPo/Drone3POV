// Shared bits for every page: the nav bar, filling in text, and showing messages.

function text(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}

function showMessage(id, message, isError = true) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = message;
  el.className = "msg " + (isError ? "error" : "ok");
  el.hidden = !message;
}

function link(href, label) {
  const a = document.createElement("a");
  a.href = href;
  a.textContent = label;
  return a;
}

// user is the /users/me response, or null when logged out
function renderNav(user) {
  const nav = document.getElementById("nav");
  if (!nav) return;
  nav.innerHTML = "";

  const brand = link("index.html", MESSAGES.appTitle);
  brand.className = "brand";
  nav.appendChild(brand);

  const right = document.createElement("div");
  right.className = "nav-links";

  if (user) {
    right.appendChild(link("user.html", MESSAGES.navAccount));
    if (user.role === "admin") right.appendChild(link("admin.html", MESSAGES.navAdmin));

    const out = document.createElement("button");
    out.textContent = MESSAGES.navLogout;
    out.className = "link-button";
    out.addEventListener("click", async () => {
      try {
        await Api.logout();
      } catch (e) {
        // cookie is cleared server side, nothing else to do
      }
      location.href = "login.html";
    });
    right.appendChild(out);
  } else {
    right.appendChild(link("login.html", MESSAGES.navLogin));
    right.appendChild(link("register.html", MESSAGES.navRegister));
  }

  nav.appendChild(right);
}

// Returns the logged in user, or null. Used by pages that work either way.
async function currentUser() {
  try {
    return await Api.me();
  } catch (e) {
    return null;
  }
}
