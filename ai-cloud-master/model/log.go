package model

import (
	"context"
	"fmt"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/QuantumNous/new-api/common"
	"github.com/QuantumNous/new-api/logger"
	"github.com/QuantumNous/new-api/types"

	"github.com/gin-gonic/gin"

	"github.com/bytedance/gopkg/util/gopool"
	"gorm.io/gorm"
)

type Log struct {
	Id               int    `json:"id" gorm:"index:idx_created_at_id,priority:1"`
	UserId           int    `json:"user_id" gorm:"index"`
	CreatedAt        int64  `json:"created_at" gorm:"bigint;index:idx_created_at_id,priority:2;index:idx_created_at_type"`
	Type             int    `json:"type" gorm:"index:idx_created_at_type"`
	Content          string `json:"content"`
	Username         string `json:"username" gorm:"index;index:index_username_model_name,priority:2;default:''"`
	TokenName        string `json:"token_name" gorm:"index;default:''"`
	ModelName        string `json:"model_name" gorm:"index;index:index_username_model_name,priority:1;default:''"`
	Quota            int    `json:"quota" gorm:"default:0"`
	PromptTokens     int    `json:"prompt_tokens" gorm:"default:0"`
	CompletionTokens int    `json:"completion_tokens" gorm:"default:0"`
	UseTime          int    `json:"use_time" gorm:"default:0"`
	IsStream         bool   `json:"is_stream"`
	ChannelId        int    `json:"channel" gorm:"index"`
	ChannelName      string `json:"channel_name" gorm:"->"`
	TokenId          int    `json:"token_id" gorm:"default:0;index"`
	Group            string `json:"group" gorm:"index"`
	Ip               string `json:"ip" gorm:"index;default:''"`
	Other            string `json:"other"`
}

// don't use iota, avoid change log type value
const (
	LogTypeUnknown = 0
	LogTypeTopup   = 1
	LogTypeConsume = 2
	LogTypeManage  = 3
	LogTypeSystem  = 4
	LogTypeError   = 5
	LogTypeRefund  = 6
)

func formatUserLogs(logs []*Log) {
	for i := range logs {
		logs[i].ChannelName = ""
		var otherMap map[string]interface{}
		otherMap, _ = common.StrToMap(logs[i].Other)
		if otherMap != nil {
			// delete admin
			delete(otherMap, "admin_info")
		}
		logs[i].Other = common.MapToJsonStr(otherMap)
		logs[i].Id = logs[i].Id % 1024
	}
}

func GetLogByKey(key string) (logs []*Log, err error) {
	if os.Getenv("LOG_SQL_DSN") != "" {
		var tk Token
		if err = DB.Model(&Token{}).Where(logKeyCol+"=?", strings.TrimPrefix(key, "sk-")).First(&tk).Error; err != nil {
			return nil, err
		}
		err = LOG_DB.Model(&Log{}).Where("token_id=?", tk.Id).Find(&logs).Error
	} else {
		err = LOG_DB.Joins("left join tokens on tokens.id = logs.token_id").Where("tokens.key = ?", strings.TrimPrefix(key, "sk-")).Find(&logs).Error
	}
	formatUserLogs(logs)
	return logs, err
}

func RecordLog(userId int, logType int, content string) {
	if logType == LogTypeConsume && !common.LogConsumeEnabled {
		return
	}
	username, _ := GetUsernameById(userId, false)
	log := &Log{
		UserId:    userId,
		Username:  username,
		CreatedAt: common.GetTimestamp(),
		Type:      logType,
		Content:   content,
	}
	err := LOG_DB.Create(log).Error
	if err != nil {
		common.SysLog("failed to record log: " + err.Error())
	}
}

func RecordErrorLog(c *gin.Context, userId int, channelId int, modelName string, tokenName string, content string, tokenId int, useTimeSeconds int,
	isStream bool, group string, other map[string]interface{}) {
	logger.LogInfo(c, fmt.Sprintf("record error log: userId=%d, channelId=%d, modelName=%s, tokenName=%s, content=%s", userId, channelId, modelName, tokenName, content))
	username := c.GetString("username")
	otherStr := common.MapToJsonStr(other)
	// 判断是否需要记录 IP
	needRecordIp := false
	if settingMap, err := GetUserSetting(userId, false); err == nil {
		if settingMap.RecordIpLog {
			needRecordIp = true
		}
	}
	log := &Log{
		UserId:           userId,
		Username:         username,
		CreatedAt:        common.GetTimestamp(),
		Type:             LogTypeError,
		Content:          content,
		PromptTokens:     0,
		CompletionTokens: 0,
		TokenName:        tokenName,
		ModelName:        modelName,
		Quota:            0,
		ChannelId:        channelId,
		TokenId:          tokenId,
		UseTime:          useTimeSeconds,
		IsStream:         isStream,
		Group:            group,
		Ip: func() string {
			if needRecordIp {
				return c.ClientIP()
			}
			return ""
		}(),
		Other: otherStr,
	}
	err := LOG_DB.Create(log).Error
	if err != nil {
		logger.LogError(c, "failed to record log: "+err.Error())
	}
}

