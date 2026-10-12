package model

import (
	"fmt"
	"sync"
	"time"

	"github.com/QuantumNous/new-api/common"
	"gorm.io/gorm"
)

// QuotaData 柱状图数据
type QuotaData struct {
	Id       int    `json:"id"`
	UserID   int    `json:"user_id" gorm:"index"`
	Username string `json:"username" gorm:"index:idx_qdt_model_user_name,priority:2;size:64;default:''"`
	// TokenID/TokenName 用于把看板统计细化到令牌维度。
	TokenID   int    `json:"token_id" gorm:"index"`
	TokenName string `json:"token_name" gorm:"size:64;default:'';index"`
	ModelName string `json:"model_name" gorm:"index:idx_qdt_model_user_name,priority:1;size:64;default:''"`
	CreatedAt int64  `json:"created_at" gorm:"bigint;index:idx_qdt_created_at,priority:2"`
	TokenUsed int    `json:"token_used" gorm:"default:0"`
	Count     int    `json:"count" gorm:"default:0"`
	Quota     int    `json:"quota" gorm:"default:0"`
	// 响应时间和首字延迟字段用于支持性能看板。
	UseTimeSum   int64 `json:"use_time_sum" gorm:"bigint;default:0"`
	UseTimeCount int   `json:"use_time_count" gorm:"default:0"`
	UseTimeMax   int   `json:"use_time_max" gorm:"default:0"`
	FRTSum       int64 `json:"frt_sum" gorm:"bigint;default:0"`
	FRTCount     int   `json:"frt_count" gorm:"default:0"`
	FRTMax       int64 `json:"frt_max" gorm:"bigint;default:0"`
}

func UpdateQuotaData() {
	for {
		if common.DataExportEnabled {
			common.SysLog("正在更新数据看板数据...")
			SaveQuotaDataCache()
		}
		time.Sleep(time.Duration(common.DataExportInterval) * time.Minute)
	}
}

var CacheQuotaData = make(map[string]*QuotaData)
var CacheQuotaDataLock = sync.Mutex{}

func maxInt64(a int64, b int64) int64 {
	if a >= b {
		return a
	}
	return b
}

func logQuotaDataCache(userId int, username string, tokenId int, tokenName string, modelName string, quota int, createdAt int64, tokenUsed int,
	useTimeSum int64, useTimeCount int, useTimeMax int, frtSum int64, frtCount int, frtMax int64) {
	key := fmt.Sprintf("%d-%d-%s-%d", userId, tokenId, modelName, createdAt)
	quotaData, ok := CacheQuotaData[key]
	if ok {
		quotaData.Count += 1
		quotaData.Quota += quota
		quotaData.TokenUsed += tokenUsed
		quotaData.UseTimeSum += useTimeSum
		quotaData.UseTimeCount += useTimeCount
		quotaData.UseTimeMax = common.IntMax(quotaData.UseTimeMax, useTimeMax)
		quotaData.FRTSum += frtSum
		quotaData.FRTCount += frtCount
		quotaData.FRTMax = maxInt64(quotaData.FRTMax, frtMax)
		if quotaData.TokenName == "" && tokenName != "" {
			quotaData.TokenName = tokenName
		}
	} else {
		quotaData = &QuotaData{
			UserID:    userId,
			Username:  username,
			TokenID:   tokenId,
			TokenName: tokenName,
			ModelName: modelName,
			CreatedAt: createdAt,
			Count:     1,
			Quota:     quota,
			TokenUsed: tokenUsed,
			UseTimeSum:   useTimeSum,
			UseTimeCount: useTimeCount,
			UseTimeMax:   useTimeMax,
			FRTSum:       frtSum,
			FRTCount:     frtCount,
			FRTMax:       frtMax,
		}
	}
	CacheQuotaData[key] = quotaData
}

func LogQuotaData(userId int, username string, tokenId int, tokenName string, modelName string, quota int, createdAt int64, tokenUsed int,
	useTimeSum int64, useTimeCount int, useTimeMax int, frtSum int64, frtCount int, frtMax int64) {
	// 只精确到小时
	createdAt = createdAt - (createdAt % 3600)

	CacheQuotaDataLock.Lock()
	defer CacheQuotaDataLock.Unlock()
	logQuotaDataCache(userId, username, tokenId, tokenName, modelName, quota, createdAt, tokenUsed,
		useTimeSum, useTimeCount, useTimeMax, frtSum, frtCount, frtMax)
}

