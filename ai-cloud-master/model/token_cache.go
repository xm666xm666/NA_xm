package model

import (
	"fmt"
	"sync"
	"sync/atomic"
	"time"

	"github.com/QuantumNous/new-api/common"
	"github.com/QuantumNous/new-api/constant"
	"github.com/bytedance/gopkg/util/gopool"
)

const (
	// tokenCacheSyncRetryAttempts 控制保存后同步重建缓存的最大尝试次数。
	tokenCacheSyncRetryAttempts = 3
	// tokenCacheAsyncRetryAttempts 控制每轮异步补偿内的同步重试次数。
	tokenCacheAsyncRetryAttempts = 3
	// tokenCacheRetryInterval 控制重试之间的最小等待时间，避免瞬时连续打满 Redis。
	tokenCacheRetryInterval = 50 * time.Millisecond
	// tokenCacheAsyncRetryLogThreshold 控制异步补偿连续失败多少次后输出诊断日志。
	tokenCacheAsyncRetryLogThreshold = 5
	// tokenCacheAsyncRetryMaxDelay 控制异步补偿退避等待的最大值，避免故障期过度打 Redis。
	tokenCacheAsyncRetryMaxDelay = 30 * time.Second
)

var (
	// tokenCacheAsyncRetryBackoffDelays 定义异步补偿连续失败后的退避序列。
	tokenCacheAsyncRetryBackoffDelays = []time.Duration{
		50 * time.Millisecond,
		100 * time.Millisecond,
		200 * time.Millisecond,
		500 * time.Millisecond,
		time.Second,
		5 * time.Second,
	}
	tokenCacheRefreshPendingByKey sync.Map
	// tokenCacheRefreshPendingSeq 为每次 pending 标记生成单调递增序号，避免并发轮次冲突。
	tokenCacheRefreshPendingSeq uint64
	// tokenCacheSyncRetryExhaustedTotal 统计同步重试耗尽次数，便于观测保存后降级到异步补偿的频率。
	tokenCacheSyncRetryExhaustedTotal uint64
	// tokenCacheAsyncRetryScheduledTotal 统计异步补偿被调度的次数，便于观测 pending 补偿压力。
	tokenCacheAsyncRetryScheduledTotal uint64
	// tokenCacheAsyncRetrySucceededTotal 统计异步补偿最终成功次数，便于确认 pending 最终收敛情况。
	tokenCacheAsyncRetrySucceededTotal uint64
	// tokenCacheAsyncRetryFailedTotal 统计异步补偿最终失败次数，便于定位长期 pending 风险。
	tokenCacheAsyncRetryFailedTotal uint64
	// tokenCachePendingReadRebuildSucceededTotal 统计运行时命中 pending 后同步回源重建成功次数。
	tokenCachePendingReadRebuildSucceededTotal uint64
	// tokenCacheLastFailureAt 记录最近一次缓存刷新失败时间，便于状态页观测。
	tokenCacheLastFailureAt int64
	// tokenCacheLastFailureReason 记录最近一次缓存刷新失败原因，便于快速排查。
	tokenCacheLastFailureReason atomic.Value
	// tokenCacheGetByKeyFunc 允许测试替换缓存读取实现，避免依赖真实 Redis。
	tokenCacheGetByKeyFunc = cacheGetTokenByKey
	// tokenCacheSyncFunc 允许测试替换缓存刷新实现，便于验证重试与 pending 行为。
	tokenCacheSyncFunc = syncTokenCache
	// tokenCacheDeleteFunc 允许测试替换缓存删除实现，便于验证删除链路的 pending 行为。
	tokenCacheDeleteFunc = deleteTokenCache
	// tokenCacheAsyncRun 允许测试接管异步执行，避免用例中出现后台竞态。
	tokenCacheAsyncRun = gopool.Go
	// tokenCacheSleep 允许测试跳过等待时间，保持单测快速稳定。
	tokenCacheSleep = time.Sleep
	// tokenCacheAlertFunc 允许测试接管告警发送，避免用例依赖真实邮件配置。
	tokenCacheAlertFunc = sendTokenCacheRefreshAlert
	// tokenCacheMarkPendingFunc 允许测试注入 pending 写入失败，验证多实例补偿链路。
	tokenCacheMarkPendingFunc = markTokenCacheRefreshPendingBase
	// tokenCacheAsyncShouldRetry 允许测试截断无限补偿循环，生产环境始终持续重试直到成功。
	tokenCacheAsyncShouldRetry = func(Token, string, error) bool { return true }
	// tokenCacheAsyncRetryLogFunc 允许测试接管异步补偿失败日志，避免单测依赖全局日志输出。
	tokenCacheAsyncRetryLogFunc = common.SysError
)

