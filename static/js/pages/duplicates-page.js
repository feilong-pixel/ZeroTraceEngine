import { $, on, setText } from "../core/dom.js";
import { ensureDialog, showAlert } from "../core/dialog.js";
import { formatDisplayTime } from "../core/format.js";
import { markI18nReady, t, translateStaticText } from "../locales/i18n.js";

const CLEANUP_SELECTION_STORAGE_KEY = "zerotrace.cleanupSelection";
const LEGACY_PLAN_STORAGE_KEY = "zerotrace.cleanupPlan";

function createState() {
  return {
    roots: [],
    groups: [],
    selectedPaths: new Set(),
    isScanning: false,
    rootScanStatus: "pending",
    scannedFiles: 0,
    candidateFiles: 0,
  };
}

function getElements() {
  return {
    backButton: $("#backButton"),
    startButton: $("#startDuplicateScanButton"),
    pathInput: $("#duplicatePathInput"),
    addRootButton: $("#addDuplicateRootButton"),
    inputStatus: $("#duplicateInputStatus"),
    rootBody: $("#duplicateRootBody"),
    groupCount: $("#duplicateGroupCount"),
    fileCount: $("#duplicateFileCount"),
    totalSize: $("#duplicateTotalSize"),
    selectedCount: $("#duplicateSelectedCount"),
    selectedSize: $("#duplicateSelectedSize"),
    scannedFiles: $("#duplicateScannedFiles"),
    candidateFiles: $("#duplicateCandidateFiles"),
    scanSpeed: $("#duplicateScanSpeed"),
    remainingTime: $("#duplicateRemainingTime"),
    status: $("#duplicateScanStatus"),
    lifecycleState: $("#duplicateLifecycleState"),
    lifecycleStage: $("#duplicateLifecycleStage"),
    currentFile: $("#duplicateCurrentFile"),
    copyCurrentFileButton: $("#copyDuplicateCurrentFileButton"),
    progressBar: $("#duplicateProgressBar"),
    stages: [...document.querySelectorAll(".duplicate-stage")],
    categoryFilter: $("#duplicateCategoryFilter"),
    sizeFilter: $("#duplicateSizeFilter"),
    riskFilter: $("#duplicateRiskFilter"),
    searchInput: $("#duplicateSearchInput"),
    sortSelect: $("#duplicateSortSelect"),
    selectAllButton: $("#selectAllDuplicatesButton"),
    clearSelectionButton: $("#clearDuplicateSelectionButton"),
    strategyOptions: [...document.querySelectorAll('input[name="duplicateSelectionStrategy"]')],
    clearButton: $("#clearDuplicateResultsButton"),
    createPlanButton: $("#createDuplicatePlanButton"),
    groupList: $("#duplicateGroupList"),
  };
}

