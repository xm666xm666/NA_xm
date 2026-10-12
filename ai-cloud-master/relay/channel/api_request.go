package channel

import (
	"context"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/http/httptrace"
	"strings"
	"sync"
	"time"

	common2 "github.com/QuantumNous/new-api/common"
	"github.com/QuantumNous/new-api/logger"
	"github.com/QuantumNous/new-api/relay/common"
	"github.com/QuantumNous/new-api/relay/constant"
	"github.com/QuantumNous/new-api/relay/helper"
	"github.com/QuantumNous/new-api/service"
	"github.com/QuantumNous/new-api/setting/operation_setting"
	"github.com/QuantumNous/new-api/types"

	"github.com/bytedance/gopkg/util/gopool"
	"github.com/gin-gonic/gin"
	"github.com/gorilla/websocket"
)

// buildRetryAttemptSuffix 基于已使用渠道链路生成重试标签，首次请求不追加标签。
func buildRetryAttemptSuffix(c *gin.Context) string {
	if c == nil {
		return ""
	}

	retryCount := len(c.GetStringSlice("use_channel")) - 1
	if retryCount <= 0 {
		return ""
	}

	return fmt.Sprintf(" | 第%d次重试", retryCount)
}

// logUpstreamRequestStart 记录上游请求开始日志，并附带原始/映射后模型名与渠道 ID 便于定位问题。
func logUpstreamRequestStart(c *gin.Context, info *common.RelayInfo) {
	modelName := ""
	mappedModelName := ""
	channelID := 0
	if info != nil {
		modelName = info.OriginModelName
		if info.IsModelMapped && info.UpstreamModelName != "" && info.UpstreamModelName != info.OriginModelName {
			// 仅在模型确实发生映射时输出映射后的模型名，避免日志噪声。
			mappedModelName = info.UpstreamModelName
		}
		if info.ChannelMeta != nil {
			channelID = info.ChannelId
		}
	}

	modelSummary := fmt.Sprintf("model=%s", modelName)
	if mappedModelName != "" {
		modelSummary = fmt.Sprintf("%s, mapped_model=%s", modelSummary, mappedModelName)
	}

	logger.LogInfo(
		c,
		fmt.Sprintf(
			"上游请求开始%s: %s, channel_id=%d",
			buildRetryAttemptSuffix(c),
			modelSummary,
			channelID,
		),
	)
}

// logUpstreamRequestFinish 记录上游请求结束日志，仅保留状态码与耗时。
func logUpstreamRequestFinish(c *gin.Context, startedAt time.Time, resp *http.Response) {
	if resp == nil {
		return
	}

	duration := time.Since(startedAt)
	logFn := logger.LogInfo
	if resp.StatusCode >= http.StatusBadRequest {
		logFn = logger.LogWarn
	}
	logFn(c, fmt.Sprintf(
		"上游请求结束%s: status=%d, duration=%s",
		buildRetryAttemptSuffix(c),
		resp.StatusCode,
		duration,
	))
}

// upstreamTransferLogger 使用 httptrace 记录“请求已成功写入上游连接”的耗时。
// 该时间点以 WroteRequest 为准，尽量贴近“网关转发耗时”而不包含模型推理时间。
type upstreamTransferLogger struct {
	startedAt   time.Time
	retrySuffix string
	once        sync.Once
	connReused  bool
}