// TokenCacheRefreshStats 汇总 token 缓存 pending 补偿链路的核心观测指标。
type TokenCacheRefreshStats struct {
	SyncRetryExhaustedTotal          uint64 `json:"sync_retry_exhausted_total"`
	AsyncRetryScheduledTotal         uint64 `json:"async_retry_scheduled_total"`
	AsyncRetrySucceededTotal         uint64 `json:"async_retry_succeeded_total"`
	AsyncRetryFailedTotal            uint64 `json:"async_retry_failed_total"`
	PendingReadRebuildSucceededTotal uint64 `json:"pending_read_rebuild_succeeded_total"`
	LastFailureAt                    int64  `json:"last_failure_at"`
	LastFailureReason                string `json:"last_failure_reason"`
}

// shouldUseRedisTokenPendingMarker 仅在 Redis 客户端可用时读写远端 pending 标记。
func shouldUseRedisTokenPendingMarker() bool {
	return common.RedisEnabled && common.RDB != nil
}

// syncTokenCache 重建 token 缓存，并且只清理本轮刷新对应的 pending 标记。
func syncTokenCache(token Token, marker string) error {
	if err := cacheSetToken(token); err != nil {
		return err
	}
	clearTokenCacheRefreshPending(token, marker)
	return nil
}

// deleteTokenCache 删除 token 缓存，并且只清理本轮删除对应的 pending 标记。
func deleteTokenCache(token Token, marker string) error {
	if err := cacheDeleteToken(token.Key); err != nil {
		return err
	}
	clearTokenCacheRefreshPending(token, marker)
	return nil
}

// refreshTokenCacheWithRetry 在有限次同步重试内尝试重建缓存，成功后只清理当前轮次的 pending 标记。
func refreshTokenCacheWithRetry(token Token, marker string, attempts int) error {
	if attempts < 1 {
		attempts = 1
	}
	var lastErr error
	for attempt := 1; attempt <= attempts; attempt++ {
		lastErr = tokenCacheSyncFunc(token, marker)
		if lastErr == nil {
			return nil
		}
		if attempt < attempts {
			tokenCacheSleep(tokenCacheRetryInterval)
		}
	}
	return fmt.Errorf("token cache refresh failed after %d attempts: %w", attempts, lastErr)
}

// deleteTokenCacheWithRetry 在有限次同步重试内尝试删除缓存，成功后只清理当前轮次的 pending 标记。
func deleteTokenCacheWithRetry(token Token, marker string, attempts int) error {
	if attempts < 1 {
		attempts = 1
	}
	var lastErr error
	for attempt := 1; attempt <= attempts; attempt++ {
		lastErr = tokenCacheDeleteFunc(token, marker)
		if lastErr == nil {
			return nil
		}
		if attempt < attempts {
			tokenCacheSleep(tokenCacheRetryInterval)
		}
	}
	return fmt.Errorf("token cache delete failed after %d attempts: %w", attempts, lastErr)
}

// scheduleAsyncTokenCacheRefresh 在同步重试仍失败时异步补偿，并沿用同一轮 marker，避免旧刷新误清新 pending。
func scheduleAsyncTokenCacheRefresh(token Token, marker string, reason string, cause error) {
	recordTokenCacheRefreshFailure(reason, cause)
	atomic.AddUint64(&tokenCacheAsyncRetryScheduledTotal, 1)
	if alertErr := tokenCacheAlertFunc(token, reason, cause); alertErr != nil {
		common.SysError(fmt.Sprintf("failed to alert token cache refresh issue (%s): %v", reason, alertErr))
	}
	tokenCacheAsyncRun(func() {
		currentMarker := marker
		retryFailures := 0
		for {
			// pending 写入失败时要先补齐远端 marker，避免多实例下只有本地知道缓存已过期。
			if currentMarker == "" {
				var markErr error
				currentMarker, markErr = markTokenCacheRefreshPending(token)
				if markErr != nil {
					retryFailures++
					recordTokenCacheRefreshFailure(reason, markErr)
					if !continueTokenCacheAsyncRetry(token, reason, retryFailures, markErr) {
						return
					}
					continue
				}
			}
			if err := refreshTokenCacheWithRetry(token, currentMarker, tokenCacheAsyncRetryAttempts); err != nil {
				retryFailures++
				recordTokenCacheRefreshFailure(reason, err)
				if !continueTokenCacheAsyncRetry(token, reason, retryFailures, err) {
					return
				}
				continue
			}
			atomic.AddUint64(&tokenCacheAsyncRetrySucceededTotal, 1)
			return
		}
	})
}

