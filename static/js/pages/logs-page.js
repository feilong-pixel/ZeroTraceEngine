import { $ } from "../core/dom.js";
import { ensureDialog, showAlert } from "../core/dialog.js";
import { formatDisplayTime } from "../core/format.js";
import { markI18nReady, t, translateStaticText } from "../locales/i18n.js";

const AUDIT_API = "/recycle/loadAuditLogs";

function createLogsState() {
  return {
    logs: [],
    isLoading: false,
    filters: {
      action: "",
      result: "",
      source: "",
      keyword: "",
    },
  };
}

function getLogsElements() {
  return {
    reloadButton: $("#reloadAuditButton"),
    backButton: $("#backButton"),
    exportButton: $("#exportAuditButton"),
    logCount: $("#auditLogCount"),
    cleanCount: $("#auditCleanCount"),
    restoreCount: $("#auditRestoreCount"),
    failedCount: $("#auditFailedCount"),
    status: $("#auditStatus"),
    actionFilter: $("#auditActionFilter"),
    resultFilter: $("#auditResultFilter"),
    sourceFilter: $("#auditSourceFilter"),
    searchInput: $("#auditSearchInput"),
    tableHint: $("#auditTableHint"),
    tableBody: $("#auditTableBody"),
  };
}

function bindEvents(els, state) {
  els.backButton?.addEventListener("click", () => {
    location.href = "/";
  });
  els.reloadButton?.addEventListener("click", () => loadAuditLogs(els, state));
  els.exportButton?.addEventListener("click", () => exportAuditCsv(els, state));

  els.actionFilter?.addEventListener("change", () => {
    state.filters.action = els.actionFilter.value;
    render(els, state);
  });

  els.resultFilter?.addEventListener("change", () => {
    state.filters.result = els.resultFilter.value;
    render(els, state);
  });

  els.sourceFilter?.addEventListener("change", () => {
    state.filters.source = els.sourceFilter.value;
    render(els, state);
  });

  els.searchInput?.addEventListener("input", () => {
    state.filters.keyword = els.searchInput.value.trim().toLowerCase();
    render(els, state);
  });
}

async function loadAuditLogs(els, state) {
  state.isLoading = true;
  setStatus(els, t("logs.status.loading"));
  setHint(els, t("logs.hints.loading"));
  updateControls(els, state);

  try {
    const data = await fetchJson(AUDIT_API);
    state.logs = normalizeRecycleRecords(data);

    setStatus(els, state.logs.length > 0 ? t("logs.status.read") : t("logs.status.noLogs"));
    setHint(
      els,
      state.logs.length > 0 ? t("logs.hints.loaded") : t("logs.hints.noLogs"),
    );
    render(els, state);
  } catch (error) {
    console.error("[audit] load failed:", error);
    state.logs = [];
    setStatus(els, t("logs.status.failed"));
    setHint(els, t("logs.hints.failed"));
    render(els, state);
  } finally {
    state.isLoading = false;
    updateControls(els, state);
  }
}

async function exportAuditCsv(els, state) {
  const logs = getVisibleLogs(state);

  if (logs.length === 0) {
    await showAlert(t("logs.alerts.nothingToExport"));
    return;
  }

  const csv = toCsv(logs);
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `zerotrace-audit-${new Date().toISOString().slice(0, 10)}.csv`;
  link.click();
  URL.revokeObjectURL(url);
  setHint(els, t("logs.hints.exported", logs.length));
}

function render(els, state) {
  renderSummary(els, state);
  renderTable(els, state);
  updateControls(els, state);
}

function renderSummary(els, state) {
  const logs = state.logs;

  setText(els.logCount, String(logs.length));
  setText(els.cleanCount, String(logs.filter((log) => log.action === "clean").length));
  setText(
    els.restoreCount,
    String(logs.filter((log) => log.action === "restore").length),
  );
  setText(els.failedCount, String(logs.filter((log) => log.result === "failed").length));
}

function renderTable(els, state) {
  if (!els.tableBody) return;

  const visibleLogs = getVisibleLogs(state);

  if (visibleLogs.length === 0) {
    const emptyMessage = state.logs.length === 0
      ? t("logs.noLogs")
      : t("logs.noFilteredLogs");
    const hintMessage = state.logs.length === 0
      ? t("logs.hints.noLogs")
      : t("logs.hints.noFilteredLogs");

    els.tableBody.innerHTML = `
      <tr>
        <td colspan="7" class="empty-cell">${emptyMessage}</td>
      </tr>
    `;
    setHint(els, hintMessage);
    return;
  }

  els.tableBody.innerHTML = visibleLogs.map(renderRow).join("");
  setHint(els, t("logs.hints.visibleCount", visibleLogs.length));
}

function updateControls(els, state) {
  const hasLogs = state.logs.length > 0;
  const hasVisibleLogs = getVisibleLogs(state).length > 0;
  const busy = state.isLoading;

  if (els.reloadButton) els.reloadButton.disabled = busy;
  if (els.exportButton) els.exportButton.disabled = busy || !hasVisibleLogs;
  if (els.actionFilter) els.actionFilter.disabled = busy || !hasLogs;
  if (els.resultFilter) els.resultFilter.disabled = busy || !hasLogs;
  if (els.sourceFilter) els.sourceFilter.disabled = busy || !hasLogs;
  if (els.searchInput) els.searchInput.disabled = busy || !hasLogs;
}