func SaveQuotaDataCache() {
	CacheQuotaDataLock.Lock()
	defer CacheQuotaDataLock.Unlock()
	size := len(CacheQuotaData)
	// 如果缓存中有数据，就保存到数据库中
	// 1. 先查询数据库中是否有数据
	// 2. 如果有数据，就更新数据
	// 3. 如果没有数据，就插入数据
	for _, quotaData := range CacheQuotaData {
		quotaDataDB := &QuotaData{}
		DB.Table("quota_data").Where("user_id = ? and token_id = ? and model_name = ? and created_at = ?",
			quotaData.UserID, quotaData.TokenID, quotaData.ModelName, quotaData.CreatedAt).First(quotaDataDB)
		if quotaDataDB.Id > 0 {
			increaseQuotaData(
				quotaData.UserID,
				quotaData.TokenID,
				quotaData.TokenName,
				quotaData.ModelName,
				quotaData.Count,
				quotaData.Quota,
				quotaData.CreatedAt,
				quotaData.TokenUsed,
				quotaData.UseTimeSum,
				quotaData.UseTimeCount,
				common.IntMax(quotaDataDB.UseTimeMax, quotaData.UseTimeMax),
				quotaData.FRTSum,
				quotaData.FRTCount,
				maxInt64(quotaDataDB.FRTMax, quotaData.FRTMax),
			)
		} else {
			DB.Table("quota_data").Create(quotaData)
		}
	}
	CacheQuotaData = make(map[string]*QuotaData)
	common.SysLog(fmt.Sprintf("保存数据看板数据成功，共保存%d条数据", size))
}

func increaseQuotaData(userId int, tokenId int, tokenName string, modelName string, count int, quota int, createdAt int64, tokenUsed int,
	useTimeSum int64, useTimeCount int, useTimeMax int, frtSum int64, frtCount int, frtMax int64) {
	updates := map[string]interface{}{
		"count":          gorm.Expr("count + ?", count),
		"quota":          gorm.Expr("quota + ?", quota),
		"token_used":     gorm.Expr("token_used + ?", tokenUsed),
		"use_time_sum":   gorm.Expr("use_time_sum + ?", useTimeSum),
		"use_time_count": gorm.Expr("use_time_count + ?", useTimeCount),
		"use_time_max":   useTimeMax,
		"frt_sum":        gorm.Expr("frt_sum + ?", frtSum),
		"frt_count":      gorm.Expr("frt_count + ?", frtCount),
		"frt_max":        frtMax,
	}
	// 避免历史空值把已有 token_name 覆盖回空字符串。
	if tokenName != "" {
		updates["token_name"] = tokenName
	}
	err := DB.Table("quota_data").Where("user_id = ? and token_id = ? and model_name = ? and created_at = ?",
		userId, tokenId, modelName, createdAt).Updates(updates).Error
	if err != nil {
		common.SysLog(fmt.Sprintf("increaseQuotaData error: %s", err))
	}
}

// applyQuotaDataTokenFilter 在原有查询条件上追加 token 维度过滤。
func applyQuotaDataTokenFilter(tx *gorm.DB, tokenId int, tokenName string) *gorm.DB {
	if tokenId > 0 {
		tx = tx.Where("token_id = ?", tokenId)
	}
	if tokenName != "" {
		tx = tx.Where("token_name = ?", tokenName)
	}
	return tx
}

func GetQuotaDataByUsername(username string, startTime int64, endTime int64, tokenId int, tokenName string) (quotaData []*QuotaData, err error) {
	var quotaDatas []*QuotaData
	// 从quota_data表中查询数据
	tx := DB.Table("quota_data").Where("username = ? and created_at >= ? and created_at <= ?", username, startTime, endTime)
	tx = applyQuotaDataTokenFilter(tx, tokenId, tokenName)
	err = tx.Find(&quotaDatas).Error
	return quotaDatas, err
}

func GetQuotaDataByUserId(userId int, startTime int64, endTime int64, tokenId int, tokenName string) (quotaData []*QuotaData, err error) {
	var quotaDatas []*QuotaData
	// 从quota_data表中查询数据
	tx := DB.Table("quota_data").Where("user_id = ? and created_at >= ? and created_at <= ?", userId, startTime, endTime)
	tx = applyQuotaDataTokenFilter(tx, tokenId, tokenName)
	err = tx.Find(&quotaDatas).Error
	return quotaDatas, err
}

func GetAllQuotaDates(startTime int64, endTime int64, username string, tokenId int, tokenName string) (quotaData []*QuotaData, err error) {
	if username != "" {
		return GetQuotaDataByUsername(username, startTime, endTime, tokenId, tokenName)
	}
	var quotaDatas []*QuotaData
	// 从quota_data表中查询数据
	// only select model_name, sum(count) as count, sum(quota) as quota, model_name, created_at from quota_data group by model_name, created_at;
	//err = DB.Table("quota_data").Where("created_at >= ? and created_at <= ?", startTime, endTime).Find(&quotaDatas).Error
	tx := DB.Table("quota_data").Select("model_name, sum(count) as count, sum(quota) as quota, sum(token_used) as token_used, sum(use_time_sum) as use_time_sum, sum(use_time_count) as use_time_count, max(use_time_max) as use_time_max, sum(frt_sum) as frt_sum, sum(frt_count) as frt_count, max(frt_max) as frt_max, created_at").Where("created_at >= ? and created_at <= ?", startTime, endTime)
	tx = applyQuotaDataTokenFilter(tx, tokenId, tokenName)
	err = tx.Group("model_name, created_at").Find(&quotaDatas).Error
	return quotaDatas, err
}