// scheduleAsyncTokenCacheDelete 在删除缓存失败后持续异步补偿，直到缓存真正被删除才清理 pending。
func scheduleAsyncTokenCacheDelete(token Token, marker string, reason string, cause error) {
	recordTokenCacheRefreshFailure(reason, cause)
	atomic.AddUint64(&tokenCacheAsyncRetryScheduledTotal, 1)
	if alertErr := tokenCacheAlertFunc(token, reason, cause); alertErr != nil {
		common.SysError(fmt.Sprintf("failed to alert token cache delete issue (%s): %v", reason, alertErr))
	}
	tokenCacheAsyncRun(func() {
		currentMarker := marker
		retryFailures := 0
		for {
			// 删除链路同样要先保证远端 pending 可见，避免其他实例继续读取旧缓存。
			if currentMarker == "" {
				var markErr error
				currentMarker, markErr = markTokenCacheRefreshPending(token)
				if markErr != nil {
					retryFailures++
					recordTokenCacheRefreshFailure(reason, markErr)
					if !continueTokenCacheAsyncRetry(token, reason, retryFailures, markErr) {
						return
					}
					continue
				}
			}
			if err := deleteTokenCacheWithRetry(token, currentMarker, tokenCacheAsyncRetryAttempts); err != nil {
				retryFailures++
				recordTokenCacheRefreshFailure(reason, err)
				if !continueTokenCacheAsyncRetry(token, reason, retryFailures, err) {
					return
				}
				continue
			}
			atomic.AddUint64(&tokenCacheAsyncRetrySucceededTotal, 1)
			return
		}
	})
}

// continueTokenCacheAsyncRetry 处理异步补偿单轮失败后的日志、退出判断和退避等待。
func continueTokenCacheAsyncRetry(token Token, reason string, retryFailures int, err error) bool {
	logTokenCacheAsyncRetryFailure(token, reason, retryFailures, err)
	if !tokenCacheAsyncShouldRetry(token, reason, err) {
		atomic.AddUint64(&tokenCacheAsyncRetryFailedTotal, 1)
		return false
	}
	tokenCacheSleep(tokenCacheAsyncRetryDelay(retryFailures))
	return true
}

// logTokenCacheAsyncRetryFailure 在连续第五次失败时输出一次诊断日志，避免故障期每轮刷屏。
func logTokenCacheAsyncRetryFailure(token Token, reason string, retryFailures int, err error) {
	if retryFailures != tokenCacheAsyncRetryLogThreshold {
		return
	}
	tokenCacheAsyncRetryLogFunc(fmt.Sprintf(
		"token cache async retry failed %d times after %s for token_id=%d: %v",
		retryFailures,
		reason,
		token.Id,
		err,
	))
}

// tokenCacheAsyncRetryDelay 返回异步补偿连续失败后的退避等待时间。
func tokenCacheAsyncRetryDelay(retryFailures int) time.Duration {
	if retryFailures <= 0 {
		return tokenCacheRetryInterval
	}
	if retryFailures <= len(tokenCacheAsyncRetryBackoffDelays) {
		return tokenCacheAsyncRetryBackoffDelays[retryFailures-1]
	}
	return tokenCacheAsyncRetryMaxDelay
}

