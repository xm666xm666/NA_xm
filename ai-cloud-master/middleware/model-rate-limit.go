package middleware

import (
	"context"
	"fmt"
	"net/http"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/QuantumNous/new-api/common"
	"github.com/QuantumNous/new-api/common/limiter"
	"github.com/QuantumNous/new-api/constant"
	"github.com/QuantumNous/new-api/dto"
	"github.com/QuantumNous/new-api/logger"
	"github.com/QuantumNous/new-api/service"
	"github.com/QuantumNous/new-api/setting"
	"github.com/QuantumNous/new-api/types"

	"github.com/gin-gonic/gin"
	"github.com/go-redis/redis/v8"
)

const (
	ModelRequestRateLimitCountMark        = "MRRL"
	ModelRequestRateLimitSuccessCountMark = "MRRLS"
)

const (
	// tokenModelLimitTypeConcurrency 标识令牌-模型并发限制。
	tokenModelLimitTypeConcurrency = "concurrency"
	// tokenModelLimitTypeRPM 标识令牌-模型 RPM 限制。
	tokenModelLimitTypeRPM = "rpm"
	// tokenModelLimitTypeTPM 标识令牌-模型 TPM 记账桶。
	tokenModelLimitTypeTPM = "tpm"
	// tokenModelTPMWindowSeconds 固定 TPM 的滚动统计窗口。
	tokenModelTPMWindowSeconds int64 = 60
	// tokenModelRateLimitRuleContextKey 保存当前请求命中的限流规则。
	tokenModelRateLimitRuleContextKey = "token_model_rate_limit_rule"
	// tokenModelTPMReservationContextKey 保存当前请求的 Prompt Token 预占。
	tokenModelTPMReservationContextKey = "token_model_tpm_reservation"
)

// tokenModelMemoryLimiter 提供无 Redis 场景下的最小内存实现。
var tokenModelMemoryLimiter tokenModelMemoryLimiterState

// acquireRedisTokenModelConcurrencyScript 原子完成过期租约清理、并发准入和租约写入。
const acquireRedisTokenModelConcurrencyScript = `
redis.call("ZREMRANGEBYSCORE", KEYS[1], "-inf", ARGV[1])
local leaseExists = redis.call("EXISTS", KEYS[2])
local activeCount = redis.call("ZCARD", KEYS[1])
if leaseExists == 0 and activeCount >= tonumber(ARGV[5]) then
	return 0
end
redis.call("SET", KEYS[2], "1", "PX", ARGV[4])
redis.call("ZADD", KEYS[1], ARGV[2], ARGV[3])
redis.call("PEXPIRE", KEYS[1], ARGV[4])
return 1
`

// checkAndRecordRedisTokenModelRPMScript 原子完成窗口清理、RPM 准入和请求记账。
const checkAndRecordRedisTokenModelRPMScript = `
redis.call("ZREMRANGEBYSCORE", KEYS[1], "-inf", ARGV[1])
local count = redis.call("ZCARD", KEYS[1])
if count >= tonumber(ARGV[4]) then
	return 0
end
redis.call("ZADD", KEYS[1], ARGV[2], ARGV[3])
redis.call("EXPIRE", KEYS[1], ARGV[5])
return 1
`

// reserveRedisTokenModelTPMScript 保证 Redis 模式的 Prompt 预占准入不可被并发请求穿透。
const reserveRedisTokenModelTPMScript = `
redis.call("ZREMRANGEBYSCORE", KEYS[1], "-inf", ARGV[1])
local members = redis.call("ZRANGE", KEYS[1], 0, -1)
local total = 0
for _, member in ipairs(members) do
	local tokens = tonumber(string.match(member, "^[^:]+:([^:]+):"))
	if not tokens then
		return redis.error_reply("invalid token model tpm member")
	end
	total = total + tokens
end
local requested = tonumber(ARGV[4])
local limit = tonumber(ARGV[5])
if total + requested > limit then
	return 0
end
redis.call("ZADD", KEYS[1], ARGV[2], ARGV[3])
redis.call("EXPIRE", KEYS[1], ARGV[6])
return 1
`

// recordRedisTokenModelRealtimeTPMScript 原子记录 Realtime 实际 usage，并返回窗口内累计 Token。
const recordRedisTokenModelRealtimeTPMScript = `
redis.call("ZREMRANGEBYSCORE", KEYS[1], "-inf", ARGV[1])
local members = redis.call("ZRANGE", KEYS[1], 0, -1)
local total = 0
for _, member in ipairs(members) do
	local tokens = tonumber(string.match(member, "^[^:]+:([^:]+):"))
	if not tokens then
		return redis.error_reply("invalid token model tpm member")
	end
	total = total + tokens
end
local requested = tonumber(ARGV[4])
if requested > 0 then
	redis.call("ZADD", KEYS[1], ARGV[2], ARGV[3])
end
redis.call("EXPIRE", KEYS[1], ARGV[5])
return total + requested
`

// settleRedisTokenModelTPMScript 原子修正 Prompt，并按响应结束时间追加 Completion。
const settleRedisTokenModelTPMScript = `
redis.call("ZREMRANGEBYSCORE", KEYS[1], "-inf", ARGV[1])
redis.call("ZREM", KEYS[1], ARGV[2])
if tonumber(ARGV[3]) > tonumber(ARGV[1]) and tonumber(ARGV[5]) > 0 then
	redis.call("ZADD", KEYS[1], ARGV[3], ARGV[4])
end
if tonumber(ARGV[8]) > 0 then
	redis.call("ZADD", KEYS[1], ARGV[6], ARGV[7])
end
redis.call("EXPIRE", KEYS[1], ARGV[9])
return 1
`

// tokenModelRateLimitRule 表示单个 token+model 的限流配置。
type tokenModelRateLimitRule struct {
	ModelName               string
	ConcurrencyLimitEnabled bool
	ConcurrencyLimit        int
	RPMLimitEnabled         bool
	RPMLimit                int
	TPMLimitEnabled         bool
	TPMLimit                int
}

// tokenModelLease 持有一次请求级并发租约的释放信息。
type tokenModelLease struct {
	bucketKey   string
	requestID   string
	stopRenewer chan struct{}
	renewerDone chan struct{}
}

// tokenModelTPMReservation 保存请求开始时写入的 Prompt Token 预占信息。
type tokenModelTPMReservation struct {
	bucketKey       string
	requestID       string
	member          string
	startedAtMillis int64
	reservedTokens  int
}

