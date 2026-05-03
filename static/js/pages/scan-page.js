import { $, on, setText } from "../core/dom.js";
import { ensureDialog, showAlert, showConfirm } from "../core/dialog.js";
import { formatDisplayTime } from "../core/format.js";
import { markI18nReady, translateStaticText } from "../locales/i18n.js";

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
  return `${(milliseconds / 1000).toFixed(2)} 秒`;
}

function setStatus(els, status, tone = "idle") {
  const statusText =
    {
      idle: "待扫描",
      running: "扫描中",
      success: "扫描完成 ✓",
      error: "扫描失败 ✗",
      emptySelection: "未选择项目",
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
    '<option value="">全部</option>',
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
        <td colspan="7">暂无扫描结果</td>
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
          low: "低",
          medium: "中",
          high: "高",
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
    return "空文件夹";
  if (item.category === "empty") return "空文件";
  if (item.category === "temp") return "临时文件";
  return item.category || "-";
}

async function startScan(els, state) {
  const startedAt = performance.now();
  state.isScanning = true;
  state.selectedPaths.clear();
  setStatus(els, null, "running");
  setText(els.scanDuration, "计时中");
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
    "确认清空当前扫描结果？\n\n此操作会清空页面结果，并清空 scan_results 表。",
    {
      title: "确认清空",
      confirmText: "清空",
      cancelText: "取消",
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
    renderSourceOptions(els, state);
    setStatus(els, null, "idle");
    setText(els.scanDuration, "-");
    renderTable(els, state);
  } catch (error) {
    console.error(error);
    setStatus(els, "清空失败", "error");
    updateControls(els, state);
    await showAlert("清空扫描结果失败。请稍后重试。");
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
  const selected = state.items.filter((item) =>
    state.selectedPaths.has(item.path),
  );

  if (selected.length === 0) {
    setStatus(els, null, "emptySelection");
    await showAlert("请先选择要加入清理计划的项目。");
    return;
  }

  const serialized = JSON.stringify(selected);
  if (serialized.length > 4 * 1024 * 1024) {
    // 4MB 警戒线
    await showAlert("选择项目过多，请减少选择数量后再试。");
    return;
  }

  localStorage.setItem("zerotrace.cleanupPlan", serialized);
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
  renderTable(els, state);
  markI18nReady();

  return { els, state };
}