// runTokenCacheRefreshAfterCommit 在写库成功后执行缓存刷新闭环，并在 pending 写入失败时继续补偿。
func runTokenCacheRefreshAfterCommit(token Token, reason string) {
	pendingMarker, pendingErr := markTokenCacheRefreshPending(token)
	if pendingErr != nil {
		common.SysError(fmt.Sprintf("failed to mark token cache refresh pending after %s: %v", reason, pendingErr))
		// 先尝试直接刷新缓存；若仍失败，再进入持续异步补偿补齐远端 pending。
		if cacheErr := refreshTokenCacheWithRetry(token, "", tokenCacheSyncRetryAttempts); cacheErr != nil {
			common.SysError(fmt.Sprintf("failed to refresh token cache synchronously after %s without pending marker: %v", reason, cacheErr))
			scheduleAsyncTokenCacheRefresh(token, "", reason, fmt.Errorf("mark pending failed: %v; refresh failed: %w", pendingErr, cacheErr))
		}
		return
	}
	// 保存成功后先做有限次同步重试，尽量在返回前修复缓存。
	if cacheErr := refreshTokenCacheWithRetry(token, pendingMarker, tokenCacheSyncRetryAttempts); cacheErr != nil {
		common.SysError(fmt.Sprintf("failed to refresh token cache synchronously after %s: %v", reason, cacheErr))
		scheduleAsyncTokenCacheRefresh(token, pendingMarker, reason, cacheErr)
	}
}

// enqueueTokenCacheDeleteAfterCommit 在删除成功后先同步标记 pending，再异步执行缓存删除闭环。
func enqueueTokenCacheDeleteAfterCommit(token Token, reason string) {
	pendingMarker, pendingErr := markTokenCacheRefreshPending(token)
	if pendingErr != nil {
		common.SysError(fmt.Sprintf("failed to mark token cache delete pending after %s: %v", reason, pendingErr))
		// pending 写入失败时保留异步补偿链路，后续会持续尝试补齐远端 marker。
		tokenCacheAsyncRun(func() {
			runTokenCacheDeleteWithoutPendingMarker(token, reason, pendingErr)
		})
		return
	}
	tokenCacheAsyncRun(func() {
		runTokenCacheDeleteWithPendingMarker(token, pendingMarker, reason)
	})
}

// runTokenCacheDeleteAfterCommit 在删库成功后执行缓存删除闭环，并在 pending 写入失败时继续补偿。
func runTokenCacheDeleteAfterCommit(token Token, reason string) {
	pendingMarker, pendingErr := markTokenCacheRefreshPending(token)
	if pendingErr != nil {
		common.SysError(fmt.Sprintf("failed to mark token cache delete pending after %s: %v", reason, pendingErr))
		// 先尝试直接删缓存；若仍失败，再进入持续异步补偿补齐远端 pending。
		runTokenCacheDeleteWithoutPendingMarker(token, reason, pendingErr)
		return
	}
	// 删除成功后先做有限次同步重试，失败时保留 pending 并交给异步补偿。
	runTokenCacheDeleteWithPendingMarker(token, pendingMarker, reason)
}

// runTokenCacheDeleteWithoutPendingMarker 处理 pending 写入失败后的删除补偿入口。
func runTokenCacheDeleteWithoutPendingMarker(token Token, reason string, pendingErr error) {
	if cacheErr := deleteTokenCacheWithRetry(token, "", tokenCacheSyncRetryAttempts); cacheErr != nil {
		common.SysError(fmt.Sprintf("failed to delete token cache synchronously after %s without pending marker: %v", reason, cacheErr))
		scheduleAsyncTokenCacheDelete(token, "", reason, fmt.Errorf("mark pending failed: %v; delete failed: %w", pendingErr, cacheErr))
	}
}

// runTokenCacheDeleteWithPendingMarker 使用已写入的 pending marker 删除缓存，失败时保留 marker 并进入异步补偿。
func runTokenCacheDeleteWithPendingMarker(token Token, pendingMarker string, reason string) {
	if cacheErr := deleteTokenCacheWithRetry(token, pendingMarker, tokenCacheSyncRetryAttempts); cacheErr != nil {
		common.SysError(fmt.Sprintf("failed to delete token cache synchronously after %s: %v", reason, cacheErr))
		scheduleAsyncTokenCacheDelete(token, pendingMarker, reason, cacheErr)
	}
}

