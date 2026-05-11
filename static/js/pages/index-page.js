import { $, on, setText } from "../core/dom.js";
import { ensureDialog } from "../core/dialog.js";
import { getLang, markI18nReady, setLang, translateStaticText } from "../locales/i18n.js";

function getIndexElements() {
  return {
    startScanButton: $("#startScanButton"),
    openRecycleButton: $("#openRecycleButton"),
    openScanButton: $("#openScanButton"),
    openCleanupButton: $("#openCleanupButton"),
    openToolsButton: $("#openToolsButton"),
    openRecycleCardButton: $("#openRecycleCardButton"),
    openLogsButton: $("#openLogsButton"),
    openRegistryButton: $("#openRegistryButton"),
    openDuplicatesButton: $("#openDuplicatesButton"),
    openUserdirButton: $("#openUserdirButton"),
    openAppscanButton: $("#openAppscanButton"),
    languageSelect: $("#languageSelect"),
    recycleCount: $("#recycleCount"),
    logCount: $("#logCount"),
  };
}

function applyDocumentLang(lang) {
  document.documentElement.lang = lang === "en" ? "en" : "zh-CN";
}

function goTo(path) {
  location.href = path;
}

async function loadDashboardStatus(els) {
  try {
    const [recycleRes, auditRes] = await Promise.all([
      fetch("/recycle/loadRecycleRecords"),
      fetch("/recycle/loadAuditLogs"),
    ]);

    if (!recycleRes.ok) {
      throw new Error(`Recycle API failed: ${recycleRes.status}`);
    }
    if (!auditRes.ok) {
      throw new Error(`Audit API failed: ${auditRes.status}`);
    }

    const recycleRecords = await recycleRes.json();
    const auditRecords = await auditRes.json();
    const activeRecords = recycleRecords.filter((record) => !record.restored_at);
    const auditCount = auditRecords.reduce((count, record) => {
      return count + (record.restored_at ? 2 : 1);
    }, 0);

    setText(els.recycleCount, activeRecords.length);
    setText(els.logCount, auditCount);
  } catch (error) {
    console.warn("Dashboard status load failed:", error);
    setText(els.recycleCount, "-");
    setText(els.logCount, "-");
  }
}

function bindIndexEvents(els) {
  on(els.startScanButton, "click", () => goTo("/scan"));
  on(els.openScanButton, "click", () => goTo("/scan"));
  on(els.openCleanupButton, "click", () => goTo("/cleanup"));
  on(els.openToolsButton, "click", () => goTo("/tools"));
  on(els.openRecycleButton, "click", () => goTo("/recycle"));
  on(els.openRecycleCardButton, "click", () => goTo("/recycle"));
  on(els.openLogsButton, "click", () => goTo("/logs"));
  if (els.openRegistryButton) on(els.openRegistryButton, "click", () => goTo("/registry"));
  if (els.openDuplicatesButton) on(els.openDuplicatesButton, "click", () => goTo("/duplicates"));
  if (els.openUserdirButton) on(els.openUserdirButton, "click", () => goTo("/user-directory"));
  if (els.openAppscanButton) on(els.openAppscanButton, "click", () => goTo("/app-scan"));
}

function bindLanguageSwitch(els) {
  if (!els.languageSelect) return;

  const currentLang = getLang();
  els.languageSelect.value = currentLang === "en" ? "en" : "zh";
  applyDocumentLang(els.languageSelect.value);

  on(els.languageSelect, "change", () => {
    const nextLang = setLang(els.languageSelect.value);
    els.languageSelect.value = nextLang === "en" ? "en" : "zh";
    applyDocumentLang(els.languageSelect.value);
    translateStaticText();
  });
}

export function initIndexPage() {
  const els = getIndexElements();

  ensureDialog();
  translateStaticText();
  bindLanguageSwitch(els);
  bindIndexEvents(els);
  loadDashboardStatus(els).finally(markI18nReady);

  return { els };
}
