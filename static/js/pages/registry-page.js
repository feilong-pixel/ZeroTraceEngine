import { $, on, setText } from "../core/dom.js";
import { ensureDialog, showAlert, showConfirm } from "../core/dialog.js";
import { markI18nReady, t, translateStaticText } from "../locales/i18n.js";

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
function createState() {
  return {
    status: "idle",       // idle | scanning | completed | noIssues | error
    issues: [],           // RegistryIssueItem[]
    reports: [],
    plans: [],
    stats: null,
    filters: {
      category: "",
      risk: "",
      source: "",
      hive: "",
      confidence: "",
      validation: "",
      layer: "all",
      search: "",
    },
    selectedIds: new Set(),
    pendingPlanId: null,  // plan_id after generate, before execute
    pendingReviewActionIds: [],
    capabilities: { is_admin: false, admin_required_hives: ["HKCR", "HKCC", "HKLM", "HKU"] },
  };
}

// ---------------------------------------------------------------------------
// DOM helpers
// ---------------------------------------------------------------------------
function getEls() {
  return {
    backButton:        $("#registryBackButton"),
    startButton:       $("#registryStartButton"),
    clearButton:       $("#registryClearButton"),
    scopeSelect:       $("#registryScopeSelect"),
    modeSelect:        $("#registryModeSelect"),
    statusText:        $("#registryScanStatusText"),
    scanProgress:      $("#registryScanProgress"),
    progressBar:       $("#registryProgressBar"),
    phaseCollect:      $("#phaseCollect"),
    phaseResolve:      $("#phaseResolve"),
    phaseRules:        $("#phaseRules"),
    phaseRisk:         $("#phaseRisk"),
    emptyState:        $("#registryEmptyState"),
    noIssues:          $("#registryNoIssues"),
    errorState:        $("#registryErrorState"),
    errorMessage:      $("#registryErrorMessage"),
    retryButton:       $("#registryRetryButton"),
    rescanButton:      $("#registryRescanButton"),
    resultsSection:    $("#registryResultsSection"),
    diagnosticsSection:$("#registryDiagnosticsSection"),
    diagnosticsList:   $("#registryDiagnosticsList"),
    planHistorySection:$("#registryPlanHistorySection"),
    planHistoryList:   $("#registryPlanHistoryList"),
    statTotal:         $("#registryStatTotal"),
    statSafe:          $("#registryStatSafe"),
    statMedium:        $("#registryStatMedium"),
    statHigh:          $("#registryStatHigh"),
    statSelected:      $("#registryStatSelected"),
    categoryFilter:    $("#registryCategoryFilter"),
    riskFilter:        $("#registryRiskFilter"),
    sourceFilter:      $("#registrySourceFilter"),
    hiveFilter:        $("#registryHiveFilter"),
    confidenceFilter:  $("#registryConfidenceFilter"),
    validationFilter:  $("#registryValidationFilter"),
    searchInput:       $("#registrySearchInput"),
    layerTabs:         [...document.querySelectorAll(".registry-layer-tab")],
    groupList:         $("#registryGroupList"),
    actionBar:         $("#registryActionBar"),
    autoSelectSafe:    $("#autoSelectSafe"),
    autoSelectAll:     $("#autoSelectAll"),
    selectNone:        $("#selectNone"),
    generatePlanButton:$("#registryGeneratePlanButton"),
    planDialog:        $("#registryPlanDialog"),
    planPreview:       $("#registryPlanPreview"),
    planCancel:        $("#planDialogCancel"),
    planSave:          $("#planDialogSave"),
    planExecute:       $("#planDialogExecute"),
    planDetailDialog:  $("#registryPlanDetailDialog"),
    planDetailContent: $("#registryPlanDetailContent"),
    planDetailClose:   $("#registryPlanDetailClose"),
  };
}

// ---------------------------------------------------------------------------
// i18n helpers
// ---------------------------------------------------------------------------
function trRisk(risk) {
  const map = { Safe: t("registry.risks.safe"), Medium: t("registry.risks.medium"), High: t("registry.risks.high") };
  return map[risk] || risk;
}

function trCategory(cat) {
  const map = {
    InvalidPath:      t("registry.categories.invalidPath"),
    OrphanCOM:        t("registry.categories.orphanCom"),
    InvalidUninstall: t("registry.categories.invalidUninstall"),
    InvalidService:   t("registry.categories.invalidService"),
    StartupIssue:     t("registry.categories.startupIssue"),
    FileAssociation:  t("registry.categories.fileAssociation"),
  };
  return map[cat] || cat;
}

function trSource(src) {
  const map = {
    Startup:         t("registry.sources.startup"),
    StartupApproved: t("registry.sources.startupApproved"),
    Uninstall:       t("registry.sources.uninstall"),
    AppPaths:        t("registry.sources.appPaths"),
    COM:             t("registry.sources.com"),
    Service:         t("registry.sources.service"),
    FileAssociation: t("registry.sources.fileAssociation"),
    ScheduledTask:   t("registry.sources.scheduledTask"),
  };
  return map[src] || src;
}

