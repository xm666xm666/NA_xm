package middleware

import "github.com/gin-gonic/gin"

// SecurityHeaders 为所有 HTTP 响应添加通用安全响应头。
func SecurityHeaders() gin.HandlerFunc {
	return func(c *gin.Context) {
		c.Header("X-Content-Type-Options", "nosniff")
		// 限制高风险对象、base 标签和允许嵌入当前页面的来源。
		c.Header("Content-Security-Policy", "object-src 'none'; base-uri 'self'; frame-ancestors 'self'")
		// 禁用当前系统未使用的浏览器敏感能力，保留 Chat 音视频、剪贴板和 Passkey 权限。
		c.Header("Permissions-Policy", "geolocation=(), payment=(), usb=(), serial=(), bluetooth=()")
		// 隔离普通跨源窗口，同时保留 OAuth 和支付弹窗的 opener 兼容性。
		c.Header("Cross-Origin-Opener-Policy", "same-origin-allow-popups")
		// 禁止其他来源以 no-cors 方式嵌入当前服务返回的资源。
		c.Header("Cross-Origin-Resource-Policy", "same-origin")
		// 为旧版浏览器提供与 CSP 一致的同源页面嵌入限制。
		c.Header("X-Frame-Options", "SAMEORIGIN")
		// 兼容旧版浏览器和现有安全扫描规则，检测到反射型 XSS 时阻止页面渲染。
		c.Header("X-XSS-Protection", "1; mode=block")
		c.Next()
	}
}
