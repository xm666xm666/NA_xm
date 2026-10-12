package model

import (
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"sync/atomic"

	"github.com/QuantumNous/new-api/common"
	"github.com/bytedance/gopkg/util/gopool"
	"gorm.io/gorm"
	"gorm.io/gorm/clause"
)

type Token struct {
	Id                 int    `json:"id"`
	UserId             int    `json:"user_id" gorm:"index"`
	Key                string `json:"key" gorm:"type:char(48);uniqueIndex"`
	Status             int    `json:"status" gorm:"default:1"`
	Name               string `json:"name" gorm:"index" `
	CreatedTime        int64  `json:"created_time" gorm:"bigint"`
	AccessedTime       int64  `json:"accessed_time" gorm:"bigint"`
	ExpiredTime        int64  `json:"expired_time" gorm:"bigint;default:-1"` // -1 means never expired
	RemainQuota        int    `json:"remain_quota" gorm:"default:0"`
	UnlimitedQuota     bool   `json:"unlimited_quota"`
	ModelLimitsEnabled bool   `json:"token_model_limit_enabled" gorm:"column:token_model_limit_enabled"`
	ModelLimits        string `json:"token_model_limit" gorm:"column:token_model_limit;type:varchar(1024);default:''"`
	// TokenModelRateLimits 独立存储令牌-模型限流配置，避免与模型白名单串义。
	TokenModelRateLimits JSONValue      `json:"token_model_rate_limits" gorm:"type:json"`
	AllowIps             *string        `json:"allow_ips" gorm:"default:''"`
	UsedQuota            int            `json:"used_quota" gorm:"default:0"` // used quota
	Group                string         `json:"group" gorm:"default:''"`
	CrossGroupRetry      bool           `json:"cross_group_retry"` // 跨分组重试，仅auto分组有效
	DeletedAt            gorm.DeletedAt `gorm:"index"`
}

func (token *Token) Clean() {
	token.Key = ""
}

// IsTokenModelRateLimitUnsupportedGroup 标记不能配置模型级限流的令牌分组。
func IsTokenModelRateLimitUnsupportedGroup(group string) bool {
	normalizedGroup := strings.TrimSpace(group)
	return normalizedGroup == "" || normalizedGroup == "auto"
}

// NormalizeTokenModelRateLimits 统一空配置的输出形态，避免接口返回 null。
func (token *Token) NormalizeTokenModelRateLimits() {
	normalized, err := normalizeTokenModelRateLimitsJSON(token.TokenModelRateLimits)
	if err != nil {
		return
	}
	token.TokenModelRateLimits = normalized
}

// PrepareTokenModelRateLimits 在保存前校验并归一化令牌-模型限流配置。
func (token *Token) PrepareTokenModelRateLimits() error {
	normalized, err := normalizeTokenModelRateLimitsJSON(token.TokenModelRateLimits)
	if err != nil {
		return err
	}
	token.TokenModelRateLimits = normalized
	if IsTokenModelRateLimitUnsupportedGroup(token.Group) && len(token.GetTokenModelRateLimits()) > 0 {
		return errors.New("未选择分组或 auto 分组与模型级限流配置不能共存")
	}
	return nil
}

// ValidateTokenModelLimitConsistency 校验模型白名单与模型级限流规则之间的最小一致性。
func (token *Token) ValidateTokenModelLimitConsistency() error {
	modelLimitsMap := token.GetModelLimitsMap()
	if len(modelLimitsMap) == 0 {
		return nil
	}
	for _, limit := range token.GetTokenModelRateLimits() {
		modelName := strings.TrimSpace(getMapString(limit, "model_name"))
		if modelName == "" {
			continue
		}
		if !modelLimitsMap[modelName] {
			return fmt.Errorf("token_model_rate_limits 中的模型 %s 不在 token_model_limit 白名单中", modelName)
		}
	}
	return nil
}