function trConfidence(confidence) {
  const map = {
    High: t("registry.confidence.high"),
    Medium: t("registry.confidence.medium"),
    Low: t("registry.confidence.low"),
  };
  return map[confidence] || confidence;
}

function trValidationStatus(status) {
  const map = {
    path_missing: t("registry.validation.pathMissing"),
    command_missing: t("registry.validation.commandMissing"),
    missing_target: t("registry.validation.missingTarget"),
    no_target: t("registry.validation.noTarget"),
    unverifiable_path: t("registry.validation.unverifiablePath"),
  };
  return map[status] || status;
}

function trSkipReason(reason) {
  const map = {
    low_confidence: t("registry.review.lowConfidence"),
    manual_review_required: t("registry.review.manualRequired"),
    machine_hive_requires_admin: t("registry.review.adminRequired"),
    diagnostic_only: t("registry.review.diagnosticOnly"),
  };
  return map[reason] || reason;
}

function trDiagnosticAdvice(item) {
  if (item.skip_reason === "diagnostic_only") {
    return t("registry.advice.diagnosticOnly");
  }
  if (item.skip_reason === "machine_hive_requires_admin") {
    return t("registry.advice.adminRequired");
  }
  if (item.rule_id === "file_assoc_missing_open_command") {
    return t("registry.advice.fileAssociation");
  }
  if (item.rule_id === "com_typelib_missing_file" || item.rule_id === "com_treat_as_missing_clsid") {
    return t("registry.advice.comDiagnostic");
  }
  if (item.confidence === "Low") {
    return t("registry.advice.lowConfidence");
  }
  return t("registry.advice.manualReview");
}

function trPlanStatus(status) {
  const map = {
    pending: t("registry.history.statusPending"),
    executed: t("registry.history.statusExecuted"),
    restored: t("registry.history.statusRestored"),
  };
  return map[status] || status;
}