function formatBytes(bytes) {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
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

function setStatus(els, tone, text) {
  const label = text || {
    idle: t("duplicates.status.idle"),
    running: t("duplicates.status.running"),
    success: t("duplicates.status.success"),
    error: t("duplicates.status.error"),
  }[tone] || tone;
  setText(els.status, label);
  setText(els.lifecycleState, label);
  if (els.status) els.status.className = `status-value status-${tone}`;
  if (els.lifecycleState) els.lifecycleState.className = `status-value status-${tone}`;
  updateStages(els, tone);
}

function updateStages(els, tone) {
  const activeByTone = { idle: 0, running: 1, success: 4, error: 0 };
  const activeCount = activeByTone[tone] ?? 0;
  const stageIndex = tone === "success" ? 3 : activeCount;
  const stageNames = [
    t("duplicates.stages.size"),
    t("duplicates.stages.quick"),
    t("duplicates.stages.full"),
    t("duplicates.stages.groups"),
  ];
  els.stages?.forEach((stage, index) => {
    stage.classList.toggle("is-active", index < activeCount || (tone === "idle" && index === 0));
    stage.classList.toggle("is-current", tone === "running" && index === activeCount);
  });
  setText(els.lifecycleStage, t("duplicates.lifecycle.stageValue", stageNames[stageIndex] || "-", stageIndex + 1, stageNames.length));
  if (els.progressBar) {
    const percent = { idle: 0, running: 55, success: 100, error: 0 }[tone] ?? 0;
    els.progressBar.style.width = `${percent}%`;
  }
}

function getVisibleGroups(els, state) {
  const category = els.categoryFilter?.value || "";
  const minSize = Number(els.sizeFilter?.value || 0);
  const risk = els.riskFilter?.value || "";
  const search = (els.searchInput?.value || "").trim().toLowerCase();
  const sort = els.sortSelect?.value || "reclaimable";

  const groups = state.groups
    .map((group) => {
      const files = group.files.filter((file) => {
        if (category && file.category !== category) return false;
        if (minSize && Number(file.size || 0) <= minSize) return false;
        if (risk && file.risk_level !== risk) return false;
        return true;
      });
      const searchMatched = !search || files.some((file) => {
        return `${file.path} ${file.source || ""}`.toLowerCase().includes(search);
      });
      return searchMatched ? { ...group, files } : { ...group, files: [] };
    })
    .filter((group) => group.files.length > 1);

  const riskScore = (group) => (group.files || []).reduce((sum, file) => {
    return sum + ({ high: 3, medium: 2, low: 1 }[file.risk_level] || 1);
  }, 0);
  groups.sort((a, b) => {
    if (sort === "risk") return riskScore(b) - riskScore(a);
    if (sort === "time") return Math.max(...b.files.map((file) => new Date(file.mtime || 0).getTime())) - Math.max(...a.files.map((file) => new Date(file.mtime || 0).getTime()));
    if (sort === "path") return String(a.files[0]?.path || "").localeCompare(String(b.files[0]?.path || ""));
    return Number(b.reclaimable_size || 0) - Number(a.reclaimable_size || 0);
  });
  return groups;
}

function getVisibleFiles(els, state) {
  return getVisibleGroups(els, state).flatMap((group) => group.files);
}

function renderRoots(els, state) {
  if (!els.rootBody) return;
  if (state.roots.length === 0) {
    els.rootBody.innerHTML = `
      <tr class="empty-row">
        <td colspan="3">${t("duplicates.noRoots")}</td>
      </tr>
    `;
    return;
  }

  const statusLabel = getRootStatusLabel(state);
  els.rootBody.innerHTML = state.roots
    .map((root, index) => `
      <tr>
        <td class="path-input-cell col-path">
          <input class="path-readonly-input" type="text" value="${escapeHtml(root)}" title="${escapeHtml(root)}" readonly />
        </td>
        <td class="col-status">${statusLabel}</td>
        <td class="col-action">
          <button class="ghost-button" data-remove-root="${index}" ${state.isScanning ? "disabled" : ""}>${t("duplicates.removeRoot")}</button>
        </td>
      </tr>
    `)
    .join("");
}

function getRootStatusLabel(state) {
  if (state.isScanning) return t("duplicates.rootStatus.running");
  return t(`duplicates.rootStatus.${state.rootScanStatus || "pending"}`);
}

function renderSummary(els, state) {
  const visibleGroups = getVisibleGroups(els, state);
  const visibleFiles = visibleGroups.flatMap((group) => group.files);
  const reclaimable = visibleGroups.reduce((sum, group) => {
    return sum + Number(group.size || 0) * Math.max(group.files.length - 1, 0);
  }, 0);

  setText(els.groupCount, visibleGroups.length);
  setText(els.fileCount, visibleFiles.length);
  setText(els.totalSize, formatBytes(reclaimable));
  setText(els.selectedCount, state.selectedPaths.size);
  setText(els.selectedSize, formatBytes(getSelectedFiles(state).reduce((sum, file) => sum + Number(file.size || 0), 0)));
  setText(els.scannedFiles, state.scannedFiles);
  setText(els.candidateFiles, state.candidateFiles);
  setCurrentFile(els, state);
  setText(els.scanSpeed, state.scannedFiles ? "-" : "-");
  setText(els.remainingTime, state.scannedFiles ? "0s" : "-");
}

function getSelectedFiles(state) {
  const selected = state.selectedPaths;
  return state.groups.flatMap((group) => group.files).filter((file) => selected.has(file.path));
}

function setCurrentFile(els, state) {
  const fileName = getCurrentFileName(state);
  setText(els.currentFile, fileName);
  if (els.currentFile) els.currentFile.title = fileName;
  if (els.copyCurrentFileButton) {
    els.copyCurrentFileButton.dataset.fileName = fileName === "-" ? "" : fileName;
    els.copyCurrentFileButton.disabled = !els.copyCurrentFileButton.dataset.fileName;
    setText(els.copyCurrentFileButton, t("duplicates.copyShort"));
  }
}

function getCurrentFileName(state) {
  const firstPath = state.groups[0]?.files?.[0]?.path;
  if (!firstPath) return "-";
  return firstPath.split(/[\\/]/).pop() || firstPath;
}

function countRiskLevels(files) {
  return files.reduce((counts, file) => {
    const risk = file.risk_level || "low";
    counts[risk] = (counts[risk] || 0) + 1;
    return counts;
  }, { low: 0, medium: 0, high: 0 });
}

function renderGroups(els, state) {
  if (!els.groupList) return;
  const groups = getVisibleGroups(els, state);

  if (groups.length === 0) {
    els.groupList.innerHTML = `<p class="muted">${t("duplicates.noResults")}</p>`;
    renderSummary(els, state);
    updateControls(els, state);
    return;
  }

  els.groupList.innerHTML = groups.map((group, groupIndex) => {
    const files = group.files.slice(0, 50);
    const hiddenCount = Math.max(group.files.length - files.length, 0);
    const rows = files.map((file) => {
      const checked = state.selectedPaths.has(file.path) ? "checked" : "";
      const risk = file.risk_level || "low";
      const isRecommended = file.path === group.recommended_keep_path;
      const riskLabel = {
        low: t("common.risks.low"),
        medium: t("common.risks.medium"),
        high: t("common.risks.high"),
      }[risk] || risk;
      const riskReasons = (file.risk_reasons || []).map((reason) => t(`duplicates.riskReasons.${reason}`)).join(" · ");

      return `
        <tr>
          <td class="col-check"><input type="checkbox" data-path="${escapeHtml(file.path)}" ${checked} ${state.isScanning ? "disabled" : ""} /></td>
          <td class="path-input-cell"><input class="path-readonly-input" type="text" value="${escapeHtml(file.path)}" title="${escapeHtml(file.path)}" readonly /></td>
          <td>${formatBytes(file.size)}</td>
          <td>${escapeHtml(formatDisplayTime(file.mtime))}</td>
          <td class="path-input-cell">
            <input class="source-readonly-input" type="text" value="${escapeHtml(file.source || "-")}" title="${escapeHtml(file.source || "-")}" readonly />
            ${isRecommended ? `<span class="keep-pill">${t("duplicates.recommendedKeep")}</span>` : ""}
          </td>
          <td><span class="risk-badge risk-${escapeHtml(risk)}" title="${escapeHtml(riskReasons)}"><span class="risk-dot"></span>${escapeHtml(riskLabel)}</span></td>
        </tr>
      `;
    }).join("");
    const riskCounts = countRiskLevels(group.files);
    const keepReasons = (group.recommended_keep_reason || []).map((reason) => t(`duplicates.keepReasons.${reason}`)).join(" · ");

    return `
      <details class="duplicate-group" open>
        <summary>
          <div>
            <strong>${escapeHtml(group.display_name || t("duplicates.groupFallback", groupIndex + 1))}</strong>
            <span>${t("duplicates.groupReadable", group.files.length, formatBytes(group.reclaimable_size || 0))}</span>
          </div>
          <span class="duplicate-risk-heatmap">
            <b class="risk-high">${riskCounts.high || 0}</b>
            <b class="risk-medium">${riskCounts.medium || 0}</b>
            <b class="risk-low">${riskCounts.low || 0}</b>
          </span>
        </summary>
        <div class="duplicate-group-meta">
          <span>${t("duplicates.recommendedKeepPath")}: ${escapeHtml(group.recommended_keep_path || "-")}</span>
          <span>${t("duplicates.keepReason")}: ${escapeHtml(keepReasons || "-")}</span>
          <span>${t("duplicates.hashLabel", String(group.hash || "").slice(0, 16))}</span>
        </div>
        <div class="scan-table-wrap">
          <table class="scan-table duplicate-file-table">
            <thead>
              <tr>
                <th class="col-check"></th>
                <th class="col-path">${t("common.labels.path")}</th>
                <th class="col-size">${t("common.labels.size")}</th>
                <th class="col-time">${t("common.labels.time")}</th>
                <th class="col-source">${t("common.labels.source")}</th>
                <th class="col-risk">${t("common.labels.risk")}</th>
              </tr>
            </thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
        ${hiddenCount ? `<p class="muted">${t("duplicates.groupLimit", hiddenCount)}</p>` : ""}
      </details>
    `;
  }).join("");

  renderSummary(els, state);
  updateControls(els, state);
}

function updateControls(els, state) {
  const hasRoots = state.roots.length > 0;
  const hasResults = state.groups.length > 0;
  const hasVisible = getVisibleFiles(els, state).length > 0;
  const hasSelection = state.selectedPaths.size > 0;

  if (els.backButton) els.backButton.disabled = state.isScanning;
  if (els.pathInput) els.pathInput.disabled = state.isScanning;
  if (els.addRootButton) els.addRootButton.disabled = state.isScanning;
  if (els.startButton) els.startButton.disabled = state.isScanning || !hasRoots;
  if (els.clearButton) els.clearButton.disabled = state.isScanning || !hasResults;
  if (els.selectAllButton) els.selectAllButton.disabled = state.isScanning || !hasVisible;
  if (els.clearSelectionButton) els.clearSelectionButton.disabled = state.isScanning || !hasSelection;
  els.strategyOptions?.forEach((option) => {
    option.disabled = state.isScanning || !hasVisible;
  });
  if (els.createPlanButton) els.createPlanButton.disabled = state.isScanning || !hasSelection;
}

async function loadSavedRoots(state) {
  try {
    const res = await fetch("/duplicates/roots", { headers: { Accept: "application/json" } });
    const payload = await res.json();
    if (!res.ok) throw new Error(payload.detail || `Load roots failed: ${res.status}`);
    state.roots = Array.isArray(payload.roots) ? payload.roots : [];
  } catch (error) {
    console.warn("Failed to load duplicate roots", error);
  }
}

async function saveRoots(state) {
  try {
    const res = await fetch("/duplicates/roots", {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ roots: state.roots }),
    });
    if (!res.ok) {
      const payload = await res.json();
      throw new Error(payload.detail || `Save roots failed: ${res.status}`);
    }
  } catch (error) {
    console.warn("Failed to save duplicate roots", error);
  }
}

