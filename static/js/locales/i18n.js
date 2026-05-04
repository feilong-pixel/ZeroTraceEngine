import en from "./en.js";
import zh from "./zh.js";

const DEFAULT_LANG = "zh";
const SUPPORTED_LANGS = ["zh", "en", "ja"];

const I18N = {
  en,
  zh,
};
const FALLBACK_LANG = "zh";

function normalizeLang(lang) {
  if (!lang) return DEFAULT_LANG;

  const normalized = String(lang).trim();

  if (normalized === "zh-CN" || normalized === "zh") return "zh";
  if (normalized === "en-US" || normalized === "en") return "en";
  if (normalized === "ja-JP" || normalized === "ja") return "ja";

  return SUPPORTED_LANGS.includes(normalized) ? normalized : DEFAULT_LANG;
}

function getByPath(obj, path) {
  if (!obj || !path) return undefined;
  return path.split(".").reduce((acc, key) => acc?.[key], obj);
}

export function getSupportedLangs() {
  return [...SUPPORTED_LANGS];
}

export function getDefaultLang() {
  return DEFAULT_LANG;
}

export function getLang() {
  return normalizeLang(localStorage.getItem("lang") || DEFAULT_LANG);
}

export function setLang(lang) {
  const normalized = normalizeLang(lang);
  localStorage.setItem("lang", normalized);
  return normalized;
}

export function detectBrowserLang() {
  return normalizeLang(navigator.language || DEFAULT_LANG);
}

export function initLang() {
  const savedLang = localStorage.getItem("lang");

  if (savedLang) {
    return setLang(savedLang);
  }

  return setLang(DEFAULT_LANG);
}

export function translateStaticText(root = document) {
  root.querySelectorAll("[data-i18n]").forEach((node) => {
    const value = t(node.dataset.i18n);
    if (value !== node.dataset.i18n) {
      node.textContent = value;
    }
  });

  root.querySelectorAll("[data-i18n-placeholder]").forEach((node) => {
    const value = t(node.dataset.i18nPlaceholder);
    if (value !== node.dataset.i18nPlaceholder) {
      node.placeholder = value;
    }
  });

  root.querySelectorAll("[data-i18n-title]").forEach((node) => {
    const value = t(node.dataset.i18nTitle);
    if (value !== node.dataset.i18nTitle) {
      node.title = value;
    }
  });

  root.querySelectorAll("[data-i18n-aria-label]").forEach((node) => {
    const value = t(node.dataset.i18nAriaLabel);
    if (value !== node.dataset.i18nAriaLabel) {
      node.setAttribute("aria-label", value);
    }
  });
}

export function markI18nReady() {
  document.documentElement.classList.remove("i18n-pending");
  document.documentElement.classList.add("i18n-ready");
}

export function scheduleI18nFallback(timeout = 1600) {
  window.setTimeout(() => {
    markI18nReady();
  }, timeout);
}

export function getLocale(lang = getLang()) {
  const normalized = normalizeLang(lang);
  return I18N[normalized] || I18N[FALLBACK_LANG];
}

export function trMsg(path, ...args) {
  const lang = getLang();
  const locale = I18N[lang] || I18N[FALLBACK_LANG];
  const value = getByPath(locale, path) ?? getByPath(locale?.messages, path);

  if (typeof value === "function") return value(...args);
  return value ?? path;
}

export function trUi(path, ...args) {
  const lang = getLang();
  const locale = I18N[lang] || I18N[FALLBACK_LANG];
  const value = getByPath(locale, path) ?? getByPath(locale?.ui, path);

  if (typeof value === "function") return value(...args);
  return value ?? path;
}

export function trDialog(path, ...args) {
  const lang = getLang();
  const locale = I18N[lang] || I18N[FALLBACK_LANG];
  const value = getByPath(locale, path) ?? getByPath(locale?.dialog, path);

  if (typeof value === "function") return value(...args);
  return value ?? path;
}

export function t(path, ...args) {
  const lang = getLang();
  const locale = I18N[lang] || I18N[FALLBACK_LANG];

  const value =
    getByPath(locale, path) ??
    getByPath(locale?.messages, path) ??
    getByPath(locale?.ui, path) ??
    getByPath(locale?.dialog, path);

  if (typeof value === "function") return value(...args);
  return value ?? path;
}

export function hasTranslation(path, lang = getLang()) {
  const normalized = normalizeLang(lang);
  const locale = I18N[normalized] || I18N[FALLBACK_LANG];

  const value =
    getByPath(locale, path) ??
    getByPath(locale?.messages, path) ??
    getByPath(locale?.ui, path) ??
    getByPath(locale?.dialog, path);

  return value !== undefined;
}