function renderRow(log) {
  const target = escapeHtml(log.target);
  const detail = escapeHtml(log.detail);

  return `
    <tr>
      <td>${escapeHtml(formatDisplayTime(log.timestamp))}</td>
      <td>${escapeHtml(toActionLabel(log.action))}</td>
      <td class="path-input-cell">
        <input class="path-readonly-input" type="text" value="${target}" title="${target}" readonly />
      </td>
      <td>${formatBytes(log.size)}</td>
      <td>${renderResult(log.result)}</td>
      <td>${escapeHtml(log.source || t("common.states.system"))}</td>
      <td class="path-input-cell">
        <input class="path-readonly-input" type="text" value="${detail}" title="${detail}" readonly />
      </td>
    </tr>
  `;
}

function renderResult(result) {
  const label = toResultLabel(result);
  return `<span class="risk-badge result-${escapeHtml(result)}"><span class="risk-dot"></span>${escapeHtml(label)}</span>`;
}

function getVisibleLogs(state) {
  const { action, result, source, keyword } = state.filters;

  return state.logs.filter((log) => {
    if (action && log.action !== action) return false;
    if (result && log.result !== result) return false;
    if (source && log.source !== source) return false;

    if (keyword) {
      const text = [
        log.timestamp,
        log.action,
        log.target,
        log.result,
        log.source,
        log.detail,
      ]
        .join(" ")
        .toLowerCase();

      if (!text.includes(keyword)) return false;
    }

    return true;
  });
}

function normalizeRecycleRecords(records) {
  if (!Array.isArray(records)) return [];

  return records.flatMap((record, index) => {
    const action = normalizeAuditAction(record.action);
    const cleanLog = {
      id: String(record.id ?? `clean-${index}`),
      timestamp: String(record.created_at ?? ""),
      action,
      target: String(record.original_path ?? ""),
      size: Number(record.size ?? 0),
      result: "success",
      source: normalizeSource(record.source),
      detail: detailForAuditAction(action, record),
    };

    const derivedLogs = [cleanLog];

    if (record.restored_at) {
      derivedLogs.push({
        id: `${cleanLog.id}-restore`,
        timestamp: String(record.restored_at),
        action: "restore",
        target: String(record.original_path ?? ""),
        size: Number(record.size ?? 0),
        result: "success",
        source: "recycle",
        detail: t("logs.details.restoredFromRecycle", record.recycle_path ?? ""),
      });
    }

    if (record.purged_at) {
      derivedLogs.push({
        id: `${cleanLog.id}-purge`,
        timestamp: String(record.purged_at),
        action: "delete",
        target: String(record.recycle_path ?? ""),
        size: Number(record.size ?? 0),
        result: "success",
        source: "recycle",
        detail: t("logs.details.purgedFromRecycle", record.recycle_path ?? ""),
      });
    }

    return derivedLogs;
  });
}

function normalizeAuditAction(value) {
  const action = String(value ?? "").trim();
  if (action === "registry_execute") return "registry_execute";
  if (action === "registry_restore") return "registry_restore";
  return "clean";
}

function detailForAuditAction(action, record) {
  if (action === "registry_execute") {
    return t("logs.details.registryExecuted", record.recycle_path ?? "", record.hash ?? "");
  }
  if (action === "registry_restore") {
    return t("logs.details.registryRestored", record.recycle_path ?? "", record.hash ?? "");
  }
  return t("logs.details.movedToRecycle", record.recycle_path ?? "");
}

function normalizeSource(value) {
  const source = String(value ?? "system").trim();
  return source || "system";
}

function toActionLabel(value) {
  return (
    {
      scan: t("common.actions.scan"),
      plan: t("common.actions.plan"),
      clean: t("common.actions.clean"),
      registry_execute: t("common.actions.registryExecute"),
      registry_restore: t("common.actions.registryRestore"),
      restore: t("common.actions.restore"),
      delete: t("common.actions.delete"),
    }[value] ?? t("common.labels.action")
  );
}

function toResultLabel(value) {
  return (
    {
      success: t("common.results.success"),
      failed: t("common.results.failed"),
      skipped: t("common.results.skipped"),
    }[value] ?? t("common.results.success")
  );
}

async function fetchJson(url) {
  const response = await fetch(url, {
    headers: {
      Accept: "application/json",
    },
  });

  if (!response.ok) {
    throw new Error(`GET ${url} failed: ${response.status}`);
  }

  return response.json();
}

function setStatus(els, text) {
  setText(els.status, text);
}

function setHint(els, text) {
  setText(els.tableHint, text);
}

function setText(element, value) {
  if (!element) return;
  element.textContent = value ?? "";
}

function formatBytes(bytes) {
  const value = Number(bytes) || 0;
  if (value < 1024) return `${value} B`;

  const units = ["KB", "MB", "GB", "TB"];
  let size = value / 1024;
  let unitIndex = 0;

  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex += 1;
  }

  return `${size.toFixed(size >= 10 ? 1 : 2)} ${units[unitIndex]}`;
}

function toCsv(logs) {
  const headers = t("logs.csvHeaders");
  const rows = logs.map((log) => [
    log.timestamp,
    toActionLabel(log.action),
    log.target,
    String(log.size),
    toResultLabel(log.result),
    log.source,
    log.detail,
  ]);

  return [headers, ...rows].map((row) => row.map(csvCell).join(",")).join("\r\n");
}

function csvCell(value) {
  return `"${String(value ?? "").replaceAll('"', '""')}"`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

export function initLogsPage() {
  const els = getLogsElements();
  const state = createLogsState();

  ensureDialog();
  translateStaticText();
  bindEvents(els, state);
  render(els, state);
  loadAuditLogs(els, state).finally(markI18nReady);

  return { els, state };
}
