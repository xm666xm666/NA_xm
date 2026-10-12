# SSRF Safe HTTP Client Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在图片和文件下载连接时固定已校验 DNS 结果，阻止 DNS 重绑定，并继续遵循 `HTTP_PROXY`、`HTTPS_PROXY` 和 `NO_PROXY`。

**Architecture:** `common.SSRFProtection` 增加带上下文的单次解析接口，统一完成 URL 规则、私有地址和可选 IP 名单校验。`service` 中新增专用 `RoundTripper`：先用原始请求选择环境代理，再把连接目标改写为已校验 IP，同时保留原始 Host 和 TLS ServerName；每次请求使用不复用连接的 Transport。

**Tech Stack:** Go 1.25.1 标准库 `net`、`net/http`、`net/url`、`crypto/tls`、`testing`；不新增第三方依赖。

## Global Constraints

- 新客户端仅用于本机直接抓取用户可控图片和文件 URL。
- 必须兼容 `HTTP_PROXY`、`HTTPS_PROXY` 和 `NO_PROXY`。
- `AllowPrivateIp=false` 时，域名解析到私有或特殊地址必须拒绝，不受 `ApplyIPFilterForDomain` 关闭影响。
- 同一次请求的 DNS 解析结果必须固定到实际连接；每次重定向重新执行该流程。
- 禁止连接复用，不修改普通上游 API 客户端、渠道代理客户端和 Worker 路径。
- 所有新增代码包含职责或安全原因注释；不新增第三方依赖。

---

### Task 1: 单次 DNS 解析与 IP 校验

**Files:**
- Modify: `common/ssrf_protection.go:3-312`
- Create: `common/ssrf_protection_test.go`

**Interfaces:**
- Produces: `(*SSRFProtection).ResolveURL(context.Context, string) (net.IP, error)`
- Produces: `ResolveURLWithFetchSetting(context.Context, string, bool, bool, bool, bool, []string, []string, []string, bool) (net.IP, error)`

- [ ] **Step 1: 写失败测试，证明域名私有地址在关闭自定义 IP 过滤时仍被拒绝**

```go
func TestResolveURLRejectsPrivateDomainWhenCustomIPFilterDisabled(t *testing.T) {
	protection := &SSRFProtection{
		DomainFilterMode: false,
		IpFilterMode: false,
		lookupIP: func(context.Context, string, string) ([]net.IP, error) {
			return []net.IP{net.ParseIP("127.0.0.1")}, nil
		},
	}

	_, err := protection.ResolveURL(context.Background(), "http://rebind.example/image.png")
	if err == nil || !strings.Contains(err.Error(), "private IP address not allowed") {
		t.Fatalf("expected private IP rejection, got %v", err)
	}
}
```

- [ ] **Step 2: 运行测试并确认按预期失败**

Run: `go test ./common -run TestResolveURLRejectsPrivateDomainWhenCustomIPFilterDisabled -count=1`

Expected: FAIL，提示 `ResolveURL` 或 `lookupIP` 尚不存在。

- [ ] **Step 3: 实现单次解析接口并让现有校验复用它**

```go
// ResolveURL 校验 URL，并返回本次请求唯一允许使用的已解析 IP。
func (p *SSRFProtection) ResolveURL(ctx context.Context, urlStr string) (net.IP, error) {
	// 保留现有协议、端口、IP 字面量和域名名单校验。
	// 域名始终解析一次；先拒绝私有地址，再按 ApplyIPFilterForDomain 决定是否应用自定义 IP 名单。
	// 所有结果通过后返回第一个 IP，空结果返回 DNS 错误。
}

// ValidateURL 保持原有接口，并复用单次解析校验。
func (p *SSRFProtection) ValidateURL(urlStr string) error {
	_, err := p.ResolveURL(context.Background(), urlStr)
	return err
}
```

将 DNS 查询封装为 `lookupIP` 测试钩子，未设置时调用 `net.DefaultResolver.LookupIP`；抽取现有 FetchSetting 构造逻辑，避免 `ValidateURLWithFetchSetting` 和 `ResolveURLWithFetchSetting` 重复配置映射。

- [ ] **Step 4: 运行 common 测试确认通过**

Run: `go test ./common -run 'TestResolveURL|TestIsPrivateIP' -count=1`

Expected: PASS。

- [ ] **Step 5: 单独提交 Task 1**

```bash
git add common/ssrf_protection.go common/ssrf_protection_test.go
git commit --only common/ssrf_protection.go common/ssrf_protection_test.go -m "fix: bind SSRF validation to DNS resolution"
```

### Task 2: 环境代理兼容的安全客户端

