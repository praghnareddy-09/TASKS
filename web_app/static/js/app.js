const updateConnectivity = () => {
  let banner = document.querySelector("[data-connectivity-banner]");
  if (!banner) {
    banner = document.createElement("div");
    banner.dataset.connectivityBanner = "";
    banner.setAttribute("role", "status");
    banner.setAttribute("aria-live", "polite");
    banner.className = "connectivity-banner";
    banner.textContent = "Check your connection. Reconnecting...";
    document.body.prepend(banner);
  }
  banner.hidden = navigator.onLine;
  document.querySelectorAll("form[data-loading-form] [type='submit']").forEach((button) => {
    button.disabled = !navigator.onLine;
  });
};

const showLiveUpdatePending = () => {
  const banner = document.querySelector("[data-live-update-banner]");
  if (banner) banner.hidden = false;
};

const hasUnsavedFormChanges = () => {
  return Array.from(document.querySelectorAll(".main-content form")).some((form) => {
    return Array.from(form.elements).some((field) => {
      if (!field.name || field.type === "submit" || field.type === "button" || field.type === "hidden") return false;
      if (field.type === "checkbox" || field.type === "radio") return field.checked !== field.defaultChecked;
      return field.value !== field.defaultValue;
    });
  });
};

const initializeCharts = (root) => {
  if (!window.Chart) return;
  root.querySelectorAll("[data-doughnut-chart]").forEach((canvas) => {
    if (Chart.getChart(canvas)) Chart.getChart(canvas).destroy();
    const chart = JSON.parse(canvas.dataset.chart || "{}");
    new Chart(canvas, {
      type: "doughnut",
      data: {
        labels: chart.labels || [],
        datasets: [{
          data: chart.values || [],
          backgroundColor: ["#f59e0b", "#4f46e5", "#16a34a", "#dc2626", "#0ea5e9"],
          borderWidth: 0
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { position: "bottom" } },
        cutout: "68%"
      }
    });
  });
};

const updateNotificationCount = async () => {
  const badge = document.querySelector("[data-unread-notification-count]");
  if (!badge) return;
  try {
    const response = await fetch("/notifications/count/", {
      credentials: "same-origin",
      headers: { "X-Requested-With": "XMLHttpRequest" }
    });
    if (!response.ok) throw new Error(`Notification count request failed (${response.status}).`);
    const data = await response.json();
    badge.textContent = data.unread;
    badge.hidden = !data.unread;
  } catch (error) {
    console.error("Could not update notification count.", error);
  }
};

const refreshWorkflowPage = async () => {
  const liveBanner = document.querySelector("[data-live-update-banner]");
  const content = document.querySelector(".main-content");
  if (!content || !navigator.onLine) {
    if (liveBanner) liveBanner.hidden = false;
    return;
  }
  if (hasUnsavedFormChanges()) {
    showLiveUpdatePending();
    return;
  }
  try {
    const response = await fetch(window.location.href, {
      credentials: "same-origin",
      headers: { "X-Requested-With": "XMLHttpRequest", "X-Workflow-Refresh": "true" }
    });
    if (!response.ok) throw new Error(`Workflow refresh failed (${response.status}).`);
    const html = await response.text();
    const documentFromResponse = new DOMParser().parseFromString(html, "text/html");
    const refreshedContent = documentFromResponse.querySelector(".main-content");
    if (!refreshedContent) throw new Error("Workflow refresh response did not include page content.");
    content.replaceChildren(...Array.from(refreshedContent.childNodes));
    if (documentFromResponse.title) document.title = documentFromResponse.title;
    initializeCharts(content);
    updateConnectivity();
    updateNotificationCount();
    content.dispatchEvent(new CustomEvent("workflow:refreshed", { bubbles: true }));
    if (liveBanner) liveBanner.hidden = true;
  } catch (error) {
    console.error("Could not synchronize this page with the latest workflow data.", error);
    showLiveUpdatePending();
  }
};

const connectWorkflowSocket = () => {
  if (!("WebSocket" in window) || !navigator.onLine) return;
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const socket = new WebSocket(`${protocol}//${window.location.host}/ws/workflow/`);
  socket.addEventListener("message", (message) => {
    let event;
    try {
      event = JSON.parse(message.data);
    } catch (error) {
      console.error("Received an invalid workflow event.", error);
      return;
    }
    if (event.type === "workflow.changed") {
      refreshWorkflowPage();
      updateNotificationCount();
    }
  });
  socket.addEventListener("close", () => {
    if (navigator.onLine) window.setTimeout(connectWorkflowSocket, 3000);
  });
  socket.addEventListener("error", () => socket.close());
};

document.addEventListener("click", (event) => {
  const target = event.target.closest("[data-sidebar-toggle], [data-password-toggle], [data-copy-target], [data-refresh-workflow]");
  if (!target) return;

  if (target.matches("[data-sidebar-toggle]")) {
    document.querySelector(".sidebar")?.classList.toggle("show");
  }

  if (target.matches("[data-password-toggle]")) {
    const input = document.querySelector(target.dataset.passwordToggle);
    if (!input) return;
    const showing = input.type === "text";
    input.type = showing ? "password" : "text";
    target.setAttribute("aria-label", showing ? "Show password" : "Hide password");
    target.innerHTML = `<i class="bi bi-eye${showing ? "" : "-slash"}" aria-hidden="true"></i>`;
  }

  if (target.matches("[data-copy-target]")) {
    const input = document.querySelector(target.dataset.copyTarget);
    if (!input) return;
    input.select();
    input.setSelectionRange(0, input.value.length);
    if (navigator.clipboard) {
      navigator.clipboard.writeText(input.value).then(
        () => { target.textContent = "Copied"; },
        (error) => {
          console.error("Could not copy the temporary password.", error);
          target.textContent = "Copy failed";
        }
      );
    } else if (document.execCommand("copy")) {
      target.textContent = "Copied";
    } else {
      target.textContent = "Copy failed";
    }
  }

  if (target.matches("[data-refresh-workflow]")) refreshWorkflowPage();
});

document.addEventListener("submit", (event) => {
  const form = event.target;
  if (!(form instanceof HTMLFormElement)) return;
  if (!navigator.onLine && form.matches("[data-loading-form]")) {
    event.preventDefault();
    updateConnectivity();
    return;
  }
  if (form.matches("[data-loading-form]")) {
    const button = form.querySelector("[type='submit']");
    if (button && navigator.onLine) {
      button.classList.add("is-submitting");
      button.disabled = true;
    }
  }
});

document.addEventListener("DOMContentLoaded", () => {
  updateConnectivity();
  window.addEventListener("offline", updateConnectivity);
  window.addEventListener("online", () => {
    updateConnectivity();
    connectWorkflowSocket();
  });
  initializeCharts(document);
  updateNotificationCount();

  document.querySelectorAll(".toast[data-bs-autohide='true']").forEach((element) => {
    if (window.bootstrap) new bootstrap.Toast(element, { delay: 4500 }).show();
  });

  if (document.body.dataset.workflowLive === "true") connectWorkflowSocket();
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js");
});
