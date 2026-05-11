import { $, on, setText } from "../core/dom.js";
import { ensureDialog, showAlert } from "../core/dialog.js";
import { markI18nReady, t, translateStaticText } from "../locales/i18n.js";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------
const CATEGORY_COLORS = {
  AI_TOOL_CACHE:     "#7c3aed",
  PYTHON_SCI_CACHE:  "#0891b2",
  IDE_BUILD_CACHE:   "#059669",
  SYSTEM_TOOL_CACHE: "#6b7280",
  USER_DATA:         "#2563eb",
  LOG_FILES:         "#d97706",
  OTHER_LARGE_FILES: "#dc2626",
};

const PAGE_SIZE = 100;
const TREEMAP_LIMIT = 16;

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
function createState() {
  return {
    status: "idle",   // idle | scanning | completed | empty | error
    meta: null,
    summary: [],
    stats: null,
    scanConfig: null,
    items: [],
    treemapItems: [],
    itemCount: 0,
    largeFiles: [],
    thresholdMb: 100,
    filters: { category: "", itemType: "", minSizeMb: "", search: "" },
    listOffset: 0,
    hasMoreItems: false,
    isLoadingItems: false,
    scanStartTime: 0,
    elapsedTimerId: 0,
    scanTaskId: "",
  };
}

// ---------------------------------------------------------------------------
// DOM refs
// ---------------------------------------------------------------------------
function getEls() {
  return {
    backButton:        $("#userdirBackButton"),
    refreshButton:     $("#userdirRefreshButton"),
    refreshLabel:      $("#userdirRefreshLabel"),
    startButton:       $("#userdirStartButton"),
    startLabel:        $("#userdirStartLabel"),
    // States
    idleState:         $("#userdirIdleState"),
    idleStartBtn:      $("#userdirIdleStartBtn"),
    scanningState:     $("#userdirScanningState"),
    resultsSection:    $("#userdirResultsSection"),
    emptyState:        $("#userdirEmptyState"),
    errorState:        $("#userdirErrorState"),
    errorMessage:      $("#userdirErrorMessage"),
    viewLogsButton:    $("#userdirViewLogsButton"),
    retryButton:       $("#userdirRetryButton"),
    // Scanning
    elapsedTime:       $("#userdirElapsedTime"),
    progressFill:      $("#userdirProgressFill"),
    currentPath:       $("#userdirCurrentPath"),
    // Completed — config
    configRoot:        $("#userdirConfigRoot"),
    configThreshold:   $("#userdirConfigThreshold"),
    configRules:       $("#userdirConfigRules"),
    configScanTime:    $("#userdirConfigScanTime"),
    configDuration:    $("#userdirConfigDuration"),
    // Completed — stats
    stat2TotalSize:    $("#userdirStat2TotalSize"),
    stat2TotalItems:   $("#userdirStat2TotalItems"),
    stat2FileCount:    $("#userdirStat2FileCount"),
    stat2Cleanable:    $("#userdirStat2Cleanable"),
    stat2CleanablePct: $("#userdirStat2CleanablePct"),
    stat2LargeItems:   $("#userdirStat2LargeItems"),
    // Category section
    catTitle:          $("#userdirCatTitle"),
    catStrip:          $("#userdirCatStrip"),
    catLegend:         $("#userdirCatLegend"),
    // Treemap
    treemapLegend:     $("#userdirTreemapLegend"),
    treemapWrap:       $("#userdirTreemapWrap"),
    treemapSvg:        $("#userdirTreemapSvg"),
    treemapEmpty:      $("#userdirTreemapEmpty"),
    // Filter + list
    categoryFilter:    $("#userdirCategoryFilter"),
    typeFilter:        $("#userdirTypeFilter"),
    minSizeFilter:     $("#userdirMinSizeFilter"),
    searchInput:       $("#userdirSearchInput"),
    clearFiltersButton: $("#userdirClearFiltersButton"),
    loadMoreRow:      $("#userdirLoadMoreRow"),
    loadMoreButton:   $("#userdirLoadMoreButton"),
    listHint:          $("#userdirListHint"),
    itemList:          $("#userdirItemList"),
    listEmpty:         $("#userdirListEmpty"),
  };
}