// tokenModelMemoryLimiterState 保存内存模式下的并发租约与 RPM 计数。
type tokenModelMemoryLimiterState struct {
	mutex       sync.Mutex
	concurrency map[string]map[string]int64
	rpm         map[string][]int64
	tpm         map[string][]tokenModelUsageRecord
}

// tokenModelUsageRecord 保存单次请求的 Prompt 预占或实际 usage 记账信息。
type tokenModelUsageRecord struct {
	recordedAtMillis int64
	requestID        string
	tokens           int
}

// init 确保内存模式下的 map 按需初始化。
func (l *tokenModelMemoryLimiterState) init() {
	if l.concurrency != nil && l.rpm != nil && l.tpm != nil {
		return
	}
	l.concurrency = make(map[string]map[string]int64)
	l.rpm = make(map[string][]int64)
	l.tpm = make(map[string][]tokenModelUsageRecord)
}

// TokenModelRequestRateLimit 在渠道选择前按 token+原始模型名执行请求前限流预检查。
func TokenModelRequestRateLimit() gin.HandlerFunc {
	return func(c *gin.Context) {
		if !shouldApplyTokenModelRequestRateLimit(c) {
			c.Next()
			return
		}

		rule, matched := getMatchedTokenModelRateLimitRule(c)
		if !matched {
			c.Next()
			return
		}
		// 保存命中规则，供 Relay 在完成 Prompt Token 估算后执行预占。
		c.Set(tokenModelRateLimitRuleContextKey, rule)

		requestID := c.GetString(common.RequestIdKey)
		if requestID == "" {
			// 兜底生成 request_id，避免日志与租约键缺失。
			requestID = common.GetTimeString() + common.GetRandomString(8)
			c.Set(common.RequestIdKey, requestID)
		}

		lease, ok := acquireTokenModelConcurrencyLease(c, rule, requestID)
		if !ok {
			return
		}

		if !checkTokenModelRPM(c, rule) {
			releaseTokenModelConcurrencyLease(c, lease)
			return
		}

		c.Next()
		// 先完成实际 Token 结算，再释放并发租约，避免下一请求看到尚未结算的旧预占。
		settleTokenModelTPMUsage(c)
		releaseTokenModelConcurrencyLease(c, lease)
	}
}

// getMatchedTokenModelRateLimitRule 仅对命中的原始模型配置返回限流规则。
func getMatchedTokenModelRateLimitRule(c *gin.Context) (tokenModelRateLimitRule, bool) {
	limitMaps, ok := common.GetContextKeyType[[]map[string]any](c, constant.ContextKeyTokenModelRateLimits)
	if !ok || len(limitMaps) == 0 {
		return tokenModelRateLimitRule{}, false
	}

	modelRequest, _, err := getModelRequest(c)
	if err != nil || modelRequest == nil {
		return tokenModelRateLimitRule{}, false
	}

	modelName := strings.TrimSpace(modelRequest.Model)
	if modelName == "" {
		return tokenModelRateLimitRule{}, false
	}

	// 提前保存原始模型名，便于后续日志与渠道选择链路复用。
	common.SetContextKey(c, constant.ContextKeyOriginalModel, modelName)
	for _, item := range limitMaps {
		rule := parseTokenModelRateLimitRule(item)
		if rule.ModelName == modelName {
			return rule, true
		}
	}
	return tokenModelRateLimitRule{}, false
}

// parseTokenModelRateLimitRule 将运行时 map 配置转换为明确结构。
func parseTokenModelRateLimitRule(item map[string]any) tokenModelRateLimitRule {
	return tokenModelRateLimitRule{
		ModelName:               strings.TrimSpace(getTokenModelLimitString(item, "model_name")),
		ConcurrencyLimitEnabled: getTokenModelLimitBool(item, "concurrency_limit_enabled"),
		ConcurrencyLimit:        getTokenModelLimitInt(item, "concurrency_limit"),
		RPMLimitEnabled:         getTokenModelLimitBool(item, "rpm_limit_enabled"),
		RPMLimit:                getTokenModelLimitInt(item, "rpm_limit"),
		// 仅保留 TPM 结构，为后续请求后记账接入预留统一配置入口。
		TPMLimitEnabled: getTokenModelLimitBool(item, "tpm_limit_enabled"),
		TPMLimit:        getTokenModelLimitInt(item, "tpm_limit"),
	}
}

// acquireTokenModelConcurrencyLease 为命中并发配置的请求申请 request_id 级租约。
func acquireTokenModelConcurrencyLease(c *gin.Context, rule tokenModelRateLimitRule, requestID string) (*tokenModelLease, bool) {
	if !rule.ConcurrencyLimitEnabled || rule.ConcurrencyLimit < 1 {
		return nil, true
	}

	modelName := common.GetContextKeyString(c, constant.ContextKeyOriginalModel)
	lease := &tokenModelLease{
		bucketKey: buildTokenModelLimitBucketKey(
			c.GetInt("token_id"),
			modelName,
			tokenModelLimitTypeConcurrency,
		),
		requestID:   requestID,
		stopRenewer: make(chan struct{}),
		renewerDone: make(chan struct{}),
	}

	ctx := common.RequestContext(c.Request)
	ttl := getTokenModelConcurrencyLeaseTTL()
	var err error
	var allowed bool
	if common.RedisEnabled {
		allowed, err = acquireRedisTokenModelConcurrencyLease(
			ctx,
			lease.bucketKey,
			lease.requestID,
			rule.ConcurrencyLimit,
			ttl,
		)
	} else {
		allowed, err = tokenModelMemoryLimiter.acquireConcurrencyLease(
			lease.bucketKey,
			lease.requestID,
			rule.ConcurrencyLimit,
			ttl,
		)
	}
	if err != nil {
		logTokenModelRateLimitError(
			c,
			tokenModelLimitTypeConcurrency,
			types.ErrorCodeTokenModelConcurrencyLimitExceeded,
			"检查令牌模型并发限制失败",
			err,
		)
		abortWithOpenAiMessage(c, http.StatusInternalServerError, "rate_limit_check_failed")
		return nil, false
	}
	if !allowed {
		message := fmt.Sprintf("当前令牌在模型 %s 上已超过并发数限制", modelName)
		logTokenModelRateLimitError(
			c,
			tokenModelLimitTypeConcurrency,
			types.ErrorCodeTokenModelConcurrencyLimitExceeded,
			message,
			err,
		)
		abortWithOpenAiMessage(
			c,
			http.StatusTooManyRequests,
			message,
			string(types.ErrorCodeTokenModelConcurrencyLimitExceeded),
		)
		return nil, false
	}
	startTokenModelConcurrencyLeaseRenewer(c, lease, ttl)
	return lease, true
}

