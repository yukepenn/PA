// Minimal keyboard shortcut bridge for Dash.
// Writes a JSON payload into the hidden dcc.Input#key_event and dispatches an input event.

(function () {
  function setKeyEvent(payload) {
    const el = document.querySelector("#key_event");
    if (!el) return;
    el.value = JSON.stringify(payload);
    el.dispatchEvent(new Event("input", { bubbles: true }));
  }

  window.addEventListener("keydown", function (e) {
    // Avoid interfering with typing in inputs/textareas
    const tag = (e.target && e.target.tagName) ? e.target.tagName.toLowerCase() : "";
    if (tag === "input" || tag === "textarea" || e.isComposing) return;

    const key = (e.key || "").toLowerCase();
    const payload = {
      key: key,
      shift: !!e.shiftKey,
      ts: Date.now(),
    };

    // Only handle keys we care about
    const isArrow = key === "arrowleft" || key === "arrowright";
    const isSpace = key === " " || key === "spacebar";
    const isHot = ["a", "v", "d", "1", "2", "3"].includes(key);
    if (!isArrow && !isSpace && !isHot) return;

    // Prevent page scroll on space
    if (isSpace) e.preventDefault();

    setKeyEvent(payload);
  });
})();

