package middleware

import (
	"fmt"
	"net/http"

	"github.com/QuantumNous/new-api/logger"
	"github.com/QuantumNous/new-api/model"
	"github.com/gin-contrib/sessions"
	"github.com/gin-gonic/gin"
)

// SessionRevocationCheck 在所有路由读取 Session 前统一移除已撤销或升级前的登录会话。
func SessionRevocationCheck() gin.HandlerFunc {
	return func(c *gin.Context) {
		session := sessions.Default(c)
		if session.Get("id") == nil {
			c.Next()
			return
		}

		sessionID, ok := session.Get("session_id").(string)
		active := ok && sessionID != ""
		if active {
			revoked, err := model.IsSessionRevoked(sessionID)
			if err != nil {
				// 查询失败时保持 fail-close，避免数据库故障绕过撤销校验。
				logger.LogError(c.Request.Context(), fmt.Sprintf("failed to verify login session revocation: %v", err))
				c.JSON(http.StatusInternalServerError, gin.H{
					"success": false,
					"message": "无法验证登录会话，请稍后重试",
				})
				c.Abort()
				return
			}
			active = !revoked
		}

		if !active {
			// 清空当前请求中的身份，防止公开 OAuth 回调继续读取已失效用户。
			session.Clear()
			if err := session.Save(); err != nil {
				logger.LogError(c.Request.Context(), fmt.Sprintf("failed to clear revoked login session: %v", err))
			}
		}
		c.Next()
	}
}