// ---------------------------------------------------------------------------
// Formatting
// ---------------------------------------------------------------------------
function fmtBytes(bytes) {
  if (bytes == null || bytes < 0) return "—";
  if (bytes === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let i = 0, v = bytes;
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
  return `${v.toFixed(v >= 100 ? 0 : v >= 10 ? 1 : 2)} ${units[i]}`;
}

function fmtDuration(ms) {
  if (ms == null || ms < 0) return "—";
  if (ms < 1000) return `${ms} ms`;
  const sec = ms / 1000;
  if (sec < 60) return `${sec.toFixed(sec >= 10 ? 1 : 2)} s`;
  const min = Math.floor(sec / 60);
  const rest = Math.round(sec % 60);
  return `${min} min ${rest} s`;
}

function fmtDate(value) {
  if (!value) return "—";
  return String(value).replace("T", " ").slice(0, 19);
}

function categoryLabel(cat) {
  const key = `userdir.categories.${toCamel(cat)}`;
  return t(key) || cat;
}

function toCamel(s) {
  return s.toLowerCase().replace(/_([a-z])/g, (_, c) => c.toUpperCase());
}

function escHtml(s) {
  return String(s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

// ---------------------------------------------------------------------------
// Mode switcher
// ---------------------------------------------------------------------------
function setMode(els, state) {
  const s = state.status;
  const show = (el, v) => el && el.classList.toggle("is-hidden", !v);

  // Sections
  show(els.idleState,      s === "idle");
  show(els.scanningState,  s === "scanning");
  show(els.resultsSection, s === "completed");
  show(els.emptyState,     s === "empty");
  show(els.errorState,     s === "error");

  // Buttons
  const scanning = s === "scanning";
  els.startButton.disabled   = scanning;
  els.refreshButton.disabled = scanning || s === "idle";
  setText(els.refreshLabel, s === "completed" || s === "empty"
    ? (t("userdir.buttons.rescan") || "重新扫描")
    : (t("common.buttons.refresh") || "刷新"));
  setText(els.startLabel, scanning
    ? (t("userdir.buttons.scanning") || "扫描中")
    : (t("userdir.buttons.startScan") || "开始扫描"));
  els.startButton.classList.remove("danger-button");
  els.startButton.classList.add("primary-button");
}

// ---------------------------------------------------------------------------
// Scanning indicator
// ---------------------------------------------------------------------------
function startScanIndicator(els, state) {
  state.scanStartTime = Date.now();
  setText(els.elapsedTime, "");
  els.progressFill.classList.add("is-indeterminate");
  els.progressFill.style.width = "45%";
  setText(els.currentPath, t("userdir.scanning.pending") || "Scan task is running. Waiting for backend status…");
  state.elapsedTimerId = setInterval(() => {
    if (state.status !== "scanning") { clearInterval(state.elapsedTimerId); return; }
    const sec = ((Date.now() - state.scanStartTime) / 1000).toFixed(1);
    setText(els.elapsedTime, `已耗时 ${sec} s`);
  }, 200);
}

function stopScanIndicator(els, state) {
  clearInterval(state.elapsedTimerId);
  state.elapsedTimerId = 0;
  els.progressFill.classList.remove("is-indeterminate");
  els.progressFill.style.width = "0";
  setText(els.currentPath, "");
}

// ---------------------------------------------------------------------------
// Render results
// ---------------------------------------------------------------------------
function renderResults(els, state) {
  const meta    = state.meta;
  const summary = state.summary;
  const totalBytes = meta.total_size_bytes || 0;

  // Config strip
  const scanConfig = state.scanConfig || {};
  setText(els.configRoot, scanConfig.root_path || meta.root_path || "%USERPROFILE%");
  setText(els.configThreshold, `≥ ${scanConfig.large_file_threshold_mb || state.thresholdMb} MB`);
  setText(els.configRules, formatScanRules(scanConfig));
  setText(els.configScanTime, fmtDate(meta.finished_at || meta.started_at));
  setText(els.configDuration, fmtDuration(meta.duration_ms));

  // Helper: find a category in summary
  const cat = (key) => summary.find(c => c.category === key) || { size_bytes: 0, item_count: 0 };

  const aiCat  = cat("AI_TOOL_CACHE");
  const logCat = cat("LOG_FILES");
  const stats  = state.stats || {};

  // Stats row
  const itemTotal = stats.total_item_count ?? (meta.total_file_count + meta.total_dir_count);
  setText(els.stat2TotalSize, fmtBytes(totalBytes));
  setText(els.stat2TotalItems, (t("userdir.list.itemCount") || "{count} items").replace("{count}", itemTotal.toLocaleString()));
  setText(els.stat2FileCount, meta.total_file_count.toLocaleString());

  const cleanableBytes = stats.cleanable_bytes ?? ((aiCat.size_bytes || 0) + (logCat.size_bytes || 0));
  const cleanablePct = stats.cleanable_percent ?? (totalBytes > 0 ? Math.round((cleanableBytes / totalBytes) * 100) : 0);
  setText(els.stat2Cleanable, fmtBytes(cleanableBytes));
  setText(els.stat2CleanablePct, (t("userdir.stats2.cleanablePct") || "{pct}% of total").replace("{pct}", cleanablePct));

  const largeItems = stats.large_review_item_count ?? 0;
  setText(els.stat2LargeItems, (t("userdir.list.itemCount") || "{count} items").replace("{count}", largeItems.toLocaleString()));

  // Category section
  const catCount = summary.filter(c => c.size_bytes > 0).length;
  setText(els.catTitle, (t("userdir.catSection.titleWithCount") || "{count} categories by size").replace("{count}", catCount));
  renderCatSection(els, state);

  // Treemap
  renderTreemap(els, state);

  // Item list
  renderItemList(els, state);
}

function formatScanRules(scanConfig) {
  const excluded = Array.isArray(scanConfig.exclude_names) && scanConfig.exclude_names.length
    ? scanConfig.exclude_names.join(" / ")
    : ".git / node_modules";
  const included = [];
  if (scanConfig.include_hidden !== false) included.push(t("userdir.config.includeHidden") || "hidden items");
  if (scanConfig.include_logs !== false) included.push(t("userdir.config.includeLogs") || "logs");
  const includeText = included.length ? included.join(" / ") : "—";
  return (t("userdir.config.rulesTemplate") || "Skip {excluded}; include {included}")
    .replace("{excluded}", excluded)
    .replace("{included}", includeText);
}

// ---------------------------------------------------------------------------
// Category distribution
// ---------------------------------------------------------------------------
function renderCatSection(els, state) {
  const total = state.summary.reduce((s, c) => s + c.size_bytes, 0) || 1;
  const sorted = [...state.summary]
    .filter(c => c.size_bytes > 0)
    .sort((a, b) => b.size_bytes - a.size_bytes);

  // Proportional strip
  els.catStrip.innerHTML = sorted.map(cat => {
    const pct = (cat.size_bytes / total * 100).toFixed(2);
    const color = CATEGORY_COLORS[cat.category] || "#6b7280";
    const label = categoryLabel(cat.category);
    return `<div class="userdir-cat-seg" style="width:${pct}%;background:${color}"
                 title="${escHtml(label)}: ${fmtBytes(cat.size_bytes)} (${parseFloat(pct).toFixed(1)}%)"
                 data-category="${escHtml(cat.category)}"></div>`;
  }).join("");

  // Legend
  els.catLegend.innerHTML = sorted.map(cat => {
    const pct = (cat.size_bytes / total * 100).toFixed(1);
    const color = CATEGORY_COLORS[cat.category] || "#6b7280";
    const label = categoryLabel(cat.category);
    return `<div class="userdir-cat-legend-item" data-category="${escHtml(cat.category)}">
      <span class="userdir-cat-legend-dot" style="background:${color}"></span>
      <span class="userdir-cat-legend-name">${escHtml(label)}</span>
      <span class="userdir-cat-legend-size">${fmtBytes(cat.size_bytes)}</span>
      <span class="userdir-cat-legend-pct muted">${pct}%</span>
    </div>`;
  }).join("");
}

// ---------------------------------------------------------------------------
// Treemap (squarified)
// ---------------------------------------------------------------------------
function squarify(items, W, H) {
  const total = items.reduce((s, x) => s + x._area, 0) || 1;
  const norm  = items.map(it => ({ ...it, area: (it._area / total) * W * H }));
  const result = [];
  let x = 0, y = 0, rw = W, rh = H, i = 0;

  while (i < norm.length) {
    const row = [norm[i++]];
    const short = () => Math.min(rw, rh);
    const worst = (r) => {
      const sum = r.reduce((s, n) => s + n.area, 0);
      const s2 = short() ** 2;
      return Math.max(...r.map(n => Math.max(s2 * n.area / sum ** 2, sum ** 2 / (s2 * n.area))));
    };
    while (i < norm.length) {
      const test = [...row, norm[i]];
      if (worst(test) <= worst(row)) row.push(norm[i++]); else break;
    }
    const sum = row.reduce((s, n) => s + n.area, 0);
    if (rw >= rh) {
      const rowW = sum / rh;
      let cy = y;
      for (const n of row) { const h = (n.area / sum) * rh; result.push({ ...n, x, y: cy, w: rowW, h }); cy += h; }
      x += rowW; rw -= rowW;
    } else {
      const rowH = sum / rw;
      let cx = x;
      for (const n of row) { const w = (n.area / sum) * rw; result.push({ ...n, x: cx, y, w, h: rowH }); cx += w; }
      y += rowH; rh -= rowH;
    }
  }
  return result;
}

function renderTreemap(els, state) {
  const svg  = els.treemapSvg;
  const wrap = els.treemapWrap;
  const W    = wrap.clientWidth || 1100;
  const H    = 120;

  svg.setAttribute("width", W);
  svg.setAttribute("height", H);
  svg.innerHTML = "";

  const top16 = state.treemapItems
    .filter(it => (it.size_bytes || 0) > 0)
    .sort((a, b) => b.size_bytes - a.size_bytes)
    .slice(0, 16)
    .map(it => ({ ...it, _area: it.size_bytes }));

  if (top16.length === 0) {
    els.treemapEmpty.classList.remove("is-hidden");
    svg.classList.add("is-hidden");
    return;
  }
  els.treemapEmpty.classList.add("is-hidden");
  svg.classList.remove("is-hidden");

  const cells = squarify(top16, W, H);
  const trunc = (s, n) => s.length <= n ? s : s.slice(0, Math.max(1, n - 1)) + "…";

  for (const c of cells) {
    const color = CATEGORY_COLORS[c.category] || "#6b7280";
    const name  = c.path.split(/[/\\]/).pop() || c.path;
    const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
    g.style.cursor = "pointer";

    const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    rect.setAttribute("x", c.x + 1); rect.setAttribute("y", c.y + 1);
    rect.setAttribute("width", Math.max(0, c.w - 2)); rect.setAttribute("height", Math.max(0, c.h - 2));
    rect.setAttribute("fill", color); rect.setAttribute("fill-opacity", "0.80"); rect.setAttribute("rx", "4");
    g.appendChild(rect);

    const border = rect.cloneNode();
    border.setAttribute("fill", "none"); border.setAttribute("stroke", "white"); border.setAttribute("stroke-width", "1"); border.setAttribute("fill-opacity", "1");
    g.appendChild(border);

    if (c.w > 80 && c.h > 38) {
      const t1 = document.createElementNS("http://www.w3.org/2000/svg", "text");
      t1.setAttribute("x", c.x + 8); t1.setAttribute("y", c.y + 18);
      t1.setAttribute("fill", "white"); t1.setAttribute("font-size", "12"); t1.setAttribute("font-weight", "700");
      t1.style.pointerEvents = "none";
      t1.textContent = trunc(name, Math.floor(c.w / 7.5));
      g.appendChild(t1);
    }
    if (c.w > 60 && c.h > 22) {
      const t2 = document.createElementNS("http://www.w3.org/2000/svg", "text");
      t2.setAttribute("x", c.x + 8); t2.setAttribute("y", c.y + (c.w > 80 && c.h > 38 ? 34 : 18));
      t2.setAttribute("fill", "white"); t2.setAttribute("font-size", "11"); t2.setAttribute("font-weight", "600"); t2.setAttribute("fill-opacity", "0.9");
      t2.style.pointerEvents = "none";
      t2.textContent = fmtBytes(c.size_bytes);
      g.appendChild(t2);
    }

    g.addEventListener("mouseenter", () => rect.setAttribute("fill-opacity", "0.95"));
    g.addEventListener("mouseleave", () => rect.setAttribute("fill-opacity", "0.80"));
    svg.appendChild(g);
  }

  // Legend
  const usedCats = [...new Set(top16.map(it => it.category))];
  els.treemapLegend.innerHTML = usedCats.map(cat => {
    const color = CATEGORY_COLORS[cat] || "#6b7280";
    return `<div class="userdir-treemap-legend-item">
      <span class="userdir-treemap-legend-dot" style="background:${color}"></span>
      <span>${escHtml(categoryLabel(cat))}</span>
    </div>`;
  }).join("");
}

// ---------------------------------------------------------------------------
// Item list
// ---------------------------------------------------------------------------
function renderItemList(els, state) {
  const rows = state.items.map(item => {
    const color    = CATEGORY_COLORS[item.category] || "#6b7280";
    const catLabel = categoryLabel(item.category);
    const icon     = item.type === "Directory" ? "DIR" : "FILE";
    const meta     = [
      item.file_count > 0 ? (t("userdir.list.fileCount") || "{count} files").replace("{count}", item.file_count.toLocaleString()) : "",
      item.is_hidden  ? "hidden"  : "",
      item.is_symlink ? "symlink" : "",
    ].filter(Boolean).join(" · ");

    return `<div class="userdir-item-row">
      <span class="userdir-item-icon">${icon}</span>
      <span class="userdir-item-path" title="${escHtml(item.path)}">${escHtml(item.path)}</span>
      <span class="userdir-item-tag" style="background:${color}20;color:${color}">${escHtml(catLabel)}</span>
      <span class="userdir-item-size">${fmtBytes(item.size_bytes)}</span>
      <span class="userdir-item-meta muted">${escHtml(meta)}</span>
      <span class="userdir-item-mtime muted">${fmtDate(item.last_modified)}</span>
      <button class="ghost-button ghost-button-sm userdir-copy-btn" data-path="${escHtml(item.path)}">${escHtml(t("userdir.buttons.copyPath") || "Copy")}</button>
    </div>`;
  }).join("");

  els.itemList.innerHTML = rows;
  els.listEmpty?.classList.toggle("is-hidden", state.items.length > 0);

  const showing = els.itemList.querySelectorAll(".userdir-item-row").length;
  const activeFilters = Object.values(state.filters).filter(Boolean).length;
  const hintKey = activeFilters > 0 ? "userdir.list.filteredHint" : "userdir.list.hint";
  setText(els.listHint, (t(hintKey) || "Showing {shown} of {total} items")
    .replace("{shown}", showing.toLocaleString())
    .replace("{total}", state.itemCount.toLocaleString()));
  els.loadMoreRow.classList.toggle("is-hidden", !state.hasMoreItems);
  els.loadMoreButton.disabled = state.isLoadingItems;
  setText(els.loadMoreButton, state.isLoadingItems
    ? (t("userdir.buttons.loadingMore") || "加载中")
    : (t("userdir.buttons.loadMore") || "加载更多"));
}

// ---------------------------------------------------------------------------
// API
// ---------------------------------------------------------------------------
async function apiScan(thresholdMb) {
  const res = await fetch("/user-directory/scan", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ large_file_threshold_mb: thresholdMb, max_concurrency: 4 }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Scan failed: ${res.status}`);
  }
  return res.json();
}

async function apiScanStatus(taskId) {
  const res = await fetch(`/user-directory/scan/${encodeURIComponent(taskId)}`);
  if (!res.ok) throw new Error(`Scan status failed: ${res.status}`);
  return res.json();
}

async function apiResults(filters, { limit = PAGE_SIZE, offset = 0 } = {}) {
  const p = new URLSearchParams();
  if (filters.category)  p.set("category",    filters.category);
  if (filters.itemType)  p.set("item_type",   filters.itemType);
  if (filters.search)    p.set("search",      filters.search);
  if (filters.minSizeMb) p.set("min_size_mb", filters.minSizeMb);
  p.set("order_by", "size_bytes"); p.set("order_dir", "DESC");
  p.set("limit", String(limit));
  p.set("offset", String(offset));
  const res = await fetch(`/user-directory/results?${p}`);
  if (!res.ok) throw new Error(`Load failed: ${res.status}`);
  return res.json();
}

async function apiTreemapItems() {
  const res = await fetch(`/user-directory/top-items?limit=${TREEMAP_LIMIT}`);
  if (!res.ok) throw new Error(`Load treemap failed: ${res.status}`);
  const data = await res.json();
  return data.items || [];
}

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------
export function initUserDirectoryPage() {
  const state = createState();
  const els   = getEls();

  ensureDialog();
  translateStaticText();
  markI18nReady();

  // Load existing results on mount
  (async () => {
    try {
      const data = await apiResults(state.filters, { limit: PAGE_SIZE, offset: 0 });
      if (data.meta) {
        state.treemapItems = await apiTreemapItems();
        applyResults(data, state, els);
      } else {
        setMode(els, state);
      }
    } catch (_) {
      setMode(els, state);
    }
  })();

  // Navigation
  on(els.backButton,     "click", () => { location.href = "/"; });
  on(els.viewLogsButton, "click", () => { location.href = "/logs"; });
  on(els.retryButton,    "click", () => startScan());
  on(els.idleStartBtn,   "click", () => startScan());
  on(els.startButton,    "click", () => { if (state.status !== "scanning") startScan(); });
  on(els.refreshButton,  "click", () => startScan());

  // ── Scan ──────────────────────────────────────────────────────────
  async function startScan() {
    state.status = "scanning";
    state.thresholdMb = 100; // default
    setMode(els, state);
    startScanIndicator(els, state);

    try {
      const task = await apiScan(state.thresholdMb);
      state.scanTaskId = task.task_id || "";
      setText(els.currentPath, t("userdir.scanning.started") || "Scan task started. Waiting for results…");
      const data = await waitForScanResult(state.scanTaskId);
      stopScanIndicator(els, state);
      els.progressFill.style.width = "100%";

      // Load only the first page for the current filters. Treemap stays global.
      const [page, treemapItems] = await Promise.all([
        apiResults(state.filters, { limit: PAGE_SIZE, offset: 0 }),
        apiTreemapItems(),
      ]);
      state.treemapItems = treemapItems;
      applyResults({
        meta:       data.result.meta,
        summary:    data.result.summary,
        stats:      data.result.stats,
        scan_config: data.result.scan_config,
        large_files: data.result.large_files,
        items:      page.items,
        item_count: page.item_count,
      }, state, els);
    } catch (err) {
      stopScanIndicator(els, state);
      state.status = "error";
      setText(els.errorMessage, err.message || String(err));
      setMode(els, state);
    }
  }

  async function waitForScanResult(taskId) {
    if (!taskId) throw new Error("Scan task was not created");
    while (state.status === "scanning") {
      const data = await apiScanStatus(taskId);
      if (data.status === "completed") return data;
      if (data.status === "error") throw new Error(data.error || "Scan failed");
      if (data.status === "missing") throw new Error(data.error || "Scan task not found");
      await new Promise(resolve => setTimeout(resolve, 1000));
    }
    throw new Error("Scan was interrupted");
  }

  function applyResults(data, state, els) {
    state.meta       = data.meta;
    state.summary    = data.summary    || [];
    state.stats      = data.stats      || null;
    state.scanConfig = data.scan_config || null;
    state.largeFiles = data.large_files || [];
    state.items      = data.items      || [];
    state.itemCount  = data.item_count || 0;
    state.listOffset = state.items.length;
    state.hasMoreItems = state.items.length < state.itemCount;

    state.status = state.itemCount > 0 ? "completed" : "empty";
    setMode(els, state);

    if (state.status === "completed") {
      renderResults(els, state);
    }
  }

  // ── Category strip / legend click → filter ─────────────────────
  on(els.catStrip, "click", (e) => {
    const seg = e.target.closest(".userdir-cat-seg");
    if (!seg) return;
    toggleCategoryFilter(seg.dataset.category, els, state);
  });

  on(els.catLegend, "click", (e) => {
    const item = e.target.closest(".userdir-cat-legend-item");
    if (!item) return;
    toggleCategoryFilter(item.dataset.category, els, state);
    els.itemList.scrollIntoView({ behavior: "smooth", block: "nearest" });
  });

  function toggleCategoryFilter(cat, els, state) {
    els.categoryFilter.value  = cat === state.filters.category ? "" : cat;
    state.filters.category    = els.categoryFilter.value;
    reloadItems();
  }

  // ── Filters ─────────────────────────────────────────────────────
  on(els.categoryFilter, "change", () => { state.filters.category  = els.categoryFilter.value; reloadItems(); });
  on(els.typeFilter,     "change", () => { state.filters.itemType  = els.typeFilter.value;     reloadItems(); });
  on(els.minSizeFilter,  "change", () => { state.filters.minSizeMb = els.minSizeFilter.value;  reloadItems(); });
  on(els.clearFiltersButton, "click", () => {
    state.filters = { category: "", itemType: "", minSizeMb: "", search: "" };
    els.categoryFilter.value = "";
    els.typeFilter.value = "";
    els.minSizeFilter.value = "";
    els.searchInput.value = "";
    reloadItems();
  });

  on(els.loadMoreButton, "click", () => loadMoreItems());

  let searchTimer = null;
  on(els.searchInput, "input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      state.filters.search = els.searchInput.value.trim();
      reloadItems();
    }, 300);
  });

  async function reloadItems() {
    if (!state.meta) return;
    try {
      const data  = await apiResults(state.filters, { limit: PAGE_SIZE, offset: 0 });
      state.items     = data.items || [];
      state.itemCount = data.item_count || 0;
      state.listOffset = state.items.length;
      state.hasMoreItems = state.items.length < state.itemCount;
      renderItemList(els, state);
    } catch (err) {
      await showAlert(err.message);
    }
  }

  async function loadMoreItems() {
    if (!state.meta || state.isLoadingItems || !state.hasMoreItems) return;
    state.isLoadingItems = true;
    renderItemList(els, state);
    try {
      const data = await apiResults(state.filters, { limit: PAGE_SIZE, offset: state.listOffset });
      state.items = [...state.items, ...(data.items || [])];
      state.itemCount = data.item_count;
      state.listOffset = state.items.length;
      state.hasMoreItems = state.items.length < state.itemCount;
    } catch (err) {
      await showAlert(err.message);
    } finally {
      state.isLoadingItems = false;
      renderItemList(els, state);
    }
  }

  // ── Copy path ────────────────────────────────────────────────────
  on(els.itemList, "click", async (e) => {
    const btn = e.target.closest(".userdir-copy-btn");
    if (!btn) return;
    try {
      await navigator.clipboard.writeText(btn.dataset.path);
      setText(btn, t("userdir.buttons.copied") || "Copied");
      setTimeout(() => setText(btn, t("userdir.buttons.copyPath") || "Copy"), 900);
    } catch (_) {
      await showAlert(`Path: ${btn.dataset.path}`);
    }
  });
}