type RecordConsumeLogParams struct {
	ChannelId        int                    `json:"channel_id"`
	PromptTokens     int                    `json:"prompt_tokens"`
	CompletionTokens int                    `json:"completion_tokens"`
	ModelName        string                 `json:"model_name"`
	TokenName        string                 `json:"token_name"`
	Quota            int                    `json:"quota"`
	Content          string                 `json:"content"`
	TokenId          int                    `json:"token_id"`
	UseTimeSeconds   int                    `json:"use_time_seconds"`
	IsStream         bool                   `json:"is_stream"`
	Group            string                 `json:"group"`
	Other            map[string]interface{} `json:"other"`
}

// extractFirstResponseTimeMs 从日志附加字段中解析首字延迟，单位为毫秒。
func extractFirstResponseTimeMs(other map[string]interface{}) (int64, bool) {
	if other == nil {
		return 0, false
	}
	value, ok := other["frt"]
	if !ok || value == nil {
		return 0, false
	}
	switch v := value.(type) {
	case int:
		if v < 0 {
			return 0, false
		}
		return int64(v), true
	case int64:
		if v < 0 {
			return 0, false
		}
		return v, true
	case float64:
		if v < 0 {
			return 0, false
		}
		return int64(v), true
	}
	valueStr := common.Interface2String(value)
	if valueStr == "" {
		return 0, false
	}
	parsed, err := strconv.ParseFloat(valueStr, 64)
	if err != nil || parsed < 0 {
		return 0, false
	}
	return int64(parsed), true
}

func RecordConsumeLog(c *gin.Context, userId int, params RecordConsumeLogParams) {
	if !common.LogConsumeEnabled {
		return
	}
	logger.LogInfo(c, fmt.Sprintf("record consume log: userId=%d, params=%s", userId, common.GetJsonString(params)))
	username := c.GetString("username")
	otherStr := common.MapToJsonStr(params.Other)
	// 判断是否需要记录 IP
	needRecordIp := false
	if settingMap, err := GetUserSetting(userId, false); err == nil {
		if settingMap.RecordIpLog {
			needRecordIp = true
		}
	}
	log := &Log{
		UserId:           userId,
		Username:         username,
		CreatedAt:        common.GetTimestamp(),
		Type:             LogTypeConsume,
		Content:          params.Content,
		PromptTokens:     params.PromptTokens,
		CompletionTokens: params.CompletionTokens,
		TokenName:        params.TokenName,
		ModelName:        params.ModelName,
		Quota:            params.Quota,
		ChannelId:        params.ChannelId,
		TokenId:          params.TokenId,
		UseTime:          params.UseTimeSeconds,
		IsStream:         params.IsStream,
		Group:            params.Group,
		Ip: func() string {
			if needRecordIp {
				return c.ClientIP()
			}
			return ""
		}(),
		Other: otherStr,
	}
	err := LOG_DB.Create(log).Error
	if err != nil {
		logger.LogError(c, "failed to record log: "+err.Error())
	}
	if common.DataExportEnabled {
		useTimeSum := int64(params.UseTimeSeconds)
		useTimeCount := 1
		useTimeMax := params.UseTimeSeconds
		frtSum := int64(0)
		frtCount := 0
		frtMax := int64(0)
		if frtMs, ok := extractFirstResponseTimeMs(params.Other); ok {
			frtSum = frtMs
			frtCount = 1
			frtMax = frtMs
		}
		gopool.Go(func() {
			// 数据看板缓存按 token 维度记录聚合结果。
			LogQuotaData(
				userId,
				username,
				params.TokenId,
				params.TokenName,
				params.ModelName,
				params.Quota,
				common.GetTimestamp(),
				params.PromptTokens+params.CompletionTokens,
				useTimeSum,
				useTimeCount,
				useTimeMax,
				frtSum,
				frtCount,
				frtMax,
			)
		})
	}
}