// releaseTokenModelConcurrencyLease 在请求结束后尽力释放租约，失败时依赖 TTL 兜底。
func releaseTokenModelConcurrencyLease(c *gin.Context, lease *tokenModelLease) {
	if lease == nil {
		return
	}

	stopTokenModelConcurrencyLeaseRenewer(lease)
	var err error
	if common.RedisEnabled {
		// 请求结束或客户端断开后 request context 可能已取消，释放 Redis 租约必须使用独立短超时上下文。
		ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
		defer cancel()
		err = releaseRedisTokenModelConcurrencyLease(ctx, lease.bucketKey, lease.requestID)
	} else {
		tokenModelMemoryLimiter.releaseConcurrencyLease(lease.bucketKey, lease.requestID)
	}
	if err != nil {
		logTokenModelRateLimitError(
			c,
			tokenModelLimitTypeConcurrency,
			types.ErrorCodeTokenModelConcurrencyLimitExceeded,
			"释放令牌模型并发租约失败",
			err,
		)
	}
}

// startTokenModelConcurrencyLeaseRenewer 在长请求执行期间周期性续租，避免 TTL 误回收活跃并发。
func startTokenModelConcurrencyLeaseRenewer(c *gin.Context, lease *tokenModelLease, ttl time.Duration) {
	if lease == nil || ttl <= 0 {
		return
	}

	interval := ttl / 2
	if interval < 10*time.Millisecond {
		interval = 10 * time.Millisecond
	}
	requestCtx := common.RequestContext(c.Request)
	go func() {
		ticker := time.NewTicker(interval)
		defer func() {
			ticker.Stop()
			close(lease.renewerDone)
		}()
		for {
			select {
			case <-lease.stopRenewer:
				return
			case <-requestCtx.Done():
				return
			case <-ticker.C:
				if err := renewTokenModelConcurrencyLease(requestCtx, lease, ttl); err != nil {
					logTokenModelRateLimitError(
						c,
						tokenModelLimitTypeConcurrency,
						types.ErrorCodeTokenModelConcurrencyLimitExceeded,
						"续租令牌模型并发租约失败",
						err,
					)
				}
			}
		}
	}()
}

// stopTokenModelConcurrencyLeaseRenewer 先停止续租协程，再执行释放，避免续租与释放互相覆盖。
func stopTokenModelConcurrencyLeaseRenewer(lease *tokenModelLease) {
	if lease == nil || lease.stopRenewer == nil || lease.renewerDone == nil {
		return
	}
	select {
	case <-lease.stopRenewer:
	default:
		close(lease.stopRenewer)
	}
	<-lease.renewerDone
}

// renewTokenModelConcurrencyLease 刷新活跃请求的租约 TTL，仅用于仍在执行中的请求。
func renewTokenModelConcurrencyLease(ctx context.Context, lease *tokenModelLease, ttl time.Duration) error {
	if lease == nil {
		return nil
	}
	if common.RedisEnabled {
		return renewRedisTokenModelConcurrencyLease(ctx, lease.bucketKey, lease.requestID, ttl)
	}
	tokenModelMemoryLimiter.renewConcurrencyLease(lease.bucketKey, lease.requestID, ttl)
	return nil
}

// checkTokenModelRPM 在请求进入渠道前直接执行 RPM 预检查并记账。
func checkTokenModelRPM(c *gin.Context, rule tokenModelRateLimitRule) bool {
	if !rule.RPMLimitEnabled || rule.RPMLimit < 1 {
		return true
	}

	modelName := common.GetContextKeyString(c, constant.ContextKeyOriginalModel)
	bucketKey := buildTokenModelLimitBucketKey(
		c.GetInt("token_id"),
		modelName,
		tokenModelLimitTypeRPM,
	)
	var err error
	var allowed bool
	if common.RedisEnabled {
		allowed, err = checkAndRecordRedisTokenModelRPM(
			common.RequestContext(c.Request),
			bucketKey,
			rule.RPMLimit,
			60,
		)
	} else {
		allowed, err = tokenModelMemoryLimiter.checkAndRecordRPM(bucketKey, rule.RPMLimit, 60)
	}
	if err != nil {
		logTokenModelRateLimitError(
			c,
			tokenModelLimitTypeRPM,
			types.ErrorCodeTokenModelRPMLimitExceeded,
			"检查令牌模型 RPM 限制失败",
			err,
		)
		abortWithOpenAiMessage(c, http.StatusInternalServerError, "rate_limit_check_failed")
		return false
	}
	if !allowed {
		message := fmt.Sprintf("当前令牌在模型 %s 上已超过 RPM 限制", modelName)
		logTokenModelRateLimitError(
			c,
			tokenModelLimitTypeRPM,
			types.ErrorCodeTokenModelRPMLimitExceeded,
			message,
			err,
		)
		abortWithOpenAiMessage(
			c,
			http.StatusTooManyRequests,
			message,
			string(types.ErrorCodeTokenModelRPMLimitExceeded),
		)
		return false
	}
	return true
}

// ReserveTokenModelTPM 用估算的 Prompt Token 原子预占 TPM，不修改用户请求的最大输出长度。
func ReserveTokenModelTPM(c *gin.Context, promptTokens int) bool {
	ruleValue, exists := c.Get(tokenModelRateLimitRuleContextKey)
	rule, matched := ruleValue.(tokenModelRateLimitRule)
	if !exists || !matched || !rule.TPMLimitEnabled || rule.TPMLimit < 1 {
		return true
	}
	if promptTokens < 0 {
		promptTokens = 0
	}

	requestID := c.GetString(common.RequestIdKey)
	modelName := common.GetContextKeyString(c, constant.ContextKeyOriginalModel)
	bucketKey := buildTokenModelLimitBucketKey(
		c.GetInt("token_id"),
		modelName,
		tokenModelLimitTypeTPM,
	)
	reservation := newTokenModelTPMReservation(bucketKey, requestID, promptTokens)

	var err error
	var allowed bool
	if common.RedisEnabled {
		allowed, err = reserveRedisTokenModelTPM(
			common.RequestContext(c.Request),
			reservation,
			rule.TPMLimit,
			tokenModelTPMWindowSeconds,
		)
	} else {
		allowed, err = tokenModelMemoryLimiter.reserveTPM(
			bucketKey,
			requestID,
			promptTokens,
			rule.TPMLimit,
			tokenModelTPMWindowSeconds,
		)
	}
	if err != nil {
		logTokenModelRateLimitError(
			c,
			tokenModelLimitTypeTPM,
			types.ErrorCodeTokenModelTPMLimitExceeded,
			"预占令牌模型 TPM 失败",
			err,
		)
		abortWithOpenAiMessage(c, http.StatusInternalServerError, "rate_limit_check_failed")
		return false
	}
	if !allowed {
		message := fmt.Sprintf(
			"当前令牌在模型 %s 上的 Prompt Token 预占会超过 TPM 限制（prompt=%d, limit=%d）",
			modelName,
			promptTokens,
			rule.TPMLimit,
		)
		logTokenModelRateLimitError(
			c,
			tokenModelLimitTypeTPM,
			types.ErrorCodeTokenModelTPMLimitExceeded,
			message,
			nil,
		)
		abortWithOpenAiMessage(
			c,
			http.StatusTooManyRequests,
			message,
			string(types.ErrorCodeTokenModelTPMLimitExceeded),
		)
		return false
	}

	c.Set(tokenModelTPMReservationContextKey, reservation)
	return true
}

