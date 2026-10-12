/* 全站会话感知、导航权限收敛与 API CSRF 头注入。 */
(() => {
  "use strict";
  const authPaths = new Set(["/login", "/register", "/forgot-password"]);
  let csrfToken = "";
  let loaded = false;
  const esc = (value) => String(value || "").replace(/[&<>\"']/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[char]));
  const originalFetch = window.fetch.bind(window);
  let authReady = Promise.resolve();
  window.fetch = (input, init = {}) => {
    const url = typeof input === "string" ? input : input?.url || "";
    const method = String(init.method || (typeof input === "object" && input?.method) || "GET").toUpperCase();
    const sameOrigin = !/^https?:\/\//i.test(url) || url.startsWith(window.location.origin);
    if (sameOrigin && ["POST", "PUT", "PATCH", "DELETE"].includes(method)) {
      return authReady.then(() => {
        const headers = new Headers(init.headers || (typeof input === "object" ? input.headers : undefined));
        if (csrfToken) headers.set("X-CSRF-Token", csrfToken);
        return originalFetch(input, { ...init, headers });
      });
    }
    return originalFetch(input, init);
  };
  function mountUser(user) {
    const menu = document.getElementById("authUserMenu");
    if (!menu) return;
    menu.innerHTML = `<details class="na-auth-menu"><summary title="账户菜单">${esc(user.username)} <span>${esc(user.role)}</span></summary><div><a href="/account">账户设置</a>${user.role === "superadmin" ? '<a href="/admin/users">管理用户</a>' : ""}<button type="button" data-na-logout>退出登录</button></div></details>`;
    menu.querySelector("[data-na-logout]")?.addEventListener("click", async () => { await originalFetch("/logout", { method:"POST", headers:{"X-CSRF-Token":csrfToken} }); window.location.assign("/login"); });
  }
  function applyPermissions(features) {
    const allowed = new Set(features);
    document.querySelectorAll("[data-permission]").forEach((node) => { node.hidden = !allowed.has(node.dataset.permission); });
    const active = document.querySelector("[role=tab].active[hidden]");
    if (active) document.querySelector("[role=tab]:not([hidden])")?.click();
  }
  async function load() {
    if (loaded) return;
    loaded = true;
    try {
      const response = await originalFetch("/auth/me", { credentials:"same-origin" });
      if (!response.ok) throw new Error("not authenticated");
      const info = await response.json();
      csrfToken = info.csrf_token || "";
      window.NAIdentity = { user:info.user, features:info.features || [], csrfToken };
      applyPermissions(info.features || []); mountUser(info.user || {});
      document.documentElement.dataset.naRole = info.user?.role || "";
    } catch (_) {
      if (!authPaths.has(window.location.pathname) && !window.location.pathname.startsWith("/reset-password/") && !window.location.pathname.startsWith("/verify-email/")) {
        window.location.replace(`/login?next=${encodeURIComponent(window.location.pathname + window.location.search)}`);
      }
    }
  }
  authReady = load();
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", () => { applyPermissions(window.NAIdentity?.features || []); mountUser(window.NAIdentity?.user || {}); });
})();
