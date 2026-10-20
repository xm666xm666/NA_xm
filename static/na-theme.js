/**
 * NA 自动配置 — 明暗主题切换（localStorage + 跨 iframe 同步）
 */
(function (global) {
  const STORAGE_KEY = "na_ui_theme";
  const MSG_TYPE = "na-theme-change";
  const THEMES = ["dark", "light"];
  const DEFAULT_THEME = "light";

  function getStored() {
    try {
      const v = localStorage.getItem(STORAGE_KEY);
      return THEMES.includes(v) ? v : DEFAULT_THEME;
    } catch (_) {
      return DEFAULT_THEME;
    }
  }

  function applyTheme(theme, { persist = true, broadcast = true } = {}) {
    const next = THEMES.includes(theme) ? theme : DEFAULT_THEME;
    document.documentElement.dataset.theme = next;
    if (persist) {
      try {
        localStorage.setItem(STORAGE_KEY, next);
      } catch (_) { /* ignore */ }
    }
    updateToggleButtons(next);
    if (broadcast) {
      postToChildren(next);
      try {
        if (global.parent && global.parent !== global) {
          global.parent.postMessage({ type: MSG_TYPE, theme: next }, "*");
        }
      } catch (_) { /* ignore */ }
    }
    return next;
  }

  function toggleTheme() {
    const cur = document.documentElement.dataset.theme || getStored();
    return applyTheme(cur === "light" ? "dark" : "light");
  }

  function postToChildren(theme) {
    document.querySelectorAll("iframe").forEach((frame) => {
      try {
        frame.contentWindow?.postMessage({ type: MSG_TYPE, theme }, "*");
      } catch (_) { /* ignore */ }
    });
  }

  function updateToggleButtons(theme) {
    const isLight = theme === "light";
    document.querySelectorAll("[data-na-theme-toggle]").forEach((btn) => {
      btn.setAttribute("aria-label", isLight ? "切换到暗色主题" : "切换到明亮主题");
      btn.setAttribute("title", isLight ? "切换为暗色主题" : "切换为明亮主题");
      btn.dataset.theme = theme;
      const label = btn.querySelector(".na-theme-toggle-label");
      if (label) label.textContent = isLight ? "暗色" : "明亮";
    });
  }

  function bindToggle(btn) {
    if (!btn || btn.dataset.naThemeBound) return;
    btn.dataset.naThemeBound = "1";
    btn.addEventListener("click", () => toggleTheme());
    updateToggleButtons(document.documentElement.dataset.theme || getStored());
  }

  function initToggles() {
    document.querySelectorAll("[data-na-theme-toggle]").forEach(bindToggle);
  }

  function onMessage(ev) {
    if (!ev.data || ev.data.type !== MSG_TYPE) return;
    if (!THEMES.includes(ev.data.theme)) return;
    applyTheme(ev.data.theme, { persist: true, broadcast: false });
  }

  function init(options = {}) {
    const theme = getStored();
    document.documentElement.dataset.theme = theme;
    updateToggleButtons(theme);
    if (options.bindToggles !== false) initToggles();
    if (!global.__naThemeMsgBound) {
      global.addEventListener("message", onMessage);
      global.__naThemeMsgBound = true;
    }
    return theme;
  }

  global.NATheme = {
    STORAGE_KEY,
    get: getStored,
    apply: applyTheme,
    toggle: toggleTheme,
    init,
    initToggles,
    bindToggle,
  };
})(typeof window !== "undefined" ? window : globalThis);
