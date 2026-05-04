import { $, on, setText } from "../core/dom.js";
import { ensureDialog, showAlert, showConfirm } from "../core/dialog.js";
import { formatDisplayTime } from "../core/format.js";
import { markI18nReady, t, translateStaticText } from "../locales/i18n.js";

const CLEANUP_SELECTION_STORAGE_KEY = "zerotrace.cleanupSelection";
const LEGACY_PLAN_STORAGE_KEY = "zerotrace.cleanupPlan";

function createScanState() {
  return {
    items: [],
    selectedPaths: new Set(),
    isScanning: false,
  };
}

function getScanElements() {
  return {
    startScanButton: $("#startScanButton"),
    backButton: $("#backButton"),
    clearResultsButton: $("#clearResultsButton"),
    selectAllButton: $("#selectAllButton"),
    invertSelectionButton: $("#invertSelectionButton"),
    createPlanButton: $("#createPlanButton"),
    categoryFilter: $("#categoryFilter"),
    riskFilter: $("#riskFilter"),
    sourceFilter: $("#sourceFilter"),
    scanResultBody: $("#scanResultBody"),
    scanItemCount: $("#scanItemCount"),
    scanTotalSize: $("#scanTotalSize"),
    selectedCount: $("#selectedCount"),
    scanStatus: $("#scanStatus"),
    scanDuration: $("#scanDuration"),
    scannerReportList: $("#scannerReportList"),
  };
}