// newUpstreamTransferTrace 为单次上游请求创建转发耗时跟踪器。
func newUpstreamTransferTrace(
	c *gin.Context,
	startedAt time.Time,
) *httptrace.ClientTrace {
	transferLogger := &upstreamTransferLogger{
		startedAt:   startedAt,
		retrySuffix: buildRetryAttemptSuffix(c),
	}

	return &httptrace.ClientTrace{
		GotConn: func(info httptrace.GotConnInfo) {
			// 记录连接是否复用，便于排查转发耗时受建连影响的场景。
			transferLogger.connReused = info.Reused
		},
		WroteRequest: func(info httptrace.WroteRequestInfo) {
			transferLogger.once.Do(func() {
				transferDuration := time.Since(transferLogger.startedAt)
				if info.Err != nil {
					logger.LogWarn(c, fmt.Sprintf(
						"上游请求转发失败%s: transfer_duration=%s, conn_reused=%t, err=%v",
						transferLogger.retrySuffix,
						transferDuration,
						transferLogger.connReused,
						info.Err,
					))
					return
				}

				logger.LogInfo(c, fmt.Sprintf(
					"上游请求已转发%s: transfer_duration=%s, conn_reused=%t",
					transferLogger.retrySuffix,
					transferDuration,
					transferLogger.connReused,
				))
			})
		},
	}
}

func SetupApiRequestHeader(info *common.RelayInfo, c *gin.Context, req *http.Header) {
	if info.RelayMode == constant.RelayModeAudioTranscription || info.RelayMode == constant.RelayModeAudioTranslation {
		// multipart/form-data
	} else if info.RelayMode == constant.RelayModeRealtime {
		// websocket
	} else {
		req.Set("Content-Type", c.Request.Header.Get("Content-Type"))
		req.Set("Accept", c.Request.Header.Get("Accept"))
		if info.IsStream && c.Request.Header.Get("Accept") == "" {
			req.Set("Accept", "text/event-stream")
		}
	}
}

// processHeaderOverride 处理请求头覆盖，支持变量替换
// 支持的变量：{api_key}
func processHeaderOverride(info *common.RelayInfo) (map[string]string, error) {
	headerOverride := make(map[string]string)
	for k, v := range info.HeadersOverride {
		str, ok := v.(string)
		if !ok {
			return nil, types.NewError(nil, types.ErrorCodeChannelHeaderOverrideInvalid)
		}

		// 替换支持的变量
		if strings.Contains(str, "{api_key}") {
			str = strings.ReplaceAll(str, "{api_key}", info.ApiKey)
		}

		headerOverride[k] = str
	}
	return headerOverride, nil
}

func DoApiRequest(a Adaptor, c *gin.Context, info *common.RelayInfo, requestBody io.Reader) (*http.Response, error) {
	fullRequestURL, err := a.GetRequestURL(info)
	if err != nil {
		return nil, fmt.Errorf("get request url failed: %w", err)
	}
	if common2.DebugEnabled {
		println("fullRequestURL:", fullRequestURL)
	}
	req, err := http.NewRequestWithContext(common2.RequestContext(c.Request), c.Request.Method, fullRequestURL, requestBody)
	if err != nil {
		return nil, fmt.Errorf("new request failed: %w", err)
	}
	headers := req.Header
	headerOverride, err := processHeaderOverride(info)
	if err != nil {
		return nil, err
	}
	for key, value := range headerOverride {
		headers.Set(key, value)
	}
	err = a.SetupRequestHeader(c, &headers, info)
	if err != nil {
		return nil, fmt.Errorf("setup request header failed: %w", err)
	}
	resp, err := doRequestWithSummary(c, req, info)
	if err != nil {
		return nil, fmt.Errorf("do request failed: %w", err)
	}
	return resp, nil
}

func DoFormRequest(a Adaptor, c *gin.Context, info *common.RelayInfo, requestBody io.Reader) (*http.Response, error) {
	fullRequestURL, err := a.GetRequestURL(info)
	if err != nil {
		return nil, fmt.Errorf("get request url failed: %w", err)
	}
	if common2.DebugEnabled {
		println("fullRequestURL:", fullRequestURL)
	}
	req, err := http.NewRequestWithContext(common2.RequestContext(c.Request), c.Request.Method, fullRequestURL, requestBody)
	if err != nil {
		return nil, fmt.Errorf("new request failed: %w", err)
	}
	// set form data
	req.Header.Set("Content-Type", c.Request.Header.Get("Content-Type"))
	headers := req.Header
	headerOverride, err := processHeaderOverride(info)
	if err != nil {
		return nil, err
	}
	for key, value := range headerOverride {
		headers.Set(key, value)
	}
	err = a.SetupRequestHeader(c, &headers, info)
	if err != nil {
		return nil, fmt.Errorf("setup request header failed: %w", err)
	}
	resp, err := doRequestWithSummary(c, req, info)
	if err != nil {
		return nil, fmt.Errorf("do request failed: %w", err)
	}
	return resp, nil
}