// CheckTokenModelRealtimeTPM 在 WebSocket Upgrade 前只读检查当前 TPM 是否已经耗尽。
func CheckTokenModelRealtimeTPM(c *gin.Context) bool {
	ruleValue, exists := c.Get(tokenModelRateLimitRuleContextKey)
	rule, matched := ruleValue.(tokenModelRateLimitRule)
	if !exists || !matched || !rule.TPMLimitEnabled || rule.TPMLimit < 1 {
		return true
	}

	modelName := common.GetContextKeyString(c, constant.ContextKeyOriginalModel)
	bucketKey := buildTokenModelLimitBucketKey(
		c.GetInt("token_id"),
		modelName,
		tokenModelLimitTypeTPM,
	)
	var err error
	var recordedTotal int
	if common.RedisEnabled {
		recordedTotal, err = getRedisTokenModelTPMRecordedTotal(
			common.RequestContext(c.Request),
			bucketKey,
			tokenModelTPMWindowSeconds,
		)
	} else {
		recordedTotal = tokenModelMemoryLimiter.getRecordedTPMTotal(
			bucketKey,
			tokenModelTPMWindowSeconds,
		)
	}
	if err != nil {
		logTokenModelRateLimitError(
			c,
			tokenModelLimitTypeTPM,
			types.ErrorCodeTokenModelTPMLimitExceeded,
			"检查 Realtime 令牌模型 TPM 限制失败",
			err,
		)
		abortWithOpenAiMessage(c, http.StatusInternalServerError, "rate_limit_check_failed")
		return false
	}
	if recordedTotal < rule.TPMLimit {
		return true
	}

	message := fmt.Sprintf(
		"当前令牌在模型 %s 上最近 60 秒 TPM 已达到限制（used=%d, limit=%d）",
		modelName,
		recordedTotal,
		rule.TPMLimit,
	)
	logTokenModelRateLimitError(
		c,
		tokenModelLimitTypeTPM,
		types.ErrorCodeTokenModelTPMLimitExceeded,
		message,
		nil,
	)
	abortWithOpenAiMessage(
		c,
		http.StatusTooManyRequests,
		message,
		string(types.ErrorCodeTokenModelTPMLimitExceeded),
	)
	return false
}

// RecordTokenModelRealtimeTPMUsage 增量记录 Realtime 实际 usage，并在达到 TPM 上限时返回 false。
func RecordTokenModelRealtimeTPMUsage(c *gin.Context, totalTokens int) (bool, error) {
	ruleValue, exists := c.Get(tokenModelRateLimitRuleContextKey)
	rule, matched := ruleValue.(tokenModelRateLimitRule)
	if !exists || !matched || !rule.TPMLimitEnabled || rule.TPMLimit < 1 {
		return true, nil
	}
	if totalTokens < 0 {
		totalTokens = 0
	}

	modelName := common.GetContextKeyString(c, constant.ContextKeyOriginalModel)
	bucketKey := buildTokenModelLimitBucketKey(
		c.GetInt("token_id"),
		modelName,
		tokenModelLimitTypeTPM,
	)
	requestID := c.GetString(common.RequestIdKey)
	var err error
	var recordedTotal int
	if common.RedisEnabled {
		recordedTotal, err = recordRedisTokenModelRealtimeTPMUsage(
			common.RequestContext(c.Request),
			bucketKey,
			requestID,
			totalTokens,
			tokenModelTPMWindowSeconds,
		)
	} else {
		recordedTotal = tokenModelMemoryLimiter.recordRealtimeTPMUsage(
			bucketKey,
			requestID,
			totalTokens,
			tokenModelTPMWindowSeconds,
		)
	}
	if err != nil {
		logTokenModelRateLimitError(
			c,
			tokenModelLimitTypeTPM,
			types.ErrorCodeTokenModelTPMLimitExceeded,
			"记录 Realtime 令牌模型 TPM 失败",
			err,
		)
		return false, err
	}
	if recordedTotal < rule.TPMLimit {
		return true, nil
	}

	message := fmt.Sprintf(
		"当前令牌在模型 %s 上最近 60 秒 TPM 已达到限制（used=%d, limit=%d）",
		modelName,
		recordedTotal,
		rule.TPMLimit,
	)
	logTokenModelRateLimitError(
		c,
		tokenModelLimitTypeTPM,
		types.ErrorCodeTokenModelTPMLimitExceeded,
		message,
		nil,
	)
	return false, nil
}

// settleTokenModelTPMUsage 有可靠 usage 时分时结算，否则保留 Prompt 预占自然过期。
func settleTokenModelTPMUsage(c *gin.Context) {
	reservationValue, exists := c.Get(tokenModelTPMReservationContextKey)
	reservation, reserved := reservationValue.(*tokenModelTPMReservation)
	if !exists || !reserved || reservation == nil {
		return
	}

	usage, ok := common.GetContextKeyType[*dto.Usage](c, constant.ContextKeyTokenModelRequestUsage)
	if !ok || !service.ValidUsage(usage) {
		// 无法确认输出用量时，仅保留请求开始时的 Prompt 预占。
		return
	}
	promptTokens := usage.PromptTokens
	if promptTokens < 0 {
		promptTokens = 0
	}
	completionTokens := usage.CompletionTokens
	if completionTokens < 0 {
		completionTokens = 0
	}

	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()

	var err error
	if common.RedisEnabled {
		err = settleRedisTokenModelTPM(
			ctx,
			reservation,
			promptTokens,
			completionTokens,
			tokenModelTPMWindowSeconds,
		)
	} else {
		tokenModelMemoryLimiter.settleTPM(
			reservation.bucketKey,
			reservation.requestID,
			promptTokens,
			completionTokens,
			tokenModelTPMWindowSeconds,
		)
	}
	if err != nil {
		logTokenModelRateLimitError(
			c,
			tokenModelLimitTypeTPM,
			types.ErrorCodeTokenModelTPMLimitExceeded,
			"结算令牌模型 TPM 失败",
			err,
		)
	}
}

