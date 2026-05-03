import { $ } from "../core/dom.js";
import { ensureDialog, showConfirm } from "../core/dialog.js";
import { markI18nReady, translateStaticText } from "../locales/i18n.js";

const PLAN_STORAGE_KEY = "zerotrace.cleanupPlan";
const CLEAN_API = "/cleanup/executePlan";
const SCAN_RESULTS_API = "/cleanup/reloadPlanFromScanResults";

function createCleanupState() {
  return {
    items: [],
    selectedIds: new Set(),
    isExecuting: false,
    filters: {
      category: "",
      risk: "",
      action: "",
    },
  };
}

function getCleanupElements() {
  return {
    reloadPlanButton: $("#reloadPlanButton"),
    backButton: $("#backButton"),
    backScanButton: $("#backScanButton"),
    executePlanButton: $("#executePlanButton"),
    planItemCount: $("#planItemCount"),
    planTotalSize: $("#planTotalSize"),
    planHighRiskCount: $("#planHighRiskCount"),
    planDirCount: $("#planDirCount"),
    planStatus: $("#planStatus"),
    categoryFilter: $("#planCategoryFilter"),
    riskFilter: $("#planRiskFilter"),
    actionFilter: $("#planActionFilter"),
    selectAllButton: $("#selectAllPlanButton"),
    invertButton: $("#invertPlanButton"),
    selectHighRiskButton: $("#selectHighRiskButton"),
    keepRecentFiles: $("#keepRecentFiles"),
    skipSystemDirs: $("#skipSystemDirs"),
    skipTinyFiles: $("#skipTinyFiles"),
    preferDuplicates: $("#preferDuplicates"),
    confirmExecuteCheck: $("#confirmExecuteCheck"),
    planHint: $("#planHint"),
    planTableHint: $("#planTableHint"),
    tableBody: $("#planTableBody"),
  };
}

function bindEvents(els, state) {
  els.backButton?.addEventListener("click", () => {
    location.href = "/";
  });
  els.backScanButton?.addEventListener("click", () => {
    location.href = "/scan";
  });
  els.reloadPlanButton?.addEventListener("click", () => reloadPlanFromScanResults(els, state));
  els.executePlanButton?.addEventListener("click", () => executePlan(els, state));
  els.confirmExecuteCheck?.addEventListener("change", () =>
    updateControls(els, state),
  );

  els.categoryFilter?.addEventListener("change", () => {
    state.filters.category = els.categoryFilter.value;
    render(els, state);
  });

  els.riskFilter?.addEventListener("change", () => {
    state.filters.risk = els.riskFilter.value;
    render(els, state);
  });

  els.actionFilter?.addEventListener("change", () => {
    state.filters.action = els.actionFilter.value;
    render(els, state);
  });

  els.selectAllButton?.addEventListener("click", () => selectAllVisible(els, state));
  els.invertButton?.addEventListener("click", () => invertVisible(els, state));
  els.selectHighRiskButton?.addEventListener("click", () =>
    selectHighRiskVisible(els, state),
  );
  els.tableBody?.addEventListener("change", (event) =>
    handleTableChange(event, els, state),
  );
}

function loadPlan(els, state) {
  const items = readStoredPlan();

  resetPlanState(els, state, items);
  render(els, state);
}

async function reloadPlanFromScanResults(els, state) {
  if (state.isExecuting) return;

  if (els.reloadPlanButton) {
    els.reloadPlanButton.disabled = true;
  }
  setStatus(els, "读取中");
  setHint(els, "正在重新读取扫描结果...");

  try {
    const response = await fetch(SCAN_RESULTS_API, {
      headers: {
        Accept: "application/json",
      },
    });
    if (!response.ok) {
      throw new Error(`Load scan results failed: ${response.status}`);
    }

    const payload = await response.json();
    const items = normalizePlanItems(payload.items || []);
    writeStoredPlan(items);
    resetPlanState(els, state, items);
    render(els, state);
  } catch (error) {
    console.error("[cleanup] reload plan failed:", error);
    setStatus(els, "读取失败");
    setHint(els, "重新读取扫描结果失败。请返回扫描页确认扫描结果后重试。");
    updateControls(els, state);
  }
}

