(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const DEFAULT_OPTIONS = {
    groups: [],
    quota_per_unit: 500000,
    quota_display_type: "USD",
    usd_exchange_rate: 1,
    custom_currency_symbol: "¤",
    custom_currency_exchange_rate: 1,
    warnings: [],
  };
  const FILTER_DEBOUNCE_MS = 350;
  const WEAK_PASSWORDS = new Set([
    "000000", "111111", "123456", "12345678", "123456789", "1234567890",
    "1q2w3e4r", "1qaz2wsx", "abc123", "admin", "admin123", "admin1234",
    "admin1234!", "admin@123", "letmein", "password", "password1", "password1!",
    "password123", "password@123", "qwerty", "qwerty123", "qwerty123!", "root",
    "root123", "test1234", "welcome",
  ]);
  const state = {
    env: "",
    users: [],
    total: 0,
    page: 1,
    pageSize: 20,
    filters: { keyword: "", group: "" },
    options: { ...DEFAULT_OPTIONS },
    loading: false,
    saving: false,
    confirming: false,
    editingId: null,
    listSequence: 0,
    optionsSequence: 0,
    editorSequence: 0,
    filterTimer: null,
    confirmAction: null,
  };

  async function request(url, options = {}) {
    const response = await fetch(url, options);
    let payload = {};
    try { payload = await response.json(); } catch (_) { /* 非 JSON 响应按 HTTP 状态处理 */ }
    if (!response.ok || !payload.success) {
      const error = new Error(payload.message || `请求失败（${response.status}）`);
      error.code = payload.code || "";
      throw error;
    }
    return payload;
  }

  function jsonOptions(method, body) {
    return {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    };
  }

  function hasSite() {
    return Boolean(state.env);
  }

  function showNotice(message = "", kind = "error") {
    const notice = $("pageNotice");
    notice.textContent = message;
    notice.classList.toggle("info", kind === "info");
    notice.hidden = !message;
  }

  function setControls() {
    const configured = hasSite();
    const busy = state.loading || state.saving || state.confirming;
    const mutationBusy = state.saving || state.confirming;
    $("addUserBtn").disabled = !configured || busy;
    ["searchBtn", "resetFilterBtn", "pageSize", "keywordInput", "groupFilter"].forEach((id) => {
      $(id).disabled = !configured || mutationBusy;
    });
    $("tableWrap").setAttribute("aria-busy", String(state.loading));
  }

  function renderGroupOptions() {
    const filter = $("groupFilter");
    const selected = filter.value || state.filters.group;
    const groups = Array.isArray(state.options.groups) ? state.options.groups : [];
    const names = [...new Set(groups.filter((name) => typeof name === "string" && name.trim()).map((name) => name.trim()))];
    if (selected && !names.includes(selected)) names.push(selected);
    filter.replaceChildren(new Option("全部分组", ""));
    const suggestions = $("groupSuggestions");
    suggestions.replaceChildren();
    names.forEach((name) => {
      filter.append(new Option(name, name));
      suggestions.append(new Option(name, name));
    });
    filter.value = names.includes(selected) ? selected : "";
  }

  function renderMessage(title, detail = "", loading = false) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 8;
    const wrap = document.createElement("div");
    wrap.className = `users-empty${loading ? " users-loading" : ""}`;
    if (title) {
      const strong = document.createElement("strong");
      strong.textContent = title;
      wrap.append(strong);
    }
    if (detail) wrap.append(document.createTextNode(detail));
    cell.append(wrap);
    row.append(cell);
    $("usersTableBody").replaceChildren(row);
  }

  function numberValue(value) {
    const parsed = Number(value || 0);
    return Number.isFinite(parsed) ? parsed : 0;
  }

  function formatInteger(value) {
    return new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 0 }).format(numberValue(value));
  }

  function compactNumber(value) {
    const number = numberValue(value);
    return new Intl.NumberFormat("zh-CN", {
      maximumFractionDigits: Math.abs(number) >= 1000000 ? 2 : 0,
      notation: Math.abs(number) >= 1000000 ? "compact" : "standard",
    }).format(number);
  }

  function formatQuota(value) {
    const quota = numberValue(value);
    const options = state.options;
    const displayType = String(options.quota_display_type || "USD").toUpperCase();
    if (displayType === "TOKENS") return compactNumber(quota);
    const unit = numberValue(options.quota_per_unit) > 0 ? numberValue(options.quota_per_unit) : 500000;
    let symbol = "$";
    let rate = 1;
    if (displayType === "CNY") {
      symbol = "¥";
      rate = numberValue(options.usd_exchange_rate) || 1;
    } else if (displayType === "CUSTOM") {
      symbol = String(options.custom_currency_symbol || "¤");
      rate = numberValue(options.custom_currency_exchange_rate) || 1;
    }
    return `${symbol}${((quota / unit) * rate).toFixed(2)}`;
  }

  function isDeleted(user) {
    const value = user.DeletedAt ?? user.deleted_at;
    if (!value) return false;
    if (typeof value === "object" && ("Valid" in value || "valid" in value)) {
      return Boolean(value.Valid ?? value.valid);
    }
    return true;
  }

  function makeTag(text, className, title = "") {
    const tag = document.createElement("span");
    tag.className = `users-tag ${className}`.trim();
    tag.textContent = text;
    if (title) tag.title = title;
    return tag;
  }

  function statusTag(user) {
    if (isDeleted(user)) return makeTag("已注销", "deleted");
    if (Number(user.status) === 1) {
      return makeTag("已启用", "enabled", `调用次数：${formatInteger(user.request_count)}`);
    }
    if (Number(user.status) === 2) {
      return makeTag("已禁用", "disabled", `调用次数：${formatInteger(user.request_count)}`);
    }
    return makeTag("未知状态", "role-unknown", `状态值：${String(user.status ?? "—")}`);
  }

  function roleTag(user) {
    const role = Number(user.role);
    if (role === 1) return makeTag("普通用户", "role-user");
    if (role === 10) return makeTag("管理员", "role-admin");
    if (role === 100) return makeTag("超级管理员", "role-root");
    if (role === 0) return makeTag("访客", "role-unknown");
    return makeTag("未知身份", "role-unknown", `角色值：${String(user.role ?? "—")}`);
  }

  function appendNameCell(row, user) {
    const cell = document.createElement("td");
    const wrap = document.createElement("div");
    wrap.className = "users-name";
    const username = document.createElement("strong");
    username.textContent = String(user.username || "—");
    username.title = String(user.username || "");
    const detail = document.createElement("small");
    const displayName = String(user.display_name || "");
    const remark = String(user.remark || "");
    const parts = [];
    if (displayName && displayName !== user.username) parts.push(displayName);
    if (remark) parts.push(remark);
    detail.textContent = parts.join(" · ") || "—";
    detail.title = parts.join("\n");
    wrap.append(username, detail);
    cell.append(wrap);
    row.append(cell);
  }

  function appendQuotaCell(row, user) {
    const cell = document.createElement("td");
    const wrap = document.createElement("div");
    wrap.className = "users-quota";
    const used = numberValue(user.used_quota);
    const remain = numberValue(user.quota);
    const total = Math.max(0, used + remain);
    const percent = total > 0 ? Math.min(100, Math.max(0, (remain / total) * 100)) : 0;
    const values = document.createElement("div");
    values.className = "users-quota-values";
    const remaining = document.createElement("strong");
    remaining.textContent = formatQuota(remain);
    const totalText = document.createElement("span");
    totalText.textContent = `/ ${formatQuota(total)}`;
    values.append(remaining, totalText);
    const track = document.createElement("div");
    track.className = "users-quota-track";
    track.setAttribute("role", "progressbar");
    track.setAttribute("aria-label", "剩余额度比例");
    track.setAttribute("aria-valuemin", "0");
    track.setAttribute("aria-valuemax", "100");
    track.setAttribute("aria-valuenow", String(Math.round(percent)));
    const bar = document.createElement("i");
    bar.style.width = `${percent}%`;
    track.append(bar);
    const detail = document.createElement("small");
    detail.textContent = `已用 ${formatQuota(used)} · 剩余 ${percent.toFixed(0)}%`;
    wrap.title = `剩余额度：${formatInteger(remain)}\n已用额度：${formatInteger(used)}\n总额度：${formatInteger(total)}`;
    wrap.append(values, track, detail);
    cell.append(wrap);
    row.append(cell);
  }

  function appendInviteCell(row, user) {
    const cell = document.createElement("td");
    const wrap = document.createElement("div");
    wrap.className = "users-invites";
    [`邀请 ${formatInteger(user.aff_count)}`, `收益 ${formatQuota(user.aff_history_quota)}`, user.inviter_id ? `邀请人 ${user.inviter_id}` : "无邀请人"]
      .forEach((text) => {
        const item = document.createElement("span");
        item.textContent = text;
        wrap.append(item);
      });
    cell.append(wrap);
    row.append(cell);
  }

  function actionButton(label, action, user, className = "") {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `users-action ${className}`.trim();
    button.textContent = label;
    button.dataset.action = action;
    button.dataset.userId = String(user.id);
    button.disabled = state.loading || state.saving || state.confirming;
    return button;
  }

  function appendActionsCell(row, user) {
    const cell = document.createElement("td");
    const wrap = document.createElement("div");
    wrap.className = "users-row-actions";
    if (isDeleted(user)) {
      const text = document.createElement("span");
      text.className = "users-deleted-note";
      text.textContent = "账户已注销";
      wrap.append(text);
    } else {
      const enabled = Number(user.status) === 1;
      wrap.append(
        actionButton(enabled ? "禁用" : "启用", enabled ? "disable" : "enable", user, enabled ? "danger" : ""),
        actionButton("编辑", "edit", user),
        actionButton("提升", "promote", user, "warning"),
        actionButton("降级", "demote", user),
      );
      const more = document.createElement("details");
      more.className = "users-more";
      const summary = document.createElement("summary");
      summary.textContent = "···";
      summary.title = "更多操作";
      summary.setAttribute("aria-label", `用户 ${user.username || user.id} 的更多操作`);
      const menu = document.createElement("div");
      menu.className = "users-more-menu";
      menu.append(
        actionButton("重置 Passkey", "passkey", user),
        actionButton("重置 2FA", "2fa", user),
        document.createElement("hr"),
        actionButton("注销", "delete", user, "danger"),
      );
      more.append(summary, menu);
      wrap.append(more);
    }
    cell.append(wrap);
    row.append(cell);
  }

  function renderTable() {
    if (state.loading) {
      renderMessage("正在读取用户", "请稍候…", true);
      return;
    }
    if (!state.users.length) {
      const filtered = state.filters.keyword || state.filters.group;
      renderMessage(filtered ? "没有匹配的用户" : "暂无用户数据", filtered ? "请调整关键字或分组后重新查询。" : "可以点击“添加用户”创建第一个账户。" );
      return;
    }
    const fragment = document.createDocumentFragment();
    state.users.forEach((user) => {
      const row = document.createElement("tr");
      row.classList.toggle("users-row-muted", isDeleted(user) || Number(user.status) !== 1);
      const id = document.createElement("td");
      id.className = "users-id";
      id.textContent = String(user.id ?? "—");
      row.append(id);
      appendNameCell(row, user);
      const status = document.createElement("td");
      status.append(statusTag(user));
      row.append(status);
      appendQuotaCell(row, user);
      const group = document.createElement("td");
      group.append(makeTag(String(user.group || "未分组"), "group"));
      row.append(group);
      const role = document.createElement("td");
      role.append(roleTag(user));
      row.append(role);
      appendInviteCell(row, user);
      appendActionsCell(row, user);
      fragment.append(row);
    });
    $("usersTableBody").replaceChildren(fragment);
  }

  function pageButton(label, page, { active = false, disabled = false } = {}) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = label;
    button.disabled = disabled || state.loading || !hasSite();
    button.classList.toggle("active", active);
    if (active) button.setAttribute("aria-current", "page");
    button.setAttribute("aria-label", label === "‹" ? "上一页" : label === "›" ? "下一页" : `第 ${label} 页`);
    button.addEventListener("click", () => {
      if (page === state.page || button.disabled) return;
      state.page = page;
      void loadUsers();
    });
    return button;
  }

  function renderPagination() {
    const totalPages = Math.ceil(state.total / state.pageSize);
    $("pageInfo").textContent = `第 ${state.total ? state.page : 0} / ${totalPages} 页`;
    const buttons = $("pageButtons");
    buttons.replaceChildren();
    if (!totalPages) return;
    buttons.append(pageButton("‹", Math.max(1, state.page - 1), { disabled: state.page <= 1 }));
    const pages = new Set([1, totalPages]);
    for (let page = state.page - 2; page <= state.page + 2; page += 1) {
      if (page >= 1 && page <= totalPages) pages.add(page);
    }
    let previous = 0;
    [...pages].sort((left, right) => left - right).forEach((page) => {
      if (previous && page - previous > 1) {
        const ellipsis = document.createElement("span");
        ellipsis.textContent = "…";
        buttons.append(ellipsis);
      }
      buttons.append(pageButton(String(page), page, { active: page === state.page }));
      previous = page;
    });
    buttons.append(pageButton("›", Math.min(totalPages, state.page + 1), { disabled: state.page >= totalPages }));
  }

  function updateTableMeta() {
    const filterText = state.filters.keyword || state.filters.group ? "筛选结果" : "用户总数";
    $("tableMeta").textContent = `${state.env.toUpperCase()} · ${filterText} ${formatInteger(state.total)} 条 · 当前第 ${state.page} 页`;
  }

  async function loadUsers() {
    if (!hasSite()) {
      state.users = [];
      state.total = 0;
      renderPagination();
      renderMessage("请先配置上游环境", "返回 NA 信息页，在站点配置中补齐连接信息。" );
      setControls();
      return false;
    }
    const sequence = ++state.listSequence;
    const env = state.env;
    const requestedPage = state.page;
    state.loading = true;
    showNotice();
    setControls();
    renderTable();
    const params = new URLSearchParams({
      page: String(state.page),
      page_size: String(state.pageSize),
      keyword: state.filters.keyword,
      group: state.filters.group,
    });
    try {
      const payload = await request(`/api/platform/${encodeURIComponent(env)}/users?${params}`);
      if (sequence !== state.listSequence || env !== state.env) return false;
      const data = payload.data || {};
      state.users = Array.isArray(data.items) ? data.items : [];
      state.total = Math.max(0, Number(data.total) || 0);
      const totalPages = Math.ceil(state.total / state.pageSize);
      if (totalPages > 0 && requestedPage > totalPages) {
        state.page = totalPages;
        state.loading = false;
        return loadUsers();
      }
      state.page = Math.max(1, Number(data.page) || requestedPage);
      $("refreshTime").textContent = `更新于 ${new Date().toLocaleTimeString("zh-CN", { hour12: false })}`;
      updateTableMeta();
      renderPagination();
      return true;
    } catch (error) {
      if (sequence !== state.listSequence || env !== state.env) return false;
      state.users = [];
      state.total = 0;
      showNotice(error.message || "用户列表加载失败");
      renderMessage("用户列表加载失败", "请检查上游登录状态、账户权限或网络连接后重试。" );
      renderPagination();
      updateTableMeta();
      return false;
    } finally {
      if (sequence === state.listSequence) {
        state.loading = false;
        setControls();
        renderTable();
        renderPagination();
      }
    }
  }

  async function loadOptions() {
    if (!hasSite()) return;
    const sequence = ++state.optionsSequence;
    const env = state.env;
    try {
      const payload = await request(`/api/platform/${encodeURIComponent(env)}/users/options`);
      if (sequence !== state.optionsSequence || env !== state.env) return;
      state.options = { ...DEFAULT_OPTIONS, ...(payload.data || {}) };
      renderGroupOptions();
      updateQuotaHint();
      if (!state.loading) renderTable();
      const warnings = Array.isArray(state.options.warnings) ? state.options.warnings.filter(Boolean) : [];
      if (warnings.length) showNotice(`部分辅助配置未读取：${warnings.join("；")}。用户管理功能仍可继续使用。`, "info");
    } catch (error) {
      if (sequence !== state.optionsSequence || env !== state.env) return;
      state.options = { ...DEFAULT_OPTIONS };
      renderGroupOptions();
      showNotice(`分组与额度配置读取失败：${error.message}。列表和账户操作不受影响。`, "info");
    }
  }

  function clearFilters() {
    if (state.filterTimer !== null) {
      clearTimeout(state.filterTimer);
      state.filterTimer = null;
    }
    state.filters = { keyword: "", group: "" };
    state.page = 1;
    $("keywordInput").value = "";
    renderGroupOptions();
    $("groupFilter").value = "";
  }

  function applyFilters() {
    if (state.filterTimer !== null) {
      clearTimeout(state.filterTimer);
      state.filterTimer = null;
    }
    state.filters = { keyword: $("keywordInput").value.trim(), group: $("groupFilter").value };
    state.page = 1;
    void loadUsers();
  }

  function scheduleFilterSearch() {
    if (state.filterTimer !== null) clearTimeout(state.filterTimer);
    state.filterTimer = setTimeout(() => {
      state.filterTimer = null;
      const keyword = $("keywordInput").value.trim();
      const group = $("groupFilter").value;
      if (keyword === state.filters.keyword && group === state.filters.group) return;
      state.filters = { keyword, group };
      state.page = 1;
      void loadUsers();
    }, FILTER_DEBOUNCE_MS);
  }

  function passwordError(password, required) {
    if (!password) return required ? "请输入密码" : "";
    const length = Array.from(password).length;
    if (length < 8) return "密码长度至少为 8 个字符";
    if (length > 20) return "密码长度不能超过 20 个字符";
    if (new TextEncoder().encode(password).length > 72) return "密码 UTF-8 编码不能超过 72 字节";
    if (WEAK_PASSWORDS.has(password.trim().toLowerCase())) return "密码过于常见，请更换更强的密码";
    const categories = [/\p{Lu}/u, /\p{Ll}/u, /\p{N}/u, /[\p{P}\p{S}]/u]
      .filter((pattern) => pattern.test(password)).length;
    return categories >= 3 ? "" : "密码必须包含大写、小写、数字、特殊符号中的至少三类";
  }

  function validateFormPassword() {
    const error = passwordError($("formPassword").value, !state.editingId);
    $("passwordError").textContent = error;
    $("formPassword").setAttribute("aria-invalid", String(Boolean(error)));
    return !error;
  }

  function updateQuotaHint() {
    const value = Number($("formQuota").value || 0);
    $("quotaHint").textContent = `等价金额：${formatQuota(Number.isFinite(value) ? value : 0)}`;
  }

  function setEditorBusy(busy) {
    state.saving = busy;
    $("saveUserBtn").disabled = busy;
    $("saveUserLabel").textContent = busy ? "正在保存…" : state.editingId ? "保存修改" : "创建用户";
    $("userDialog").querySelectorAll("input, textarea, button").forEach((control) => {
      if (control !== $("saveUserBtn")) control.disabled = busy;
    });
    setControls();
  }

  function fillBindings(user) {
    const fields = {
      bindGithub: user.github_id,
      bindDiscord: user.discord_id,
      bindOidc: user.oidc_id,
      bindWechat: user.wechat_id,
      bindEmail: user.email,
      bindTelegram: user.telegram_id,
    };
    Object.entries(fields).forEach(([id, value]) => { $(id).value = String(value || ""); });
  }

  function populateEditor(user) {
    $("formUsername").value = String(user.username || "");
    $("formDisplayName").value = String(user.display_name || "");
    $("formPassword").value = "";
    $("formPassword").type = "password";
    $("togglePassword").textContent = "显示";
    $("togglePassword").setAttribute("aria-label", "显示密码");
    $("formRemark").value = String(user.remark || "");
    $("formGroup").value = String(user.group || "default");
    $("formQuota").value = String(Number(user.quota || 0));
    $("quotaDelta").value = "";
    $("passwordError").textContent = "";
    fillBindings(user);
    updateQuotaHint();
  }

  function openCreateDialog() {
    state.editingId = null;
    state.editorSequence += 1;
    $("userForm").reset();
    populateEditor({ group: state.options.groups?.[0] || "default", quota: 0 });
    $("userDialogKicker").textContent = "新建账户";
    $("userDialogTitle").textContent = "添加用户";
    $("userDialogDescription").textContent = "创建一个上游普通用户账户，创建后可按需提升角色。";
    $("permissionFields").hidden = true;
    $("bindingFields").hidden = true;
    $("formGroup").required = false;
    $("formQuota").required = false;
    $("formPassword").required = true;
    $("passwordRequired").hidden = false;
    $("passwordHint").textContent = "大写、小写、数字、特殊符号至少三类；UTF-8 不超过 72 字节。";
    setEditorBusy(false);
    $("userDialog").showModal();
    $("formUsername").focus();
  }

  async function openEditDialog(user) {
    const userId = Number(user.id);
    if (!Number.isInteger(userId) || userId <= 0) return;
    state.editingId = userId;
    const sequence = ++state.editorSequence;
    populateEditor(user);
    $("userDialogKicker").textContent = `账户 ID · ${userId}`;
    $("userDialogTitle").textContent = "编辑用户";
    $("userDialogDescription").textContent = "修改基本资料、分组、剩余额度或登录密码。";
    $("permissionFields").hidden = false;
    $("bindingFields").hidden = false;
    $("formGroup").required = true;
    $("formQuota").required = true;
    $("formPassword").required = false;
    $("passwordRequired").hidden = true;
    $("passwordHint").textContent = "留空表示不修改密码；填写时需符合密码强度要求。";
    setEditorBusy(true);
    $("saveUserLabel").textContent = "读取详情…";
    $("userDialog").showModal();
    try {
      const payload = await request(`/api/platform/${encodeURIComponent(state.env)}/users/${userId}`);
      if (sequence !== state.editorSequence || state.editingId !== userId) return;
      populateEditor(payload.data || user);
      setEditorBusy(false);
      $("formUsername").focus();
    } catch (error) {
      if (sequence !== state.editorSequence || state.editingId !== userId) return;
      $("userDialog").close();
      NAUi.toast(error.message || "用户详情读取失败", "err");
    }
  }

  async function saveUser(event) {
    event.preventDefault();
    if (state.saving || !validateFormPassword()) return;
    const editingId = state.editingId;
    const record = {
      username: $("formUsername").value.trim(),
      display_name: $("formDisplayName").value,
      password: $("formPassword").value,
      remark: $("formRemark").value,
    };
    if (editingId) {
      const quota = Number($("formQuota").value);
      if (!Number.isSafeInteger(quota)) {
        NAUi.toast("剩余额度必须是有效整数", "warn");
        $("formQuota").focus();
        return;
      }
      record.group = $("formGroup").value.trim();
      record.quota = quota;
    }
    setEditorBusy(true);
    try {
      const url = editingId
        ? `/api/platform/${encodeURIComponent(state.env)}/users/${editingId}`
        : `/api/platform/${encodeURIComponent(state.env)}/users`;
      const payload = await request(url, jsonOptions(editingId ? "PUT" : "POST", record));
      $("userDialog").close();
      NAUi.toast(payload.message || (editingId ? "用户信息已更新" : "用户创建成功"), "ok");
      if (!editingId) clearFilters();
      await loadUsers();
    } catch (error) {
      NAUi.toast(error.message || "保存用户失败", "err");
    } finally {
      setEditorBusy(false);
      if (!state.loading) renderTable();
    }
  }

  function openConfirm({ title, kicker = "确认操作", message, detail, label, danger = false, action }) {
    state.confirmAction = action;
    $("confirmKicker").textContent = kicker;
    $("confirmTitle").textContent = title;
    $("confirmMessage").textContent = message;
    $("confirmDetail").textContent = detail || "";
    $("confirmIcon").textContent = danger ? "!" : "?";
    $("confirmIcon").classList.toggle("danger", danger);
    $("confirmActionBtn").textContent = label || "确认";
    $("confirmActionBtn").classList.toggle("na-btn-danger", danger);
    $("confirmActionBtn").classList.toggle("na-btn-primary", !danger);
    $("confirmActionBtn").disabled = false;
    $("confirmDialog").showModal();
  }

  function openManageConfirmation(user, action) {
    const username = String(user.username || `ID ${user.id}`);
    const configs = {
      enable: ["启用用户", `确定启用“${username}”吗？`, "启用后，该账户可重新登录并调用上游服务。", "确认启用", false],
      disable: ["禁用用户", `确定禁用“${username}”吗？`, "禁用后，该账户将无法登录和调用上游服务。", "确认禁用", true],
      promote: ["提升为管理员", `确定将“${username}”提升为管理员吗？`, "该账户将获得上游管理权限；只有上游超级管理员可执行此操作。", "确认提升", false],
      demote: ["降级为普通用户", `确定将“${username}”降级为普通用户吗？`, "该账户的上游管理员权限将被移除。", "确认降级", true],
      delete: ["注销用户", `确定注销“${username}”吗？`, "账户将被注销并无法登录，本页面不提供恢复操作，请谨慎执行。", "确认注销", true],
    };
    const config = configs[action];
    if (!config) return;
    openConfirm({
      title: config[0],
      kicker: `用户 ID · ${user.id}`,
      message: config[1],
      detail: config[2],
      label: config[3],
      danger: config[4],
      action: async () => {
        const payload = await request(
          `/api/platform/${encodeURIComponent(state.env)}/users/${user.id}/manage`,
          jsonOptions("POST", { action }),
        );
        NAUi.toast(payload.message || "用户管理操作成功", "ok");
        await loadUsers();
      },
    });
  }

  function openSecurityConfirmation(user, kind) {
    const passkey = kind === "passkey";
    openConfirm({
      title: passkey ? "重置 Passkey" : "重置 2FA",
      kicker: `用户 ID · ${user.id}`,
      message: `确定为“${user.username || user.id}”重置 ${passkey ? "Passkey" : "2FA"} 吗？`,
      detail: passkey ? "现有 Passkey 绑定将被清除，用户需重新设置。" : "现有两步验证绑定将被清除，用户下次登录需重新绑定。",
      label: "确认重置",
      danger: true,
      action: async () => {
        const payload = await request(
          `/api/platform/${encodeURIComponent(state.env)}/users/${user.id}/${kind}`,
          { method: "DELETE" },
        );
        NAUi.toast(payload.message || "安全设置已重置", "ok");
      },
    });
  }

  async function runConfirmedAction() {
    if (!state.confirmAction || state.confirming) return;
    state.confirming = true;
    const button = $("confirmActionBtn");
    const originalLabel = button.textContent;
    button.disabled = true;
    button.textContent = "正在执行…";
    $("confirmDialog").querySelectorAll("[data-close-dialog]").forEach((control) => { control.disabled = true; });
    setControls();
    try {
      await state.confirmAction();
      state.confirmAction = null;
      $("confirmDialog").close();
    } catch (error) {
      NAUi.toast(error.message || "操作执行失败", "err");
      button.disabled = false;
    } finally {
      state.confirming = false;
      button.textContent = originalLabel;
      $("confirmDialog").querySelectorAll("[data-close-dialog]").forEach((control) => { control.disabled = false; });
      setControls();
      if (!state.loading) renderTable();
    }
  }

  function closeDialog(id) {
    if (id === "userDialog" && state.saving) return;
    if (id === "confirmDialog" && state.confirming) return;
    $(id).close();
  }

  function bindEvents() {
    $("addUserBtn").addEventListener("click", openCreateDialog);
    $("filterForm").addEventListener("submit", (event) => {
      event.preventDefault();
      applyFilters();
    });
    $("keywordInput").addEventListener("input", scheduleFilterSearch);
    $("groupFilter").addEventListener("change", applyFilters);
    $("resetFilterBtn").addEventListener("click", () => { clearFilters(); void loadUsers(); });
    $("pageSize").addEventListener("change", (event) => {
      state.pageSize = Number(event.target.value) || 20;
      state.page = 1;
      void loadUsers();
    });
    $("usersTableBody").addEventListener("click", (event) => {
      const button = event.target.closest("button[data-action]");
      if (!button || button.disabled) return;
      const user = state.users.find((item) => String(item.id) === button.dataset.userId);
      if (!user) return;
      button.closest("details")?.removeAttribute("open");
      const action = button.dataset.action;
      if (action === "edit") void openEditDialog(user);
      else if (["enable", "disable", "promote", "demote", "delete"].includes(action)) openManageConfirmation(user, action);
      else if (["passkey", "2fa"].includes(action)) openSecurityConfirmation(user, action);
    });
    $("userForm").addEventListener("submit", saveUser);
    $("formPassword").addEventListener("input", validateFormPassword);
    $("formQuota").addEventListener("input", updateQuotaHint);
    $("togglePassword").addEventListener("click", () => {
      const visible = $("formPassword").type === "text";
      $("formPassword").type = visible ? "password" : "text";
      $("togglePassword").textContent = visible ? "显示" : "隐藏";
      $("togglePassword").setAttribute("aria-label", visible ? "显示密码" : "隐藏密码");
    });
    $("applyQuotaDelta").addEventListener("click", () => {
      const current = Number($("formQuota").value || 0);
      const delta = Number($("quotaDelta").value);
      if (!Number.isSafeInteger(current) || !Number.isSafeInteger(delta) || !Number.isSafeInteger(current + delta)) {
        NAUi.toast("额度及增减值必须是有效整数", "warn");
        return;
      }
      $("formQuota").value = String(current + delta);
      $("quotaDelta").value = "";
      updateQuotaHint();
    });
    $("confirmActionBtn").addEventListener("click", () => { void runConfirmedAction(); });
    document.querySelectorAll("[data-close-dialog]").forEach((button) => {
      button.addEventListener("click", () => closeDialog(button.dataset.closeDialog));
    });
    ["userDialog", "confirmDialog"].forEach((id) => {
      $(id).addEventListener("cancel", (event) => {
        if ((id === "userDialog" && state.saving) || (id === "confirmDialog" && state.confirming)) event.preventDefault();
      });
      $(id).addEventListener("close", () => {
        if (id === "userDialog") {
          state.editingId = null;
          state.editorSequence += 1;
          $("formPassword").value = "";
        } else if (!state.confirming) state.confirmAction = null;
      });
    });
    document.addEventListener("click", (event) => {
      document.querySelectorAll(".users-more[open]").forEach((details) => {
        if (!details.contains(event.target)) details.removeAttribute("open");
      });
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") document.querySelectorAll(".users-more[open]").forEach((details) => details.removeAttribute("open"));
    });
  }

  async function init() {
    bindEvents();
    renderGroupOptions();
    state.env = (new URLSearchParams(window.location.search).get("env") || "").trim();
    document.title = `${state.env.toUpperCase() || "上游"}用户管理 · NA信息`;
    setControls();
    if (hasSite()) await Promise.allSettled([loadOptions(), loadUsers()]);
    else await loadUsers();
  }

  window.NAPlatformUsers = {
    refresh: () => Promise.allSettled([loadOptions(), loadUsers()]),
  };
  void init();
})();
