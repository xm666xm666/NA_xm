package middleware

import (
	"fmt"
	"strings"

	"github.com/QuantumNous/new-api/common"
	"github.com/QuantumNous/new-api/logger"
	"github.com/gin-gonic/gin"
)

// RouteTagKey stores the logical route family for access log classification.
const RouteTagKey = "route_tag"

// RouteTag annotates requests so the access log can distinguish API traffic from web traffic.
func RouteTag(tag string) gin.HandlerFunc {
	return func(c *gin.Context) {
		c.Set(RouteTagKey, tag)
		c.Next()
	}
}

const maxRequestParamLogBytes = 4096

func SetUpLogger(server *gin.Engine) {
	server.Use(gin.LoggerWithFormatter(func(param gin.LogFormatterParams) string {
		var requestID string
		if param.Keys != nil {
			requestID, _ = param.Keys[common.RequestIdKey].(string)
		}
		tag := "web"
		if param.Keys != nil {
			if routeTag, ok := param.Keys[RouteTagKey].(string); ok && routeTag != "" {
				tag = routeTag
			}
		}
		return fmt.Sprintf("[GIN] %s | %s | %s | %3d | %13v | %15s | %7s %s\n",
			param.TimeStamp.Format("2006/01/02 - 15:04:05"),
			tag,
			requestID,
			param.StatusCode,
			param.Latency,
			param.ClientIP,
			param.Method,
			param.Path,
		)
	}))
}

// RequestParamLogger logs request metadata for troubleshooting without printing full bodies.
func RequestParamLogger() gin.HandlerFunc {
	return func(c *gin.Context) {
		logger.LogInfo(c, buildRequestParamLog(c))
		c.Next()
	}
}

// buildRequestParamLog formats the request metadata into a single log line.
func buildRequestParamLog(c *gin.Context) string {
	var sb strings.Builder
	sb.WriteString("incoming request | method=")
	sb.WriteString(c.Request.Method)
	sb.WriteString(" | path=")
	sb.WriteString(c.Request.URL.Path)

	rawQuery := c.Request.URL.RawQuery
	if rawQuery != "" {
		sb.WriteString(" | query=")
		sb.WriteString(truncateForLog(rawQuery))
	}

	return sb.String()
}

func truncateForLog(s string) string {
	s = strings.TrimSpace(s)
	if len(s) <= maxRequestParamLogBytes {
		return s
	}
	return s[:maxRequestParamLogBytes] + "...(truncated)"
}