// recordTokenCacheRefreshFailure 更新最近一次失败信息，并累计同步失败次数。
func recordTokenCacheRefreshFailure(reason string, err error) {
	atomic.AddUint64(&tokenCacheSyncRetryExhaustedTotal, 1)
	atomic.StoreInt64(&tokenCacheLastFailureAt, time.Now().Unix())
	if err == nil {
		tokenCacheLastFailureReason.Store(reason)
		return
	}
	tokenCacheLastFailureReason.Store(fmt.Sprintf("%s: %v", reason, err))
}

// sendTokenCacheRefreshAlert 向根用户发送缓存刷新失败告警，避免长期 pending 无人感知。
func sendTokenCacheRefreshAlert(token Token, reason string, cause error) error {
	rootUser := GetRootUser()
	if rootUser == nil || rootUser.Email == "" {
		return fmt.Errorf("root user email is empty")
	}
	subject := "Token 缓存刷新进入异步补偿"
	content := fmt.Sprintf(
		"令牌缓存同步刷新失败，已降级进入异步重试。\n原因: %s\n令牌 ID: %d\n令牌名称: %s\n错误: %v\n",
		reason,
		token.Id,
		token.Name,
		cause,
	)
	return common.SendEmail(subject, rootUser.Email, content)
}

// GetTokenCacheRefreshStats 返回 token 缓存 pending 链路的当前统计信息。
func GetTokenCacheRefreshStats() TokenCacheRefreshStats {
	stats := TokenCacheRefreshStats{
		SyncRetryExhaustedTotal:          atomic.LoadUint64(&tokenCacheSyncRetryExhaustedTotal),
		AsyncRetryScheduledTotal:         atomic.LoadUint64(&tokenCacheAsyncRetryScheduledTotal),
		AsyncRetrySucceededTotal:         atomic.LoadUint64(&tokenCacheAsyncRetrySucceededTotal),
		AsyncRetryFailedTotal:            atomic.LoadUint64(&tokenCacheAsyncRetryFailedTotal),
		PendingReadRebuildSucceededTotal: atomic.LoadUint64(&tokenCachePendingReadRebuildSucceededTotal),
		LastFailureAt:                    atomic.LoadInt64(&tokenCacheLastFailureAt),
	}
	if value, ok := tokenCacheLastFailureReason.Load().(string); ok {
		stats.LastFailureReason = value
	}
	return stats
}

// resetTokenCacheRefreshStats 仅供测试重置统计信息，避免全局计数互相污染。
func resetTokenCacheRefreshStats() {
	atomic.StoreUint64(&tokenCacheSyncRetryExhaustedTotal, 0)
	atomic.StoreUint64(&tokenCacheAsyncRetryScheduledTotal, 0)
	atomic.StoreUint64(&tokenCacheAsyncRetrySucceededTotal, 0)
	atomic.StoreUint64(&tokenCacheAsyncRetryFailedTotal, 0)
	atomic.StoreUint64(&tokenCachePendingReadRebuildSucceededTotal, 0)
	atomic.StoreInt64(&tokenCacheLastFailureAt, 0)
	tokenCacheLastFailureReason.Store("")
}

// nextTokenCacheRefreshMarker 为每一轮缓存刷新生成独立 marker，用于防止旧轮次误清新轮次的 pending 标记。
func nextTokenCacheRefreshMarker() string {
	sequence := atomic.AddUint64(&tokenCacheRefreshPendingSeq, 1)
	return fmt.Sprintf("%d:%d", time.Now().UnixNano(), sequence)
}

// markTokenCacheRefreshPending 在配置保存成功后标记缓存待刷新，并返回当前轮次的 marker。
func markTokenCacheRefreshPending(token Token) (string, error) {
	return tokenCacheMarkPendingFunc(token)
}

// markTokenCacheRefreshPendingBase 是默认的 pending 标记实现。
func markTokenCacheRefreshPendingBase(token Token) (string, error) {
	if token.Key == "" {
		return "", nil
	}
	pendingKey := tokenCacheRefreshPendingKey(token.Key)
	marker := nextTokenCacheRefreshMarker()
	if shouldUseRedisTokenPendingMarker() {
		// expiration=0 表示 Redis pending 不自动过期，只能由缓存刷新成功后显式清理。
		if err := common.RedisSet(pendingKey, marker, 0); err != nil {
			// Redis 可用时不允许退化为仅本地 pending，避免其他实例继续读取旧缓存。
			return "", fmt.Errorf("failed to mark token cache refresh pending in redis: %w", err)
		}
	}
	tokenCacheRefreshPendingByKey.Store(pendingKey, marker)
	return marker, nil
}

