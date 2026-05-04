import { $, on, setText } from "../core/dom.js";
import { ensureDialog, showConfirm } from "../core/dialog.js";
import { formatDisplayTime } from "../core/format.js";
import { markI18nReady, t, translateStaticText } from "../locales/i18n.js";

function createRecycleState() {
  return {
    records: [],
    selectedIds: new Set(),
    isLoading: false,
    isRestoring: false,
    isPurging: false,
  };
}

function getRecycleElements() {
  return {
    refreshRecycleButton: $("#refreshRecycleButton"),
    backButton: $("#backButton"),
    openLogsButton: $("#openLogsButton"),
    selectAllRecycleButton: $("#selectAllRecycleButton"),
    invertRecycleSelectionButton: $("#invertRecycleSelectionButton"),
    restoreSelectedButton: $("#restoreSelectedButton"),
    purgeSelectedButton: $("#purgeSelectedButton"),
    recycleCategoryFilter: $("#recycleCategoryFilter"),
    recycleResultBody: $("#recycleResultBody"),
    recycleItemCount: $("#recycleItemCount"),
    recycleTotalSize: $("#recycleTotalSize"),
    selectedRecycleCount: $("#selectedRecycleCount"),
    recycleStatus: $("#recycleStatus"),
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
    .replaceAll("'", "&#39;");
}

function getFilteredRecords(els, state) {
  const category = els.recycleCategoryFilter?.value || "";

  return state.records.filter((record) => {
    if (category && record.category !== category) return false;
    return !record.restored_at;
  });
}

function getActiveRecords(state) {
  return state.records.filter((record) => !record.restored_at);
}

function updateControls(els, state) {
  const activeRecords = getActiveRecords(state);
  const visibleRecords = getFilteredRecords(els, state);
  const busy = state.isLoading || state.isRestoring || state.isPurging;
  const hasActiveRecords = activeRecords.length > 0;
  const hasVisibleRecords = visibleRecords.length > 0;
  const hasSelection = state.selectedIds.size > 0;

  if (els.backButton) els.backButton.disabled = busy;
  if (els.openLogsButton) els.openLogsButton.disabled = busy;
  if (els.refreshRecycleButton) els.refreshRecycleButton.disabled = busy;
  if (els.recycleCategoryFilter) {
    els.recycleCategoryFilter.disabled = busy || !hasActiveRecords;
  }
  if (els.selectAllRecycleButton) {
    els.selectAllRecycleButton.disabled = busy || !hasVisibleRecords;
  }
  if (els.invertRecycleSelectionButton) {
    els.invertRecycleSelectionButton.disabled = busy || !hasVisibleRecords;
  }
  if (els.restoreSelectedButton) {
    els.restoreSelectedButton.disabled = busy || !hasSelection;
  }
  if (els.purgeSelectedButton) {
    els.purgeSelectedButton.disabled = busy || !hasSelection;
  }

  els.recycleResultBody
    ?.querySelectorAll('input[type="checkbox"]')
    .forEach((checkbox) => {
      checkbox.disabled = busy;
    });
}

function renderSummary(els, state) {
  const activeRecords = getActiveRecords(state);
  const totalSize = activeRecords.reduce((sum, record) => {
    return sum + Number(record.size || 0);
  }, 0);

  setText(els.recycleItemCount, activeRecords.length);
  setText(els.recycleTotalSize, formatBytes(totalSize));
  setText(els.selectedRecycleCount, state.selectedIds.size);
}

function renderTable(els, state) {
  if (!els.recycleResultBody) return;

  const records = getFilteredRecords(els, state);

  if (records.length === 0) {
    els.recycleResultBody.innerHTML = `
      <tr class="empty-row">
        <td colspan="7">${t("recycle.noRecords")}</td>
      </tr>
    `;
    renderSummary(els, state);
    updateControls(els, state);
    return;
  }

  els.recycleResultBody.innerHTML = records
    .map((record) => {
      const checked = state.selectedIds.has(record.id) ? "checked" : "";
      const disabled = state.isLoading || state.isRestoring || state.isPurging ? "disabled" : "";
      const originalPath = escapeHtml(record.original_path);
      const recyclePath = escapeHtml(record.recycle_path);

      return `
      <tr>
        <td class="col-check">
          <input type="checkbox" data-id="${escapeHtml(record.id)}" ${checked} ${disabled} />
        </td>
        <td class="path-input-cell">
          <input class="path-readonly-input" type="text" value="${originalPath}" title="${originalPath}" readonly />
        </td>
        <td class="path-input-cell">
          <input class="path-readonly-input" type="text" value="${recyclePath}" title="${recyclePath}" readonly />
        </td>
        <td>${formatBytes(record.size)}</td>
        <td>${escapeHtml(toCategoryLabel(record.category))}</td>
        <td>${escapeHtml(record.source || "-")}</td>
        <td>${formatDisplayTime(record.created_at)}</td>
      </tr>
    `;
    })
    .join("");

  renderSummary(els, state);
  updateControls(els, state);
}

async function loadRecycleRecords(els, state) {
  state.isLoading = true;
  setText(els.recycleStatus, t("recycle.status.loading"));
  updateControls(els, state);

  try {
    const res = await fetch("/recycle/loadRecycleRecords");
    if (!res.ok) throw new Error(`Recycle API failed: ${res.status}`);

    state.records = await res.json();
    state.selectedIds.clear();

    setText(els.recycleStatus, t("recycle.status.loaded"));
    renderTable(els, state);
  } catch (error) {
    console.error(error);
    setText(els.recycleStatus, t("recycle.status.loadFailed"));
  } finally {
    state.isLoading = false;
    updateControls(els, state);
  }
}

function selectAllVisible(els, state) {
  getFilteredRecords(els, state).forEach((record) => {
    state.selectedIds.add(record.id);
  });

  renderTable(els, state);
}

function invertSelection(els, state) {
  getFilteredRecords(els, state).forEach((record) => {
    if (state.selectedIds.has(record.id)) {
      state.selectedIds.delete(record.id);
    } else {
      state.selectedIds.add(record.id);
    }
  });

  renderTable(els, state);
}

async function restoreSelected(els, state) {
  const ids = Array.from(state.selectedIds);

  if (ids.length === 0) {
    setText(els.recycleStatus, t("recycle.status.emptySelection"));
    return;
  }

  const ok = await showConfirm(t("recycle.confirmRestore", ids.length));
  if (!ok) return;

  setText(els.recycleStatus, t("recycle.status.restoring"));
  state.isRestoring = true;
  updateControls(els, state);

  try {
    const res = await fetch("/recycle/restore", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ ids }),
    });

    if (!res.ok) throw new Error(`Restore API failed: ${res.status}`);

    await loadRecycleRecords(els, state);
    setText(els.recycleStatus, t("recycle.status.restored"));
  } catch (error) {
    console.error(error);
    setText(els.recycleStatus, t("recycle.status.restoreFailed"));
  } finally {
    state.isRestoring = false;
    updateControls(els, state);
  }
}