**Files:**
- Create: `service/ssrf_http_client.go`
- Create: `service/ssrf_http_client_test.go`
- Modify: `service/download.go:54-69`

**Interfaces:**
- Consumes: `common.ResolveURLWithFetchSetting(...) (net.IP, error)`
- Produces: `GetSSRFHttpClient() *http.Client`

- [ ] **Step 1: 写失败测试，证明一次解析结果固定到实际请求**

```go
func TestSSRFRoundTripperPinsFirstResolution(t *testing.T) {
	var lookups int
	// 本地测试服务验证请求连接成功且 Host 仍为原域名。
	roundTripper := newSSRFRoundTripper(func(context.Context, string) (net.IP, error) {
		lookups++
		if lookups == 1 {
			return net.ParseIP("127.0.0.1"), nil
		}
		return net.ParseIP("127.0.0.2"), nil
	}, func(*http.Request) (*url.URL, error) { return nil, nil })

	// 使用 rebind.example 和测试服务端口请求，断言成功、Host 未改写且 lookups == 1。
}
```

- [ ] **Step 2: 写失败测试，证明代理选择使用原始域名且代理收到固定 IP**

```go
func TestSSRFRoundTripperPinsTargetThroughHTTPProxy(t *testing.T) {
	// proxyFunc 断言输入仍为 public.example，并返回 httptest 代理地址。
	// 代理处理器断言 req.URL.Hostname() 是已校验 IP，req.Host 仍为 public.example。
}

func TestSSRFRoundTripperHonorsNoProxyDecision(t *testing.T) {
	// proxyFunc 对原始域名返回 nil；断言请求直连固定 IP，代理未收到请求。
}
```

- [ ] **Step 3: 运行测试并确认按预期失败**

Run: `go test ./service -run TestSSRFRoundTripper -count=1`

Expected: FAIL，提示 `newSSRFRoundTripper` 尚不存在。

- [ ] **Step 4: 实现最小安全 RoundTripper**

```go
// ssrfRoundTripper 将已校验的 DNS 结果固定到本次实际连接。
type ssrfRoundTripper struct {
	base       *http.Transport
	resolveURL func(context.Context, string) (net.IP, error)
	proxy      func(*http.Request) (*url.URL, error)
}

func (t *ssrfRoundTripper) RoundTrip(req *http.Request) (*http.Response, error) {
	// 先用原始请求计算 ProxyFromEnvironment/NO_PROXY，再解析并校验目标。
	// 克隆请求并把 URL Host 改写为 net.JoinHostPort(已校验 IP, 端口)，Request.Host 保留原始值。
	// 克隆 Transport，关闭 Keep-Alive，固定本次 proxyURL，并为 HTTPS 保留原始 TLS ServerName。
	// HTTPS 代理使用自定义 DialTLSContext，以代理域名校验外层 TLS，目标 TLS 仍校验原始域名。
	return transport.RoundTrip(pinnedRequest)
}
```

客户端超时、连接上限和重定向上限沿用现有 `GetHttpClient`；重定向只限制最多 10 次，实际安全校验由每次 `RoundTrip` 执行，避免二次 DNS 查询。

- [ ] **Step 5: 修改非 Worker 下载入口**

```go
// 非 Worker 下载使用安全客户端，将 DNS 校验结果固定到实际连接。
return GetSSRFHttpClient().Get(originUrl)
```

删除该路径原先独立调用 `ValidateURLWithFetchSetting` 的代码，避免连接前后两次 DNS 解析。

- [ ] **Step 6: 运行定向测试确认通过**

Run: `go test ./common ./service -run 'TestResolveURL|TestSSRFRoundTripper' -count=1`

Expected: PASS。

- [ ] **Step 7: 运行回归与格式检查**

Run: `gofmt -w common/ssrf_protection.go common/ssrf_protection_test.go service/ssrf_http_client.go service/ssrf_http_client_test.go service/download.go`

Run: `go test ./common ./service -count=1`

Run: `go test ./... -count=1`

Expected: 所有可运行命令退出码为 0；若全量测试依赖缺失的外部服务，记录具体失败包和错误，不把它误报为本次回归。

- [ ] **Step 8: 复核注释、最小 diff 和安全属性后提交**

```bash
git diff --check
git diff -- common/ssrf_protection.go common/ssrf_protection_test.go service/ssrf_http_client.go service/ssrf_http_client_test.go service/download.go
git add service/ssrf_http_client.go service/ssrf_http_client_test.go service/download.go
git commit --only service/ssrf_http_client.go service/ssrf_http_client_test.go service/download.go -m "fix: prevent DNS rebinding in file downloads"
```
