import { $, on, setText } from "./dom.js";
import { t, getLang } from "../locales/i18n.js";

const dialogState = {
  resolver: null,
  mode: "alert",
  lang: getLang(),
};

function getDialogElements() {
  return {
    dialogOverlay: $("#dialogOverlay"),
    dialogTitle: $("#dialogTitle"),
    dialogMessage: $("#dialogMessage"),
    dialogConfirmButton: $("#dialogConfirmButton"),
    dialogCancelButton: $("#dialogCancelButton"),
  };
}

function applyDialogTranslations(els) {
  if (!els.dialogTitle) return;

  setText(els.dialogTitle, t("dialog.title.confirm"));

  if (els.dialogConfirmButton) {
    setText(els.dialogConfirmButton, t("dialog.buttons.confirm"));
  }

  if (els.dialogCancelButton) {
    setText(els.dialogCancelButton, t("dialog.buttons.cancel"));
  }
}

export function setDialogLanguage(lang = getLang()) {
  dialogState.lang = lang;
  document.documentElement.lang = lang === "zh" ? "zh-CN" : lang;

  const els = getDialogElements();
  applyDialogTranslations(els);
}

export function closeDialog(result) {
  const els = getDialogElements();

  if (!els.dialogOverlay) return;

  els.dialogOverlay.classList.add("is-hidden");

  const resolver = dialogState.resolver;
  dialogState.resolver = null;

  if (resolver) {
    resolver(result);
  }
}

export function showDialog(message, mode = "alert", options = {}) {
  const els = getDialogElements();
  const {
    dialogOverlay,
    dialogTitle,
    dialogMessage,
    dialogConfirmButton,
    dialogCancelButton,
  } = els;

  if (
    !dialogOverlay ||
    !dialogTitle ||
    !dialogMessage ||
    !dialogConfirmButton ||
    !dialogCancelButton
  ) {
    return Promise.resolve(
      mode === "confirm" ? window.confirm(message) : (window.alert(message), true),
    );
  }

  dialogState.mode = mode;

  const titleText = options.title || t("dialog.title.confirm");
  const confirmText = options.confirmText || (
    mode === "confirm" ? t("dialog.buttons.confirm") : t("dialog.buttons.ok")
  );
  const cancelText = options.cancelText || t("dialog.buttons.cancel");

  setText(dialogTitle, titleText);
  setText(dialogMessage, message);
  setText(dialogConfirmButton, confirmText);
  setText(dialogCancelButton, cancelText);

  dialogCancelButton.classList.toggle("is-hidden", mode !== "confirm");
  dialogOverlay.classList.remove("is-hidden");

  if (mode === "confirm") {
    dialogCancelButton.focus();
  } else {
    dialogConfirmButton.focus();
  }

  return new Promise((resolve) => {
    dialogState.resolver = resolve;
  });
}

export function showAlert(message, options = {}) {
  return showDialog(message, "alert", options);
}

export function showConfirm(message, options = {}) {
  return showDialog(message, "confirm", options);
}

export function bindDialogEvents() {
  const els = getDialogElements();

  if (els.dialogConfirmButton) {
    on(els.dialogConfirmButton, "click", () => {
      closeDialog(true);
    });
  }

  if (els.dialogCancelButton) {
    on(els.dialogCancelButton, "click", () => {
      closeDialog(false);
    });
  }

  if (els.dialogOverlay) {
    on(els.dialogOverlay, "click", (event) => {
      if (event.target === els.dialogOverlay && dialogState.mode === "alert") {
        closeDialog(true);
      }
    });
  }
}

let bound = false;

export function ensureDialog() {
  if (bound) return;
  bindDialogEvents();
  bound = true;
}