function resetPlanState(els, state, items) {
  resetFilters(els, state);
  resetStrategyOptions(els);

  state.items = items;
  state.selectedIds = new Set(items.map((item) => item.id));
  state.isExecuting = false;

  if (els.confirmExecuteCheck) {
    els.confirmExecuteCheck.checked = false;
  }

  setStatus(els, items.length > 0 ? "待确认" : "无计划");
  setHint(
    els,
    items.length > 0
      ? "请确认计划内容后，再执行清理。"
      : "暂无清理计划。请先从扫描页生成。",
  );
}

function resetFilters(els, state) {
  state.filters = {
    category: "",
    risk: "",
    action: "",
  };

  if (els.categoryFilter) els.categoryFilter.value = "";
  if (els.riskFilter) els.riskFilter.value = "";
  if (els.actionFilter) els.actionFilter.value = "";
}

function resetStrategyOptions(els) {
  [
    els.keepRecentFiles,
    els.skipSystemDirs,
    els.skipTinyFiles,
    els.preferDuplicates,
  ].forEach((checkbox) => {
    if (checkbox) checkbox.checked = true;
  });
}

async function executePlan(els, state) {
  if (!els.confirmExecuteCheck?.checked) {
    setHint(els, "请先勾选确认项。");
    return;
  }

  const selectedItems = getSelectedItems(state);

  if (selectedItems.length === 0) {
    setHint(els, "没有选中的计划项目。");
    return;
  }

  const ok = await showConfirm(
    `确认执行清理？\n\n选中项目：${selectedItems.length}\n操作方式：移入 ZeroTraceRecycle\n\n此操作可在回收区恢复。`,
  );

  if (!ok) return;

  setStatus(els, "执行中");
  setHint(els, "正在执行清理，请稍候...");
  state.isExecuting = true;
  updateControls(els, state);

  try {
    const result = await postJson(
      CLEAN_API,
      selectedItems.map((item) => ({
        path: item.path,
        size: item.size,
        file_type: item.file_type,
        category: item.category,
        source: item.source,
        scanner: item.scanner,
        mtime: item.last_modified ?? item.mtime ?? null,
        risk_level: item.risk,
      })),
    );

    const removedPaths = new Set([
      ...(result.cleaned ?? []).map((record) => record.original_path),
      ...(result.failed ?? [])
        .filter((failure) => failure.removable_from_plan)
        .map((failure) => failure.path),
    ]);

    state.items = state.items.filter((item) => !removedPaths.has(item.path));
    state.selectedIds = new Set(
      [...state.selectedIds].filter((id) => {
        const item = state.items.find((planItem) => planItem.id === id);
        return item && !removedPaths.has(item.path);
      }),
    );
    writeStoredPlan(state.items);

    if (els.confirmExecuteCheck) {
      els.confirmExecuteCheck.checked = false;
    }

    if ((result.failed_count ?? 0) > 0) {
      setStatus(els, "部分完成");
      setHint(
        els,
        `已移动 ${result.cleaned_count ?? 0} 项，${result.failed_count} 项未移动。不存在的临时文件已从计划中移除，被占用的文件请关闭相关程序后重试。`,
      );
    } else {
      setStatus(els, "执行完成");
      setHint(els, "清理完成。项目已移动至回收区。");
    }
    render(els, state);
  } catch (error) {
    console.error("[cleanup] execute failed:", error);
    setStatus(els, "执行失败");
    setHint(els, "执行失败。请确认文件仍存在，或查看日志后重试。");
    render(els, state);
  } finally {
    state.isExecuting = false;
    updateControls(els, state);
  }
}

function handleTableChange(event, els, state) {
  const target = event.target;

  if (!(target instanceof HTMLInputElement)) return;
  if (!target.classList.contains("plan-row-check")) return;

  const id = target.dataset.id;
  if (!id) return;

  if (target.checked) {
    state.selectedIds.add(id);
  } else {
    state.selectedIds.delete(id);
  }

  renderSummary(els, state);
  updateControls(els, state);
}

function render(els, state) {
  renderSummary(els, state);
  renderTable(els, state);
  updateControls(els, state);
}

function renderSummary(els, state) {
  const selectedItems = getSelectedItems(state);
  const highRiskCount = selectedItems.filter((item) => item.risk === "high").length;
  const totalSize = selectedItems.reduce((sum, item) => sum + item.size, 0);
  const dirCount = new Set(selectedItems.map((item) => getDirName(item.path))).size;

  setText(els.planItemCount, String(selectedItems.length));
  setText(els.planTotalSize, formatBytes(totalSize));
  setText(els.planHighRiskCount, String(highRiskCount));
  setText(els.planDirCount, String(dirCount));
}