function escHtml(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// ---------------------------------------------------------------------------
// UI state transitions
// ---------------------------------------------------------------------------
function setStatus(state, els, newStatus, message) {
  state.status = newStatus;
  els.emptyState.classList.toggle("is-hidden", newStatus !== "idle");
  els.noIssues.classList.toggle("is-hidden", newStatus !== "noIssues");
  els.errorState.classList.toggle("is-hidden", newStatus !== "error");
  els.resultsSection.classList.toggle("is-hidden", newStatus !== "completed");
  els.diagnosticsSection.classList.toggle("is-hidden", newStatus !== "completed" || state.reports.length === 0);
  els.actionBar.classList.toggle("is-hidden", newStatus !== "completed");
  els.scanProgress.classList.toggle("is-hidden", newStatus !== "scanning");

  const statusMap = {
    idle:      t("registry.status.idle"),
    scanning:  t("registry.status.scanning"),
    completed: t("registry.status.completed"),
    noIssues:  t("registry.status.noIssues"),
    error:     t("registry.status.error"),
  };
  setText(els.statusText, message || statusMap[newStatus] || newStatus);

  if (newStatus === "error" && message) {
    setText(els.errorMessage, message);
  }
}

function setScanLock(els, locked) {
  els.startButton.disabled    = locked;
  els.scopeSelect.disabled    = locked;
  els.modeSelect.disabled     = locked;
  els.clearButton.disabled    = locked;
}

// Animate scan phases (simulated, since scan is synchronous)
function animateScanPhases(els) {
  const phases = [els.phaseCollect, els.phaseResolve, els.phaseRules, els.phaseRisk];
  phases.forEach(p => p.classList.remove("is-active", "is-done"));
  phases[0].classList.add("is-active");

  const delays = [0, 600, 1200, 1800];
  delays.forEach((delay, i) => {
    setTimeout(() => {
      phases.forEach(p => p.classList.remove("is-active"));
      if (i > 0) phases[i - 1].classList.add("is-done");
      if (i < phases.length) phases[i].classList.add("is-active");
    }, delay);
  });
}

// ---------------------------------------------------------------------------
// Stats
// ---------------------------------------------------------------------------
function renderStats(els, stats, selectedCount) {
  setText(els.statTotal,    stats?.total ?? 0);
  setText(els.statSafe,     stats?.by_risk?.Safe   ?? 0);
  setText(els.statMedium,   stats?.by_risk?.Medium ?? 0);
  setText(els.statHigh,     stats?.by_risk?.High   ?? 0);
  setText(els.statSelected, selectedCount);
}

function renderDiagnostics(state, els) {
  const reports = state.reports || [];
  if (!reports.length) {
    els.diagnosticsSection.classList.add("is-hidden");
    return;
  }

  els.diagnosticsSection.classList.toggle("is-hidden", state.status !== "completed");
  els.diagnosticsList.innerHTML = reports.map(report => `
    <div class="registry-group-card registry-diagnostic-card">
      <div class="registry-group-header">
        <div class="registry-group-title">
          <strong>${escHtml(report.hive)}\\${escHtml(report.key_path)}</strong>
          <span class="muted">${escHtml(report.scan_type)}</span>
        </div>
        <span class="status-${escHtml(report.status)}">${escHtml(report.status)}</span>
      </div>
      <div class="registry-diagnostic-grid">
        <span>${t("registry.diagnostics.checked")}<strong>${report.checked ?? 0}</strong></span>
        <span>${t("registry.diagnostics.issues")}<strong>${report.issues ?? 0}</strong></span>
        <span>${t("registry.diagnostics.skipped")}<strong>${report.skipped ?? 0}</strong></span>
        <span>${t("registry.diagnostics.duration")}<strong>${report.duration_ms ?? "-"}</strong></span>
        ${report.limit ? `<span>${t("registry.diagnostics.limit")}<strong>${report.limit}</strong></span>` : ""}
        ${report.truncated ? `<span class="diagnostic-warning">${t("registry.diagnostics.truncated")}<strong>${t("common.results.skipped")}</strong></span>` : ""}
        ${report.error ? `<span class="diagnostic-error">${t("registry.diagnostics.error")}<strong>${escHtml(report.error)}</strong></span>` : ""}
      </div>
    </div>
  `).join("");
}

function formatDisplayTime(value) {
  if (!value) return "-";
  return String(value).replace("T", " ").replace(/\.\d+/, "").replace(/\+00:00$/, "");
}

function canRestorePlan(plan) {
  return plan.status === "pending" || plan.status === "executed";
}

function renderPlanHistory(state, els) {
  const plans = state.plans || [];
  els.planHistorySection.classList.toggle("is-hidden", plans.length === 0);
  if (!plans.length) {
    els.planHistoryList.innerHTML = "";
    return;
  }

  els.planHistoryList.innerHTML = plans.map(plan => {
    const risk = plan.risk_summary || {};
    const restoreDisabled = canRestorePlan(plan) ? "" : "disabled";
    return `
      <div class="registry-group-card registry-plan-card">
        <div class="registry-group-header">
          <div class="registry-group-title">
            <strong>${escHtml(formatDisplayTime(plan.created_at))}</strong>
            <span class="selected-badge status-${escHtml(plan.status)}">${escHtml(trPlanStatus(plan.status))}</span>
          </div>
          <div class="registry-group-actions">
            <button class="ghost-button ghost-button-sm registry-plan-detail" data-plan-id="${escHtml(plan.plan_id)}" type="button">${t("registry.buttons.viewDetails")}</button>
            <button class="ghost-button ghost-button-sm registry-restore-plan" data-plan-id="${escHtml(plan.plan_id)}" type="button" ${restoreDisabled}>${t("registry.buttons.restorePlan")}</button>
          </div>
        </div>
        <div class="registry-diagnostic-grid registry-plan-history-grid">
          <span>${t("registry.plan.affectedItems")}<strong>${plan.action_count ?? 0}</strong></span>
          <span>${t("registry.risks.safe")}<strong>${risk.Safe ?? 0}</strong></span>
          <span>${t("registry.risks.medium")}<strong>${risk.Medium ?? 0}</strong></span>
          <span>${t("registry.risks.high")}<strong>${risk.High ?? 0}</strong></span>
        </div>
        <input type="text" readonly class="path-readonly-input registry-plan-id-input" value="${escHtml(plan.plan_id)}" title="${escHtml(plan.plan_dir || plan.plan_id)}" />
      </div>
    `;
  }).join("");

  els.planHistoryList.querySelectorAll(".registry-restore-plan").forEach(btn => {
    on(btn, "click", () => restorePlan(state, els, btn.dataset.planId));
  });
  els.planHistoryList.querySelectorAll(".registry-plan-detail").forEach(btn => {
    on(btn, "click", () => showPlanDetail(els, btn.dataset.planId));
  });
}

// ---------------------------------------------------------------------------
// Result groups
// ---------------------------------------------------------------------------
const CATEGORY_ORDER = [
  "StartupIssue", "InvalidUninstall", "InvalidPath",
  "InvalidService", "OrphanCOM", "FileAssociation",
];

function riskOrder(risk) {
  return { High: 0, Medium: 1, Safe: 2 }[risk] ?? 3;
}

function applyFilters(state) {
  const { category, risk, source, hive, confidence, validation, layer, search } = state.filters;
  const q = search.toLowerCase();
  return state.issues.filter(item => {
    if (layer === "executable" && (item.skip_reason || !isSelectableIssue(item))) return false;
    if (layer === "review" && (!item.skip_reason || item.skip_reason === "diagnostic_only")) return false;
    if (layer === "diagnostic" && item.skip_reason !== "diagnostic_only") return false;
    if (category && item.category !== category) return false;
    if (risk     && item.risk     !== risk)     return false;
    if (source   && item.source   !== source)   return false;
    if (hive     && item.hive     !== hive)      return false;
    if (confidence && item.confidence !== confidence) return false;
    if (validation && item.validation_status !== validation) return false;
    if (q && !`${item.key_path}${item.value_name ?? ""}${item.target_path ?? ""}${item.description}`.toLowerCase().includes(q)) return false;
    return true;
  });
}

function groupIssues(issues) {
  const map = new Map();
  for (const item of issues) {
    if (!map.has(item.category)) map.set(item.category, []);
    map.get(item.category).push(item);
  }
  // Sort groups by CATEGORY_ORDER, then by risk within group
  const sorted = [...map.entries()].sort(
    ([a], [b]) => (CATEGORY_ORDER.indexOf(a) - CATEGORY_ORDER.indexOf(b))
  );
  sorted.forEach(([, arr]) => arr.sort((a, b) => riskOrder(a.risk) - riskOrder(b.risk)));
  return sorted;
}

function renderGroups(state, els) {
  const filtered = applyFilters(state);
  const groups   = groupIssues(filtered);
  const container = els.groupList;

  if (filtered.length === 0) {
    container.innerHTML = `<p class="muted registry-empty-results">${t("registry.noResults")}</p>`;
    return;
  }

  container.innerHTML = groups.map(([category, items]) => {
    const groupSelected = items.filter(i => state.selectedIds.has(i.id)).length;
    return `
    <div class="registry-group-card" data-category="${escHtml(category)}">
      <div class="registry-group-header">
        <div class="registry-group-title">
          <strong>${escHtml(trCategory(category))}</strong>
          <span class="muted">(${items.length})</span>
          <span class="selected-badge group-selected-badge ${groupSelected > 0 ? "" : "is-hidden"}" data-selected-category="${escHtml(category)}">${groupSelected} ${t("registry.labels.selected")}</span>
        </div>
        <div class="registry-group-actions">
          <button class="ghost-button ghost-button-sm group-select-all" data-category="${escHtml(category)}" type="button">${t("registry.buttons.selectGroup")}</button>
          <button class="ghost-button ghost-button-sm group-deselect" data-category="${escHtml(category)}" type="button">${t("registry.buttons.deselectGroup")}</button>
        </div>
      </div>
      <div class="scan-table-wrap">
        <table class="scan-table registry-table">
          <thead>
            <tr>
              <th class="col-check"></th>
              <th class="col-issue" data-i18n="registry.labels.issue">${t("registry.labels.issue")}</th>
              <th class="col-key" data-i18n="registry.labels.keyPath">${t("registry.labels.keyPath")}</th>
              <th class="col-target" data-i18n="registry.labels.targetPath">${t("registry.labels.targetPath")}</th>
              <th class="col-risk" data-i18n="common.labels.riskLevel">${t("common.labels.riskLevel")}</th>
              <th class="col-source" data-i18n="common.labels.source">${t("common.labels.source")}</th>
            </tr>
          </thead>
          <tbody>
            ${items.map(item => renderIssueRow(item, state.selectedIds.has(item.id))).join("")}
          </tbody>
        </table>
      </div>
    </div>`;
  }).join("");

  // Bind checkbox events
  container.querySelectorAll("input.registry-checkbox").forEach(cb => {
    on(cb, "change", () => {
      const id = cb.dataset.id;
      if (cb.checked) state.selectedIds.add(id);
      else             state.selectedIds.delete(id);
      updateSelectionUI(state, els, { rerenderGroups: false });
    });
  });

  // Bind group select/deselect buttons
  container.querySelectorAll(".group-select-all").forEach(btn => {
    on(btn, "click", () => {
      const cat = btn.dataset.category;
      filtered.filter(i => i.category === cat && isSelectableIssue(i)).forEach(i => state.selectedIds.add(i.id));
      renderGroups(state, els);
      updateSelectionUI(state, els, { rerenderGroups: false });
    });
  });
  container.querySelectorAll(".group-deselect").forEach(btn => {
    on(btn, "click", () => {
      const cat = btn.dataset.category;
      filtered.filter(i => i.category === cat).forEach(i => state.selectedIds.delete(i.id));
      renderGroups(state, els);
      updateSelectionUI(state, els, { rerenderGroups: false });
    });
  });
}

function renderIssueRow(item, checked) {
  const riskClass = { Safe: "risk-safe", Medium: "risk-medium", High: "risk-high" }[item.risk] || "";
  const criticalNote = item.is_system_critical
    ? `<span class="critical-badge" title="${t("registry.warning.systemCritical")}">${t("registry.labels.systemCritical")}</span>`
    : "";
  const disabledAttr = isSelectableIssue(item) ? "" : "disabled";
  const checkedAttr  = checked && isSelectableIssue(item) ? "checked" : "";
  const rowClass     = item.risk === "High" ? "row-high-risk" : "";
  const highWarning  = item.risk === "High"
    ? `<span class="high-risk-badge" title="${t("registry.warning.highRisk")}">${t("registry.risks.high")}</span>`
    : "";

  const fullKeyPath = item.value_name != null
    ? `${item.hive}\\${item.key_path}  →  ${item.value_name}`
    : `${item.hive}\\${item.key_path}`;
  const targetVal = item.target_path || "—";
  const confidence = item.confidence || "High";
  const validation = item.validation_status || "missing_target";
  const confidenceNote = `<span class="selected-badge" title="${escHtml(trValidationStatus(validation))}">${escHtml(trConfidence(confidence))}</span>`;
  const reviewNote = item.skip_reason
    ? `<span class="high-risk-badge" title="${escHtml(trSkipReason(item.skip_reason))}">${t("registry.labels.reviewRequired")}</span>`
    : "";
  const reviewDetail = renderReviewDetail(item, confidence, validation);

  return `
  <tr class="${rowClass}" data-id="${escHtml(item.id)}">
    <td class="col-check">
      <input type="checkbox" class="registry-checkbox" data-id="${escHtml(item.id)}" ${checkedAttr} ${disabledAttr} />
    </td>
    <td class="col-issue path-input-cell">
      <div class="registry-issue-cell">
        <input type="text" readonly class="path-readonly-input" value="${escHtml(item.description)}" />
        <span>${criticalNote}${highWarning}${confidenceNote}${reviewNote}</span>
        ${reviewDetail}
      </div>
    </td>
    <td class="col-key path-input-cell">
      <input type="text" readonly class="path-readonly-input" value="${escHtml(fullKeyPath)}" title="${escHtml(fullKeyPath)}" />
    </td>
    <td class="col-target path-input-cell">
      <input type="text" readonly class="path-readonly-input${!item.target_path ? " is-missing" : ""}" value="${escHtml(targetVal)}" title="${escHtml(targetVal)}" />
    </td>
    <td class="col-risk"><span class="risk-badge ${riskClass}">${trRisk(item.risk)}</span></td>
    <td class="col-source">${escHtml(trSource(item.source))}</td>
  </tr>`;
}

function renderReviewDetail(item, confidence, validation) {
  if (!item.skip_reason) return "";
  return `
    <div class="registry-review-detail">
      <span><strong>${t("registry.review.reason")}</strong>${escHtml(trSkipReason(item.skip_reason))}</span>
      <span><strong>${t("registry.review.validation")}</strong>${escHtml(trValidationStatus(validation))}</span>
      <span><strong>${t("registry.review.confidence")}</strong>${escHtml(trConfidence(confidence))}</span>
      <span><strong>${t("registry.review.advice")}</strong>${escHtml(trDiagnosticAdvice(item))}</span>
    </div>
  `;
}

function isSelectableIssue(item) {
  return !item.is_system_critical && item.skip_reason !== "diagnostic_only";
}

function updateGroupSelectedBadges(state, els) {
  const filtered = applyFilters(state);
  const selectedByCategory = new Map();
  for (const item of filtered) {
    if (!state.selectedIds.has(item.id)) continue;
    selectedByCategory.set(item.category, (selectedByCategory.get(item.category) || 0) + 1);
  }

  els.groupList.querySelectorAll("[data-selected-category]").forEach(badge => {
    const category = badge.dataset.selectedCategory;
    const count = selectedByCategory.get(category) || 0;
    badge.classList.toggle("is-hidden", count === 0);
    badge.textContent = `${count} ${t("registry.labels.selected")}`;
  });
}

function updateSelectionUI(state, els, options = {}) {
  renderStats(els, state.stats, state.selectedIds.size);
  els.generatePlanButton.disabled = state.selectedIds.size === 0;
  if (options.rerenderGroups === false) {
    updateGroupSelectedBadges(state, els);
  } else {
    renderGroups(state, els);
  }
}

// ---------------------------------------------------------------------------
// Plan dialog
// ---------------------------------------------------------------------------
function showPlanDialog(state, els, planMeta) {
  const { risk_summary, action_count } = planMeta;
  const reviewCount = planMeta.review_action_count || 0;
  const reviewActions = planMeta.review_actions || [];
  const requiresAdmin = selectedRequiresAdmin(state);
  els.planPreview.innerHTML = `
    <table class="scan-table registry-plan-table">
      <tr><td>${t("registry.plan.affectedItems")}</td><td><strong>${action_count}</strong></td></tr>
      <tr><td>${t("registry.risks.safe")}</td><td>${risk_summary.Safe ?? 0}</td></tr>
      <tr><td>${t("registry.risks.medium")}</td><td>${risk_summary.Medium ?? 0}</td></tr>
      <tr><td>${t("registry.risks.high")}</td><td>${risk_summary.High ?? 0}</td></tr>
      <tr><td>${t("registry.plan.reviewItems")}</td><td>${reviewCount}</td></tr>
    </table>
    <p class="muted registry-plan-note">${t("registry.plan.backupNote")}</p>
    ${reviewCount > 0
      ? `<p class="registry-plan-note danger-text">${t("registry.plan.reviewOnly")}</p>`
      : ""}
    ${reviewActions.length > 0 ? renderReviewConfirmations(reviewActions) : ""}
    ${requiresAdmin && !state.capabilities.is_admin
      ? `<p class="registry-plan-note danger-text">${t("registry.warning.adminRequired")}</p>`
      : ""}
  `;
  state.pendingPlanId = planMeta.plan_id;
  state.pendingReviewActionIds = [];
  els.planExecute.disabled = reviewActions.length > 0 || (requiresAdmin && !state.capabilities.is_admin);
  els.planDialog.classList.remove("is-hidden");
  bindReviewConfirmationToggles(state, els, reviewActions);
  els.planCancel.focus();
}

function closePlanDialog(els) {
  els.planExecute.disabled = false;
  els.planDialog.classList.add("is-hidden");
}

function renderReviewConfirmations(reviewActions) {
  return `
    <div class="registry-review-confirm-list">
      <p class="registry-plan-note">${t("registry.review.confirmIntro")}</p>
      ${reviewActions.map(action => `
        <label class="registry-review-confirm-item">
          <input type="checkbox" class="registry-review-confirm-checkbox" data-action-id="${escHtml(action.id)}" />
          <span>
            <strong>${escHtml(action.hive)}\\${escHtml(action.keyPath)}</strong>
            <small>${escHtml(trSkipReason(action.skipReason))}</small>
          </span>
        </label>
      `).join("")}
    </div>
  `;
}

function bindReviewConfirmationToggles(state, els, reviewActions) {
  const requiredIds = new Set(reviewActions.map(action => action.id));
  els.planPreview.querySelectorAll(".registry-review-confirm-checkbox").forEach(cb => {
    on(cb, "change", () => {
      state.pendingReviewActionIds = [...els.planPreview.querySelectorAll(".registry-review-confirm-checkbox:checked")]
        .map(item => item.dataset.actionId)
        .filter(Boolean);
      const allConfirmed = state.pendingReviewActionIds.every(id => requiredIds.has(id))
        && state.pendingReviewActionIds.length === requiredIds.size;
      const requiresAdmin = selectedRequiresAdmin(state);
      els.planExecute.disabled = !allConfirmed || (requiresAdmin && !state.capabilities.is_admin);
    });
  });
}

function renderPlanDetail(plan) {
  const risk = plan.risk_summary || {};
  const actions = plan.actions || [];
  return `
    <table class="scan-table registry-plan-table">
      <tr><td>${t("registry.history.planId")}</td><td><input type="text" readonly class="path-readonly-input" value="${escHtml(plan.plan_id)}" /></td></tr>
      <tr><td>${t("registry.history.status")}</td><td>${escHtml(trPlanStatus(plan.status))}</td></tr>
      <tr><td>${t("registry.history.createdAt")}</td><td>${escHtml(formatDisplayTime(plan.created_at))}</td></tr>
      <tr><td>${t("registry.plan.affectedItems")}</td><td>${plan.action_count ?? actions.length}</td></tr>
      <tr><td>${t("registry.risks.safe")}</td><td>${risk.Safe ?? 0}</td></tr>
      <tr><td>${t("registry.risks.medium")}</td><td>${risk.Medium ?? 0}</td></tr>
      <tr><td>${t("registry.risks.high")}</td><td>${risk.High ?? 0}</td></tr>
    </table>
    <div class="registry-plan-detail-list">
      ${actions.map(action => renderPlanDetailAction(action)).join("")}
    </div>
  `;
}

function renderPlanDetailAction(action) {
  const fullKeyPath = action.value_name != null
    ? `${action.hive}\\${action.key_path}  →  ${action.value_name}`
    : `${action.hive}\\${action.key_path}`;
  return `
    <div class="registry-review-detail registry-plan-detail-action">
      <span><strong>${t("registry.labels.keyPath")}</strong>${escHtml(fullKeyPath)}</span>
      <span><strong>${t("common.labels.riskLevel")}</strong>${escHtml(trRisk(action.risk))}</span>
      <span><strong>${t("registry.review.confidence")}</strong>${escHtml(trConfidence(action.confidence || ""))}</span>
      <span><strong>${t("registry.review.validation")}</strong>${escHtml(trValidationStatus(action.validation_status || ""))}</span>
      ${action.skip_reason ? `<span><strong>${t("registry.review.reason")}</strong>${escHtml(trSkipReason(action.skip_reason))}</span>` : ""}
      <span><strong>${t("registry.history.backupFile")}</strong>${escHtml(action.backup_path || action.reg_file || "")}</span>
    </div>
  `;
}

async function showPlanDetail(els, planId) {
  if (!planId) return;
  try {
    const resp = await fetch(`/registry/plan/${planId}`);
    const data = await resp.json();
    if (!resp.ok || !data.ok) throw new Error(data.detail || "Failed to load plan detail");
    els.planDetailContent.innerHTML = renderPlanDetail(data.plan);
    els.planDetailDialog.classList.remove("is-hidden");
    els.planDetailClose.focus();
  } catch (err) {
    await showAlert(t("registry.error.planDetailFailed") + ": " + err.message);
  }
}

function closePlanDetail(els) {
  els.planDetailDialog.classList.add("is-hidden");
}

// ---------------------------------------------------------------------------
// Auto-selection strategies
// ---------------------------------------------------------------------------
function autoSelectSafe(state) {
  state.selectedIds.clear();
  state.issues
    .filter(i => i.risk === "Safe" && i.selected !== false && !i.skip_reason && !i.is_system_critical)
    .forEach(i => state.selectedIds.add(i.id));
}

function autoSelectSafeAndMedium(state) {
  state.selectedIds.clear();
  state.issues
    .filter(i => (i.risk === "Safe" || i.risk === "Medium") && i.selected !== false && !i.skip_reason && !i.is_system_critical)
    .forEach(i => state.selectedIds.add(i.id));
}

function selectedRequiresAdmin(state) {
  const adminHives = new Set(state.capabilities.admin_required_hives || []);
  return state.issues.some(item => state.selectedIds.has(item.id) && adminHives.has(item.hive));
}

// ---------------------------------------------------------------------------
// Core scan flow
// ---------------------------------------------------------------------------
async function startScan(state, els) {
  const scope = els.scopeSelect.value;
  const mode  = els.modeSelect.value;

  setStatus(state, els, "scanning");
  setScanLock(els, true);
  animateScanPhases(els);

  try {
    const resp = await fetch("/registry/scan", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ scope, mode }),
    });
    const data = await resp.json();

    if (!resp.ok) throw new Error(data.detail || resp.statusText);
    if (!data.ok) throw new Error(data.detail || "Scan failed");

    state.issues = data.issues || [];
    state.reports = data.reports || [];
    state.stats  = data.stats;

    // Apply default safe-only selection
    autoSelectSafe(state);

    if (state.issues.length === 0) {
      setStatus(state, els, "noIssues");
    } else {
      setStatus(state, els, "completed",
        t("registry.status.completedWithCount").replace("{n}", state.issues.length));
      renderStats(els, state.stats, state.selectedIds.size);
      renderGroups(state, els);
      renderDiagnostics(state, els);
      els.generatePlanButton.disabled = state.selectedIds.size === 0;
    }

    els.clearButton.disabled = state.issues.length === 0;
  } catch (err) {
    setStatus(state, els, "error", err.message);
  } finally {
    setScanLock(els, false);
    els.scanProgress.classList.add("is-hidden");
  }
}