async function loadSavedResults(els, state) {
  try {
    const res = await fetch("/duplicates/results", { headers: { Accept: "application/json" } });
    const payload = await res.json();
    if (!res.ok) throw new Error(payload.detail || `Load duplicate results failed: ${res.status}`);
    state.groups = payload.groups || [];
    state.scannedFiles = payload.scanned_files || 0;
    state.candidateFiles = payload.candidate_files || 0;
    state.rootScanStatus = state.groups.length > 0 ? "success" : "pending";
    setStatus(els, state.groups.length > 0 ? "success" : "idle");
  } catch (error) {
    console.warn("Failed to load duplicate results", error);
    state.rootScanStatus = "pending";
    setStatus(els, "idle");
  }
}

async function clearSavedResults() {
  const res = await fetch("/duplicates/results/clear", {
    method: "POST",
    headers: { Accept: "application/json" },
  });
  if (!res.ok) {
    const payload = await res.json();
    throw new Error(payload.detail || `Clear duplicate results failed: ${res.status}`);
  }
}

function addRoot(els, state) {
  const value = els.pathInput?.value.trim();
  if (!value) {
    setText(els.inputStatus, t("duplicates.alerts.emptyRoot"));
    return;
  }
  if (!state.roots.includes(value)) {
    state.roots.push(value);
    state.rootScanStatus = "pending";
    void saveRoots(state);
  }
  if (els.pathInput) els.pathInput.value = "";
  setText(els.inputStatus, "");
  renderRoots(els, state);
  updateControls(els, state);
}