// currentTokenCacheRefreshPendingMarkerByKey 读取当前 token 的 pending marker，优先以 Redis 为准，回退到本地标记。
func currentTokenCacheRefreshPendingMarkerByKey(key string) (string, bool) {
	if key == "" {
		return "", false
	}
	pendingKey := tokenCacheRefreshPendingKey(key)
	if shouldUseRedisTokenPendingMarker() {
		if value, err := common.RedisGet(pendingKey); err == nil && value != "" {
			return value, true
		}
	}
	if value, exists := tokenCacheRefreshPendingByKey.Load(pendingKey); exists {
		if marker, ok := value.(string); ok && marker != "" {
			return marker, true
		}
	}
	return "", false
}

// clearTokenCacheRefreshPending 在缓存刷新成功后清理待刷新标记；若 marker 已过期，则说明已有更新轮次覆盖当前请求，不应误删。
func clearTokenCacheRefreshPending(token Token, marker string) {
	// 空 marker 来自普通 DB 回填，不能清理其他实例或更新轮次写入的 pending。
	if token.Key == "" || marker == "" {
		return
	}
	currentMarker, exists := currentTokenCacheRefreshPendingMarkerByKey(token.Key)
	if !exists {
		return
	}
	if currentMarker != marker {
		return
	}
	pendingKey := tokenCacheRefreshPendingKey(token.Key)
	tokenCacheRefreshPendingByKey.Delete(pendingKey)
	if shouldUseRedisTokenPendingMarker() {
		if err := common.RedisDelKey(pendingKey); err != nil {
			common.SysLog("failed to clear token cache refresh pending: " + err.Error())
		}
	}
}

// isTokenCacheRefreshPendingByKey 判断当前 token 是否仍处于缓存待刷新状态。
func isTokenCacheRefreshPendingByKey(key string) bool {
	_, exists := currentTokenCacheRefreshPendingMarkerByKey(key)
	return exists
}

// tokenCacheRefreshPendingKey 统一生成待刷新标记的缓存键。
func tokenCacheRefreshPendingKey(key string) string {
	return fmt.Sprintf("token_refresh_pending:%s", common.GenerateHMAC(key))
}

func cacheSetToken(token Token) error {
	key := common.GenerateHMAC(token.Key)
	token.NormalizeTokenModelRateLimits()
	token.Clean()
	err := common.RedisHSetObj(fmt.Sprintf("token:%s", key), &token, time.Duration(common.RedisKeyCacheSeconds())*time.Second)
	if err != nil {
		return err
	}
	return nil
}

func cacheDeleteToken(key string) error {
	key = common.GenerateHMAC(key)
	err := common.RedisDelKey(fmt.Sprintf("token:%s", key))
	if err != nil {
		return err
	}
	return nil
}

func cacheIncrTokenQuota(key string, increment int64) error {
	key = common.GenerateHMAC(key)
	err := common.RedisHIncrBy(fmt.Sprintf("token:%s", key), constant.TokenFiledRemainQuota, increment)
	if err != nil {
		return err
	}
	return nil
}

func cacheDecrTokenQuota(key string, decrement int64) error {
	return cacheIncrTokenQuota(key, -decrement)
}

func cacheSetTokenField(key string, field string, value string) error {
	key = common.GenerateHMAC(key)
	err := common.RedisHSetField(fmt.Sprintf("token:%s", key), field, value)
	if err != nil {
		return err
	}
	return nil
}

// CacheGetTokenByKey 从缓存中获取 token，如果缓存中不存在，则从数据库中获取
func cacheGetTokenByKey(key string) (*Token, error) {
	hmacKey := common.GenerateHMAC(key)
	if !common.RedisEnabled {
		return nil, fmt.Errorf("redis is not enabled")
	}
	var token Token
	err := common.RedisHGetObj(fmt.Sprintf("token:%s", hmacKey), &token)
	if err != nil {
		return nil, err
	}
	token.Key = key
	token.NormalizeTokenModelRateLimits()
	return &token, nil
}
