import { ensureDialog, showAlert } from "./dialog.js";
import { setText } from "./dom.js";

export async function handleApiError(error, els, opts = {}) {
  console.error(opts.context ?? "API Error", error);

  if (typeof opts.setStatus === "function") {
    opts.setStatus(els, null, "error");
  } else if (els?.status) {
    setText(els.status, opts.statusText ?? "Error");
    els.status.dataset.state = "error";
  }

  if (opts.alert) {
    ensureDialog();
    await showAlert(opts.alert, opts.alertOptions ?? {});
  }
}
