(async () => {
  const params = new URLSearchParams(window.location.search);
  const env = params.get("env") || "";
  const kind = params.get("kind") || "channels";
  let tokenQuotaLegacy = kind === "tokens";
  let observer;
  if (kind !== "tokens" || !env) {
    tokenQuotaLegacy = false;
  }

  const applyLegacyTokenQuotaUi = () => {
    if (kind !== "tokens" || !document.body) return;
    const hasLegacyClass = document.body.classList.contains("na-legacy-token-quota");
    if (hasLegacyClass !== tokenQuotaLegacy) {
      document.body.classList.toggle("na-legacy-token-quota", tokenQuotaLegacy);
    }
    if (!tokenQuotaLegacy) {
      document.querySelectorAll(".semi-form-field").forEach((field) => {
        const labelNode = field.querySelector("label, .semi-form-field-label");
        if (labelNode?.dataset.naOriginalText) {
          labelNode.textContent = labelNode.dataset.naOriginalText;
        }
        field.style.display = "";
        field.removeAttribute("data-na-legacy-unlimited");
      });
      return;
    }
    document.querySelectorAll(".semi-form-field").forEach((field) => {
      const labelNode = field.querySelector("label, .semi-form-field-label");
      const text = labelNode?.textContent?.trim() || "";
      if (text === "金额额度限制") {
        if (!labelNode.dataset.naOriginalText) labelNode.dataset.naOriginalText = labelNode.textContent;
        if (labelNode.textContent !== "无限额度") labelNode.textContent = "无限额度";
        if (!field.hasAttribute("data-na-legacy-unlimited")) field.setAttribute("data-na-legacy-unlimited", "");
      } else if (
        text === "Token 额度限制" ||
        text === "限制周期" ||
        text === "Token 上限（整数 k）"
      ) {
        if (field.style.display !== "none") field.style.display = "none";
      }
    });
  };

  try {
    const response = await fetch(
      `/api/platform/${encodeURIComponent(env)}/capabilities?refresh=1`,
      { cache: "no-store", credentials: "same-origin" },
    );
    const result = await response.json();
    if (response.ok && result.success) {
      tokenQuotaLegacy = result.data?.token_quota_capabilities !== true;
      window.NA_PLATFORM_CAPABILITIES = {
        ...(window.NA_PLATFORM_CAPABILITIES || {}),
        token_quota_capabilities: !tokenQuotaLegacy,
      };
      localStorage.setItem(
        "na_platform_capabilities",
        JSON.stringify(window.NA_PLATFORM_CAPABILITIES),
      );
    }
  } catch (_) {
    tokenQuotaLegacy = true;
  }

  if (document.body) {
    document.body.classList.toggle("na-legacy-token-quota", kind === "tokens" && tokenQuotaLegacy);
  }
  if (kind === "tokens") {
    observer = new MutationObserver(() => applyLegacyTokenQuotaUi());
    const observe = () => {
      if (!document.body) return;
      observer.observe(document.body, { attributes: true, childList: true, subtree: true });
      applyLegacyTokenQuotaUi();
    };
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", observe, { once: true });
    } else {
      observe();
    }
  }
})();
