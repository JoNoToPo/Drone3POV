text("heading", MESSAGES.adminTitle);
text("users-title", MESSAGES.usersTitle);
text("endpoints-title", MESSAGES.endpointsTitle);
text("col-id", MESSAGES.colId);
text("col-email", MESSAGES.colEmail);
text("col-role", MESSAGES.colRole);
text("col-created", MESSAGES.colCreated);
text("col-requests", MESSAGES.colRequests);
text("col-method", MESSAGES.colMethod);
text("col-endpoint", MESSAGES.colEndpoint);
text("col-endpoint-requests", MESSAGES.colRequests);

function addRow(tbody, values) {
  const tr = document.createElement("tr");
  for (const value of values) {
    const td = document.createElement("td");
    td.textContent = value;
    tr.appendChild(td);
  }
  tbody.appendChild(tr);
}

async function loadAdmin() {
  // Nav first, so a normal user still gets the nav bar while seeing the 403 message
  renderNav(await currentUser());

  // The server decides who is an admin. A normal user gets the API's 403 message here.
  try {
    const [users, endpoints] = await Promise.all([Api.adminUsers(), Api.adminEndpoints()]);

    const usersBody = document.getElementById("users");
    for (const u of users) {
      addRow(usersBody, [u.id, u.email, u.role, new Date(u.created_at).toLocaleString(), u.total_requests]);
    }

    const endpointsBody = document.getElementById("endpoints");
    for (const e of endpoints) {
      addRow(endpointsBody, [e.method, e.endpoint, e.total_requests]);
    }

    document.getElementById("content").hidden = false;
  } catch (err) {
    showMessage("page-message", err.message);
  }
}

loadAdmin();
