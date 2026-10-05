document.addEventListener("DOMContentLoaded", () => {
  const sidebar = document.querySelector(".sidebar");
  document.querySelectorAll("[data-sidebar-toggle]").forEach((button) => {
    button.addEventListener("click", () => sidebar?.classList.toggle("show"));
  });

  document.querySelectorAll("[data-password-toggle]").forEach((button) => {
    button.addEventListener("click", () => {
      const input = document.querySelector(button.dataset.passwordToggle);
      if (!input) return;
      const showing = input.type === "text";
      input.type = showing ? "password" : "text";
      button.setAttribute("aria-label", showing ? "Show password" : "Hide password");
      button.innerHTML = `<i class="bi bi-eye${showing ? "" : "-slash"}" aria-hidden="true"></i>`;
    });
  });

  document.querySelectorAll(".toast[data-bs-autohide='true']").forEach((element) => {
    if (window.bootstrap) new bootstrap.Toast(element, { delay: 4500 }).show();
  });

  document.querySelectorAll("form[data-loading-form]").forEach((form) => {
    form.addEventListener("submit", () => {
      const button = form.querySelector("[type='submit']");
      if (button) {
        button.classList.add("is-submitting");
        button.disabled = true;
      }
    });
  });

  document.querySelectorAll("[data-doughnut-chart]").forEach((canvas) => {
    if (!window.Chart) return;
    const chart = JSON.parse(canvas.dataset.chart || "{}");
    new Chart(canvas, {
      type: "doughnut",
      data: { labels: chart.labels || [], datasets: [{ data: chart.values || [], backgroundColor: ["#f59e0b", "#4f46e5", "#16a34a"], borderWidth: 0 }] },
      options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: "bottom" } }, cutout: "68%" }
    });
  });
});