async function loadPlanHistory(state, els) {
  try {
    const resp = await fetch("/registry/plans");
    const data = await resp.json();
    if (!resp.ok || !data.ok) throw new Error(data.detail || "Failed to load plans");
    state.plans = data.plans || [];
    renderPlanHistory(state, els);
  } catch {
    state.plans = [];
    renderPlanHistory(state, els);
  }
}

async function restorePlan(state, els, planId) {
  if (!planId) return;
  let preview = null;
  try {
    const previewResp = await fetch(`/registry/plan/${planId}/restore-preview`);
    preview = await previewResp.json();
    if (!previewResp.ok || !preview.ok) throw new Error(preview.detail || "Restore preview failed");
  } catch (err) {
    await showAlert(t("registry.error.restorePreviewFailed") + ": " + err.message);
    return;
  }
  const ok = await showConfirm(
    t("registry.history.confirmRestoreWithPreview")
      .replace("{actions}", preview.action_count ?? 0)
      .replace("{overwrites}", preview.overwrite_count ?? 0)
      .replace("{missing}", preview.missing_backup_count ?? 0)
  );
  if (!ok) return;

  try {
    const resp = await fetch(`/registry/plan/${planId}/restore`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ confirm_overwrite: true }),
    });
    const data = await resp.json();
    if (!resp.ok || !data.ok) {
      const details = Array.isArray(data.errors) && data.errors.length > 0
        ? data.errors.join("\n")
        : data.detail;
      throw new Error(details || "Restore failed");
    }
    await showAlert(
      t("registry.history.restored")
        .replace("{succeeded}", data.succeeded ?? 0)
        .replace("{failed}", data.failed ?? 0)
    );
    await loadPlanHistory(state, els);
  } catch (err) {
    await showAlert(t("registry.error.restoreFailed") + ": " + err.message);
  }
}

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------
export function initRegistryPage() {
  const state = createState();
  const els   = getEls();

  ensureDialog();
  translateStaticText();

  fetch("/registry/capabilities")
    .then(r => r.json())
    .then(data => {
      if (data.ok) {
        state.capabilities = data;
      }
    })
    .catch(() => {});

  // Load saved results from previous session
  fetch("/registry/results")
    .then(r => r.json())
    .then(data => {
      if (data.ok && data.issues?.length > 0) {
        state.issues = data.issues;
        state.reports = data.reports || [];
        state.stats  = data.stats;
        autoSelectSafe(state);
        setStatus(state, els, "completed",
          t("registry.status.completedWithCount").replace("{n}", state.issues.length));
        renderStats(els, state.stats, state.selectedIds.size);
        renderGroups(state, els);
        renderDiagnostics(state, els);
        els.generatePlanButton.disabled = state.selectedIds.size === 0;
        els.clearButton.disabled = false;
      } else {
        markI18nReady();
      }
    })
    .catch(() => markI18nReady());

  loadPlanHistory(state, els);

  // Navigation
  on(els.backButton, "click", () => { window.location.href = "/"; });
  on(els.retryButton,  "click", () => startScan(state, els));
  on(els.rescanButton, "click", () => startScan(state, els));

  // Scan
  on(els.startButton, "click", () => startScan(state, els));

  // Clear
  on(els.clearButton, "click", async () => {
    const ok = await showConfirm(t("registry.confirmClear"));
    if (!ok) return;
    await fetch("/registry/results", { method: "DELETE" });
    state.issues = [];
    state.reports = [];
    state.stats  = null;
    state.selectedIds.clear();
    setStatus(state, els, "idle");
    els.clearButton.disabled = true;
  });

  // Filters
  const rerender = () => renderGroups(state, els);
  on(els.categoryFilter, "change", () => { state.filters.category = els.categoryFilter.value; rerender(); });
  on(els.riskFilter,     "change", () => { state.filters.risk     = els.riskFilter.value;     rerender(); });
  on(els.sourceFilter,   "change", () => { state.filters.source   = els.sourceFilter.value;   rerender(); });
  on(els.hiveFilter,     "change", () => { state.filters.hive     = els.hiveFilter.value;     rerender(); });
  on(els.confidenceFilter, "change", () => { state.filters.confidence = els.confidenceFilter.value; rerender(); });
  on(els.validationFilter, "change", () => { state.filters.validation = els.validationFilter.value; rerender(); });
  on(els.searchInput,    "input",  () => { state.filters.search   = els.searchInput.value;    rerender(); });
  els.layerTabs.forEach(tab => {
    on(tab, "click", () => {
      state.filters.layer = tab.dataset.layer || "all";
      els.layerTabs.forEach(item => item.classList.toggle("is-active", item === tab));
      rerender();
    });
  });

  // Auto-select
  on(els.autoSelectSafe, "click", () => { autoSelectSafe(state);           updateSelectionUI(state, els); });
  on(els.autoSelectAll,  "click", () => { autoSelectSafeAndMedium(state);  updateSelectionUI(state, els); });
  on(els.selectNone,     "click", () => { state.selectedIds.clear();       updateSelectionUI(state, els); });

  // Generate plan
  on(els.generatePlanButton, "click", async () => {
    if (state.selectedIds.size === 0) return;
    const highSelected = state.issues.filter(i => state.selectedIds.has(i.id) && i.risk === "High");
    if (highSelected.length > 0) {
      const proceed = await showConfirm(
        t("registry.warning.highRiskConfirm").replace("{n}", highSelected.length)
      );
      if (!proceed) return;
    }

    els.generatePlanButton.disabled = true;
    try {
      const resp = await fetch("/registry/plan", {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ issue_ids: [...state.selectedIds] }),
      });
      const data = await resp.json();
      if (!resp.ok || !data.ok) throw new Error(data.detail || "Plan generation failed");
      showPlanDialog(state, els, data);
      await loadPlanHistory(state, els);
    } catch (err) {
      await showAlert(t("registry.error.planFailed") + ": " + err.message);
    } finally {
      els.generatePlanButton.disabled = false;
    }
  });

  // Plan dialog actions
  on(els.planCancel,  "click", () => closePlanDialog(els));
  on(els.planSave,    "click", () => {
    closePlanDialog(els);
    showAlert(t("registry.plan.savedOnly"));
  });
  on(els.planExecute, "click", async () => {
    closePlanDialog(els);
    const planId = state.pendingPlanId;
    if (!planId) return;
    try {
      const resp = await fetch(`/registry/plan/${planId}/execute`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ confirmed_review_action_ids: state.pendingReviewActionIds }),
      });
      const data = await resp.json();
      if (!resp.ok || !data.ok) {
        const details = Array.isArray(data.errors) && data.errors.length > 0
          ? data.errors.join("\n")
          : data.detail;
        if (data.snapshot_changed) {
          throw new Error(`${t("registry.error.snapshotChanged")}\n${details || ""}`.trim());
        }
        throw new Error(details || "Execution failed");
      }
      const msg = t("registry.plan.executed")
        .replace("{n}", data.succeeded)
        .replace("{failed}", data.failed > 0 ? ` (${data.failed} ${t("registry.plan.failedSuffix")})` : "");
      setText(els.statusText, msg);
      await loadPlanHistory(state, els);
      state.selectedIds.clear();
      updateSelectionUI(state, els);
    } catch (err) {
      await showAlert(
        t("registry.error.executeFailed") + ": " + err.message,
        { title: t("dialog.title.error") },
      );
    }
  });

  on(els.planDialog, "click", event => {
    if (event.target === els.planDialog) {
      closePlanDialog(els);
    }
  });
  on(els.planDetailClose, "click", () => closePlanDetail(els));
  on(els.planDetailDialog, "click", event => {
    if (event.target === els.planDetailDialog) {
      closePlanDetail(els);
    }
  });

  markI18nReady();
}