function renderTable(els, state) {
  const visibleItems = getVisibleItems(state);

  if (!els.tableBody) return;

  if (visibleItems.length === 0) {
    els.tableBody.innerHTML = `
      <tr>
        <td colspan="7" class="empty-cell">暂无符合条件的计划项目</td>
      </tr>
    `;
    setText(
      els.planTableHint,
      "请调整筛选条件，或返回扫描页重新生成清理计划。",
    );
    return;
  }

  els.tableBody.innerHTML = visibleItems.map((item) => renderRow(item, state)).join("");
  setText(
    els.planTableHint,
    `当前显示 ${visibleItems.length} 项，请确认路径、大小、来源与风险后执行。`,
  );
}

function renderRow(item, state) {
  const checked = state.selectedIds.has(item.id) ? "checked" : "";
  const disabled = state.isExecuting ? "disabled" : "";
  const path = escapeHtml(item.path);

  return `
    <tr>
      <td class="col-check">
        <input
          class="plan-row-check"
          type="checkbox"
          data-id="${escapeHtml(item.id)}"
          ${checked}
          ${disabled}
        />
      </td>
      <td class="path-input-cell">
        <input class="path-readonly-input" type="text" value="${path}" title="${path}" readonly />
      </td>
      <td>${formatBytes(item.size)}</td>
      <td>${escapeHtml(toCategoryLabel(item.category))}</td>
      <td>${escapeHtml(toSourceLabel(item.source))}</td>
      <td>${renderRisk(item.risk)}</td>
      <td>${escapeHtml(toActionLabel(item.action))}</td>
    </tr>
  `;
}

function renderRisk(risk) {
  const label = toRiskLabel(risk);
  return `<span class="risk-badge risk-${escapeHtml(risk)}"><span class="risk-dot"></span>${escapeHtml(label)}</span>`;
}

function selectAllVisible(els, state) {
  getVisibleItems(state).forEach((item) => state.selectedIds.add(item.id));
  render(els, state);
}

function invertVisible(els, state) {
  getVisibleItems(state).forEach((item) => {
    if (state.selectedIds.has(item.id)) {
      state.selectedIds.delete(item.id);
    } else {
      state.selectedIds.add(item.id);
    }
  });

  render(els, state);
}

function selectHighRiskVisible(els, state) {
  state.selectedIds.clear();
  getVisibleItems(state)
    .filter((item) => item.risk === "high")
    .forEach((item) => state.selectedIds.add(item.id));
  render(els, state);
}

function getVisibleItems(state) {
  return state.items.filter((item) => {
    if (state.filters.category && item.category !== state.filters.category) return false;
    if (state.filters.risk && item.risk !== state.filters.risk) return false;
    if (state.filters.action && item.action !== state.filters.action) return false;
    return true;
  });
}

function getSelectedItems(state) {
  return state.items.filter((item) => state.selectedIds.has(item.id));
}

function readStoredPlan() {
  try {
    return normalizePlanItems(JSON.parse(localStorage.getItem(PLAN_STORAGE_KEY) || "[]"));
  } catch (error) {
    console.warn("[cleanup] invalid stored plan:", error);
    return [];
  }
}

function writeStoredPlan(items) {
  localStorage.setItem(PLAN_STORAGE_KEY, JSON.stringify(items));
}

function normalizePlanItems(rawItems) {
  if (!Array.isArray(rawItems)) return [];

  return rawItems.map((item, index) => {
    const path = String(item.path ?? item.file_path ?? "");
    const id = String(item.id ?? item.path ?? `plan-item-${index}`);

    return {
      id,
      path,
      size: Number(item.size ?? item.size_bytes ?? 0),
      file_type: normalizeFileType(item.file_type),
      category: normalizeCategory(item.category),
      source: normalizeSource(item.source),
      risk: normalizeRisk(item.risk ?? item.risk_level),
      scanner: normalizeScanner(item.scanner),
      action: normalizeAction(item.action),
      last_modified: item.last_modified ?? item.mtime ?? null,
    };
  });
}

async function postJson(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    throw new Error(`POST ${url} failed: ${response.status}`);
  }

  return response.json();
}

