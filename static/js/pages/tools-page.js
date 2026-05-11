import { $, on } from "../core/dom.js";
import { markI18nReady, t, translateStaticText } from "../locales/i18n.js";

function getToolsElements() {
  return {
    backButton: $("#backButton"),
    copyButtons: document.querySelectorAll("[data-copy-value]"),
  };
}

async function copyText(value) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(value);
    return;
  }

  const textarea = document.createElement("textarea");
  textarea.value = value;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.left = "-9999px";
  document.body.appendChild(textarea);
  textarea.select();
  document.execCommand("copy");
  textarea.remove();
}

function setStatus(button, message) {
  const statusTarget = button.dataset.copyStatus;
  const statusElement = statusTarget ? $(statusTarget) : null;
  if (!statusElement) return;
  statusElement.textContent = message;
}

function bindEvents(els) {
  on(els.backButton, "click", () => {
    location.href = "/";
  });

  els.copyButtons.forEach((button) => {
    on(button, "click", async () => {
      const value = button.dataset.copyValue;
      try {
        await copyText(value);
        setStatus(button, t("tools.copyValueCopied", value));
      } catch {
        setStatus(button, t("tools.copyValueFailed", value));
      }
    });
  });
}

export function initToolsPage() {
  const els = getToolsElements();

  translateStaticText();
  bindEvents(els);
  markI18nReady();
}