function formatBytes(bytes) {
  if (!bytes) return "0 B";

  const units = ["B", "KB", "MB", "GB"];
  let size = Number(bytes);
  let index = 0;

  while (size >= 1024 && index < units.length - 1) {
    size /= 1024;
    index += 1;
  }

  return `${size.toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function getFilteredItems(els, state) {
  const category = els.categoryFilter?.value || "";
  const risk = els.riskFilter?.value || "";
  const source = els.sourceFilter?.value || "";

  return state.items.filter((item) => {
    if (category && item.category !== category) return false;
    if (risk && item.risk_level !== risk) return false;
    if (source && item.source !== source) return false;
    return true;
  });
}

function updateControls(els, state) {
  const hasResults = state.items.length > 0;
  const visibleItems = getFilteredItems(els, state);
  const hasVisibleResults = visibleItems.length > 0;
  const hasSelection = state.selectedPaths.size > 0;

  if (els.backButton) els.backButton.disabled = state.isScanning;
  if (els.startScanButton) els.startScanButton.disabled = state.isScanning;
  if (els.clearResultsButton)
    els.clearResultsButton.disabled = state.isScanning || !hasResults;
  if (els.selectAllButton)
    els.selectAllButton.disabled = state.isScanning || !hasVisibleResults;
  if (els.invertSelectionButton)
    els.invertSelectionButton.disabled = state.isScanning || !hasVisibleResults;
  if (els.createPlanButton)
    els.createPlanButton.disabled = state.isScanning || !hasSelection;
  if (els.categoryFilter)
    els.categoryFilter.disabled = state.isScanning || !hasResults;
  if (els.riskFilter) els.riskFilter.disabled = state.isScanning || !hasResults;
  if (els.sourceFilter)
    els.sourceFilter.disabled = state.isScanning || !hasResults;

  els.scanResultBody
    ?.querySelectorAll('input[type="checkbox"]')
    .forEach((checkbox) => {
      checkbox.disabled = state.isScanning;
    });
}

function formatDuration(milliseconds) {
  if (milliseconds == null) return "-";
  if (milliseconds < 1000) return `${Math.round(milliseconds)} ms`;
  return t("common.units.seconds", (milliseconds / 1000).toFixed(2));
}

function setStatus(els, status, tone = "idle") {
  const statusText =
    {
      idle: t("scan.status.idle"),
      running: t("scan.status.running"),
      success: t("scan.status.success"),
      error: t("scan.status.error"),
      emptySelection: t("scan.status.emptySelection"),
    }[tone] || status;

  setText(els.scanStatus, status || statusText);

  if (els.scanStatus) {
    els.scanStatus.className = `status-value status-${tone}`;
  }
}

function renderSourceOptions(els, state) {
  if (!els.sourceFilter) return;

  const selected = els.sourceFilter.value;
  const sources = Array.from(
    new Set(state.items.map((item) => item.source).filter(Boolean)),
  ).sort((a, b) => a.localeCompare(b));

  els.sourceFilter.innerHTML = [
    `<option value="">${t("common.labels.all")}</option>`,
    ...sources.map((source) => {
      const isSelected = source === selected ? "selected" : "";
      return `<option value="${escapeHtml(source)}" ${isSelected}>${escapeHtml(source)}</option>`;
    }),
  ].join("");

  if (selected && !sources.includes(selected)) {
    els.sourceFilter.value = "";
  }
}

function renderSummary(els, state) {
  const totalSize = state.items.reduce((sum, item) => {
    return sum + Number(item.size || 0);
  }, 0);

  setText(els.scanItemCount, state.items.length);
  setText(els.scanTotalSize, formatBytes(totalSize));
  setText(els.selectedCount, state.selectedPaths.size);
}

function renderTable(els, state) {
  if (!els.scanResultBody) return;

  const items = getFilteredItems(els, state);

  if (items.length === 0) {
    els.scanResultBody.innerHTML = `
      <tr class="empty-row">
        <td colspan="7">${t("scan.noResults")}</td>
      </tr>
    `;
    renderSummary(els, state);
    updateControls(els, state);
    return;
  }

  els.scanResultBody.innerHTML = items
    .map((item) => {
      const checked = state.selectedPaths.has(item.path) ? "checked" : "";
      const risk = item.risk_level || "low";
      const path = escapeHtml(item.path);
      const source = escapeHtml(item.source || "-");
      const riskLabel =
        {
          low: t("common.risks.low"),
          medium: t("common.risks.medium"),
          high: t("common.risks.high"),
        }[risk] || risk;

      return `
      <tr>
        <td class="col-check">
          <input type="checkbox" data-path="${path}" ${checked} />
        </td>
        <td class="path-input-cell">
          <input class="path-readonly-input" type="text" value="${path}" title="${path}" readonly />
        </td>
        <td>${formatBytes(item.size)}</td>
        <td>${escapeHtml(toCategoryLabel(item))}</td>
        <td>${source}</td>
        <td>${escapeHtml(formatDisplayTime(item.mtime || item.last_modified))}</td>
        <td>
          <span class="risk-badge risk-${escapeHtml(risk)}">
            <span class="risk-dot"></span>${escapeHtml(riskLabel)}
          </span>
        </td>
      </tr>
    `;
    })
    .join("");

  renderSummary(els, state);
  updateControls(els, state);
}

function toCategoryLabel(item) {
  if (item.category === "empty" && item.file_type === "folder")
    return t("scan.categories.emptyFolder");
  if (item.category === "empty") return t("common.categories.empty");
  if (item.category === "temp") return t("common.categories.temp");
  if (item.category === "browser_cache") return t("common.categories.browserCache");
  if (item.category === "log") return t("common.categories.logFile");
  if (item.category === "update") return t("common.categories.windowsUpdate");
  if (item.category === "thumbnail") return t("common.categories.thumbnail");
  return item.category || "-";
}

function renderScannerReports(els, reports = []) {
  if (!els.scannerReportList) return;

  if (!Array.isArray(reports) || reports.length === 0) {
    els.scannerReportList.innerHTML = `
      <p class="muted">${t("scan.diagnosticsEmpty")}</p>
    `;
    return;
  }

  els.scannerReportList.innerHTML = reports
    .map((report) => {
      const status = report.status === "error"
        ? t("scan.diagnosticsStatus.error")
        : t("scan.diagnosticsStatus.ok");
      const roots = Array.isArray(report.roots) && report.roots.length > 0
        ? report.roots.join("; ")
        : t("scan.diagnosticsNoRoots");
      const error = report.error
        ? `<p class="scanner-report-error">${escapeHtml(report.error)}</p>`
        : "";

      return `
        <article class="scanner-report-item scanner-report-${escapeHtml(report.status || "ok")}">
          <div>
            <strong>${escapeHtml(report.scanner || "-")}</strong>
            <span>${escapeHtml(status)} · ${t("scan.diagnosticsCount", Number(report.count || 0))}</span>
          </div>
          <input class="path-readonly-input" type="text" value="${escapeHtml(roots)}" title="${escapeHtml(roots)}" readonly />
          ${error}
        </article>
      `;
    })
    .join("");
}

async function startScan(els, state) {
  const startedAt = performance.now();
  state.isScanning = true;
  state.selectedPaths.clear();
  setStatus(els, null, "running");
  setText(els.scanDuration, t("scan.timing"));
  updateControls(els, state);

  try {
    const res = await fetch("/scan/start", {
      method: "POST",
      headers: {
        Accept: "application/json",
      },
    });
    if (!res.ok) throw new Error(`Scan API failed: ${res.status}`);

    const payload = await res.json();
    state.items = Array.isArray(payload) ? payload : payload.items || [];
    renderScannerReports(els, payload.scanner_reports || []);
    renderSourceOptions(els, state);

    setStatus(els, null, "success");
    setText(els.scanDuration, formatDuration(performance.now() - startedAt));
    renderTable(els, state);
  } catch (error) {
    console.error(error);
    setStatus(els, null, "error");
    setText(els.scanDuration, formatDuration(performance.now() - startedAt));
  } finally {
    state.isScanning = false;
    updateControls(els, state);
  }
}

async function clearResults(els, state) {
  if (state.isScanning) return;

  const ok = await showConfirm(
    t("scan.confirmClear.message"),
    {
      title: t("scan.confirmClear.title"),
      confirmText: t("scan.confirmClear.confirmText"),
      cancelText: t("common.buttons.cancel"),
    },
  );
  if (!ok) return;

  if (els.clearResultsButton) {
    els.clearResultsButton.disabled = true;
  }

  try {
    const res = await fetch("/scan/clearResults", {
      method: "POST",
      headers: {
        Accept: "application/json",
      },
    });
    if (!res.ok) throw new Error(`Clear scan results failed: ${res.status}`);

    if (els.categoryFilter) els.categoryFilter.value = "";
    if (els.riskFilter) els.riskFilter.value = "";
    if (els.sourceFilter) els.sourceFilter.value = "";

    state.items = [];
    state.selectedPaths.clear();
    renderScannerReports(els, []);
    renderSourceOptions(els, state);
    setStatus(els, null, "idle");
    setText(els.scanDuration, "-");
    renderTable(els, state);
  } catch (error) {
    console.error(error);
    setStatus(els, t("scan.status.clearFailed"), "error");
    updateControls(els, state);
    await showAlert(t("scan.alerts.clearFailed"));
  }
}

function selectAllVisible(els, state) {
  getFilteredItems(els, state).forEach((item) => {
    state.selectedPaths.add(item.path);
  });

  renderTable(els, state);
}

function invertSelection(els, state) {
  getFilteredItems(els, state).forEach((item) => {
    if (state.selectedPaths.has(item.path)) {
      state.selectedPaths.delete(item.path);
    } else {
      state.selectedPaths.add(item.path);
    }
  });

  renderTable(els, state);
}

async function createCleanupPlan(els, state) {
  if (state.selectedPaths.size === 0) {
    setStatus(els, null, "emptySelection");
    await showAlert(t("scan.alerts.emptySelection"));
    return;
  }

  localStorage.removeItem(LEGACY_PLAN_STORAGE_KEY);
  localStorage.setItem(
    CLEANUP_SELECTION_STORAGE_KEY,
    JSON.stringify([...state.selectedPaths]),
  );
  location.href = "/cleanup";
}

function bindScanEvents(els, state) {
  on(els.backButton, "click", () => {
    if (state.isScanning) return;
    location.href = "/";
  });
  on(els.startScanButton, "click", () => startScan(els, state));
  on(els.clearResultsButton, "click", () => clearResults(els, state));
  on(els.selectAllButton, "click", () => selectAllVisible(els, state));
  on(els.invertSelectionButton, "click", () => invertSelection(els, state));
  on(els.createPlanButton, "click", () => createCleanupPlan(els, state));
  on(els.categoryFilter, "change", () => renderTable(els, state));
  on(els.riskFilter, "change", () => renderTable(els, state));
  on(els.sourceFilter, "change", () => renderTable(els, state));

  on(els.scanResultBody, "change", (event) => {
    const checkbox = event.target;
    if (checkbox.type !== "checkbox") return;

    const path = checkbox.dataset.path;
    if (!path) return;

    if (checkbox.checked) {
      state.selectedPaths.add(path);
    } else {
      state.selectedPaths.delete(path);
    }

    renderSummary(els, state);
    updateControls(els, state);
  });
}

export function initScanPage() {
  const els = getScanElements();
  const state = createScanState();

  ensureDialog();
  translateStaticText();
  bindScanEvents(els, state);
  renderSourceOptions(els, state);
  setStatus(els, null, "idle");
  renderScannerReports(els, []);
  renderTable(els, state);
  markI18nReady();

  return { els, state };
}