function updateControls(els, state) {
  const hasPlan = state.items.length > 0;
  const visibleItems = getVisibleItems(state);
  const hasVisibleItems = visibleItems.length > 0;
  const hasVisibleHighRisk = visibleItems.some((item) => item.risk === "high");
  const hasSelection = state.selectedIds.size > 0;
  const canExecute =
    hasPlan &&
    hasSelection &&
    Boolean(els.confirmExecuteCheck?.checked) &&
    !state.isExecuting;

  if (els.confirmExecuteCheck && (!hasPlan || !hasSelection)) {
    els.confirmExecuteCheck.checked = false;
  }

  if (els.backButton) els.backButton.disabled = state.isExecuting;
  if (els.backScanButton) els.backScanButton.disabled = state.isExecuting;
  if (els.reloadPlanButton) els.reloadPlanButton.disabled = state.isExecuting;
  if (els.executePlanButton) els.executePlanButton.disabled = !canExecute;

  if (els.categoryFilter) els.categoryFilter.disabled = state.isExecuting || !hasPlan;
  if (els.riskFilter) els.riskFilter.disabled = state.isExecuting || !hasPlan;
  if (els.actionFilter) els.actionFilter.disabled = state.isExecuting || !hasPlan;

  if (els.selectAllButton) els.selectAllButton.disabled = state.isExecuting || !hasVisibleItems;
  if (els.invertButton) els.invertButton.disabled = state.isExecuting || !hasVisibleItems;
  if (els.selectHighRiskButton) {
    els.selectHighRiskButton.disabled = state.isExecuting || !hasVisibleHighRisk;
  }

  if (els.confirmExecuteCheck) {
    els.confirmExecuteCheck.disabled = state.isExecuting || !hasPlan || !hasSelection;
  }

  [
    els.keepRecentFiles,
    els.skipSystemDirs,
    els.skipTinyFiles,
    els.preferDuplicates,
  ].forEach((checkbox) => {
    if (checkbox) checkbox.disabled = state.isExecuting || !hasPlan;
  });

  els.tableBody
    ?.querySelectorAll(".plan-row-check")
    .forEach((checkbox) => {
      checkbox.disabled = state.isExecuting;
    });
}

function setStatus(els, text) {
  setText(els.planStatus, text);
}

function setHint(els, text) {
  setText(els.planHint, text);
}

function setText(element, value) {
  if (!element) return;
  element.textContent = value ?? "";
}

function getDirName(path) {
  const normalized = String(path).replaceAll("\\", "/");
  const index = normalized.lastIndexOf("/");
  return index >= 0 ? normalized.slice(0, index) : "";
}

function normalizeCategory(value) {
  const v = String(value ?? "").toLowerCase();

  if (["temp", "cache", "browser_cache", "log", "duplicate", "empty"].includes(v)) {
    return v === "browser_cache" ? "cache" : v;
  }
  if (v.includes("duplicate") || v.includes("重复")) return "duplicate";
  if (v.includes("cache") || v.includes("缓存")) return "cache";
  if (v.includes("log") || v.includes("日志")) return "log";
  if (v.includes("empty") || v.includes("空")) return "empty";
  return "temp";
}

function normalizeRisk(value) {
  const v = String(value ?? "").toLowerCase();

  if (["low", "medium", "high"].includes(v)) return v;
  if (v.includes("高")) return "high";
  if (v.includes("中")) return "medium";
  return "low";
}

function normalizeSource(value) {
  return String(value ?? "scan") || "scan";
}

function normalizeFileType(value) {
  const v = String(value ?? "file").toLowerCase();
  return v === "folder" ? "folder" : "file";
}

function normalizeScanner(value) {
  return String(value ?? "UnknownScanner") || "UnknownScanner";
}

function normalizeAction(value) {
  const v = String(value ?? "").toLowerCase();

  if (["recycle", "ignore"].includes(v)) return v;
  if (v.includes("ignore") || v.includes("忽略")) return "ignore";
  return "recycle";
}

function toCategoryLabel(value) {
  return (
    {
      temp: "临时文件",
      cache: "缓存",
      log: "日志",
      duplicate: "重复文件",
      empty: "空文件",
    }[value] ?? "其他"
  );
}

function toRiskLabel(value) {
  return (
    {
      low: "低",
      medium: "中",
      high: "高",
    }[value] ?? "低"
  );
}

function toSourceLabel(value) {
  return value || "扫描结果";
}

function toActionLabel(value) {
  return (
    {
      recycle: "移入回收区",
      ignore: "忽略",
    }[value] ?? "移入回收区"
  );
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

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

export function initCleanupPage() {
  const els = getCleanupElements();
  const state = createCleanupState();

  ensureDialog();
  translateStaticText();
  bindEvents(els, state);
  loadPlan(els, state);
  markI18nReady();

  return { els, state };
}
