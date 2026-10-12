(() => {
  "use strict";

  document.querySelectorAll("[data-password-toggle]").forEach((button) => {
    const input = button.closest(".auth-input-action")?.querySelector("input");
    if (!(input instanceof HTMLInputElement)) return;
    button.addEventListener("click", () => {
      const visible = input.type === "text";
      input.type = visible ? "password" : "text";
      button.textContent = visible ? "显示" : "隐藏";
      button.setAttribute("aria-label", visible ? "显示密码" : "隐藏密码");
      input.focus({ preventScroll: true });
    });
  });

  const copyButton = document.querySelector("[data-copy-recovery-code]");
  const recoveryCode = document.querySelector("[data-recovery-code]");
  if (copyButton instanceof HTMLButtonElement && recoveryCode) {
    copyButton.addEventListener("click", async () => {
      const value = String(recoveryCode.textContent || "").trim();
      try {
        await navigator.clipboard.writeText(value);
        copyButton.textContent = "已复制，请妥善保存";
        copyButton.dataset.copied = "true";
      } catch (_) {
        copyButton.textContent = "复制失败，请手动保存";
      }
    });
  }
})();
