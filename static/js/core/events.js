export function on(element, eventName, handler, options) {
  if (!element) return;
  element.addEventListener(eventName, handler, options);
}

export function off(element, eventName, handler, options) {
  if (!element) return;
  element.removeEventListener(eventName, handler, options);
}

export function delegate(root, eventName, selector, handler) {
  if (!root) return;
  root.addEventListener(eventName, (event) => {
    const target = event.target.closest(selector);
    if (!target || !root.contains(target)) return;
    handler(event, target);
  });
}