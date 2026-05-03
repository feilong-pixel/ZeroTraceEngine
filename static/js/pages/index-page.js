import { $, on, setText } from "../core/dom.js";
import { ensureDialog } from "../core/dialog.js";
import { markI18nReady, translateStaticText } from "../locales/i18n.js";

function getIndexElements() {
  return {
    startScanButton: $("#startScanButton"),
    openRecycleButton: $("#openRecycleButton"),
    openScanButton: $("#openScanButton"),
    openCleanupButton: $("#openCleanupButton"),
    openRecycleCardButton: $("#openRecycleCardButton"),
    openLogsButton: $("#openLogsButton"),
    recycleCount: $("#recycleCount"),
    logCount: $("#logCount"),
  };
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
  on(els.openRecycleButton, "click", () => goTo("/recycle"));
  on(els.openRecycleCardButton, "click", () => goTo("/recycle"));
  on(els.openLogsButton, "click", () => goTo("/logs"));
}

export function initIndexPage() {
  const els = getIndexElements();

  ensureDialog();
  translateStaticText();
  bindIndexEvents(els);
  loadDashboardStatus(els).finally(markI18nReady);

  return { els };
}
