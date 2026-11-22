text("heading", MESSAGES.accountTitle);
text("email-label", MESSAGES.loggedInAs);
text("role-label", MESSAGES.roleLabel);
text("calls-label", MESSAGES.callsUsed);
text("detect-title", MESSAGES.detectTitle);
text("detect-help", MESSAGES.detectHelp);
text("detect", MESSAGES.detectButton);

function showUser(user) {
  text("email", user.email);
  text("role", user.role);
  text("calls", `${user.api_calls_used} ${MESSAGES.of} ${user.free_calls_limit} ${MESSAGES.freeCalls}`);

  const warning = document.getElementById("warning");
  if (user.free_calls_exceeded) {
    warning.textContent = user.warning;
    warning.hidden = false;
  } else {
    warning.hidden = true;
  }
}

async function loadUser() {
  try {
    const user = await Api.me();
    renderNav(user);
    showUser(user);
    document.getElementById("content").hidden = false;
  } catch (err) {
    renderNav(null);
    showMessage("page-message", err.status === 401 ? MESSAGES.notLoggedIn : err.message);
  }
}

// Draws the photo on the canvas with a box around each person the API found.
function drawBoxes(file, result) {
  const canvas = document.getElementById("canvas");
  const ctx = canvas.getContext("2d");
  const img = new Image();

  img.onload = () => {
    canvas.width = img.naturalWidth;
    canvas.height = img.naturalHeight;
    ctx.drawImage(img, 0, 0);

    // the API gives boxes in the original image's pixels
    const sx = img.naturalWidth / result.image_width;
    const sy = img.naturalHeight / result.image_height;
    const lineWidth = Math.max(2, Math.round(img.naturalWidth / 300));

    ctx.lineWidth = lineWidth;
    ctx.font = `${lineWidth * 7}px sans-serif`;

    for (const person of result.people) {
      const [x1, y1, x2, y2] = person.box;
      ctx.strokeStyle = "#00e676";
      ctx.strokeRect(x1 * sx, y1 * sy, (x2 - x1) * sx, (y2 - y1) * sy);

      const label = Math.round(person.confidence * 100) + "%";
      ctx.fillStyle = "#00e676";
      ctx.fillRect(x1 * sx, y1 * sy - lineWidth * 9, ctx.measureText(label).width + lineWidth * 2, lineWidth * 9);
      ctx.fillStyle = "#000";
      ctx.fillText(label, x1 * sx + lineWidth, y1 * sy - lineWidth * 2);
    }

    URL.revokeObjectURL(img.src);
    canvas.hidden = false;
  };

  img.src = URL.createObjectURL(file);
}

document.getElementById("detect").addEventListener("click", async () => {
  const file = document.getElementById("photo").files[0];
  const button = document.getElementById("detect");

  if (!file) {
    showMessage("detect-message", MESSAGES.detectPick);
    return;
  }

  showMessage("detect-message", "");
  button.disabled = true;
  button.textContent = MESSAGES.working;

  try {
    const result = await Api.detect(file);
    showMessage("detect-message", MESSAGES.detectResult(result.people_count, Math.round(result.inference_ms)), false);
    drawBoxes(file, result);
    // calls used went up, so refresh the numbers
    showUser(await Api.me());
  } catch (err) {
    showMessage("detect-message", err.message);
  } finally {
    button.disabled = false;
    button.textContent = MESSAGES.detectButton;
  }
});

loadUser();