func DoWssRequest(a Adaptor, c *gin.Context, info *common.RelayInfo, requestBody io.Reader) (*websocket.Conn, error) {
	fullRequestURL, err := a.GetRequestURL(info)
	if err != nil {
		return nil, fmt.Errorf("get request url failed: %w", err)
	}
	targetHeader := http.Header{}
	headerOverride, err := processHeaderOverride(info)
	if err != nil {
		return nil, err
	}
	for key, value := range headerOverride {
		targetHeader.Set(key, value)
	}
	err = a.SetupRequestHeader(c, &targetHeader, info)
	if err != nil {
		return nil, fmt.Errorf("setup request header failed: %w", err)
	}
	targetHeader.Set("Content-Type", c.Request.Header.Get("Content-Type"))
	targetConn, _, err := websocket.DefaultDialer.Dial(fullRequestURL, targetHeader)
	if err != nil {
		return nil, fmt.Errorf("dial failed to %s: %w", fullRequestURL, err)
	}
	// send request body
	//all, err := io.ReadAll(requestBody)
	//err = service.WssString(c, targetConn, string(all))
	return targetConn, nil
}

func startPingKeepAlive(c *gin.Context, pingInterval time.Duration) context.CancelFunc {
	pingerCtx, stopPinger := context.WithCancel(context.Background())

	gopool.Go(func() {
		defer func() {
			// 增加panic恢复处理
			if r := recover(); r != nil {
				if common2.DebugEnabled {
					println("SSE ping goroutine panic recovered:", fmt.Sprintf("%v", r))
				}
			}
			if common2.DebugEnabled {
				println("SSE ping goroutine stopped.")
			}
		}()

		if pingInterval <= 0 {
			pingInterval = helper.DefaultPingInterval
		}

		ticker := time.NewTicker(pingInterval)
		// 确保在任何情况下都清理ticker
		defer func() {
			ticker.Stop()
			if common2.DebugEnabled {
				println("SSE ping ticker stopped")
			}
		}()

		var pingMutex sync.Mutex
		if common2.DebugEnabled {
			println("SSE ping goroutine started")
		}

		// 增加超时控制，防止goroutine长时间运行
		maxPingDuration := 120 * time.Minute // 最大ping持续时间
		pingTimeout := time.NewTimer(maxPingDuration)
		defer pingTimeout.Stop()

		for {
			select {
			// 发送 ping 数据
			case <-ticker.C:
				if err := sendPingData(c, &pingMutex); err != nil {
					if common2.DebugEnabled {
						println("SSE ping error, stopping goroutine:", err.Error())
					}
					return
				}
			// 收到退出信号
			case <-pingerCtx.Done():
				return
			// request 结束
			case <-c.Request.Context().Done():
				return
			// 超时保护，防止goroutine无限运行
			case <-pingTimeout.C:
				if common2.DebugEnabled {
					println("SSE ping goroutine timeout, stopping")
				}
				return
			}
		}
	})

	return stopPinger
}

func sendPingData(c *gin.Context, mutex *sync.Mutex) error {
	// 增加超时控制，防止锁死等待
	done := make(chan error, 1)
	go func() {
		mutex.Lock()
		defer mutex.Unlock()

		err := helper.PingData(c)
		if err != nil {
			logger.LogError(c, "SSE ping error: "+err.Error())
			done <- err
			return
		}

		if common2.DebugEnabled {
			println("SSE ping data sent.")
		}
		done <- nil
	}()

	// 设置发送ping数据的超时时间
	select {
	case err := <-done:
		return err
	case <-time.After(10 * time.Second):
		return errors.New("SSE ping data send timeout")
	case <-c.Request.Context().Done():
		return errors.New("request context cancelled during ping")
	}
}