// buildTokenModelLimitBucketKey 构造 token_id + 原始模型名维度的存储键。
func buildTokenModelLimitBucketKey(tokenID int, modelName string, limitType string) string {
	return fmt.Sprintf("tokenModelRateLimit:%s:%d:%s", limitType, tokenID, modelName)
}

// shouldApplyTokenModelRequestRateLimit 仅在一期验收范围内启用新令牌模型限流。
func shouldApplyTokenModelRequestRateLimit(c *gin.Context) bool {
	path := c.Request.URL.Path
	if strings.HasPrefix(path, "/v1beta/models/") {
		return true
	}
	if !strings.HasPrefix(path, "/v1/") {
		return false
	}
	if strings.HasPrefix(path, "/v1/video/generations") || strings.HasPrefix(path, "/v1/videos") {
		return false
	}
	return true
}

// getTokenModelConcurrencyLeaseTTL 统一并发租约 TTL，避免请求异常退出导致永久占坑。
func getTokenModelConcurrencyLeaseTTL() time.Duration {
	if common.RelayTimeout > 0 {
		return time.Duration(common.RelayTimeout+60) * time.Second
	}
	return 10 * time.Minute
}

// acquireRedisTokenModelConcurrencyLease 使用 Redis ZSET + request_id lease 实现最小并发控制。
func acquireRedisTokenModelConcurrencyLease(ctx context.Context, bucketKey string, requestID string, limit int, ttl time.Duration) (bool, error) {
	leaseKey := bucketKey + ":lease:" + requestID
	nowMillis := time.Now().UnixMilli()
	expireAtMillis := nowMillis + ttl.Milliseconds()
	result, err := common.RDB.Eval(
		ctx,
		acquireRedisTokenModelConcurrencyScript,
		[]string{bucketKey, leaseKey},
		nowMillis,
		expireAtMillis,
		requestID,
		ttl.Milliseconds(),
		limit,
	).Int64()
	if err != nil {
		return false, err
	}
	return result == 1, nil
}

// releaseRedisTokenModelConcurrencyLease 删除 request_id 对应租约。
func releaseRedisTokenModelConcurrencyLease(ctx context.Context, bucketKey string, requestID string) error {
	leaseKey := bucketKey + ":lease:" + requestID
	_, err := common.RDB.Pipelined(ctx, func(pipe redis.Pipeliner) error {
		pipe.Del(ctx, leaseKey)
		pipe.ZRem(ctx, bucketKey, requestID)
		return nil
	})
	return err
}

// renewRedisTokenModelConcurrencyLease 刷新 request_id 对应租约 TTL 与过期时间。
func renewRedisTokenModelConcurrencyLease(ctx context.Context, bucketKey string, requestID string, ttl time.Duration) error {
	leaseKey := bucketKey + ":lease:" + requestID
	exists, err := common.RDB.Exists(ctx, leaseKey).Result()
	if err != nil || exists == 0 {
		return err
	}
	expireAtMillis := time.Now().Add(ttl).UnixMilli()
	_, err = common.RDB.Pipelined(ctx, func(pipe redis.Pipeliner) error {
		pipe.Expire(ctx, leaseKey, ttl)
		pipe.ZAdd(ctx, bucketKey, &redis.Z{
			Score:  float64(expireAtMillis),
			Member: requestID,
		})
		pipe.Expire(ctx, bucketKey, ttl)
		return nil
	})
	return err
}

// checkAndRecordRedisTokenModelRPM 在同一窗口内原子检查并记录 RPM 次数。
func checkAndRecordRedisTokenModelRPM(ctx context.Context, bucketKey string, limit int, windowSeconds int64) (bool, error) {
	nowMillis := time.Now().UnixMilli()
	windowStart := nowMillis - windowSeconds*1000
	ttlSeconds := windowSeconds * 2
	member := fmt.Sprintf("%d-%s", nowMillis, common.GetRandomString(6))
	result, err := common.RDB.Eval(
		ctx,
		checkAndRecordRedisTokenModelRPMScript,
		[]string{bucketKey},
		windowStart,
		nowMillis,
		member,
		limit,
		ttlSeconds,
	).Int64()
	if err != nil {
		return false, err
	}
	return result == 1, nil
}

// getRedisTokenModelTPMRecordedTotal 汇总窗口内的 Prompt 预占和实际 token 欠账。
func getRedisTokenModelTPMRecordedTotal(ctx context.Context, bucketKey string, windowSeconds int64) (int, error) {
	nowMillis := time.Now().UnixMilli()
	windowStart := nowMillis - windowSeconds*1000
	if err := common.RDB.ZRemRangeByScore(ctx, bucketKey, "-inf", strconv.FormatInt(windowStart, 10)).Err(); err != nil {
		return 0, err
	}
	members, err := common.RDB.ZRangeByScore(ctx, bucketKey, &redis.ZRangeBy{
		Min: strconv.FormatInt(windowStart+1, 10),
		Max: "+inf",
	}).Result()
	if err != nil {
		return 0, err
	}
	totalTokens := 0
	for _, member := range members {
		tokens, parseErr := parseRedisTokenModelTPMMemberTokens(member)
		if parseErr != nil {
			return 0, parseErr
		}
		totalTokens += tokens
	}
	return totalTokens, nil
}

// newTokenModelTPMReservation 构造可被精确替换或删除的请求级 TPM 预占。
func newTokenModelTPMReservation(bucketKey string, requestID string, promptTokens int) *tokenModelTPMReservation {
	startedAtMillis := time.Now().UnixMilli()
	return &tokenModelTPMReservation{
		bucketKey:       bucketKey,
		requestID:       requestID,
		member:          fmt.Sprintf("%d:%d:%s", startedAtMillis, promptTokens, requestID),
		startedAtMillis: startedAtMillis,
		reservedTokens:  promptTokens,
	}
}