func GetAllLogs(logType int, startTimestamp int64, endTimestamp int64, modelName string, username string, tokenName string, startIdx int, num int, channel int, group string) (logs []*Log, total int64, err error) {
	var tx *gorm.DB
	if logType == LogTypeUnknown {
		tx = LOG_DB
	} else {
		tx = LOG_DB.Where("logs.type = ?", logType)
	}

	if modelName != "" {
		// 模型名筛选按字面量匹配，避免用户通配符扩大日志范围。
		tx = tx.Where("logs.model_name LIKE ? ESCAPE '!'", escapeLikePattern(modelName))
	}
	if username != "" {
		tx = tx.Where("logs.username = ?", username)
	}
	if tokenName != "" {
		tx = tx.Where("logs.token_name = ?", tokenName)
	}
	if startTimestamp != 0 {
		tx = tx.Where("logs.created_at >= ?", startTimestamp)
	}
	if endTimestamp != 0 {
		tx = tx.Where("logs.created_at <= ?", endTimestamp)
	}
	if channel != 0 {
		tx = tx.Where("logs.channel_id = ?", channel)
	}
	if group != "" {
		tx = tx.Where("logs."+logGroupCol+" = ?", group)
	}
	err = tx.Model(&Log{}).Count(&total).Error
	if err != nil {
		return nil, 0, err
	}
	err = tx.Order("logs.id desc").Limit(num).Offset(startIdx).Find(&logs).Error
	if err != nil {
		return nil, 0, err
	}

	channelIds := types.NewSet[int]()
	for _, log := range logs {
		if log.ChannelId != 0 {
			channelIds.Add(log.ChannelId)
		}
	}

	if channelIds.Len() > 0 {
		var channels []struct {
			Id   int    `gorm:"column:id"`
			Name string `gorm:"column:name"`
		}
		if err = DB.Table("channels").Select("id, name").Where("id IN ?", channelIds.Items()).Find(&channels).Error; err != nil {
			return logs, total, err
		}
		channelMap := make(map[int]string, len(channels))
		for _, channel := range channels {
			channelMap[channel.Id] = channel.Name
		}
		for i := range logs {
			logs[i].ChannelName = channelMap[logs[i].ChannelId]
		}
	}

	return logs, total, err
}

func GetUserLogs(userId int, logType int, startTimestamp int64, endTimestamp int64, modelName string, tokenName string, startIdx int, num int, group string) (logs []*Log, total int64, err error) {
	var tx *gorm.DB
	if logType == LogTypeUnknown {
		tx = LOG_DB.Where("logs.user_id = ?", userId)
	} else {
		tx = LOG_DB.Where("logs.user_id = ? and logs.type = ?", userId, logType)
	}

	if modelName != "" {
		// 模型名筛选按字面量匹配，避免用户通配符扩大日志范围。
		tx = tx.Where("logs.model_name LIKE ? ESCAPE '!'", escapeLikePattern(modelName))
	}
	if tokenName != "" {
		tx = tx.Where("logs.token_name = ?", tokenName)
	}
	if startTimestamp != 0 {
		tx = tx.Where("logs.created_at >= ?", startTimestamp)
	}
	if endTimestamp != 0 {
		tx = tx.Where("logs.created_at <= ?", endTimestamp)
	}
	if group != "" {
		tx = tx.Where("logs."+logGroupCol+" = ?", group)
	}
	err = tx.Model(&Log{}).Count(&total).Error
	if err != nil {
		return nil, 0, err
	}
	err = tx.Order("logs.id desc").Limit(num).Offset(startIdx).Find(&logs).Error
	if err != nil {
		return nil, 0, err
	}

	formatUserLogs(logs)
	return logs, total, err
}

func SearchAllLogs(keyword string) (logs []*Log, err error) {
	keywordPattern := escapeLikePattern(keyword) + "%"
	err = LOG_DB.Where("type = ? or content LIKE ? ESCAPE '!'", keyword, keywordPattern).
		Order("id desc").
		Limit(common.MaxRecentItems).
		Find(&logs).Error
	return logs, err
}

func SearchUserLogs(userId int, keyword string) (logs []*Log, err error) {
	err = LOG_DB.Where("user_id = ? and type = ?", userId, keyword).Order("id desc").Limit(common.MaxRecentItems).Find(&logs).Error
	formatUserLogs(logs)
	return logs, err
}

type Stat struct {
	Quota int `json:"quota"`
	Rpm   int `json:"rpm"`
	Tpm   int `json:"tpm"`
}

// ChannelModelPair 表示渠道列表页请求统计时使用的渠道-模型组合键。
type ChannelModelPair struct {
	ChannelID int    `json:"channel_id"`
	ModelName string `json:"model_name"`
}

// Key 返回渠道-模型组合在内存聚合中的稳定键。
func (pair ChannelModelPair) Key() string {
	return fmt.Sprintf("%d:%s", pair.ChannelID, pair.ModelName)
}

