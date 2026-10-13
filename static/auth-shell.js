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
  function mountUser(user, pendingRequests = 0) {
    const menu = document.getElementById("authUserMenu");
    if (!menu) return;
    const count = Number.isFinite(Number(pendingRequests)) ? Math.max(0, Number(pendingRequests)) : 0;
    const permissionLink = user.role === "superadmin"
      ? `<a href="/admin/users#permission-requests">权限申请${count ? ` <span class="na-auth-count" aria-label="${count} 条待处理">${count}</span>` : ""}</a><a href="/admin/users#users">管理用户</a>`
      : '<a href="/permissions/request">申请功能权限</a>';
    menu.innerHTML = `<details class="na-auth-menu"><summary title="账户菜单">${esc(user.username)} <span>${esc(user.role)}</span></summary><div><a href="/account">账户设置</a>${permissionLink}<button type="button" data-na-logout>退出登录</button></div></details>`;
    menu.querySelector("[data-na-logout]")?.addEventListener("click", async (event) => {
      const button = event.currentTarget;
      button.disabled = true;
      try {
        const response = await originalFetch("/logout", { method:"POST", headers:{"X-CSRF-Token":csrfToken} });
        if (!response.ok) throw new Error(`logout failed: ${response.status}`);
        csrfToken = "";
        window.NAIdentity = undefined;
        window.location.replace("/login");
      } catch (_) {
        button.disabled = false;
        window.alert("退出登录失败，请刷新页面后重试。");
      }
    });
  }
  function applyPermissions(features) {
    const allowed = new Set(features);
    document.querySelectorAll("[data-permission]").forEach((node) => {
      const permitted = allowed.has(node.dataset.permission);
      node.hidden = !permitted;
      const viewId = node.getAttribute("aria-controls");
      const view = viewId && document.getElementById(viewId);
      if (!view || permitted) return;
      view.hidden = true;
    });
    const hasVisibleTab = Array.from(document.querySelectorAll("#navTabs [role=tab]"))
      .some((node) => !node.hidden && allowed.has(node.dataset.permission));
    const navTabs = document.getElementById("navTabs");
    const notice = document.getElementById("noPermissionNotice");
    if (navTabs) navTabs.hidden = !hasVisibleTab;
    if (notice) notice.hidden = hasVisibleTab;
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
      window.NAIdentity = { user:info.user, features:info.features || [], csrfToken, pendingPermissionRequests:info.pending_permission_requests || 0 };
      applyPermissions(info.features || []); mountUser(info.user || {}, info.pending_permission_requests || 0);
      document.documentElement.dataset.naRole = info.user?.role || "";
      document.documentElement.classList.remove("na-permissions-pending");
      document.documentElement.classList.add("na-permissions-ready");
      window.dispatchEvent(new CustomEvent("na-permissions-ready", { detail: { features: info.features || [] } }));
    } catch (_) {
      if (!authPaths.has(window.location.pathname) && !window.location.pathname.startsWith("/reset-password/") && !window.location.pathname.startsWith("/verify-email/")) {
        window.location.replace(`/login?next=${encodeURIComponent(window.location.pathname + window.location.search)}`);
      }
    }
  }
  authReady = load();
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", () => { applyPermissions(window.NAIdentity?.features || []); mountUser(window.NAIdentity?.user || {}, window.NAIdentity?.pendingPermissionRequests || 0); });
})();
