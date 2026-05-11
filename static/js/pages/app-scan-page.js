import { $, on, setText } from "../core/dom.js";
import { ensureDialog, showAlert, showConfirm } from "../core/dialog.js";
import { markI18nReady, t, translateStaticText } from "../locales/i18n.js";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------
const SOURCE_COLORS = {
  registry:  "#2563eb",
  directory: "#16a34a",
  uwp:       "#9333ea",
  invalid:   "#dc2626",
};
const DRIVE_COLORS = ["#2563eb", "#16a34a", "#9333ea", "#f59e0b", "#0891b2", "#dc2626", "#64748b"];

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
function createState() {
  return {
    status: "idle",  // idle | scanning | completed | error | empty
    meta: null,
    summary: null,
    allItems: [],   // cached first result page for summary widgets
    treemapItems: [],
    items: [],      // filtered page
    itemCount: 0,
    timedOutCount: 0,
    driveUsage: null,
    filters: { source: "", status: "", minSize: "", search: "" },
    offset: 0,
    pageSize: 100,
    hasMore: false,
    isLoadingItems: false,
    listRequestId: 0,
    scanTaskId: "",
    stageTimers: [],
  };
}

// ---------------------------------------------------------------------------
// DOM refs
// ---------------------------------------------------------------------------
function getEls() {
  return {
    backButton:          $("#appscanBackButton"),
    clearButton:         $("#appscanClearButton"),
    startButton:         $("#appscanStartButton"),
    startLabel:          $("#appscanStartLabel"),
    statusText:          $("#appscanStatusText"),
    // stat cards
    statTotalWrap:       $("#appscanStatTotalWrap"),
    statTotal:           $("#appscanStatTotal"),
    statTotalSkel:       $("#appscanStatTotalSkel"),
    statSizeWrap:        $("#appscanStatSizeWrap"),
    statSize:            $("#appscanStatSize"),
    statSizeSkel:        $("#appscanStatSizeSkel"),
    statLargestWrap:     $("#appscanStatLargestWrap"),
    statLargest:         $("#appscanStatLargest"),
    statLargestSkel:     $("#appscanStatLargestSkel"),
    // source + residual
    sourceSkel:          $("#appscanSourceSkel"),
    sourceContent:       $("#appscanSourceContent"),
    sourceTotal:         $("#appscanSourceTotal"),
    segTrack:            $("#appscanSegTrack"),
    legend:              $("#appscanLegend"),
    residualPanel:       $("#appscanResidualPanel"),
    residualSkel:        $("#appscanResidualSkel"),
    residualContent:     $("#appscanResidualContent"),
    residualNum:         $("#appscanResidualNum"),
    residualLabel:       $(".appscan-residual-label"),
    jumpInvalidButton:   $("#appscanJumpInvalidButton"),
    residualClean:       $("#appscanResidualClean"),
    // treemap
    treemapWrap:         $("#appscanTreemapWrap"),
    treemapSvg:          $("#appscanTreemapSvg"),
    treemapEmpty:        $("#appscanTreemapEmpty"),
    treemapSkel:         $("#appscanTreemapSkel"),
    // drive usage
    driveContent:        $("#appscanDriveContent"),
    driveMiniPie:        $("#appscanDriveMiniPie"),
    driveLegend:         $("#appscanDriveLegend"),
    driveEmpty:          $("#appscanDriveEmpty"),
    // empty state
    emptyState:          $("#appscanEmptyState"),
    // filter
    filterBar:           $("#appscanFilterBar"),
    filterSource:        $("#appscanFilterSource"),
    filterStatus:        $("#appscanFilterStatus"),
    filterSize:          $("#appscanFilterSize"),
    searchInput:         $("#appscanSearchInput"),
    filterCount:         $("#appscanFilterCount"),
    // list panel
    listPanel:           $("#appscanListPanel"),
    scanningCard:        $("#appscanScanningCard"),
    scanMeta:            $("#appscanScanMeta"),
    stageLabel:          $("#appscanStageLabel"),
    currentPath:         $("#appscanCurrentPath"),
    stageList:           $("#appscanStageList"),
    errorCard:           $("#appscanErrorCard"),
    errorMessage:        $("#appscanErrorMessage"),
    retryButton:         $("#appscanRetryButton"),
    emptyListCard:       $("#appscanEmptyList"),
    listWrap:            $("#appscanListWrap"),
    itemList:            $("#appscanItemList"),
    loadMoreRow:         $("#appscanLoadMoreRow"),
    loadMoreButton:      $("#appscanLoadMoreButton"),
    rescanTimeoutButton: $("#appscanRescanTimeoutButton"),
  };
}

// ---------------------------------------------------------------------------
// Formatting
// ---------------------------------------------------------------------------
function fmtBytes(n) {
  if (n == null || n < 0) return "—";
  if (n === 0) return "0 B";
  const u = ["B", "KB", "MB", "GB", "TB"];
  let i = 0, v = n;
  while (v >= 1024 && i < u.length - 1) { v /= 1024; i++; }
  return `${v.toFixed(v >= 100 ? 0 : v >= 10 ? 1 : 2)} ${u[i]}`;
}

function srcLabel(src) {
  return { registry: t("appscan.sources.registry") || "注册表",
           directory: t("appscan.sources.directory") || "目录扫描",
           uwp: "UWP" }[src] || src;
}