// ChannelModelActivityStat 表示近一月按活跃分钟计算得到的平均与峰值 RPM/TPM 统计。
type ChannelModelActivityStat struct {
	ChannelID     int     `json:"channel_id"`
	ModelName     string  `json:"model_name"`
	ActiveMinutes int64   `json:"active_minutes"`
	AvgRPM        float64 `json:"avg_rpm"`
	AvgTPM        float64 `json:"avg_tpm"`
	PeakRPM       int64   `json:"peak_rpm"`
	PeakTPM       int64   `json:"peak_tpm"`
	TotalRequests int64   `json:"total_requests"`
	TotalTokens   int64   `json:"total_tokens"`
}

// channelModelMinuteStatRow 对应数据库中“每分钟一行”的中间聚合结果。
type channelModelMinuteStatRow struct {
	ChannelID    int
	ModelName    string
	MinuteBucket int64
	RequestCount int64
	TokenCount   int64
}

// GetChannelModelActivityStats 按渠道-模型组合查询窗口期内“活跃分钟平均与峰值 RPM/TPM”。
// 这里的活跃分钟指窗口内至少出现过一次成功消费日志的分钟数。
func GetChannelModelActivityStats(pairs []ChannelModelPair, startTimestamp int64, endTimestamp int64) ([]ChannelModelActivityStat, error) {
	if len(pairs) == 0 {
		return make([]ChannelModelActivityStat, 0), nil
	}

	// 先去重并过滤空模型，避免重复条件放大 SQL 长度。
	uniquePairs := make([]ChannelModelPair, 0, len(pairs))
	seenPairs := make(map[string]struct{}, len(pairs))
	for _, pair := range pairs {
		trimmedModelName := strings.TrimSpace(pair.ModelName)
		if pair.ChannelID <= 0 || trimmedModelName == "" {
			continue
		}
		normalizedPair := ChannelModelPair{
			ChannelID: pair.ChannelID,
			ModelName: trimmedModelName,
		}
		pairKey := normalizedPair.Key()
		if _, exists := seenPairs[pairKey]; exists {
			continue
		}
		seenPairs[pairKey] = struct{}{}
		uniquePairs = append(uniquePairs, normalizedPair)
	}
	if len(uniquePairs) == 0 {
		return make([]ChannelModelActivityStat, 0), nil
	}

	// 先按分钟做数据库聚合，再在 Go 侧折算活跃分钟平均值与峰值，兼容多数据库方言。
	minuteBucketExpr := "(created_at / 60)"
	minuteRows := make([]channelModelMinuteStatRow, 0)
	query := LOG_DB.Table("logs").
		Select(
			"channel_id, model_name, "+minuteBucketExpr+" AS minute_bucket, count(*) AS request_count, "+
				"COALESCE(sum(prompt_tokens), 0) + COALESCE(sum(completion_tokens), 0) AS token_count",
		).
		Where("type = ?", LogTypeConsume)
	if startTimestamp > 0 {
		query = query.Where("created_at >= ?", startTimestamp)
	}
	if endTimestamp > 0 {
		query = query.Where("created_at <= ?", endTimestamp)
	}

	// 使用 OR 组合精确匹配 channel_id + model_name，避免 channel/model 各自 IN 带来的笛卡尔误匹配。
	pairClauses := make([]string, 0, len(uniquePairs))
	pairArgs := make([]interface{}, 0, len(uniquePairs)*2)
	for _, pair := range uniquePairs {
		pairClauses = append(pairClauses, "(channel_id = ? AND model_name = ?)")
		pairArgs = append(pairArgs, pair.ChannelID, pair.ModelName)
	}
	query = query.Where(strings.Join(pairClauses, " OR "), pairArgs...)

	if err := query.
		Group("channel_id, model_name, " + minuteBucketExpr).
		Scan(&minuteRows).Error; err != nil {
		return nil, err
	}

	// 只为真实命中的组合建立聚合结果，避免给无日志组合返回 0 值假数据。
	resultByKey := make(map[string]*ChannelModelActivityStat, len(minuteRows))

	// 逐分钟累加请求数与 token 数，并把分钟行数视为活跃分钟数。
	for _, row := range minuteRows {
		pairKey := ChannelModelPair{ChannelID: row.ChannelID, ModelName: row.ModelName}.Key()
		stat := resultByKey[pairKey]
		if stat == nil {
			stat = &ChannelModelActivityStat{
				ChannelID: row.ChannelID,
				ModelName: row.ModelName,
			}
			resultByKey[pairKey] = stat
		}
		stat.ActiveMinutes++
		stat.TotalRequests += row.RequestCount
		stat.TotalTokens += row.TokenCount
		if row.RequestCount > stat.PeakRPM {
			stat.PeakRPM = row.RequestCount
		}
		if row.TokenCount > stat.PeakTPM {
			stat.PeakTPM = row.TokenCount
		}
	}

	// 按请求顺序输出真实存在的统计项，兼顾前端回填稳定性与无日志组合过滤。
	results := make([]ChannelModelActivityStat, 0, len(resultByKey))
	for _, pair := range uniquePairs {
		stat := resultByKey[pair.Key()]
		if stat == nil {
			continue
		}
		// 最后再计算平均值，避免每个分钟桶都做浮点运算。
		activeMinutes := float64(stat.ActiveMinutes)
		stat.AvgRPM = float64(stat.TotalRequests) / activeMinutes
		stat.AvgTPM = float64(stat.TotalTokens) / activeMinutes
		results = append(results, *stat)
	}

	return results, nil
}