// reserveRedisTokenModelTPM 原子完成窗口清理、Token 汇总、准入判断和 Prompt 预占。
func reserveRedisTokenModelTPM(
	ctx context.Context,
	reservation *tokenModelTPMReservation,
	limit int,
	windowSeconds int64,
) (bool, error) {
	windowStart := reservation.startedAtMillis - windowSeconds*1000
	ttlSeconds := windowSeconds * 2
	result, err := common.RDB.Eval(
		ctx,
		reserveRedisTokenModelTPMScript,
		[]string{reservation.bucketKey},
		windowStart,
		reservation.startedAtMillis,
		reservation.member,
		reservation.reservedTokens,
		limit,
		ttlSeconds,
	).Int64()
	if err != nil {
		return false, err
	}
	return result == 1, nil
}

// recordRedisTokenModelRealtimeTPMUsage 记录一次 Realtime 实际 usage，并返回窗口累计值。
func recordRedisTokenModelRealtimeTPMUsage(
	ctx context.Context,
	bucketKey string,
	requestID string,
	totalTokens int,
	windowSeconds int64,
) (int, error) {
	nowMillis := time.Now().UnixMilli()
	windowStart := nowMillis - windowSeconds*1000
	ttlSeconds := windowSeconds * 2
	member := fmt.Sprintf(
		"%d:%d:%s:realtime:%s",
		nowMillis,
		totalTokens,
		requestID,
		common.GetRandomString(6),
	)
	recordedTotal, err := common.RDB.Eval(
		ctx,
		recordRedisTokenModelRealtimeTPMScript,
		[]string{bucketKey},
		windowStart,
		nowMillis,
		member,
		totalTokens,
		ttlSeconds,
	).Int()
	if err != nil {
		return 0, err
	}
	return recordedTotal, nil
}

// settleRedisTokenModelTPM 按请求开始时间修正 Prompt，并按响应结束时间记录 Completion。
func settleRedisTokenModelTPM(
	ctx context.Context,
	reservation *tokenModelTPMReservation,
	promptTokens int,
	completionTokens int,
	windowSeconds int64,
) error {
	nowMillis := time.Now().UnixMilli()
	windowStart := nowMillis - windowSeconds*1000
	ttlSeconds := windowSeconds * 2
	promptMember := fmt.Sprintf(
		"%d:%d:%s:prompt",
		reservation.startedAtMillis,
		promptTokens,
		reservation.requestID,
	)
	completionMember := fmt.Sprintf(
		"%d:%d:%s:completion",
		nowMillis,
		completionTokens,
		reservation.requestID,
	)
	return common.RDB.Eval(
		ctx,
		settleRedisTokenModelTPMScript,
		[]string{reservation.bucketKey},
		windowStart,
		reservation.member,
		reservation.startedAtMillis,
		promptMember,
		promptTokens,
		nowMillis,
		completionMember,
		completionTokens,
		ttlSeconds,
	).Err()
}

// parseRedisTokenModelTPMMemberTokens 从 Redis 成员串中解析 usage token 数，保持记账格式兼容集中处理。
func parseRedisTokenModelTPMMemberTokens(member string) (int, error) {
	parts := strings.SplitN(member, ":", 3)
	if len(parts) < 2 {
		return 0, fmt.Errorf("invalid token model tpm member: %s", member)
	}
	tokens, err := strconv.Atoi(parts[1])
	if err != nil {
		return 0, fmt.Errorf("invalid token model tpm member tokens: %w", err)
	}
	if tokens < 0 {
		return 0, fmt.Errorf("invalid token model tpm member tokens: %d", tokens)
	}
	return tokens, nil
}

// acquireConcurrencyLease 在内存模式下按 request_id 记录活跃并发租约。
func (l *tokenModelMemoryLimiterState) acquireConcurrencyLease(bucketKey string, requestID string, limit int, ttl time.Duration) (bool, error) {
	l.mutex.Lock()
	defer l.mutex.Unlock()

	l.init()
	nowMillis := time.Now().UnixMilli()
	expireAtMillis := nowMillis + ttl.Milliseconds()
	bucket := l.concurrency[bucketKey]
	if bucket == nil {
		bucket = make(map[string]int64)
		l.concurrency[bucketKey] = bucket
	}
	for id, expireAt := range bucket {
		if expireAt <= nowMillis {
			delete(bucket, id)
		}
	}
	if expireAt, exists := bucket[requestID]; exists && expireAt > nowMillis {
		bucket[requestID] = expireAtMillis
		return true, nil
	}
	if len(bucket) >= limit {
		return false, nil
	}
	bucket[requestID] = expireAtMillis
	return true, nil
}

// releaseConcurrencyLease 在内存模式下删除已完成请求的并发租约。
func (l *tokenModelMemoryLimiterState) releaseConcurrencyLease(bucketKey string, requestID string) {
	l.mutex.Lock()
	defer l.mutex.Unlock()

	l.init()
	bucket := l.concurrency[bucketKey]
	if bucket == nil {
		return
	}
	delete(bucket, requestID)
	if len(bucket) == 0 {
		delete(l.concurrency, bucketKey)
	}
}

// renewConcurrencyLease 在内存模式下延长活跃请求的并发租约 TTL。
func (l *tokenModelMemoryLimiterState) renewConcurrencyLease(bucketKey string, requestID string, ttl time.Duration) {
	l.mutex.Lock()
	defer l.mutex.Unlock()

	l.init()
	bucket := l.concurrency[bucketKey]
	if bucket == nil {
		return
	}
	if _, exists := bucket[requestID]; !exists {
		return
	}
	bucket[requestID] = time.Now().Add(ttl).UnixMilli()
}

// checkAndRecordRPM 在内存模式下按滑动窗口记录 RPM 次数。
func (l *tokenModelMemoryLimiterState) checkAndRecordRPM(bucketKey string, limit int, windowSeconds int64) (bool, error) {
	l.mutex.Lock()
	defer l.mutex.Unlock()

	l.init()
	nowMillis := time.Now().UnixMilli()
	windowStart := nowMillis - windowSeconds*1000
	records := l.rpm[bucketKey]
	filtered := make([]int64, 0, len(records)+1)
	for _, record := range records {
		if record > windowStart {
			filtered = append(filtered, record)
		}
	}
	if len(filtered) >= limit {
		l.rpm[bucketKey] = filtered
		return false, nil
	}
	filtered = append(filtered, nowMillis)
	l.rpm[bucketKey] = filtered
	return true, nil
}