async function startScan(els, state) {
  state.isScanning = true;
  state.rootScanStatus = "running";
  state.groups = [];
  state.scannedFiles = 0;
  state.candidateFiles = 0;
  state.selectedPaths.clear();
  setStatus(els, "running");
  renderRoots(els, state);
  renderGroups(els, state);
  updateControls(els, state);

  try {
    const res = await fetch("/duplicates/scan", {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ roots: state.roots }),
    });
    const payload = await res.json();
    if (!res.ok) throw new Error(payload.detail || `Duplicate scan failed: ${res.status}`);

    state.groups = payload.groups || [];
    state.scannedFiles = payload.scanned_files || 0;
    state.candidateFiles = payload.candidate_files || 0;
    state.rootScanStatus = "success";
    setStatus(els, "success");
  } catch (error) {
    console.error(error);
    state.rootScanStatus = "error";
    setStatus(els, "error");
    await showAlert(error.message || t("duplicates.alerts.scanFailed"));
  } finally {
    state.isScanning = false;
    renderRoots(els, state);
    renderGroups(els, state);
    updateControls(els, state);
  }
}

function replaceSelection(els, state, paths) {
  state.selectedPaths.clear();
  paths.forEach((path) => state.selectedPaths.add(path));
  renderGroups(els, state);
}

function applySelectionStrategy(els, state) {
  const strategy = els.strategyOptions.find((option) => option.checked)?.value || "smart";
  if (strategy === "highRisk") {
    replaceSelection(
      els,
      state,
      getVisibleFiles(els, state).filter((file) => file.risk_level === "high").map((file) => file.path),
    );
    return;
  }
  autoSelect(els, state, strategy);
}