func SumUsedQuota(logType int, startTimestamp int64, endTimestamp int64, modelName string, username string, tokenName string, channel int, group string) (stat Stat) {
	tx := LOG_DB.Table("logs").Select("sum(quota) quota")

	// 为rpm和tpm创建单独的查询
	rpmTpmQuery := LOG_DB.Table("logs").Select("count(*) rpm, sum(prompt_tokens) + sum(completion_tokens) tpm")

	if username != "" {
		tx = tx.Where("username = ?", username)
		rpmTpmQuery = rpmTpmQuery.Where("username = ?", username)
	}
	if tokenName != "" {
		tx = tx.Where("token_name = ?", tokenName)
		rpmTpmQuery = rpmTpmQuery.Where("token_name = ?", tokenName)
	}
	if startTimestamp != 0 {
		tx = tx.Where("created_at >= ?", startTimestamp)
	}
	if endTimestamp != 0 {
		tx = tx.Where("created_at <= ?", endTimestamp)
	}
	if modelName != "" {
		// 配额和 RPM/TPM 统计共用相同的模型名字面量筛选。
		modelNamePattern := escapeLikePattern(modelName)
		tx = tx.Where("model_name LIKE ? ESCAPE '!'", modelNamePattern)
		rpmTpmQuery = rpmTpmQuery.Where("model_name LIKE ? ESCAPE '!'", modelNamePattern)
	}
	if channel != 0 {
		tx = tx.Where("channel_id = ?", channel)
		rpmTpmQuery = rpmTpmQuery.Where("channel_id = ?", channel)
	}
	if group != "" {
		tx = tx.Where(logGroupCol+" = ?", group)
		rpmTpmQuery = rpmTpmQuery.Where(logGroupCol+" = ?", group)
	}

	tx = tx.Where("type = ?", LogTypeConsume)
	rpmTpmQuery = rpmTpmQuery.Where("type = ?", LogTypeConsume)

	// 只统计最近60秒的rpm和tpm
	rpmTpmQuery = rpmTpmQuery.Where("created_at >= ?", time.Now().Add(-60*time.Second).Unix())

	// 执行查询
	tx.Scan(&stat)
	rpmTpmQuery.Scan(&stat)

	return stat
}

func SumUsedToken(logType int, startTimestamp int64, endTimestamp int64, modelName string, username string, tokenName string) (token int) {
	tx := LOG_DB.Table("logs").Select("ifnull(sum(prompt_tokens),0) + ifnull(sum(completion_tokens),0)")
	if username != "" {
		tx = tx.Where("username = ?", username)
	}
	if tokenName != "" {
		tx = tx.Where("token_name = ?", tokenName)
	}
	if startTimestamp != 0 {
		tx = tx.Where("created_at >= ?", startTimestamp)
	}
	if endTimestamp != 0 {
		tx = tx.Where("created_at <= ?", endTimestamp)
	}
	if modelName != "" {
		tx = tx.Where("model_name = ?", modelName)
	}
	tx.Where("type = ?", LogTypeConsume).Scan(&token)
	return token
}

func DeleteOldLog(ctx context.Context, targetTimestamp int64, limit int) (int64, error) {
	var total int64 = 0

	for {
		if nil != ctx.Err() {
			return total, ctx.Err()
		}

		result := LOG_DB.Where("created_at < ?", targetTimestamp).Limit(limit).Delete(&Log{})
		if nil != result.Error {
			return total, result.Error
		}

		total += result.RowsAffected

		if result.RowsAffected < int64(limit) {
			break
		}
	}

	return total, nil
}