// getRecordedTPMTotal 在内存模式下汇总窗口内已记账 token 总量，并顺手清理过期记录。
func (l *tokenModelMemoryLimiterState) getRecordedTPMTotal(bucketKey string, windowSeconds int64) int {
	l.mutex.Lock()
	defer l.mutex.Unlock()

	l.init()
	nowMillis := time.Now().UnixMilli()
	windowStart := nowMillis - windowSeconds*1000
	records := l.tpm[bucketKey]
	filtered := make([]tokenModelUsageRecord, 0, len(records))
	totalTokens := 0
	for _, record := range records {
		if record.recordedAtMillis > windowStart {
			filtered = append(filtered, record)
			totalTokens += record.tokens
		}
	}
	if len(filtered) == 0 {
		delete(l.tpm, bucketKey)
		return 0
	}
	l.tpm[bucketKey] = filtered
	return totalTokens
}

// reserveTPM 在内存模式下原子完成窗口清理、汇总、准入判断和 Prompt 预占。
func (l *tokenModelMemoryLimiterState) reserveTPM(
	bucketKey string,
	requestID string,
	promptTokens int,
	limit int,
	windowSeconds int64,
) (bool, error) {
	l.mutex.Lock()
	defer l.mutex.Unlock()

	l.init()
	nowMillis := time.Now().UnixMilli()
	windowStart := nowMillis - windowSeconds*1000
	records := l.tpm[bucketKey]
	filtered := make([]tokenModelUsageRecord, 0, len(records)+1)
	totalTokens := 0
	for _, record := range records {
		if record.recordedAtMillis > windowStart {
			filtered = append(filtered, record)
			totalTokens += record.tokens
		}
	}
	if totalTokens+promptTokens > limit {
		l.tpm[bucketKey] = filtered
		return false, nil
	}
	filtered = append(filtered, tokenModelUsageRecord{
		recordedAtMillis: nowMillis,
		requestID:        requestID,
		tokens:           promptTokens,
	})
	l.tpm[bucketKey] = filtered
	return true, nil
}

// recordRealtimeTPMUsage 在内存模式下记录一次 Realtime 实际 usage，并返回窗口累计值。
func (l *tokenModelMemoryLimiterState) recordRealtimeTPMUsage(
	bucketKey string,
	requestID string,
	totalTokens int,
	windowSeconds int64,
) int {
	l.mutex.Lock()
	defer l.mutex.Unlock()

	l.init()
	nowMillis := time.Now().UnixMilli()
	windowStart := nowMillis - windowSeconds*1000
	records := l.tpm[bucketKey]
	filtered := make([]tokenModelUsageRecord, 0, len(records)+1)
	recordedTotal := 0
	for _, record := range records {
		if record.recordedAtMillis > windowStart {
			filtered = append(filtered, record)
			recordedTotal += record.tokens
		}
	}
	if totalTokens > 0 {
		filtered = append(filtered, tokenModelUsageRecord{
			recordedAtMillis: nowMillis,
			requestID:        requestID + ":realtime:" + common.GetRandomString(6),
			tokens:           totalTokens,
		})
		recordedTotal += totalTokens
	}
	if len(filtered) == 0 {
		delete(l.tpm, bucketKey)
		return 0
	}
	l.tpm[bucketKey] = filtered
	return recordedTotal
}

// settleTPM 在内存模式下按开始时间修正 Prompt，并按结束时间追加 Completion。
func (l *tokenModelMemoryLimiterState) settleTPM(
	bucketKey string,
	requestID string,
	promptTokens int,
	completionTokens int,
	windowSeconds int64,
) {
	l.mutex.Lock()
	defer l.mutex.Unlock()

	l.init()
	nowMillis := time.Now().UnixMilli()
	windowStart := nowMillis - windowSeconds*1000
	records := l.tpm[bucketKey]
	filtered := make([]tokenModelUsageRecord, 0, len(records)+1)
	for _, record := range records {
		if record.recordedAtMillis <= windowStart {
			continue
		}
		if record.requestID == requestID {
			if promptTokens > 0 {
				record.tokens = promptTokens
				filtered = append(filtered, record)
			}
			continue
		}
		filtered = append(filtered, record)
	}
	if completionTokens > 0 {
		filtered = append(filtered, tokenModelUsageRecord{
			recordedAtMillis: nowMillis,
			requestID:        requestID + ":completion",
			tokens:           completionTokens,
		})
	}
	if len(filtered) == 0 {
		delete(l.tpm, bucketKey)
		return
	}
	l.tpm[bucketKey] = filtered
}

// logTokenModelRateLimitError 按约定字段输出错误日志，便于联调与告警检索。
func logTokenModelRateLimitError(c *gin.Context, limitType string, errorCode types.ErrorCode, message string, err error) {
	errorSuffix := ""
	if err != nil {
		errorSuffix = fmt.Sprintf(", cause=%s", err.Error())
	}
	logger.LogError(
		common.RequestContext(c.Request),
		fmt.Sprintf(
			"token model rate limit hit: request_id=%s, token_id=%d, token_name=%s, model_name=%s, limit_type=%s, error_code=%s, message=%s%s",
			c.GetString(common.RequestIdKey),
			c.GetInt("token_id"),
			c.GetString("token_name"),
			common.GetContextKeyString(c, constant.ContextKeyOriginalModel),
			limitType,
			errorCode,
			message,
			errorSuffix,
		),
	)
}

// getTokenModelLimitString 兼容 token_model_rate_limits 中的字符串字段读取。
func getTokenModelLimitString(data map[string]any, key string) string {
	value, ok := data[key]
	if !ok || value == nil {
		return ""
	}
	switch typed := value.(type) {
	case string:
		return typed
	default:
		return fmt.Sprintf("%v", typed)
	}
}

// getTokenModelLimitBool 兼容 bool/string/number 三类配置值。
func getTokenModelLimitBool(data map[string]any, key string) bool {
	value, ok := data[key]
	if !ok || value == nil {
		return false
	}
	switch typed := value.(type) {
	case bool:
		return typed
	case string:
		return strings.EqualFold(strings.TrimSpace(typed), "true")
	case int:
		return typed != 0
	case int64:
		return typed != 0
	case float64:
		return typed != 0
	default:
		return false
	}
}

// getTokenModelLimitInt 兼容 JSON 反序列化后的常见数字类型。
func getTokenModelLimitInt(data map[string]any, keys ...string) int {
	for _, key := range keys {
		value, ok := data[key]
		if !ok || value == nil {
			continue
		}
		switch typed := value.(type) {
		case int:
			return typed
		case int64:
			return int(typed)
		case float64:
			return int(typed)
		case string:
			trimmed := strings.TrimSpace(typed)
			if trimmed == "" {
				continue
			}
			if parsed, err := strconv.Atoi(trimmed); err == nil {
				return parsed
			}
		}
	}
	return 0
}