function clearSelection(els, state) {
  state.selectedPaths.clear();
  renderGroups(els, state);
}

function autoSelect(els, state, mode) {
  state.selectedPaths.clear();
  getVisibleGroups(els, state).forEach((group) => {
    if (mode === "smart" && group.recommended_keep_path) {
      group.files
        .filter((file) => file.path !== group.recommended_keep_path)
        .forEach((file) => state.selectedPaths.add(file.path));
      return;
    }
    const files = [...group.files].sort((a, b) => {
      const left = new Date(a.mtime || 0).getTime();
      const right = new Date(b.mtime || 0).getTime();
      return mode === "oldest" ? left - right : right - left;
    });
    files.slice(1).forEach((file) => state.selectedPaths.add(file.path));
  });
  renderGroups(els, state);
}

async function createPlan(els, state) {
  if (state.selectedPaths.size === 0) {
    await showAlert(t("duplicates.alerts.emptySelection"));
    return;
  }

  const paths = [...state.selectedPaths];
  const res = await fetch("/duplicates/createPlan", {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ paths }),
  });
  const payload = await res.json();
  if (!res.ok) {
    await showAlert(payload.detail || t("duplicates.alerts.planFailed"));
    return;
  }

  localStorage.removeItem(LEGACY_PLAN_STORAGE_KEY);
  localStorage.setItem(CLEANUP_SELECTION_STORAGE_KEY, JSON.stringify(payload.paths || paths));
  location.href = "/cleanup";
}

async function copyCurrentFileName(els) {
  const fileName = els.copyCurrentFileButton?.dataset.fileName || "";
  if (!fileName) return;
  try {
    await navigator.clipboard.writeText(fileName);
    setText(els.copyCurrentFileButton, t("duplicates.copiedShort"));
    window.setTimeout(() => setText(els.copyCurrentFileButton, t("duplicates.copyShort")), 900);
  } catch (error) {
    console.error(error);
    await showAlert(t("duplicates.alerts.copyFailed"));
  }
}

function bindEvents(els, state) {
  on(els.backButton, "click", () => {
    if (!state.isScanning) location.href = "/";
  });
  on(els.addRootButton, "click", () => addRoot(els, state));
  on(els.pathInput, "keydown", (event) => {
    if (event.key === "Enter") addRoot(els, state);
  });
  on(els.startButton, "click", () => startScan(els, state));
  on(els.clearButton, "click", async () => {
    try {
      await clearSavedResults();
    } catch (error) {
      console.warn("Failed to clear duplicate results", error);
    }
    state.groups = [];
    state.rootScanStatus = "pending";
    state.scannedFiles = 0;
    state.candidateFiles = 0;
    state.selectedPaths.clear();
    setStatus(els, "idle");
    renderGroups(els, state);
  });
  on(els.selectAllButton, "click", () => applySelectionStrategy(els, state));
  on(els.clearSelectionButton, "click", () => clearSelection(els, state));
  on(els.copyCurrentFileButton, "click", () => copyCurrentFileName(els));
  on(els.createPlanButton, "click", () => createPlan(els, state));
  on(els.categoryFilter, "change", () => renderGroups(els, state));
  on(els.sizeFilter, "change", () => renderGroups(els, state));
  on(els.riskFilter, "change", () => renderGroups(els, state));
  on(els.searchInput, "input", () => renderGroups(els, state));
  on(els.sortSelect, "change", () => renderGroups(els, state));
  on(els.rootBody, "click", (event) => {
    const button = event.target.closest("[data-remove-root]");
    if (!button || state.isScanning) return;
    state.roots.splice(Number(button.dataset.removeRoot), 1);
    state.rootScanStatus = "pending";
    void saveRoots(state);
    renderRoots(els, state);
    updateControls(els, state);
  });
  on(els.groupList, "change", (event) => {
    const checkbox = event.target;
    if (checkbox.type !== "checkbox") return;
    if (checkbox.checked) {
      state.selectedPaths.add(checkbox.dataset.path);
    } else {
      state.selectedPaths.delete(checkbox.dataset.path);
    }
    renderSummary(els, state);
    updateControls(els, state);
  });
}

export async function initDuplicatesPage() {
  const els = getElements();
  const state = createState();

  ensureDialog();
  translateStaticText();
  await loadSavedRoots(state);
  await loadSavedResults(els, state);
  bindEvents(els, state);
  renderRoots(els, state);
  renderGroups(els, state);
  markI18nReady();
}
