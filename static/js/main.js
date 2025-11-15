// Theme toggle + tabs

document.addEventListener("DOMContentLoaded", () => {
  // Theme toggle
  const body = document.body;
  const btn = document.getElementById("theme-toggle");

  function applyTheme(theme) {
    body.classList.remove("theme-light", "theme-dark");
    body.classList.add(theme);
    if (btn) {
      btn.textContent = theme === "theme-dark" ? "🌙 Тъмна тема" : "🌞 Светла тема";
    }
  }

  const storedTheme = window.localStorage.getItem("villageTheme");
  if (storedTheme) {
    applyTheme(storedTheme);
  } else {
    applyTheme("theme-light");
  }

  if (btn) {
    btn.addEventListener("click", () => {
      const current = body.classList.contains("theme-dark")
        ? "theme-dark"
        : "theme-light";
      const next = current === "theme-dark" ? "theme-light" : "theme-dark";
      applyTheme(next);
      window.localStorage.setItem("villageTheme", next);
    });
  }

  // Tabs
  const tabLinks = document.querySelectorAll(".tab-link");
  const tabPanels = document.querySelectorAll(".tab-panel");

  tabLinks.forEach((btn) => {
    btn.addEventListener("click", () => {
      const target = btn.getAttribute("data-tab-target");

      tabLinks.forEach((b) => b.classList.remove("tab-active"));
      tabPanels.forEach((p) => p.classList.remove("tab-panel-active"));

      btn.classList.add("tab-active");
      const panel = document.querySelector(target);
      if (panel) panel.classList.add("tab-panel-active");

      if (target === "#requests-tab") {
        window.location.hash = "requests-tab";
      } else {
        window.location.hash = "rides-tab";
      }
    });
  });

  // Activate tab from hash
  if (window.location.hash === "#requests-tab") {
    const btn = document.querySelector('.tab-link[data-tab-target="#requests-tab"]');
    if (btn) btn.click();
  }
});