function toCategoryLabel(value) {
  return (
    {
      temp: t("common.categories.temp"),
      browser_cache: t("common.categories.browserCache"),
      log: t("common.categories.log"),
      thumbnail: t("common.categories.thumbnail"),
      empty: t("common.categories.empty"),
    }[value] ?? value ?? "-"
  );
}

async function purgeSelected(els, state) {
  const ids = Array.from(state.selectedIds);

  if (ids.length === 0) {
    setText(els.recycleStatus, t("recycle.status.emptySelection"));
    return;
  }

  const ok = await showConfirm(t("recycle.confirmPurge", ids.length));
  if (!ok) return;

  setText(els.recycleStatus, t("recycle.status.purging"));
  state.isPurging = true;
  updateControls(els, state);

  try {
    const res = await fetch("/recycle/purge", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ ids }),
    });

    if (!res.ok) throw new Error(`Purge API failed: ${res.status}`);

    await loadRecycleRecords(els, state);
    setText(els.recycleStatus, t("recycle.status.purged"));
  } catch (error) {
    console.error(error);
    setText(els.recycleStatus, t("recycle.status.purgeFailed"));
  } finally {
    state.isPurging = false;
    updateControls(els, state);
  }
}

function bindRecycleEvents(els, state) {
  on(els.backButton, "click", () => {
    location.href = "/";
  });
  on(els.refreshRecycleButton, "click", () => loadRecycleRecords(els, state));
  on(els.selectAllRecycleButton, "click", () => selectAllVisible(els, state));
  on(els.invertRecycleSelectionButton, "click", () => invertSelection(els, state));
  on(els.restoreSelectedButton, "click", () => restoreSelected(els, state));
  on(els.purgeSelectedButton, "click", () => purgeSelected(els, state));
  on(els.recycleCategoryFilter, "change", () => renderTable(els, state));
  on(els.openLogsButton, "click", () => {location.href = "/logs";});

  on(els.recycleResultBody, "change", (event) => {
    const checkbox = event.target;
    if (checkbox.type !== "checkbox") return;

    const id = checkbox.dataset.id;
    if (!id) return;

    if (checkbox.checked) {
      state.selectedIds.add(id);
    } else {
      state.selectedIds.delete(id);
    }

    renderSummary(els, state);
    updateControls(els, state);
  });
}

export function initRecyclePage() {
  const els = getRecycleElements();
  const state = createRecycleState();

  ensureDialog();
  translateStaticText();
  bindRecycleEvents(els, state);
  renderTable(els, state);
  loadRecycleRecords(els, state).finally(markI18nReady);

  return { els, state };
}
