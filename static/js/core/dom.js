export const $ = (selector, root = document) => root.querySelector(selector);
export const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

export function on(element, eventName, handler, options) {
  if (!element) return;
  element.addEventListener(eventName, handler, options);
}

export function setText(element, value) {
  if (!element) return;
  element.textContent = value ?? "";
}

export function show(element, display = "") {
  if (!element) return;
  element.style.display = display;
}

export function hide(element) {
  if (!element) return;
  element.style.display = "none";
}

export function toggleClass(element, className, force) {
  if (!element) return;
  element.classList.toggle(className, force);
}