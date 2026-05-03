import { initLang } from "./locales/i18n.js";
import { initIndexPage } from "./pages/index-page.js";
import { initRecyclePage } from "./pages/recycle-page.js";
import { initScanPage } from "./pages/scan-page.js";
import { initLogsPage } from "./pages/logs-page.js";
import { initCleanupPage } from "./pages/cleanup-page.js";

function initApp() {
  initLang();

  if (document.querySelector(".dashboard-page")) {
    initIndexPage();
    return;
  }

  if (document.querySelector(".recycle-page")) {
    initRecyclePage();
    return;
  }

  if (document.querySelector(".scan-page")) {
    initScanPage();
  }

  if (document.querySelector(".logs-page")) {
    initLogsPage();
  }

  if (document.querySelector(".cleanup-page")) {
    initCleanupPage();
  }
}

document.addEventListener("DOMContentLoaded", initApp);
