package middleware

import (
	"net"
	"net/url"
	"strconv"
	"strings"

	"github.com/gin-contrib/cors"
	"github.com/gin-gonic/gin"
)

// isAllowedCORSOrigin 允许指定业务域名子域和 10.0.0.0/8 地址使用 HTTP/HTTPS 任意合法端口。
func isAllowedCORSOrigin(origin string) bool {
	originURL, err := url.Parse(origin)
	if err != nil || (originURL.Scheme != "http" && originURL.Scheme != "https") {
		return false
	}
	if originURL.User != nil || originURL.Path != "" || originURL.RawQuery != "" || originURL.Fragment != "" {
		return false
	}
	if port := originURL.Port(); port != "" {
		portNumber, err := strconv.Atoi(port)
		if err != nil || portNumber < 1 || portNumber > 65535 {
			return false
		}
	}

	hostname := strings.ToLower(strings.TrimSuffix(originURL.Hostname(), "."))
	if ip := net.ParseIP(hostname); ip != nil {
		ipv4 := ip.To4()
		return ipv4 != nil && ipv4[0] == 10
	}
	return strings.HasSuffix(hostname, ".pharmaronclinical.com")
}

func CORS() gin.HandlerFunc {
	config := cors.DefaultConfig()
	config.AllowOriginFunc = isAllowedCORSOrigin
	// 不允许浏览器跨域携带 Cookie 等凭证。
	config.AllowCredentials = false
	config.AllowMethods = []string{"GET", "POST", "PUT", "DELETE", "OPTIONS"}
	config.AllowHeaders = []string{"*"}
	return cors.New(config)
}
