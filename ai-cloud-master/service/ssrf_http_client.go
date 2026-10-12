package service

import (
	"context"
	"crypto/tls"
	"fmt"
	"net"
	"net/http"
	"net/url"
	"time"

	"github.com/QuantumNous/new-api/common"
	"github.com/QuantumNous/new-api/setting/system_setting"
)

// ssrfRoundTripper 将代理请求交给原 Transport，并固定直连请求的 DNS 结果。
type ssrfRoundTripper struct {
	base           *http.Transport
	proxyTransport http.RoundTripper
	resolveURL     func(context.Context, string) (net.IP, error)
	proxy          func(*http.Request) (*url.URL, error)
}

// newSSRFRoundTripper 创建可测试的代理分流与直连 SSRF 安全传输器。
func newSSRFRoundTripper(resolveURL func(context.Context, string) (net.IP, error), proxy func(*http.Request) (*url.URL, error)) *ssrfRoundTripper {
	base := &http.Transport{
		MaxIdleConns:        common.RelayMaxIdleConns,
		MaxIdleConnsPerHost: common.RelayMaxIdleConnsPerHost,
		ForceAttemptHTTP2:   true,
		Proxy:               proxy,
	}
	return &ssrfRoundTripper{
		base:           base,
		proxyTransport: base,
		resolveURL:     resolveURL,
		proxy:          proxy,
	}
}

// RoundTrip 先按原域名选择代理，仅对直连请求固定已校验 IP。
func (t *ssrfRoundTripper) RoundTrip(req *http.Request) (*http.Response, error) {
	proxyURL, err := t.proxy(req)
	if err != nil {
		return nil, fmt.Errorf("resolve request proxy: %w", err)
	}
	if proxyURL != nil {
		// 有效代理路径复用原 Transport，由代理承担目标 DNS 与 SSRF 防护。
		return t.proxyTransport.RoundTrip(req)
	}

	ip, err := t.resolveURL(req.Context(), req.URL.String())
	if err != nil {
		return nil, fmt.Errorf("request reject: %w", err)
	}

	if ip == nil {
		return t.base.RoundTrip(req)
	}

	transport := t.base.Clone()
	// 直连安全请求使用独立连接，避免跨 DNS 校验结果复用连接。
	transport.DisableKeepAlives = true
	transport.Proxy = nil

	hostname := req.URL.Hostname()
	port := req.URL.Port()
	if port == "" {
		if req.URL.Scheme == "https" {
			port = "443"
		} else {
			port = "80"
		}
	}

	tlsConfig := transport.TLSClientConfig
	if tlsConfig == nil {
		tlsConfig = &tls.Config{}
	} else {
		tlsConfig = tlsConfig.Clone()
	}
	tlsConfig.ServerName = hostname
	transport.TLSClientConfig = tlsConfig

	pinnedReq := req.Clone(req.Context())
	pinnedURL := *req.URL
	pinnedURL.Host = net.JoinHostPort(ip.String(), port)
	pinnedReq.URL = &pinnedURL
	// 直连使用固定 IP 建连，但应用层 Host 保留原域名。
	pinnedReq.Host = req.URL.Host
	return transport.RoundTrip(pinnedReq)
}

// resolveURLForSSRFRequest 读取当前 FetchSetting 并返回本次请求可连接的固定 IP。
func resolveURLForSSRFRequest(ctx context.Context, urlStr string) (net.IP, error) {
	fetchSetting := system_setting.GetFetchSetting()
	return common.ResolveURLWithFetchSetting(
		ctx,
		urlStr,
		fetchSetting.EnableSSRFProtection,
		fetchSetting.AllowPrivateIp,
		fetchSetting.DomainFilterMode,
		fetchSetting.IpFilterMode,
		fetchSetting.DomainList,
		fetchSetting.IpList,
		fetchSetting.AllowedPorts,
		fetchSetting.ApplyIPFilterForDomain,
	)
}

// checkSSRFRedirect 限制重定向次数；每个新目标由 RoundTrip 重新校验。
func checkSSRFRedirect(_ *http.Request, via []*http.Request) error {
	if len(via) >= 10 {
		return fmt.Errorf("stopped after 10 redirects")
	}
	return nil
}

// GetSSRFHttpClient 返回代理走原 Transport、直连防 DNS 重绑定的 HTTP 客户端。
func GetSSRFHttpClient() *http.Client {
	roundTripper := newSSRFRoundTripper(resolveURLForSSRFRequest, http.ProxyFromEnvironment)
	if client := GetHttpClient(); client != nil && client.Transport != nil {
		// 代理路径复用现有客户端 Transport 和连接池。
		roundTripper.proxyTransport = client.Transport
	}
	client := &http.Client{
		Transport:     roundTripper,
		CheckRedirect: checkSSRFRedirect,
	}
	if common.RelayTimeout != 0 {
		client.Timeout = time.Duration(common.RelayTimeout) * time.Second
	}
	return client
}
