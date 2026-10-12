package controller

import (
	"strconv"

	"github.com/QuantumNous/new-api/common"
	"github.com/QuantumNous/new-api/service"

	"github.com/gin-gonic/gin"
)

// GetModelQuotas 返回模型配额页面所需的普通项/共享池项/子项聚合数据。
func GetModelQuotas(c *gin.Context) {
	items, err := service.ListModelQuotas(c.Query("group"))
	if err != nil {
		common.ApiError(c, err)
		return
	}
	common.ApiSuccess(c, items)
}

// UpdateModelQuota 保存普通模型项或共享配额池项的额度配置。
func UpdateModelQuota(c *gin.Context) {
	request := service.SaveModelQuotaConfigRequest{}
	if err := c.ShouldBindJSON(&request); err != nil {
		common.ApiError(c, err)
		return
	}
	// 管理员接口已由路由层鉴权，这里透传操作者 ID 用于补充审计日志。
	item, err := service.SaveModelQuotaConfig(c.GetInt("id"), request)
	if err != nil {
		common.ApiError(c, err)
		return
	}
	common.ApiSuccess(c, item)
}

// SaveSharedModelQuotaPool 保存共享配额池配置及其成员关系。
func SaveSharedModelQuotaPool(c *gin.Context) {
	request := service.SaveSharedPoolRequest{}
	if err := c.ShouldBindJSON(&request); err != nil {
		common.ApiError(c, err)
		return
	}
	// 管理员接口已由路由层鉴权，这里透传操作者 ID 用于补充审计日志。
	item, err := service.SaveSharedPool(c.GetInt("id"), request)
	if err != nil {
		common.ApiError(c, err)
		return
	}
	common.ApiSuccess(c, item)
}

// DeleteModelQuota 删除普通模型项。
func DeleteModelQuota(c *gin.Context) {
	id, err := strconv.Atoi(c.Param("id"))
	if err != nil {
		common.ApiError(c, err)
		return
	}
	if err = service.DeleteModelQuota(c.GetInt("id"), id); err != nil {
		common.ApiError(c, err)
		return
	}
	common.ApiSuccess(c, nil)
}

// DeleteSharedModelQuotaPool 删除整个共享配额池。
func DeleteSharedModelQuotaPool(c *gin.Context) {
	id, err := strconv.Atoi(c.Param("id"))
	if err != nil {
		common.ApiError(c, err)
		return
	}
	if err = service.DeleteSharedPool(c.GetInt("id"), id); err != nil {
		common.ApiError(c, err)
		return
	}
	common.ApiSuccess(c, nil)
}

// RemoveSharedModelQuotaTag 将共享池子项恢复为普通模型项。
func RemoveSharedModelQuotaTag(c *gin.Context) {
	id, err := strconv.Atoi(c.Param("id"))
	if err != nil {
		common.ApiError(c, err)
		return
	}
	item, err := service.RemoveSharedPoolMemberTag(c.GetInt("id"), id)
	if err != nil {
		common.ApiError(c, err)
		return
	}
	common.ApiSuccess(c, item)
}

// GetModelQuotaReferences 返回指定模型配额当前引用的令牌名称列表。
func GetModelQuotaReferences(c *gin.Context) {
	id, err := strconv.Atoi(c.Param("id"))
	if err != nil {
		common.ApiError(c, err)
		return
	}
	info, err := service.GetModelQuotaReferenceInfo(id)
	if err != nil {
		common.ApiError(c, err)
		return
	}
	common.ApiSuccess(c, info)
}