// PruneTokenModelRateLimitsByModelLimits 在启用模型白名单时，自动移除不再命中的模型级限流规则。
func (token *Token) PruneTokenModelRateLimitsByModelLimits() error {
	if !token.ModelLimitsEnabled || strings.TrimSpace(token.ModelLimits) == "" {
		return nil
	}
	modelLimitsMap := token.GetModelLimitsMap()
	filteredLimits := make([]map[string]any, 0)
	for _, limit := range token.GetTokenModelRateLimits() {
		modelName := strings.TrimSpace(getMapString(limit, "model_name"))
		if modelName == "" {
			continue
		}
		if !modelLimitsMap[modelName] {
			continue
		}
		filteredLimits = append(filteredLimits, limit)
	}
	bytes, err := common.Marshal(filteredLimits)
	if err != nil {
		return fmt.Errorf("token_model_rate_limits 序列化失败: %w", err)
	}
	token.TokenModelRateLimits = JSONValue(bytes)
	return nil
}

// GetTokenModelRateLimits 返回解析后的令牌-模型限流配置，解析失败时返回空切片。
func (token *Token) GetTokenModelRateLimits() []map[string]any {
	limits, err := parseTokenModelRateLimits(token.TokenModelRateLimits)
	if err != nil {
		return []map[string]any{}
	}
	return limits
}

// normalizeTokenModelRateLimitsJSON 将空值和合法配置统一归一化为标准 JSON 数组。
func normalizeTokenModelRateLimitsJSON(raw JSONValue) (JSONValue, error) {
	limits, err := parseTokenModelRateLimits(raw)
	if err != nil {
		return nil, err
	}
	bytes, err := common.Marshal(limits)
	if err != nil {
		return nil, fmt.Errorf("token_model_rate_limits 序列化失败: %w", err)
	}
	return JSONValue(bytes), nil
}

// parseTokenModelRateLimits 解析并校验令牌-模型限流配置的最小闭环约束。
func parseTokenModelRateLimits(raw JSONValue) ([]map[string]any, error) {
	trimmed := strings.TrimSpace(string(raw))
	if trimmed == "" || trimmed == "null" {
		return []map[string]any{}, nil
	}

	var limits []map[string]any
	if err := common.Unmarshal([]byte(trimmed), &limits); err != nil {
		return nil, errors.New("token_model_rate_limits 格式错误，必须为 JSON 数组")
	}

	seenModelNames := make(map[string]struct{}, len(limits))
	for index, limit := range limits {
		modelName := strings.TrimSpace(getMapString(limit, "model_name"))
		if modelName == "" {
			return nil, fmt.Errorf("token_model_rate_limits[%d].model_name 不能为空", index)
		}
		if _, exists := seenModelNames[modelName]; exists {
			return nil, fmt.Errorf("token_model_rate_limits 中存在重复 model_name: %s", modelName)
		}
		seenModelNames[modelName] = struct{}{}
		limit["model_name"] = modelName

		if err := validateBooleanFlag(limit, index, "concurrency_limit_enabled"); err != nil {
			return nil, err
		}
		if err := validateBooleanFlag(limit, index, "rpm_limit_enabled"); err != nil {
			return nil, err
		}
		if err := validateBooleanFlag(limit, index, "tpm_limit_enabled"); err != nil {
			return nil, err
		}
		if err := validateEnabledPositiveLimit(limit, index, "concurrency_limit_enabled", "并发限制", "concurrency_limit"); err != nil {
			return nil, err
		}
		if err := validateEnabledPositiveLimit(limit, index, "rpm_limit_enabled", "RPM 限制", "rpm_limit"); err != nil {
			return nil, err
		}
		if err := validateEnabledPositiveLimit(limit, index, "tpm_limit_enabled", "TPM 限制", "tpm_limit"); err != nil {
			return nil, err
		}
	}
	return limits, nil
}

// validateBooleanFlag 拒绝无效启用状态，避免字符串或数字被宽松解释成布尔值。
func validateBooleanFlag(limit map[string]any, index int, key string) error {
	value, exists := limit[key]
	if !exists || value == nil {
		return nil
	}
	if _, ok := value.(bool); !ok {
		return fmt.Errorf("token_model_rate_limits[%d].%s 必须为布尔值", index, key)
	}
	return nil
}

