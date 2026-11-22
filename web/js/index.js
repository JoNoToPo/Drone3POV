document.title = MESSAGES.appTitle;
text("title", MESSAGES.appTitle);
text("tagline", MESSAGES.tagline);
text("intro", MESSAGES.landingIntro);
text("how-title", MESSAGES.landingHowTitle);
text("cta", MESSAGES.landingCta);

const steps = document.getElementById("steps");
for (const step of MESSAGES.landingSteps) {
  const li = document.createElement("li");
  li.textContent = step;
  steps.appendChild(li);
}

currentUser().then((user) => {
  renderNav(user);
  if (user) document.getElementById("cta").href = "user.html";
});
