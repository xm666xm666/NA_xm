/**
 * NA 自动配置 — 共享 UI 工具（Toast、步骤状态、Banner、引导）
 */
(function (global) {
  const FLOW_KEY = "na_flow_progress";
  const ONBOARD_KEY = "na_onboarding_dismissed";

  function ensureToastStack() {
    let stack = document.getElementById("naToastStack");
    if (!stack) {
      stack = document.createElement("div");
      stack.id = "naToastStack";
      stack.className = "na-toast-stack";
      stack.setAttribute("aria-live", "polite");
      document.body.appendChild(stack);
    }
    return stack;
  }

  function toast(msg, type = "info", ms = 4200) {
    const stack = ensureToastStack();
    const el = document.createElement("div");
    el.className = "na-toast " + (type || "info");
    el.textContent = msg;
    stack.appendChild(el);
    setTimeout(() => {
      el.style.opacity = "0";
      el.style.transform = "translateX(12px)";
      el.style.transition = "0.3s ease";
      setTimeout(() => el.remove(), 320);
    }, ms);
  }

  function showBanner(id, msg, type = "info") {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = msg;
    el.className = "na-banner visible " + (type || "info");
  }

  function hideBanner(id) {
    const el = document.getElementById(id);
    if (!el) return;
    el.className = "na-banner";
    el.textContent = "";
  }

  function normalizeFlowProgress(raw) {
    const step1 = Boolean(raw?.step1);
    const step2 = step1 && Boolean(raw?.step2);
    const step3 = step2 && Boolean(raw?.step3);
    const runningStep = Number(raw?.runningStep) || 0;
    return { step1, step2, step3, runningStep };
  }

  function getFlowProgress() {
    try {
      return normalizeFlowProgress(JSON.parse(localStorage.getItem(FLOW_KEY) || "{}") || {});
    } catch (_) {
      return normalizeFlowProgress({});
    }
  }

  function setFlowProgress(patch) {
    const next = normalizeFlowProgress({ ...getFlowProgress(), ...patch });
    try {
      localStorage.setItem(FLOW_KEY, JSON.stringify(next));
    } catch (_) { /* ignore */ }
    updateStepNav(next);
    return next;
  }

  /** 从智能体 pipeline steps[] 推导顶栏步骤状态（前置失败则后续还原为数字） */
  function progressFromPipelineSteps(steps) {
    const status = {};
    (steps || []).forEach((s) => {
      status[s.id] = s.status;
    });
    const isOk = (id) => status[id] === "ok";
    return normalizeFlowProgress({
      step1: isOk("extract"),
      step2: isOk("batch"),
      step3: isOk("summary"),
      runningStep: 0,
    });
  }

  function updateStepNav(progress) {
    const norm = normalizeFlowProgress(progress);
    const stepKeys = { 1: "step1", 2: "step2", 3: "step3" };
    document.querySelectorAll(".na-nav-tabs button[data-step]").forEach((btn) => {
      const stepNum = Number(btn.dataset.step);
      if (!stepNum) return;
      const key = stepKeys[stepNum];
      const done = Boolean(norm[key]);
      const running = norm.runningStep === stepNum && !done;
      btn.classList.toggle("na-step-done", done);
      btn.classList.toggle("na-step-running", running);
    });
  }

  function initStepNav() {
    updateStepNav(getFlowProgress());
  }

  function initReducedMotion() {
    const prefers = global.matchMedia("(prefers-reduced-motion: reduce)");
    const apply = () => {
      document.documentElement.classList.toggle("na-bg-simple", prefers.matches);
    };
    apply();
    if (prefers.addEventListener) prefers.addEventListener("change", apply);
    else prefers.addListener(apply);
  }

  function initOnboarding(stepsHtml, onStart) {
    if (localStorage.getItem(ONBOARD_KEY)) return;
    const wrap = document.createElement("div");
    wrap.className = "na-onboarding";
    wrap.innerHTML =
      '<div class="na-onboarding-card" role="dialog" aria-labelledby="naObTitle">' +
      "<h2 id=\"naObTitle\">三步完成 New API 配置</h2>" +
      (stepsHtml || "") +
      '<div class="na-toolbar" style="margin-top:0">' +
      '<button type="button" class="na-btn na-btn-primary" id="naObStart">开始</button>' +
      '<button type="button" class="na-btn na-btn-secondary" id="naObSkip">跳过引导</button>' +
      "</div></div>";
    document.body.appendChild(wrap);
    wrap.querySelector("#naObStart").onclick = () => {
      localStorage.setItem(ONBOARD_KEY, "1");
      wrap.remove();
      if (onStart) onStart();
    };
    wrap.querySelector("#naObSkip").onclick = () => {
      localStorage.setItem(ONBOARD_KEY, "1");
      wrap.remove();
    };
  }

  function flashEl(el) {
    if (!el) return;
    el.classList.remove("na-highlight-flash");
    void el.offsetWidth;
    el.classList.add("na-highlight-flash");
    el.scrollIntoView({ behavior: "smooth", block: "center" });
    setTimeout(() => el.classList.remove("na-highlight-flash"), 2800);
  }

  const ICONS = {
    input: '<svg viewBox="0 0 24 24"><path d="M4 7h16M4 12h10M4 17h7"/><path d="M15 12h5M17.5 9.5v5"/></svg>',
    output: '<svg viewBox="0 0 24 24"><path d="M13 3L4 14h7l-1 7 9-11h-7l1-7z"/></svg>',
    globe: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a15 15 0 0 1 0 18M12 3a15 15 0 0 0 0 18"/></svg>',
    chart: '<svg viewBox="0 0 24 24"><path d="M4 19V5M4 19h16"/><rect x="7" y="10" width="3" height="6"/><rect x="12" y="7" width="3" height="9"/><rect x="17" y="12" width="3" height="4"/></svg>',
    connect: '<svg viewBox="0 0 24 24"><path d="M8 12h8M12 8v8"/><circle cx="12" cy="12" r="9"/></svg>',
  };

  function icon(name) {
    const svg = ICONS[name] || ICONS.input;
    return '<span class="na-icon na-panel-icon" aria-hidden="true">' + svg + "</span>";
  }

  function filenameFromDisposition(header, fallback) {
    if (!header) return fallback || "export.xlsx";
    const star = /filename\*\s*=\s*UTF-8''([^;]+)/i.exec(header);
    if (star) {
      try {
        return decodeURIComponent(star[1].trim().replace(/"/g, ""));
      } catch (_) { /* ignore */ }
    }
    const quoted = /filename\s*=\s*"([^"]+)"/i.exec(header);
    if (quoted) return quoted[1];
    const plain = /filename\s*=\s*([^;]+)/i.exec(header);
    if (plain) return plain[1].trim().replace(/^UTF-8''/i, "");
    return fallback || "export.xlsx";
  }

  async function downloadUrl(url, fallbackName, opts) {
    if (opts && opts.confirmSecrets) {
      const ok = window.confirm("该文件可能含密钥。确认下载到本机？明文下载是显式、可审计的动作。");
      if (!ok) throw new Error("已取消下载");
    }
    const resp = await fetch(url);
    const ctype = (resp.headers.get("Content-Type") || "").toLowerCase();
    if (!resp.ok || ctype.includes("application/json")) {
      const data = await resp.json().catch(() => ({}));
      throw new Error(data.message || `下载失败 HTTP ${resp.status}`);
    }
    const blob = await resp.blob();
    const filename = filenameFromDisposition(
      resp.headers.get("Content-Disposition"),
      fallbackName || "export.xlsx"
    );
    const href = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = href;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(href);
    return filename;
  }

  const ARTIFACTS_MSG = "na-artifacts-changed";

  function notifyArtifactsChanged(kinds) {
    /* 仅在写出新文件后调用。onArtifactsChanged 回调里不要再 notify，避免循环。 */
    const payload = {
      type: ARTIFACTS_MSG,
      kinds: Array.isArray(kinds) ? kinds.filter(Boolean) : (kinds ? [kinds] : []),
    };
    try {
      if (global.parent && global.parent !== global) {
        global.parent.postMessage(payload, "*");
      }
    } catch (_) { /* ignore */ }
  }

  function onArtifactsChanged(handler) {
    if (typeof handler !== "function") return;
    global.addEventListener("message", (ev) => {
      const data = ev.data || {};
      if (data.type === ARTIFACTS_MSG) handler(data);
    });
  }

  function broadcastToFrames(payload) {
    const frames = global.document ? global.document.querySelectorAll("iframe.na-iframe") : [];
    frames.forEach((frame) => {
      try { frame.contentWindow?.postMessage(payload, "*"); } catch (_) { /* ignore */ }
    });
  }

  function initArtifactBridge(onLocal) {
    global.addEventListener("message", (ev) => {
      const data = ev.data || {};
      if (data.type !== ARTIFACTS_MSG) return;
      if (ev.source && ev.source !== global) broadcastToFrames(data);
      if (typeof onLocal === "function") onLocal(data);
    });
  }

  global.NAUi = {
    toast,
    showBanner,
    hideBanner,
    getFlowProgress,
    setFlowProgress,
    progressFromPipelineSteps,
    initStepNav,
    initReducedMotion,
    initOnboarding,
    flashEl,
    icon,
    filenameFromDisposition,
    downloadUrl,
    notifyArtifactsChanged,
    onArtifactsChanged,
    initArtifactBridge,
    broadcastToFrames,
    ARTIFACTS_MSG,
  };
})(window);