// validateEnabledPositiveLimit 仅在规则显式启用时校验阈值必须大于等于 1。
func validateEnabledPositiveLimit(limit map[string]any, index int, enabledKey string, label string, valueKeys ...string) error {
	if !getMapBool(limit, enabledKey) {
		return nil
	}
	value, ok := getMapInt(limit, valueKeys...)
	if !ok || value < 1 {
		return fmt.Errorf("token_model_rate_limits[%d] 的%s启用后必须大于等于 1", index, label)
	}
	return nil
}

// getMapString 兼容 map 中的字符串字段读取。
func getMapString(data map[string]any, key string) string {
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

// getMapBool 兼容布尔和常见数字/字符串布尔值读取。
func getMapBool(data map[string]any, key string) bool {
	value, ok := data[key]
	if !ok || value == nil {
		return false
	}
	switch typed := value.(type) {
	case bool:
		return typed
	case string:
		return strings.EqualFold(strings.TrimSpace(typed), "true")
	case float64:
		return typed != 0
	case json.Number:
		intValue, err := typed.Int64()
		return err == nil && intValue != 0
	default:
		return false
	}
}

// getMapInt 兼容 JSON 反序列化后的常见数字类型读取。
func getMapInt(data map[string]any, keys ...string) (int, bool) {
	for _, key := range keys {
		value, ok := data[key]
		if !ok || value == nil {
			continue
		}
		switch typed := value.(type) {
		case int:
			return typed, true
		case int64:
			return int(typed), true
		case float64:
			return int(typed), true
		case json.Number:
			intValue, err := typed.Int64()
			if err == nil {
				return int(intValue), true
			}
		case string:
			intValue := common.String2Int(strings.TrimSpace(typed))
			if intValue != 0 || strings.TrimSpace(typed) == "0" {
				return intValue, true
			}
		}
	}
	return 0, false
}

func (token *Token) GetIpLimits() []string {
	// delete empty spaces
	//split with \n
	ipLimits := make([]string, 0)
	if token.AllowIps == nil {
		return ipLimits
	}
	cleanIps := strings.ReplaceAll(*token.AllowIps, " ", "")
	if cleanIps == "" {
		return ipLimits
	}
	ips := strings.Split(cleanIps, "\n")
	for _, ip := range ips {
		ip = strings.TrimSpace(ip)
		ip = strings.ReplaceAll(ip, ",", "")
		if ip != "" {
			ipLimits = append(ipLimits, ip)
		}
	}
	return ipLimits
}

func GetAllUserTokens(userId int, startIdx int, num int) ([]*Token, error) {
	var tokens []*Token
	var err error
	err = DB.Where("user_id = ?", userId).Order("id desc").Limit(num).Offset(startIdx).Find(&tokens).Error
	for _, token := range tokens {
		token.NormalizeTokenModelRateLimits()
	}
	return tokens, err
}

func SearchUserTokens(userId int, keyword string, token string) (tokens []*Token, err error) {
	if token != "" {
		token = strings.Trim(token, "sk-")
	}
	keywordPattern := "%" + escapeLikePattern(keyword) + "%"
	tokenPattern := "%" + escapeLikePattern(token) + "%"
	err = DB.Where("user_id = ?", userId).
		Where("name LIKE ? ESCAPE '!'", keywordPattern).
		Where(commonKeyCol+" LIKE ? ESCAPE '!'", tokenPattern).
		Find(&tokens).Error
	for _, token := range tokens {
		token.NormalizeTokenModelRateLimits()
	}
	return tokens, err
}

func ValidateUserToken(key string) (token *Token, err error) {
	if key == "" {
		return nil, errors.New("未提供令牌")
	}
	token, err = GetTokenByKey(key, false)
	if err == nil {
		if token.Status == common.TokenStatusExhausted {
			keyPrefix := key[:3]
			keySuffix := key[len(key)-3:]
			return token, errors.New("该令牌额度已用尽 TokenStatusExhausted[sk-" + keyPrefix + "***" + keySuffix + "]")
		} else if token.Status == common.TokenStatusExpired {
			return token, errors.New("该令牌已过期")
		}
		if token.Status != common.TokenStatusEnabled {
			return token, errors.New("该令牌状态不可用")
		}
		if token.ExpiredTime != -1 && token.ExpiredTime < common.GetTimestamp() {
			if !common.RedisEnabled {
				token.Status = common.TokenStatusExpired
				err := token.SelectUpdate()
				if err != nil {
					common.SysLog("failed to update token status" + err.Error())
				}
			}
			return token, errors.New("该令牌已过期")
		}
		if !token.UnlimitedQuota && token.RemainQuota <= 0 {
			if !common.RedisEnabled {
				// in this case, we can make sure the token is exhausted
				token.Status = common.TokenStatusExhausted
				err := token.SelectUpdate()
				if err != nil {
					common.SysLog("failed to update token status" + err.Error())
				}
			}
			keyPrefix := key[:3]
			keySuffix := key[len(key)-3:]
			return token, fmt.Errorf("[sk-%s***%s] 该令牌额度已用尽 !token.UnlimitedQuota && token.RemainQuota = %d", keyPrefix, keySuffix, token.RemainQuota)
		}
		return token, nil
	}
	common.SysLog("ValidateUserToken: failed to get token: " + err.Error())
	if errors.Is(err, gorm.ErrRecordNotFound) {
		return nil, errors.New("无效的令牌")
	} else {
		return nil, errors.New("无效的令牌，数据库查询出错，请联系管理员")
	}
}

func GetTokenByIds(id int, userId int) (*Token, error) {
	if id == 0 || userId == 0 {
		return nil, errors.New("id 或 userId 为空！")
	}
	token := Token{Id: id, UserId: userId}
	var err error = nil
	err = DB.First(&token, "id = ? and user_id = ?", id, userId).Error
	token.NormalizeTokenModelRateLimits()
	return &token, err
}

func GetTokenById(id int) (*Token, error) {
	if id == 0 {
		return nil, errors.New("id 为空！")
	}
	token := Token{Id: id}
	var err error = nil
	err = DB.First(&token, "id = ?", id).Error
	token.NormalizeTokenModelRateLimits()
	if shouldUpdateRedis(true, err) {
		gopool.Go(func() {
			if err := syncTokenCache(token, ""); err != nil {
				common.SysLog("failed to update user status cache: " + err.Error())
			}
		})
	}
	return &token, err
}

func GetTokenByKey(key string, fromDB bool) (token *Token, err error) {
	pendingRefresh := false
	pendingMarker := ""
	defer func() {
		if shouldUpdateRedis(fromDB, err) && token != nil {
			// pending 状态下优先同步重建，避免继续复用旧缓存。
			if pendingRefresh {
				if refreshErr := refreshTokenCacheWithRetry(*token, pendingMarker, tokenCacheSyncRetryAttempts); refreshErr != nil {
					common.SysError("failed to rebuild pending token cache synchronously: " + refreshErr.Error())
					scheduleAsyncTokenCacheRefresh(*token, pendingMarker, "pending read rebuild", refreshErr)
				} else {
					// 运行时命中 pending 并回源重建成功后，记录一次成功收敛事件。
					atomic.AddUint64(&tokenCachePendingReadRebuildSucceededTotal, 1)
				}
				return
			}
			// 常规 DB 回填仍保持异步更新，降低读取路径开销。
			gopool.Go(func() {
				if err := syncTokenCache(*token, ""); err != nil {
					common.SysLog("failed to update user status cache: " + err.Error())
				}
			})
		}
	}()
	if !fromDB && common.RedisEnabled {
		pendingMarker, pendingRefresh = currentTokenCacheRefreshPendingMarkerByKey(key)
	}
	if !fromDB && common.RedisEnabled && !pendingRefresh {
		// Try Redis first
		token, err := tokenCacheGetByKeyFunc(key)
		if err == nil {
			return token, nil
		}
		// Don't return error - fall through to DB
	}
	fromDB = true
	err = DB.Where(commonKeyCol+" = ?", key).First(&token).Error
	if token != nil {
		token.NormalizeTokenModelRateLimits()
	}
	return token, err
}

func (token *Token) Insert() error {
	var err error
	if err = token.PrepareTokenModelRateLimits(); err != nil {
		return err
	}
	if err = token.PruneTokenModelRateLimitsByModelLimits(); err != nil {
		return err
	}
	if err = token.ValidateTokenModelLimitConsistency(); err != nil {
		return err
	}
	if err = validateTokenModelQuotaDimensionAvailability(DB, token); err != nil {
		return err
	}
	err = DB.Transaction(func(tx *gorm.DB) error {
		if txErr := applyTokenModelQuotaLedger(tx, nil, token); txErr != nil {
			return txErr
		}
		if txErr := tx.Create(token).Error; txErr != nil {
			return txErr
		}
		// 令牌主记录落库后再写入派生关联，确保关联表持有稳定 token_id。
		return ReplaceTokenModelQuotaRelations(tx, token)
	})
	if shouldUpdateRedis(true, err) {
		// 新增成功后统一走 pending + 同步重试 + 异步补偿闭环，避免多实例继续读到旧缓存。
		runTokenCacheRefreshAfterCommit(*token, "insert")
	}
	return err
}

// Update Make sure your token's fields is completed, because this will update non-zero values
func (token *Token) Update() (err error) {
	if err = token.PrepareTokenModelRateLimits(); err != nil {
		return err
	}
	if err = token.PruneTokenModelRateLimitsByModelLimits(); err != nil {
		return err
	}
	if err = token.ValidateTokenModelLimitConsistency(); err != nil {
		return err
	}
	if err = validateTokenModelQuotaDimensionAvailability(DB, token); err != nil {
		return err
	}
	defer func() {
		if shouldUpdateRedis(true, err) {
			// 更新成功后复用统一缓存闭环，保证 pending 与补偿策略一致。
			runTokenCacheRefreshAfterCommit(*token, "update")
		}
	}()
	err = DB.Transaction(func(tx *gorm.DB) error {
		previousToken, txErr := getTokenForUpdate(tx, token.Id)
		if txErr != nil {
			return txErr
		}
		if txErr = applyTokenModelQuotaLedger(tx, previousToken, token); txErr != nil {
			return txErr
		}
		if txErr = tx.Model(token).
			Select(
				"name",
				"status",
				"expired_time",
				"remain_quota",
				"unlimited_quota",
				"token_model_limit_enabled",
				"token_model_limit",
				"token_model_rate_limits",
				"allow_ips",
				"group",
				"cross_group_retry",
			).
			Updates(token).Error; txErr != nil {
			return txErr
		}
		// 令牌编辑成功后用最新规则全量重建关联，避免旧规则残留。
		return ReplaceTokenModelQuotaRelations(tx, token)
	})
	return err
}

func (token *Token) SelectUpdate() (err error) {
	defer func() {
		if shouldUpdateRedis(true, err) {
			gopool.Go(func() {
				err := cacheSetToken(*token)
				if err != nil {
					common.SysLog("failed to update token cache: " + err.Error())
				}
			})
		}
	}()
	// This can update zero values
	return DB.Model(token).Select("accessed_time", "status").Updates(token).Error
}

func (token *Token) Delete() (err error) {
	defer func() {
		if shouldUpdateRedis(true, err) {
			// 删除后异步走统一 pending/删除补偿闭环，避免旧缓存残留。
			enqueueTokenCacheDeleteAfterCommit(*token, "delete")
		}
	}()
	err = DB.Transaction(func(tx *gorm.DB) error {
		currentToken, txErr := getTokenForDelete(tx, token)
		if txErr != nil {
			return txErr
		}
		if txErr = applyTokenModelQuotaLedger(tx, currentToken, nil); txErr != nil {
			return txErr
		}
		if txErr = DeleteTokenModelQuotaRelationsByTokenIDs(tx, []int{currentToken.Id}); txErr != nil {
			return txErr
		}
		return tx.Delete(currentToken).Error
	})
	return err
}

func (token *Token) IsModelLimitsEnabled() bool {
	return token.ModelLimitsEnabled
}

func (token *Token) GetModelLimits() []string {
	if token.ModelLimits == "" {
		return []string{}
	}
	return strings.Split(token.ModelLimits, ",")
}

func (token *Token) GetModelLimitsMap() map[string]bool {
	limits := token.GetModelLimits()
	limitsMap := make(map[string]bool)
	for _, limit := range limits {
		limitsMap[limit] = true
	}
	return limitsMap
}

func DisableModelLimits(tokenId int) error {
	token, err := GetTokenById(tokenId)
	if err != nil {
		return err
	}
	token.ModelLimitsEnabled = false
	token.ModelLimits = ""
	return token.Update()
}

func DeleteTokenById(id int, userId int) (err error) {
	// Why we need userId here? In case user want to delete other's token.
	if id == 0 || userId == 0 {
		return errors.New("id 或 userId 为空！")
	}
	token := Token{Id: id, UserId: userId}
	err = DB.Where(token).First(&token).Error
	if err != nil {
		return err
	}
	return token.Delete()
}

func IncreaseTokenQuota(id int, key string, quota int) (err error) {
	if quota < 0 {
		return errors.New("quota 不能为负数！")
	}
	if common.RedisEnabled {
		gopool.Go(func() {
			err := cacheIncrTokenQuota(key, int64(quota))
			if err != nil {
				common.SysLog("failed to increase token quota: " + err.Error())
			}
		})
	}
	if common.BatchUpdateEnabled {
		addNewRecord(BatchUpdateTypeTokenQuota, id, quota)
		return nil
	}
	return increaseTokenQuota(id, quota)
}

func increaseTokenQuota(id int, quota int) (err error) {
	err = DB.Model(&Token{}).Where("id = ?", id).Updates(
		map[string]interface{}{
			"remain_quota":  gorm.Expr("remain_quota + ?", quota),
			"used_quota":    gorm.Expr("used_quota - ?", quota),
			"accessed_time": common.GetTimestamp(),
		},
	).Error
	return err
}

func DecreaseTokenQuota(id int, key string, quota int) (err error) {
	if quota < 0 {
		return errors.New("quota 不能为负数！")
	}
	if common.RedisEnabled {
		gopool.Go(func() {
			err := cacheDecrTokenQuota(key, int64(quota))
			if err != nil {
				common.SysLog("failed to decrease token quota: " + err.Error())
			}
		})
	}
	if common.BatchUpdateEnabled {
		addNewRecord(BatchUpdateTypeTokenQuota, id, -quota)
		return nil
	}
	return decreaseTokenQuota(id, quota)
}

func decreaseTokenQuota(id int, quota int) (err error) {
	err = DB.Model(&Token{}).Where("id = ?", id).Updates(
		map[string]interface{}{
			"remain_quota":  gorm.Expr("remain_quota - ?", quota),
			"used_quota":    gorm.Expr("used_quota + ?", quota),
			"accessed_time": common.GetTimestamp(),
		},
	).Error
	return err
}

// CountUserTokens returns total number of tokens for the given user, used for pagination
func CountUserTokens(userId int) (int64, error) {
	var total int64
	err := DB.Model(&Token{}).Where("user_id = ?", userId).Count(&total).Error
	return total, err
}

// BatchDeleteTokens 删除指定用户的一组令牌，返回成功删除数量
func BatchDeleteTokens(ids []int, userId int) (int, error) {
	if len(ids) == 0 {
		return 0, errors.New("ids 不能为空！")
	}

	var tokens []Token
	err := DB.Transaction(func(tx *gorm.DB) error {
		if txErr := tx.
			Clauses(clause.Locking{Strength: "UPDATE"}).
			Where("user_id = ? AND id IN (?)", userId, ids).
			Find(&tokens).Error; txErr != nil {
			return txErr
		}
		for index := range tokens {
			tokens[index].NormalizeTokenModelRateLimits()
			if txErr := applyTokenModelQuotaLedger(tx, &tokens[index], nil); txErr != nil {
				return txErr
			}
		}
		tokenIDs := make([]int, 0, len(tokens))
		for _, token := range tokens {
			tokenIDs = append(tokenIDs, token.Id)
		}
		if txErr := DeleteTokenModelQuotaRelationsByTokenIDs(tx, tokenIDs); txErr != nil {
			return txErr
		}
		return tx.Where("user_id = ? AND id IN (?)", userId, ids).Delete(&Token{}).Error
	})
	if err != nil {
		return 0, err
	}

	if common.RedisEnabled {
		for _, token := range tokens {
			// 批量删除逐个复用单删缓存闭环，保证 pending、重试与最终清理语义一致。
			enqueueTokenCacheDeleteAfterCommit(token, "batch delete")
		}
	}

	return len(tokens), nil
}
