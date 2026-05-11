import { initLang } from "./locales/i18n.js";
import { initIndexPage } from "./pages/index-page.js";
import { initRecyclePage } from "./pages/recycle-page.js";
import { initScanPage } from "./pages/scan-page.js";
import { initLogsPage } from "./pages/logs-page.js";
import { initCleanupPage } from "./pages/cleanup-page.js";
import { initDuplicatesPage } from "./pages/duplicates-page.js";
import { initToolsPage } from "./pages/tools-page.js";
import { initRegistryPage } from "./pages/registry-page.js";
import { initUserDirectoryPage } from "./pages/user-directory-page.js";
import { initAppScanPage } from "./pages/app-scan-page.js";

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

  if (document.querySelector(".duplicates-page")) {
    initDuplicatesPage();
  }

  if (document.querySelector(".logs-page")) {
    initLogsPage();
  }

  if (document.querySelector(".cleanup-page")) {
    initCleanupPage();
  }

  if (document.querySelector(".tools-page")) {
    initToolsPage();
  }

  if (document.querySelector(".registry-page")) {
    initRegistryPage();
  }

  if (document.querySelector(".userdir-page")) {
    initUserDirectoryPage();
  }

  if (document.querySelector(".appscan-page")) {
    initAppScanPage();
  }
}

document.addEventListener("DOMContentLoaded", initApp);