function escHtml(s) {
  return String(s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

// ---------------------------------------------------------------------------
// Squarified Treemap
// ---------------------------------------------------------------------------
function squarify(items, W, H) {
  const total = items.reduce((s, x) => s + (x.size_bytes || 0), 0) || 1;
  const norm = items.map(it => ({ ...it, area: ((it.size_bytes || 0) / total) * W * H }));
  const result = [];
  let x = 0, y = 0, rw = W, rh = H;
  let i = 0;
  while (i < norm.length) {
    const row = [norm[i++]];
    const short = () => Math.min(rw, rh);
    const worst = (r) => {
      const sum = r.reduce((s, n) => s + n.area, 0);
      const s2 = short() * short();
      return Math.max(...r.map(n => Math.max(s2 * n.area / (sum * sum), (sum * sum) / (s2 * n.area))));
    };
    while (i < norm.length) {
      const test = [...row, norm[i]];
      if (worst(test) <= worst(row)) { row.push(norm[i++]); } else break;
    }
    const sum = row.reduce((s, n) => s + n.area, 0);
    if (rw >= rh) {
      const rowW = sum / rh;
      let cy = y;
      for (const n of row) {
        const cellH = (n.area / sum) * rh;
        result.push({ ...n, x, y: cy, w: rowW, h: cellH });
        cy += cellH;
      }
      x += rowW; rw -= rowW;
    } else {
      const rowH = sum / rw;
      let cx = x;
      for (const n of row) {
        const cellW = (n.area / sum) * rw;
        result.push({ ...n, x: cx, y, w: cellW, h: rowH });
        cx += cellW;
      }
      y += rowH; rh -= rowH;
    }
  }
  return result;
}

function renderTreemap(els, items) {
  const wrap = els.treemapWrap;
  const svg  = els.treemapSvg;
  const W = wrap.clientWidth || 1100;
  const H = 180;

  const valid = items.filter(a => a.is_valid && (a.size_bytes || 0) > 0)
                     .sort((a, b) => (b.size_bytes || 0) - (a.size_bytes || 0))
                     .slice(0, 16);

  svg.innerHTML = "";
  svg.setAttribute("width", W);
  svg.setAttribute("height", H);

  if (valid.length === 0) {
    els.treemapEmpty.classList.remove("is-hidden");
    svg.classList.add("is-hidden");
    return;
  }
  els.treemapEmpty.classList.add("is-hidden");
  svg.classList.remove("is-hidden");

  const cells = squarify(valid, W, H);
  const trunc = (s, n) => s.length <= n ? s : s.slice(0, Math.max(1, n - 1)) + "…";
  const addText = (parent, text, x, y, size, weight = "600", opacity = "1") => {
    const el = document.createElementNS("http://www.w3.org/2000/svg", "text");
    el.setAttribute("x", x);
    el.setAttribute("y", y);
    el.setAttribute("fill", "white");
    el.setAttribute("font-size", String(size));
    el.setAttribute("font-weight", weight);
    el.setAttribute("fill-opacity", opacity);
    el.style.pointerEvents = "none";
    el.textContent = text;
    parent.appendChild(el);
  };

  for (const c of cells) {
    const fill  = SOURCE_COLORS[c.source] || "#6b7280";
    const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
    g.style.cursor = "pointer";
    g.setAttribute("data-id", c.id);
    const title = document.createElementNS("http://www.w3.org/2000/svg", "title");
    title.textContent = `${c.name}\n${fmtBytes(c.size_bytes)}\n${c.install_path || ""}`;
    g.appendChild(title);

    const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    rect.setAttribute("x", c.x + 1);
    rect.setAttribute("y", c.y + 1);
    rect.setAttribute("width", Math.max(0, c.w - 2));
    rect.setAttribute("height", Math.max(0, c.h - 2));
    rect.setAttribute("fill", fill);
    rect.setAttribute("fill-opacity", "0.78");
    rect.setAttribute("rx", "3");
    g.appendChild(rect);

    const border = rect.cloneNode();
    border.setAttribute("fill", "none");
    border.setAttribute("stroke", "white");
    border.setAttribute("stroke-width", "1");
    border.setAttribute("fill-opacity", "1");
    g.appendChild(border);

    const textX = c.x + 8;
    const maxChars = Math.max(3, Math.floor((c.w - 14) / 7.2));
    if (c.w > 84 && c.h > 32) {
      addText(g, trunc(c.name, maxChars), textX, c.y + 17, 12, "700");
      if (c.h > 48) addText(g, fmtBytes(c.size_bytes), textX, c.y + 33, 11, "600", "0.9");
    } else if (c.w > 58 && c.h > 36) {
      addText(g, trunc(c.name, Math.max(3, Math.floor((c.w - 12) / 8.2))), c.x + 6, c.y + 16, 10, "700");
      addText(g, fmtBytes(c.size_bytes), c.x + 6, c.y + 30, 10, "600", "0.9");
    } else if (c.w > 52 && c.h > 22) {
      addText(g, fmtBytes(c.size_bytes), c.x + 6, c.y + 16, 10, "600", "0.9");
    }

    g.addEventListener("mouseenter", () => rect.setAttribute("fill-opacity", "0.95"));
    g.addEventListener("mouseleave", () => rect.setAttribute("fill-opacity", "0.78"));
    svg.appendChild(g);
  }
}

function renderDriveUsage(els, usage) {
  const drives = usage?.drives || [];
  const total = usage?.total_size_bytes || 0;
  els.driveLegend.innerHTML = "";
  els.driveMiniPie.innerHTML = "";

  if (!drives.length || total <= 0) {
    els.driveContent.classList.add("is-hidden");
    els.driveEmpty.classList.remove("is-hidden");
    return;
  }
  els.driveContent.classList.remove("is-hidden");
  els.driveEmpty.classList.add("is-hidden");

  let angle = 0;
  drives.forEach((drive, idx) => {
    const portion = total ? drive.size_bytes / total : 0;
    const color = DRIVE_COLORS[idx % DRIVE_COLORS.length];
    const nextAngle = idx === drives.length - 1 ? 360 : angle + portion * 360;
    const segment = portion >= 0.999
      ? document.createElementNS("http://www.w3.org/2000/svg", "circle")
      : document.createElementNS("http://www.w3.org/2000/svg", "path");
    if (portion >= 0.999) {
      segment.setAttribute("cx", "36");
      segment.setAttribute("cy", "36");
      segment.setAttribute("r", "21");
    } else {
      segment.setAttribute("d", describeArc(36, 36, 21, angle, nextAngle));
    }
    segment.setAttribute("fill", "none");
    segment.setAttribute("stroke", color);
    segment.setAttribute("stroke-width", "14");
    segment.setAttribute("stroke-linecap", "butt");
    const title = document.createElementNS("http://www.w3.org/2000/svg", "title");
    title.textContent = `${drive.drive} · ${fmtBytes(drive.size_bytes)} · ${drive.percent.toFixed(1)}%`;
    segment.appendChild(title);
    els.driveMiniPie.appendChild(segment);
    angle = nextAngle;
  });

  els.driveLegend.innerHTML = drives.slice(0, 4).map((drive, idx) => `
    <div class="appscan-drive-legend-item">
      <span class="appscan-drive-name" style="color:${DRIVE_COLORS[idx % DRIVE_COLORS.length]}">${escHtml(drive.drive)}</span>
      <span class="appscan-drive-size">${escHtml(fmtBytes(drive.size_bytes))}</span>
    </div>
  `).join("");
}

function polarPoint(cx, cy, r, angleDegrees) {
  const angleRadians = (angleDegrees - 90) * Math.PI / 180;
  return {
    x: cx + r * Math.cos(angleRadians),
    y: cy + r * Math.sin(angleRadians),
  };
}

function describeArc(cx, cy, r, startAngle, endAngle) {
  const start = polarPoint(cx, cy, r, startAngle);
  const end = polarPoint(cx, cy, r, endAngle);
  const largeArcFlag = endAngle - startAngle > 180 ? 1 : 0;
  return [
    "M", start.x.toFixed(3), start.y.toFixed(3),
    "A", r, r, 0, largeArcFlag, 1, end.x.toFixed(3), end.y.toFixed(3),
  ].join(" ");
}

// ---------------------------------------------------------------------------
// Stage indicator animation (client-side simulation)
// ---------------------------------------------------------------------------
const STAGE_DEFS = [
  { id: "registry",  label: "RegistryAppLocator" },
  { id: "directory", label: "DirectoryAppLocator" },
  { id: "merge",     label: "AppInstallLocator（合并去重）" },
  { id: "sizes",     label: "DirectorySizeAnalyzer（并发）" },
  { id: "aggregate", label: "Aggregation" },
];

function renderStages(el, activeIdx) {
  el.innerHTML = STAGE_DEFS.map((s, i) => {
    const st = i < activeIdx ? "done" : i === activeIdx ? "running" : "pending";
    const stLabel = st === "done" ? "DONE" : st === "running" ? "RUNNING" : "PENDING";
    return `<div class="appscan-stage appscan-stage-${st}">
      <span class="appscan-stage-dot"></span>
      <span class="appscan-stage-name">${escHtml(s.label)}</span>
      <span class="appscan-stage-state">${stLabel}</span>
    </div>`;
  }).join("");
}

function startStageAnimation(els, state) {
  let idx = 0;
  renderStages(els.stageList, idx);
  setText(els.stageLabel, `${t("appscan.labels.currentStage") || "Current stage"}: ${STAGE_DEFS[idx].label}`);

  const intervals = [1800, 1200, 800, 4000, 500];
  let timerIdx = 0;
  function advance() {
    if (state.status !== "scanning") return;
    idx = Math.min(idx + 1, STAGE_DEFS.length - 1);
    renderStages(els.stageList, idx);
    setText(els.stageLabel, `${t("appscan.labels.currentStage") || "Current stage"}: ${STAGE_DEFS[idx].label}`);
    if (idx < STAGE_DEFS.length - 1 && timerIdx < intervals.length - 1) {
      timerIdx++;
      const id = setTimeout(advance, intervals[timerIdx]);
      state.stageTimers.push(id);
    }
  }
  const id0 = setTimeout(advance, intervals[0]);
  state.stageTimers.push(id0);
}

function clearStageTimers(state) {
  for (const id of state.stageTimers) clearTimeout(id);
  state.stageTimers = [];
}

// ---------------------------------------------------------------------------
// Render: stat cards
// ---------------------------------------------------------------------------
function showCardSkel(els, scanning) {
  const pairs = [
    [els.statTotalWrap, els.statTotalSkel],
    [els.statSizeWrap,  els.statSizeSkel],
    [els.statLargestWrap, els.statLargestSkel],
  ];
  for (const [val, skel] of pairs) {
    val.classList.toggle("is-hidden", scanning);
    skel.classList.toggle("is-hidden", !scanning);
  }
}

function renderStatCards(els, summary) {
  showCardSkel(els, false);
  setText(els.statTotal, summary.total_apps ?? "—");
  setText(els.statSize, fmtBytes(summary.total_size_bytes));
  els.statLargestWrap.parentElement?.querySelector(".appscan-largest-sub")?.remove();
  if (summary.largest_app_name) {
    setText(els.statLargest, fmtBytes(summary.largest_app_bytes));
    const sub = document.createElement("div");
    sub.className = "appscan-largest-sub";
    sub.textContent = summary.largest_app_name;
    sub.title = summary.largest_app_name;
    els.statLargestWrap.insertAdjacentElement("afterend", sub);
    els.statLargest.title = `${summary.largest_app_name} · ${fmtBytes(summary.largest_app_bytes)}`;
  } else {
    setText(els.statLargest, "—");
    els.statLargest.removeAttribute("title");
  }
}

// ---------------------------------------------------------------------------
// Render: source bar
// ---------------------------------------------------------------------------
function showSourceSkel(els, scanning) {
  els.sourceSkel.classList.toggle("is-hidden", !scanning);
  els.sourceContent.classList.toggle("is-hidden", scanning);
  els.residualSkel.classList.toggle("is-hidden", !scanning);
  els.residualContent.classList.toggle("is-hidden", scanning);
}

function renderSourceBar(els, summary) {
  showSourceSkel(els, false);
  const total = summary.total_apps || 1;
  const scope = t("appscan.labels.latestScan") || "Latest scan";
  setText(els.sourceTotal, `${scope} · ${summary.total_apps} ${t("appscan.labels.itemsUnit") || "items"}`);

  const segs = [
    { key: "registry",  label: t("appscan.sources.registry") || "注册表",   n: summary.by_source?.registry  || 0, color: SOURCE_COLORS.registry },
    { key: "directory", label: t("appscan.sources.directory") || "目录扫描", n: summary.by_source?.directory || 0, color: SOURCE_COLORS.directory },
    { key: "uwp",       label: "UWP",                                         n: summary.by_source?.uwp       || 0, color: SOURCE_COLORS.uwp },
    { key: "invalid",   label: t("appscan.status.invalid") || "残留",         n: summary.invalid_count        || 0, color: SOURCE_COLORS.invalid },
  ];

  els.segTrack.innerHTML = segs.filter(s => s.n > 0)
    .map(s => `<div class="appscan-seg" style="width:${(s.n/total)*100}%;background:${s.color}" title="${escHtml(s.label)} · ${s.n}"></div>`)
    .join("");

  els.legend.innerHTML = segs.map(s => `
    <div class="appscan-legend-item">
      <span class="appscan-legend-dot" style="background:${s.color}"></span>
      <span>${escHtml(s.label)}</span>
      <span class="appscan-legend-n">${s.n}</span>
      <span class="appscan-legend-pct">${Math.round((s.n/total)*100)}%</span>
    </div>`).join("");

  // residual callout
  const n = summary.invalid_count || 0;
  setText(els.residualNum, n);
  if (n > 0) {
    els.residualPanel.classList.add("appscan-residual-active");
    els.jumpInvalidButton.classList.remove("is-hidden");
    els.residualClean.classList.add("is-hidden");
  } else {
    els.residualPanel.classList.remove("appscan-residual-active");
    els.jumpInvalidButton.classList.add("is-hidden");
    els.residualClean.classList.remove("is-hidden");
  }
}

// ---------------------------------------------------------------------------
// Render: list items
// ---------------------------------------------------------------------------
function makeIconClass(item) {
  if (!item.is_valid) return "appscan-icon is-invalid";
  if (item.is_portable) return "appscan-icon is-portable";
  return `appscan-icon src-${item.source}`;
}

function iconLetter(item) {
  if (!item.is_valid) return "!";
  if (item.is_portable) return "P";
  if (item.source === "uwp") return "U";
  return (item.name || "?").charAt(0).toUpperCase();
}

function itemStatusClass(item) {
  if (!item.is_valid) return "is-invalid";
  if (!item.install_path) return "is-unknown";
  return "is-valid";
}

function itemStatusLabel(item) {
  if (!item.is_valid) return t("appscan.status.invalid") || "invalid";
  if (!item.install_path) return t("appscan.status.unknownPath") || "unknown path";
  return t("appscan.status.valid") || "valid";
}

function sizeSourceLabel(item) {
  const status = sizeSourceStatus(item);
  const labels = {
    computed: t("appscan.sizeSource.computed") || "computed",
    estimated: t("appscan.sizeSource.estimated") || "estimated",
    partialTimeout: t("appscan.sizeSource.partialTimeout") || "partial timeout",
    timeout: t("appscan.sizeSource.timeout") || "size skipped",
    pending: t("appscan.sizeSource.pending") || "pending",
  };
  return status ? labels[status] : "";
}

function sizeSourceStatus(item) {
  const notes = Array.isArray(item.notes) ? item.notes : [];
  if (notes.includes("Size computed from directory")) {
    return "computed";
  }
  if (notes.includes("Estimated size from registry")) {
    return "estimated";
  }
  if (notes.includes("Directory size scan timed out; partial size")) {
    return "partialTimeout";
  }
  if (notes.includes("Directory size scan skipped after timeout")) {
    return "timeout";
  }
  if (item.is_valid && item.install_path && !item.size_bytes) {
    return "pending";
  }
  return "";
}

function renderItems(els, state) {
  const maxSize = state.items.reduce((m, a) => Math.max(m, a.size_bytes || 0), 1);
  const frag = document.createDocumentFragment();

  for (const item of state.items) {
    const pct = item.size_bytes ? Math.min(100, (item.size_bytes / maxSize) * 100) : 0;
    const srcColor = SOURCE_COLORS[item.source] || "#6b7280";
    const row = document.createElement("div");
    row.className = "appscan-item-row" + (!item.is_valid ? " is-invalid" : "");
    row.dataset.id = item.id;
    row.innerHTML = buildRowHTML(item, pct, srcColor);

    frag.appendChild(row);
  }

  els.itemList.appendChild(frag);
  updateFilterCount(els, state);
  updateTimeoutRescanButton(els, state);
}

function hasTimedOutItems(items) {
  return (items || []).some(item => {
    const notes = Array.isArray(item.notes) ? item.notes : [];
    return notes.includes("Directory size scan timed out; partial size")
      || notes.includes("Directory size scan skipped after timeout");
  });
}

function updateTimeoutRescanButton(els, state) {
  if (!els.rescanTimeoutButton) return;
  const visible = state.status === "completed" && (state.timedOutCount > 0 || hasTimedOutItems(state.items));
  els.rescanTimeoutButton.classList.toggle("is-hidden", !visible);
  els.rescanTimeoutButton.disabled = state.status === "scanning" || state.isLoadingItems;
}

function updateFilterCount(els, state) {
  const shownN = state.items.length;
  const totalN = state.itemCount;
  setText(els.filterCount, `${shownN} / ${totalN} ${t("appscan.labels.itemsUnit") || "items"}`);
}

// ---------------------------------------------------------------------------
// UI mode switcher
// ---------------------------------------------------------------------------
function setMode(els, state) {
  const { status } = state;

  // scanning card
  els.scanningCard.classList.toggle("is-hidden", status !== "scanning");
  // error card
  els.errorCard.classList.toggle("is-hidden", status !== "error");
  // empty (no apps found)
  els.emptyListCard.classList.toggle("is-hidden", !(status === "completed" && state.itemCount === 0));
  // results list
  els.listWrap.classList.toggle("is-hidden", !(status === "completed" && state.itemCount > 0));

  // page empty state (pre-scan)
  els.emptyState.classList.toggle("is-hidden", status !== "idle");

  // buttons
  const scanning = status === "scanning";
  els.startButton.disabled = scanning;
  els.clearButton.disabled = scanning || !state.meta;
  updateTimeoutRescanButton(els, state);
  setText(
    els.startLabel,
    scanning
      ? (t("appscan.status.scanning") || "扫描中…")
      : status === "completed"
        ? (t("appscan.buttons.rescan") || "重新扫描")
        : (t("appscan.buttons.startScan") || "开始扫描"),
  );

  // stat card skeletons
  showCardSkel(els, scanning);
  showSourceSkel(els, scanning);

  // treemap skel
  els.treemapSkel.classList.toggle("is-hidden", !scanning);
  els.treemapSvg.classList.toggle("is-hidden", scanning);
  els.treemapEmpty.classList.add("is-hidden");

  // status bar
  if (status === "idle")     setText(els.statusText, t("appscan.status.idle")     || "准备就绪");
  if (status === "scanning") setText(els.statusText, t("appscan.status.scanning") || "扫描中…");
  if (status === "error")    setText(els.statusText, t("appscan.status.error")    || "扫描失败");
  if (status === "completed" && state.meta) {
    const dur = ((state.meta.duration_ms || 0) / 1000).toFixed(1);
    const keys = state.meta.scanned_registry_keys || 0;
    setText(els.statusText, `${t("appscan.status.done") || "扫描完成"} · ${dur}s · ${keys} ${t("appscan.status.regKeys") || "注册表键"}`);
  }
}

// ---------------------------------------------------------------------------
// Apply scan results
// ---------------------------------------------------------------------------
function applyResults(data, state, els) {
  clearStageTimers(state);
  state.status = "completed";
  state.meta = data.meta;
  state.summary = data.summary || buildFakeSummary(data.meta);
  state.allItems = data.items || [];
  state.treemapItems = data.treemap_items || state.treemapItems || [];
  state.items = state.allItems;
  state.itemCount = data.item_count || state.allItems.length;
  state.timedOutCount = data.timed_out_count || 0;
  state.driveUsage = data.drive_usage || state.driveUsage || null;
  state.hasMore = state.items.length < state.itemCount;

  setMode(els, state);
  els.itemList.innerHTML = "";
  renderDriveUsage(els, state.driveUsage);
  renderTreemap(els, state.treemapItems);
  if (state.summary) {
    renderStatCards(els, state.summary);
    renderSourceBar(els, state.summary);
  }

  if (state.itemCount === 0) {
    updateLoadMore(els, state);
    return;
  }

  renderItems(els, state);
  updateLoadMore(els, state);
}

function buildFakeSummary(meta) {
  if (!meta) return null;
  return {
    total_apps: meta.total_apps,
    total_size_bytes: meta.total_size_bytes,
    invalid_count: meta.invalid_count,
    by_source: {},
    largest_app_name: null,
    largest_app_bytes: null,
  };
}

function updateLoadMore(els, state) {
  if (state.hasMore) {
    els.loadMoreRow.classList.remove("is-hidden");
  } else {
    els.loadMoreRow.classList.add("is-hidden");
  }
  els.loadMoreButton.disabled = state.isLoadingItems;
}

// ---------------------------------------------------------------------------
// API helpers
// ---------------------------------------------------------------------------
function buildParams(state) {
  const { source, status, minSize, search } = state.filters;
  const p = new URLSearchParams();
  if (source)    p.set("source",    source);
  if (status)    p.set("status",    status);
  if (minSize)   p.set("min_size",  minSize);
  if (search)    p.set("search",    search);
  p.set("limit",  String(state.pageSize));
  p.set("offset", String(state.offset));
  return p;
}

async function fetchPage(state) {
  const res = await fetch(`/app-scan/results?${buildParams(state)}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function fetchTopItems() {
  const res = await fetch("/app-scan/top-items?limit=16");
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const data = await res.json();
  return data.items || [];
}

async function fetchDriveUsage() {
  const res = await fetch("/app-scan/drive-usage");
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

function fallbackTopItems(items) {
  return (items || [])
    .filter(item => item.is_valid)
    .sort((a, b) => (b.size_bytes || 0) - (a.size_bytes || 0))
    .slice(0, 16);
}

async function startScanTask() {
  const res = await fetch("/app-scan/scan", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ max_concurrency: 6 }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

async function startSizeRescanTask() {
  const res = await fetch("/app-scan/size-rescan", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ max_concurrency: 6 }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

async function fetchScanTask(taskId) {
  const res = await fetch(`/app-scan/scan/${encodeURIComponent(taskId)}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function reloadFilteredList(state, els) {
  const requestId = ++state.listRequestId;
  state.isLoadingItems = true;
  updateLoadMore(els, state);

  try {
    const data = await fetchPage(state);
    if (requestId !== state.listRequestId) return;
    state.items = data.items || [];
    state.itemCount = data.item_count || 0;
    state.timedOutCount = data.timed_out_count || state.timedOutCount || 0;
    state.hasMore = state.offset + state.items.length < state.itemCount;

    els.itemList.innerHTML = "";
    renderItems(els, state);
  } finally {
    if (requestId === state.listRequestId) {
      state.isLoadingItems = false;
      updateLoadMore(els, state);
    }
  }
}

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------
export function initAppScanPage() {
  ensureDialog();
  translateStaticText();
  markI18nReady();

  const state = createState();
  const els = getEls();
  let searchTimer = null;

  // ── Navigation ──────────────────────────────────────────────────
  on(els.backButton,    "click", () => { location.href = "/"; });

  // ── Start / Stop scan ───────────────────────────────────────────
  on(els.startButton, "click", async () => {
    if (state.status === "scanning") return; // no real cancel on sync endpoint

    state.status = "scanning";
    state.offset = 0;
    state.items = [];
    state.allItems = [];
    state.treemapItems = [];
    state.driveUsage = null;
    state.timedOutCount = 0;
    state.summary = null;
    state.meta = null;
    state.listRequestId += 1;

    els.itemList.innerHTML = "";
    renderDriveUsage(els, null);
    renderTreemap(els, []);
    setMode(els, state);
    renderStages(els.stageList, 0);
    setText(els.scanMeta, t("appscan.status.scanMetaStart") || "Scanning registry and install directories...");
    startStageAnimation(els, state);

    try {
      const task = await startScanTask();
      state.scanTaskId = task.task_id || "";
      const data = state.scanTaskId ? await waitForScanResult(state, els, state.scanTaskId) : task;
      const result = data.result || data;
      const [page, treemapItems, driveUsage] = await Promise.all([
        fetchPage(state).catch(() => ({ items: result.items || [], item_count: result.item_count || 0 })),
        fetchTopItems().catch(() => fallbackTopItems(result.items)),
        fetchDriveUsage().catch(() => null),
      ]);
      if (result.meta) {
        const keys = result.meta.scanned_registry_keys || 0;
        const dirs = result.meta.scanned_directories || 0;
        const scanMetaDone = t("appscan.status.scanMetaDone");
        setText(
          els.scanMeta,
          typeof scanMetaDone === "function"
            ? scanMetaDone(keys, dirs)
            : `Scanned ${keys} registry keys · ${dirs} directories`,
        );
      }
      applyResults({
        ...result,
        items: page.items || [],
        item_count: page.item_count || 0,
        treemap_items: treemapItems,
        drive_usage: driveUsage,
      }, state, els);
      if (state.scanTaskId && data.status !== "completed") {
        pollFinalScanResult(state, els, state.scanTaskId);
      }
    } catch (err) {
      clearStageTimers(state);
      state.status = "error";
      setMode(els, state);
      setText(els.errorMessage, err.message || String(err));
    }
  });

  on(els.retryButton, "click", () => els.startButton.click());

  on(els.rescanTimeoutButton, "click", async () => {
    const ok = await showConfirm(
      t("appscan.confirmRescanTimeout.message") || "Recalculate timed-out size entries? This may take a long time.",
      {
        title: t("appscan.confirmRescanTimeout.title") || "Recalculate Timed-Out Items",
        confirmText: t("appscan.confirmRescanTimeout.confirmText") || "Recalculate",
      },
    );
    if (!ok) return;
    const original = els.rescanTimeoutButton.textContent;
    els.rescanTimeoutButton.disabled = true;
    els.rescanTimeoutButton.textContent = t("appscan.status.recalculating") || "重新计算中…";
    try {
      const task = await startSizeRescanTask();
      state.scanTaskId = task.task_id || "";
      const data = await waitForScanResult(state, els, state.scanTaskId);
      const result = data.result || data;
      const [page, treemapItems, driveUsage] = await Promise.all([
        fetchPage(state),
        fetchTopItems(),
        fetchDriveUsage(),
      ]);
      applyResults({
        ...result,
        items: page.items || [],
        item_count: page.item_count || 0,
        treemap_items: treemapItems,
        drive_usage: driveUsage,
      }, state, els);
    } catch (err) {
      await showAlert(err.message || String(err));
    } finally {
      els.rescanTimeoutButton.textContent = original;
      updateTimeoutRescanButton(els, state);
    }
  });

  async function waitForScanResult(state, els, taskId) {
    if (!taskId) throw new Error("Scan task was not created");
    while (state.scanTaskId === taskId) {
      const data = await fetchScanTask(taskId);
      renderTaskProgress(els, data);
      if (data.result) return data;
      if (data.status === "completed") return data;
      if (data.status === "error") throw new Error(data.error || "Scan failed");
      if (data.status === "missing") throw new Error(data.error || "Scan task not found");
      await new Promise(resolve => setTimeout(resolve, 1000));
    }
    throw new Error("Scan was interrupted");
  }

  async function pollFinalScanResult(state, els, taskId) {
    try {
      while (taskId === state.scanTaskId) {
        const data = await fetchScanTask(taskId);
        if (data.status === "completed" && data.result) {
          const [page, treemapItems, driveUsage] = await Promise.all([
            fetchPage(state),
            fetchTopItems(),
            fetchDriveUsage(),
          ]);
          applyResults({
            ...data.result,
            items: page.items || [],
            item_count: page.item_count || 0,
            treemap_items: treemapItems,
            drive_usage: driveUsage,
          }, state, els);
          return;
        }
        if (data.status === "error" || data.status === "missing") return;
        await new Promise(resolve => setTimeout(resolve, 1500));
      }
    } catch {
      // Size enrichment is best-effort after the discovery result is visible.
    }
  }

  function renderTaskProgress(els, data) {
    const stage = data.stage || "queued";
    const activeIdx = Math.max(0, STAGE_DEFS.findIndex(s => s.id === stage));
    renderStages(els.stageList, activeIdx >= 0 ? activeIdx : 0);
    setText(els.stageLabel, `${t("appscan.labels.currentStage") || "Current stage"}: ${stage}`);
    const progress = data.progress || {};
    const total = progress.total_apps || 0;
    const keys = progress.scanned_registry_keys || 0;
    const dirs = progress.scanned_directories || 0;
    const scanProgress = t("appscan.status.scanProgress");
    setText(
      els.scanMeta,
      typeof scanProgress === "function"
        ? scanProgress(total, keys, dirs)
        : `Apps ${total} · Registry ${keys} · Directories ${dirs}`,
    );
  }

  // ── Filters ─────────────────────────────────────────────────────
  async function applyFilters() {
    state.offset = 0;
    try {
      await reloadFilteredList(state, els);
    } catch (err) {
      await showAlert(err.message || String(err));
    }
  }

  on(els.filterSource,    "change", () => { state.filters.source    = els.filterSource.value;    applyFilters(); });
  on(els.filterStatus,    "change", () => { state.filters.status    = els.filterStatus.value;    applyFilters(); });
  on(els.filterSize,      "change", () => { state.filters.minSize   = els.filterSize.value;      applyFilters(); });
  on(els.searchInput, "input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      state.filters.search = els.searchInput.value.trim();
      applyFilters();
    }, 280);
  });

  // ── Jump to invalid ─────────────────────────────────────────────
  on(els.jumpInvalidButton, "click", () => {
    els.filterStatus.value = "invalid";
    state.filters.status = "invalid";
    applyFilters();
    els.filterBar.scrollIntoView({ behavior: "smooth", block: "start" });
  });

  // ── List clicks ─────────────────────────────────────────────────
  on(els.itemList, "click", async (e) => {
    const row = e.target.closest(".appscan-item-row");
    if (!row) return;

    // copy btn
    const copyButton = e.target.closest("[data-action='copy']");
    if (copyButton) {
      const path = row.querySelector(".appscan-path")?.title || "";
      if (!path) return;
      const copied = await copyToClipboard(path);
      if (copied) {
        const original = copyButton.textContent;
        copyButton.textContent = t("appscan.actions.copied") || "已复制";
        copyButton.disabled = true;
        setTimeout(() => {
          copyButton.textContent = original;
          copyButton.disabled = false;
        }, 900);
      }
      return;
    }
  });

  // ── Load more ───────────────────────────────────────────────────
  on(els.loadMoreButton, "click", async () => {
    if (state.isLoadingItems || !state.hasMore) return;
    state.isLoadingItems = true;
    els.loadMoreButton.disabled = true;
    state.offset += state.pageSize;
    try {
      const data = await fetchPage(state);
      const newItems = data.items || [];
      state.items = state.items.concat(newItems);
      state.hasMore = state.offset + newItems.length < (data.item_count || 0);
      state.itemCount = data.item_count || state.itemCount;
      state.timedOutCount = data.timed_out_count || state.timedOutCount || 0;

      const maxSize = state.items.reduce((m, a) => Math.max(m, a.size_bytes || 0), 1);
      const frag = document.createDocumentFragment();
      for (const item of newItems) {
        const pct = item.size_bytes ? Math.min(100, (item.size_bytes / maxSize) * 100) : 0;
        const srcColor = SOURCE_COLORS[item.source] || "#6b7280";
        const row = document.createElement("div");
        row.className = "appscan-item-row" + (!item.is_valid ? " is-invalid" : "");
        row.dataset.id = item.id;
        row.innerHTML = buildRowHTML(item, pct, srcColor);
        frag.appendChild(row);
      }
      els.itemList.appendChild(frag);
      updateFilterCount(els, state);
    } catch (err) {
      state.offset = Math.max(0, state.offset - state.pageSize);
      await showAlert(err.message || String(err));
    } finally {
      state.isLoadingItems = false;
      updateLoadMore(els, state);
    }
  });

  on(els.clearButton, "click", () => clearResults(state, els));

  // ── Load existing results on mount ──────────────────────────────
  loadExistingResults(state, els);
}

// ---------------------------------------------------------------------------
// Load existing on mount
// ---------------------------------------------------------------------------
async function loadExistingResults(state, els) {
  try {
    const res = await fetch("/app-scan/results?limit=100");
    if (!res.ok) return;
    const data = await res.json();
    if (!data.meta) {
      // No previous results
      state.status = "idle";
      setMode(els, state);
      return;
    }
    const [treemapItems, driveUsage] = await Promise.all([fetchTopItems(), fetchDriveUsage()]);
    applyResults({ ...data, treemap_items: treemapItems, drive_usage: driveUsage }, state, els);
  } catch (_) {
    state.status = "idle";
    setMode(els, state);
  }
}

async function clearResults(state, els) {
  if (!state.meta || state.status === "scanning") return;
  const ok = await showConfirm(
    t("appscan.confirmClear.message") || "Clear all application scan results?",
    {
      title: t("appscan.confirmClear.title") || "Clear Results",
      confirmText: t("appscan.confirmClear.confirmText") || "Clear",
    },
  );
  if (!ok) return;
  try {
    els.clearButton.disabled = true;
    const res = await fetch("/app-scan/results", { method: "DELETE" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    state.status = "idle";
    state.meta = null;
    state.summary = null;
    state.allItems = [];
    state.treemapItems = [];
    state.driveUsage = null;
    state.items = [];
    state.itemCount = 0;
    state.timedOutCount = 0;
    state.offset = 0;
    state.hasMore = false;
    els.itemList.innerHTML = "";
    renderTreemap(els, []);
    renderDriveUsage(els, null);
    setMode(els, state);
  } catch (err) {
    await showAlert(err.message || String(err));
  } finally {
    els.clearButton.disabled = !state.meta;
  }
}

// ---------------------------------------------------------------------------
// Row HTML builder (used for load-more)
// ---------------------------------------------------------------------------
function buildRowHTML(item, pct, srcColor) {
  return `
    <div class="appscan-item-name-col">
      <div class="${makeIconClass(item)}">${iconLetter(item)}</div>
      <div class="appscan-name-box">
        <div class="appscan-name" title="${escHtml(item.name)}">
          ${escHtml(item.name)}
          ${item.is_portable ? `<span class="appscan-portable-tag">PORTABLE</span>` : ""}
        </div>
        <div class="appscan-path" title="${escHtml(item.install_path || '')}">${escHtml(item.install_path || "(无安装路径)")}</div>
      </div>
    </div>
    <div class="appscan-size-col">
      <span class="appscan-size-num">${sizeSourceStatus(item) === "partialTimeout" ? "&gt; " : ""}${fmtBytes(item.size_bytes)}</span>
      ${sizeSourceLabel(item) ? `<span class="appscan-size-source">${escHtml(sizeSourceLabel(item))}</span>` : ""}
      ${item.is_valid && item.size_bytes ? `<div class="appscan-size-bar"><span style="width:${pct}%;background:${srcColor}"></span></div>` : ""}
    </div>
    <div class="appscan-meta-col">
      <div class="appscan-version">${escHtml(item.version || "—")}</div>
      <div class="appscan-publisher">${escHtml(item.publisher || (item.is_portable ? "Portable" : "—"))}</div>
    </div>
    <div class="appscan-source-col">
      <span class="appscan-source-tag" style="border-color:${srcColor}40;color:${srcColor};background:${srcColor}10">${escHtml(srcLabel(item.source))}</span>
    </div>
    <div>
      <span class="appscan-status-tag ${itemStatusClass(item)}">${itemStatusLabel(item)}</span>
    </div>
    <div class="appscan-act-col">
      <button class="appscan-copy-btn" data-action="copy" title="${escHtml(t('appscan.actions.copyPath') || '复制路径')}" ${!item.install_path ? "disabled" : ""}>${escHtml(t("appscan.actions.copy") || "复制")}</button>
    </div>`;
}

// ---------------------------------------------------------------------------
// Clipboard
// ---------------------------------------------------------------------------
async function copyToClipboard(text) {
  if (!text) return false;
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.cssText = "position:fixed;opacity:0";
    document.body.appendChild(ta);
    ta.select();
    const copied = document.execCommand("copy");
    document.body.removeChild(ta);
    return copied;
  }
}