func DoRequest(c *gin.Context, req *http.Request, info *common.RelayInfo) (*http.Response, error) {
	return doRequestWithSummary(c, req, info)
}

// doRequestWithSummary 负责统一的上游请求发送以及开始结束日志。
func doRequestWithSummary(c *gin.Context, req *http.Request, info *common.RelayInfo) (*http.Response, error) {
	// 客户端已经断开时，不再继续发起下游请求，直接返回本地取消错误。
	if common2.IsRequestCanceled(c.Request) {
		return nil, types.NewClientDisconnectedError()
	}

	var client *http.Client
	var err error
	if info.ChannelSetting.Proxy != "" {
		client, err = service.NewProxyHttpClient(info.ChannelSetting.Proxy)
		if err != nil {
			return nil, fmt.Errorf("new proxy http client failed: %w", err)
		}
	} else {
		client = service.GetHttpClient()
	}

	var stopPinger context.CancelFunc
	if info.IsStream {
		helper.SetEventStreamHeaders(c)
		// 处理流式请求的 ping 保活
		generalSettings := operation_setting.GetGeneralSetting()
		if generalSettings.PingIntervalEnabled && !info.DisablePing {
			pingInterval := time.Duration(generalSettings.PingIntervalSeconds) * time.Second
			stopPinger = startPingKeepAlive(c, pingInterval)
			// 使用defer确保在任何情况下都能停止ping goroutine
			defer func() {
				if stopPinger != nil {
					stopPinger()
					if common2.DebugEnabled {
						println("SSE ping goroutine stopped by defer")
					}
				}
			}()
		}
	}

	startedAt := time.Now()
	logUpstreamRequestStart(c, info)
	req = req.WithContext(
		httptrace.WithClientTrace(
			req.Context(),
			newUpstreamTransferTrace(c, startedAt),
		),
	)

	resp, err := client.Do(req)
	if err != nil {
		// 请求发送过程中若客户端中途断开，统一返回本地取消错误，避免污染渠道失败语义。
		if common2.IsRequestCanceled(c.Request) {
			return nil, types.NewClientDisconnectedError()
		}
		return nil, types.NewError(err, types.ErrorCodeDoRequestFailed, types.ErrOptionWithHideErrMsg("upstream error: do request failed"))
	}
	if resp == nil {
		return nil, errors.New("resp is nil")
	}
	logUpstreamRequestFinish(c, startedAt, resp)

	_ = req.Body.Close()
	_ = c.Request.Body.Close()
	return resp, nil
}

func DoTaskApiRequest(a TaskAdaptor, c *gin.Context, info *common.RelayInfo, requestBody io.Reader) (*http.Response, error) {
	fullRequestURL, err := a.BuildRequestURL(info)
	if err != nil {
		return nil, err
	}
	req, err := http.NewRequestWithContext(common2.RequestContext(c.Request), c.Request.Method, fullRequestURL, requestBody)
	if err != nil {
		return nil, fmt.Errorf("new request failed: %w", err)
	}
	// 为任务请求保留可重复获取请求体的能力，兼容后续可能的重试或重放场景。
	req.GetBody = func() (io.ReadCloser, error) {
		return io.NopCloser(requestBody), nil
	}

	err = a.BuildRequestHeader(c, req, info)
	if err != nil {
		return nil, fmt.Errorf("setup request header failed: %w", err)
	}
	resp, err := doRequestWithSummary(c, req, info)
	if err != nil {
		return nil, fmt.Errorf("do request failed: %w", err)
	}
	return resp, nil
}