// 检查Redis中的请求限制
func checkRedisRateLimit(ctx context.Context, rdb *redis.Client, key string, maxCount int, duration int64) (bool, error) {
	// 如果maxCount为0，表示不限制
	if maxCount == 0 {
		return true, nil
	}

	// 获取当前计数
	length, err := rdb.LLen(ctx, key).Result()
	if err != nil {
		return false, err
	}

	// 如果未达到限制，允许请求
	if length < int64(maxCount) {
		return true, nil
	}

	// 检查时间窗口
	oldTimeStr, _ := rdb.LIndex(ctx, key, -1).Result()
	oldTime, err := time.Parse(timeFormat, oldTimeStr)
	if err != nil {
		return false, err
	}

	nowTimeStr := time.Now().Format(timeFormat)
	nowTime, err := time.Parse(timeFormat, nowTimeStr)
	if err != nil {
		return false, err
	}
	// 如果在时间窗口内已达到限制，拒绝请求
	subTime := nowTime.Sub(oldTime).Seconds()
	if int64(subTime) < duration {
		rdb.Expire(ctx, key, time.Duration(setting.ModelRequestRateLimitDurationMinutes)*time.Minute)
		return false, nil
	}

	return true, nil
}

// 记录Redis请求
func recordRedisRequest(ctx context.Context, rdb *redis.Client, key string, maxCount int) {
	// 如果maxCount为0，不记录请求
	if maxCount == 0 {
		return
	}

	now := time.Now().Format(timeFormat)
	rdb.LPush(ctx, key, now)
	rdb.LTrim(ctx, key, 0, int64(maxCount-1))
	rdb.Expire(ctx, key, time.Duration(setting.ModelRequestRateLimitDurationMinutes)*time.Minute)
}

// Redis限流处理器
func redisRateLimitHandler(duration int64, totalMaxCount, successMaxCount int) gin.HandlerFunc {
	return func(c *gin.Context) {
		userId := strconv.Itoa(c.GetInt("id"))
		ctx := context.Background()
		rdb := common.RDB

		// 1. 检查成功请求数限制
		successKey := fmt.Sprintf("rateLimit:%s:%s", ModelRequestRateLimitSuccessCountMark, userId)
		allowed, err := checkRedisRateLimit(ctx, rdb, successKey, successMaxCount, duration)
		if err != nil {
			fmt.Println("检查成功请求数限制失败:", err.Error())
			abortWithOpenAiMessage(c, http.StatusInternalServerError, "rate_limit_check_failed")
			return
		}
		if !allowed {
			abortWithOpenAiMessage(c, http.StatusTooManyRequests, fmt.Sprintf("您已达到请求数限制：%d分钟内最多请求%d次", setting.ModelRequestRateLimitDurationMinutes, successMaxCount))
			return
		}

		//2.检查总请求数限制并记录总请求（当totalMaxCount为0时会自动跳过，使用令牌桶限流器
		if totalMaxCount > 0 {
			totalKey := fmt.Sprintf("rateLimit:%s", userId)
			// 初始化
			tb := limiter.New(ctx, rdb)
			allowed, err = tb.Allow(
				ctx,
				totalKey,
				limiter.WithCapacity(int64(totalMaxCount)*duration),
				limiter.WithRate(int64(totalMaxCount)),
				limiter.WithRequested(duration),
			)

			if err != nil {
				fmt.Println("检查总请求数限制失败:", err.Error())
				abortWithOpenAiMessage(c, http.StatusInternalServerError, "rate_limit_check_failed")
				return
			}

			if !allowed {
				abortWithOpenAiMessage(c, http.StatusTooManyRequests, fmt.Sprintf("您已达到总请求数限制：%d分钟内最多请求%d次，包括失败次数，请检查您的请求是否正确", setting.ModelRequestRateLimitDurationMinutes, totalMaxCount))
			}
		}

		// 4. 处理请求
		c.Next()

		// 5. 如果请求成功，记录成功请求
		if c.Writer.Status() < 400 {
			recordRedisRequest(ctx, rdb, successKey, successMaxCount)
		}
	}
}

// 内存限流处理器
func memoryRateLimitHandler(duration int64, totalMaxCount, successMaxCount int) gin.HandlerFunc {
	inMemoryRateLimiter.Init(time.Duration(setting.ModelRequestRateLimitDurationMinutes) * time.Minute)

	return func(c *gin.Context) {
		userId := strconv.Itoa(c.GetInt("id"))
		totalKey := ModelRequestRateLimitCountMark + userId
		successKey := ModelRequestRateLimitSuccessCountMark + userId

		// 1. 检查总请求数限制（当totalMaxCount为0时跳过）
		if totalMaxCount > 0 && !inMemoryRateLimiter.Request(totalKey, totalMaxCount, duration) {
			c.Status(http.StatusTooManyRequests)
			c.Abort()
			return
		}

		// 2. 检查成功请求数限制
		// 使用一个临时key来检查限制，这样可以避免实际记录
		checkKey := successKey + "_check"
		if !inMemoryRateLimiter.Request(checkKey, successMaxCount, duration) {
			c.Status(http.StatusTooManyRequests)
			c.Abort()
			return
		}

		// 3. 处理请求
		c.Next()

		// 4. 如果请求成功，记录到实际的成功请求计数中
		if c.Writer.Status() < 400 {
			inMemoryRateLimiter.Request(successKey, successMaxCount, duration)
		}
	}
}

// ModelRequestRateLimit 模型请求限流中间件
func ModelRequestRateLimit() func(c *gin.Context) {
	return func(c *gin.Context) {
		// 在每个请求时检查是否启用限流
		if !setting.ModelRequestRateLimitEnabled {
			c.Next()
			return
		}

		// 计算限流参数
		duration := int64(setting.ModelRequestRateLimitDurationMinutes * 60)
		totalMaxCount := setting.ModelRequestRateLimitCount
		successMaxCount := setting.ModelRequestRateLimitSuccessCount

		// 获取分组
		group := common.GetContextKeyString(c, constant.ContextKeyTokenGroup)
		if group == "" {
			group = common.GetContextKeyString(c, constant.ContextKeyUserGroup)
		}

		//获取分组的限流配置
		groupTotalCount, groupSuccessCount, found := setting.GetGroupRateLimit(group)
		if found {
			totalMaxCount = groupTotalCount
			successMaxCount = groupSuccessCount
		}

		// 根据存储类型选择并执行限流处理器
		if common.RedisEnabled {
			redisRateLimitHandler(duration, totalMaxCount, successMaxCount)(c)
		} else {
			memoryRateLimitHandler(duration, totalMaxCount, successMaxCount)(c)
		}
	}
}
