package service

import (
	"errors"
	"fmt"
	"sort"
	"strconv"
	"strings"

	"github.com/QuantumNous/new-api/model"
	"golang.org/x/sync/singleflight"
	"gorm.io/gorm"
)

// modelQuotaCandidateSyncGroup 合并并发候选同步请求，避免同一时间重复扫描渠道能力。
var modelQuotaCandidateSyncGroup singleflight.Group

// ModelQuotaTokenRateLimit 表示模型配额项下真实生效的 token 限流配置。
type ModelQuotaTokenRateLimit struct {
	TokenID          int    `json:"token_id"`
	TokenName        string `json:"token_name"`
	ConcurrencyLimit *int   `json:"concurrency_limit,omitempty"`
	RPMLimit         *int   `json:"rpm_limit,omitempty"`
	TPMLimit         *int   `json:"tpm_limit,omitempty"`
}

// ModelQuotaItem 是模型配额页面读取接口返回的统一结构。
type ModelQuotaItem struct {
	ID                int                        `json:"id"`
	ItemType          string                     `json:"item_type"`
	Group             string                     `json:"group,omitempty"`
	ModelName         string                     `json:"model_name,omitempty"`
	QuotaName         string                     `json:"quota_name"`
	SharedPoolID      *int                       `json:"shared_pool_id,omitempty"`
	RPM               *int                       `json:"rpm,omitempty"`
	TPM               *int                       `json:"tpm,omitempty"`
	Concurrency       *int                       `json:"concurrency,omitempty"`
	RemainRPM         *int                       `json:"remain_rpm,omitempty"`
	RemainTPM         *int                       `json:"remain_tpm,omitempty"`
	RemainConcurrency *int                       `json:"remain_concurrency,omitempty"`
	IsAvailable       bool                       `json:"is_available"`
	Children          []ModelQuotaItem           `json:"children"`
	TokenRateLimits   []ModelQuotaTokenRateLimit `json:"token_rate_limits"`
}

// SaveModelQuotaConfigRequest 表示普通模型项或共享配额池项的额度保存请求。
type SaveModelQuotaConfigRequest struct {
	ID          int  `json:"id"`
	RPM         *int `json:"rpm"`
	TPM         *int `json:"tpm"`
	Concurrency *int `json:"concurrency"`
}

// SaveSharedPoolRequest 表示共享配额池及其成员关系的保存请求。
type SaveSharedPoolRequest struct {
	PoolID      int    `json:"pool_id"`
	PoolName    string `json:"pool_name"`
	RPM         *int   `json:"rpm"`
	TPM         *int   `json:"tpm"`
	Concurrency *int   `json:"concurrency"`
	MemberIDs   []int  `json:"member_ids"`
}

// ModelQuotaReferenceInfo 表示某个模型配额当前被哪些令牌引用。
type ModelQuotaReferenceInfo struct {
	ModelQuotaID int      `json:"model_quota_id"`
	TokenNames   []string `json:"token_names"`
}

// modelQuotaAllocatedLimits 汇总某个模型配额作用域下，已被 token 模型限流占用的三维额度。
type modelQuotaAllocatedLimits struct {
	RPM         int
	TPM         int
	Concurrency int
}

// modelQuotaRemainLimits 保存一次配置更新计算出的三维剩余额度。
type modelQuotaRemainLimits struct {
	RPM         *int
	TPM         *int
	Concurrency *int
}

// ListModelQuotas 返回模型配额页面所需的普通项/共享池项/子项聚合结构。
func ListModelQuotas(group string) ([]ModelQuotaItem, error) {
	if err := syncModelQuotaCandidates(); err != nil {
		return nil, err
	}
	quotas, err := model.ListAllModelQuotas(nil)
	if err != nil {
		return nil, err
	}
	items := buildModelQuotaItems(quotas, strings.TrimSpace(group))
	if err = attachTokenRateLimitsToModelQuotaItems(&items); err != nil {
		return nil, err
	}
	return items, nil
}

// SyncModelQuotaCandidatesForTokenEditor 在令牌编辑页读取候选/能力前补齐候选同步，
// 避免必须先访问模型配额页才能看到最新的关联配额池。
func SyncModelQuotaCandidatesForTokenEditor() error {
	return syncModelQuotaCandidates()
}

// SaveModelQuotaConfig 保存普通模型项或共享配额池项的配置值，并记录管理员审计日志。
func SaveModelQuotaConfig(operatorID int, request SaveModelQuotaConfigRequest) (*ModelQuotaItem, error) {
	if request.ID <= 0 {
		return nil, errors.New("模型配额 ID 不能为空")
	}
	if err := validateModelQuotaConfigValues(
		request.RPM,
		request.TPM,
		request.Concurrency,
	); err != nil {
		return nil, err
	}
	auditContent := ""
	err := model.DB.Transaction(func(tx *gorm.DB) error {
		quota, err := model.GetModelQuotaByIDForUpdate(tx, request.ID)
		if err != nil {
			return err
		}
		if quota.QuotaType == model.ModelQuotaTypeSharedPoolMember {
			return errors.New("共享配额池子项不支持直接编辑额度")
		}
		allocatedLimits, err := loadAllocatedModelQuotaLimits(tx, quota)
		if err != nil {
			return err
		}
		remainLimits, err := deriveModelQuotaRemainLimits(
			request.RPM,
			request.TPM,
			request.Concurrency,
			allocatedLimits,
		)
		if err != nil {
			return err
		}
		quota.RPM = cloneIntPointer(request.RPM)
		quota.TPM = cloneIntPointer(request.TPM)
		quota.Concurrency = cloneIntPointer(request.Concurrency)
		quota.RemainRPM = remainLimits.RPM
		quota.RemainTPM = remainLimits.TPM
		quota.RemainConcurrency = remainLimits.Concurrency
		if err = quota.Update(tx); err != nil {
			return err
		}
		auditContent = buildModelQuotaManageAuditContent(quota)
		return nil
	})
	if err != nil {
		return nil, err
	}
	// 事务提交成功后再写审计日志，避免回滚时留下误导性记录。
	recordModelQuotaManageLog(operatorID, auditContent)
	return findModelQuotaItemByID(request.ID)
}

// SaveSharedPool 保存共享配额池配置，并批量更新其成员关系与管理员审计日志。
func SaveSharedPool(operatorID int, request SaveSharedPoolRequest) (*ModelQuotaItem, error) {
	poolName := strings.TrimSpace(request.PoolName)
	if poolName == "" {
		return nil, errors.New("共享配额池名称不能为空")
	}
	memberIDs := uniquePositiveInts(request.MemberIDs)
	if len(memberIDs) == 0 {
		return nil, errors.New("共享配额池至少需要一个成员模型")
	}
	if err := validateModelQuotaConfigValues(
		request.RPM,
		request.TPM,
		request.Concurrency,
	); err != nil {
		return nil, err
	}

	poolID := request.PoolID
	auditContent := ""
	err := model.DB.Transaction(func(tx *gorm.DB) error {
		pool, err := loadOrCreateSharedPool(tx, poolID, poolName)
		if err != nil {
			return err
		}
		isCreate := pool.Id == 0
		pool.QuotaName = poolName

		// 先锁定本次成员行，再基于已提交关系汇总占用，避免和令牌限流分配互相覆盖余额。
		members, err := model.GetModelQuotasByIDsForUpdate(tx, memberIDs)
		if err != nil {
			return err
		}
		if len(members) != len(memberIDs) {
			return errors.New("部分共享配额池成员不存在")
		}
		for _, member := range members {
			if member.QuotaType == model.ModelQuotaTypeSharedPool {
				return errors.New("共享配额池项不能作为共享配额池成员")
			}
		}
		// 共享池保存时按最终成员集合派生余额，避免父池余额被客户端输入改脏。
		allocatedLimits, err := loadAllocatedModelQuotaLimitsByRelationQuotaIDs(tx, memberIDs)
		if err != nil {
			return err
		}
		remainLimits, err := deriveModelQuotaRemainLimits(
			request.RPM,
			request.TPM,
			request.Concurrency,
			allocatedLimits,
		)
		if err != nil {
			return err
		}
		pool.RPM = cloneIntPointer(request.RPM)
		pool.TPM = cloneIntPointer(request.TPM)
		pool.Concurrency = cloneIntPointer(request.Concurrency)
		pool.RemainRPM = remainLimits.RPM
		pool.RemainTPM = remainLimits.TPM
		pool.RemainConcurrency = remainLimits.Concurrency
		if pool.Id == 0 {
			if err = pool.Insert(tx); err != nil {
				return err
			}
		} else if err = pool.Update(tx); err != nil {
			return err
		}
		poolID = pool.Id

		// 现有成员也要加锁，避免移出/切池时和并发引用检查读到不稳定状态。
		existingMembers, err := model.ListSharedPoolMembersForUpdate(tx, poolID)
		if err != nil {
			return err
		}
		memberIDSet := make(map[int]struct{}, len(memberIDs))
		for _, memberID := range memberIDs {
			memberIDSet[memberID] = struct{}{}
		}
		if err = validateSharedPoolMemberChanges(tx, poolID, existingMembers, members); err != nil {
			return err
		}
		for _, existingMember := range existingMembers {
			if _, exists := memberIDSet[existingMember.Id]; exists {
				continue
			}
			resetSharedPoolMemberToNormal(existingMember)
			if err = existingMember.Update(tx); err != nil {
				return err
			}
		}
		for _, member := range members {
			assignModelQuotaToSharedPool(member, poolID)
			if err = member.Update(tx); err != nil {
				return err
			}
		}
		auditContent = buildSharedPoolManageAuditContent(pool, members, isCreate)
		return nil
	})
	if err != nil {
		return nil, err
	}
	// 共享池变更提交成功后再补记管理员日志，确保审计结果与数据库状态一致。
	recordModelQuotaManageLog(operatorID, auditContent)
	return findModelQuotaItemByID(poolID)
}

// DeleteModelQuota 删除普通模型项；若仍被令牌引用则直接阻断。
func DeleteModelQuota(operatorID int, id int) error {
	if id <= 0 {
		return errors.New("模型配额 ID 不能为空")
	}
	auditContent := ""
	err := model.DB.Transaction(func(tx *gorm.DB) error {
		quota, err := model.GetModelQuotaByIDForUpdate(tx, id)
		if err != nil {
			return err
		}
		if quota.QuotaType == model.ModelQuotaTypeSharedPool {
			return errors.New("共享配额池请使用删除共享池操作")
		}
		if quota.QuotaType == model.ModelQuotaTypeSharedPoolMember {
			return errors.New("共享池子项请使用移出共享池操作")
		}
		if err = validateModelQuotaHasNoTokenReference(tx, quota, "删除模型配额"); err != nil {
			return err
		}
		auditContent = fmt.Sprintf(
			"管理员删除模型配额普通项[%s](ID:%d)",
			buildModelQuotaAuditLabel(quota),
			quota.Id,
		)
		return model.DeleteModelQuotaByID(tx, quota.Id)
	})
	if err != nil {
		return err
	}
	recordModelQuotaManageLog(operatorID, auditContent)
	return nil
}

// RemoveSharedPoolMemberTag 将共享池子项恢复为普通模型项；若仍被引用则阻断。
func RemoveSharedPoolMemberTag(operatorID int, id int) (*ModelQuotaItem, error) {
	if id <= 0 {
		return nil, errors.New("模型配额 ID 不能为空")
	}
	auditContent := ""
	err := model.DB.Transaction(func(tx *gorm.DB) error {
		quota, err := lockQuotaAndCurrentSharedPoolForUpdate(tx, id)
		if err != nil {
			return err
		}
		if quota.QuotaType != model.ModelQuotaTypeSharedPoolMember {
			return errors.New("目标记录不是共享池子项")
		}
		if err = validateModelQuotaHasNoTokenReference(tx, quota, "删除共享池标签"); err != nil {
			return err
		}
		resetSharedPoolMemberToNormal(quota)
		if err = quota.Update(tx); err != nil {
			return err
		}
		auditContent = fmt.Sprintf(
			"管理员删除共享池标签[%s](ID:%d)，已恢复为普通模型项",
			buildModelQuotaAuditLabel(quota),
			quota.Id,
		)
		return nil
	})
	if err != nil {
		return nil, err
	}
	recordModelQuotaManageLog(operatorID, auditContent)
	return findModelQuotaItemByID(id)
}

// DeleteSharedPool 在确认成员无令牌引用后删除整个共享池，并将子项恢复为普通模型项。
func DeleteSharedPool(operatorID int, id int) error {
	if id <= 0 {
		return errors.New("共享配额池 ID 不能为空")
	}
	auditContent := ""
	err := model.DB.Transaction(func(tx *gorm.DB) error {
		pool, err := model.GetModelQuotaByIDForUpdate(tx, id)
		if err != nil {
			return err
		}
		if pool.QuotaType != model.ModelQuotaTypeSharedPool {
			return errors.New("目标记录不是共享配额池")
		}
		members, err := model.ListSharedPoolMembersForUpdate(tx, pool.Id)
		if err != nil {
			return err
		}
		if err = validateSharedPoolHasNoTokenReference(tx, pool, members); err != nil {
			return err
		}
		for _, member := range members {
			resetSharedPoolMemberToNormal(member)
			if err = member.Update(tx); err != nil {
				return err
			}
		}
		auditContent = fmt.Sprintf(
			"管理员删除共享配额池[%s](ID:%d)，成员：%s",
			buildModelQuotaAuditLabel(pool),
			pool.Id,
			buildSharedPoolMemberSummary(members),
		)
		return model.DeleteModelQuotaByID(tx, pool.Id)
	})
	if err != nil {
		return err
	}
	recordModelQuotaManageLog(operatorID, auditContent)
	return nil
}

// GetModelQuotaReferenceInfo 返回某个模型配额当前引用的令牌列表，供前端删除前提示使用。
func GetModelQuotaReferenceInfo(id int) (*ModelQuotaReferenceInfo, error) {
	if id <= 0 {
		return nil, errors.New("模型配额 ID 不能为空")
	}
	quota, err := model.GetModelQuotaByID(nil, id)
	if err != nil {
		return nil, err
	}
	tokenNames, err := listReferencingTokenNamesByQuota(nil, quota)
	if err != nil {
		return nil, err
	}
	return &ModelQuotaReferenceInfo{
		ModelQuotaID: quota.Id,
		TokenNames:   tokenNames,
	}, nil
}

// buildModelQuotaItems 将持久化记录转换为页面直出的树形结构。
func buildModelQuotaItems(quotas []*model.ModelQuota, groupFilter string) []ModelQuotaItem {
	parents := make(map[int]*ModelQuotaItem)
	childrenByPoolID := make(map[int][]ModelQuotaItem)
	items := []ModelQuotaItem{}
	for _, quota := range quotas {
		switch quota.QuotaType {
		case model.ModelQuotaTypeSharedPool:
			item := buildModelQuotaItem(quota)
			parents[quota.Id] = &item
		case model.ModelQuotaTypeSharedPoolMember:
			if quota.SharedPoolID == nil {
				continue
			}
			if groupFilter != "" && quota.Group != groupFilter {
				continue
			}
			childrenByPoolID[*quota.SharedPoolID] = append(
				childrenByPoolID[*quota.SharedPoolID],
				buildModelQuotaItem(quota),
			)
		default:
			if groupFilter != "" && quota.Group != groupFilter {
				continue
			}
			items = append(items, buildModelQuotaItem(quota))
		}
	}
	poolIDs := make([]int, 0, len(parents))
	for poolID := range parents {
		poolIDs = append(poolIDs, poolID)
	}
	sort.Ints(poolIDs)
	for _, poolID := range poolIDs {
		parent := parents[poolID]
		children := childrenByPoolID[poolID]
		sort.Slice(children, func(i int, j int) bool {
			if children[i].Group == children[j].Group {
				if children[i].ModelName == children[j].ModelName {
					return children[i].ID < children[j].ID
				}
				return children[i].ModelName < children[j].ModelName
			}
			return children[i].Group < children[j].Group
		})
		parent.Children = children
		if groupFilter != "" && len(children) == 0 {
			continue
		}
		items = append(items, *parent)
	}
	sort.Slice(items, func(i int, j int) bool {
		if items[i].ItemType == items[j].ItemType {
			if items[i].Group == items[j].Group {
				if items[i].QuotaName == items[j].QuotaName {
					return items[i].ID < items[j].ID
				}
				return items[i].QuotaName < items[j].QuotaName
			}
			return items[i].Group < items[j].Group
		}
		return modelQuotaSortWeight(items[i].ItemType) < modelQuotaSortWeight(items[j].ItemType)
	})
	return items
}

// buildModelQuotaItem 将单条数据库记录映射为接口响应项。
func buildModelQuotaItem(quota *model.ModelQuota) ModelQuotaItem {
	return ModelQuotaItem{
		ID:                quota.Id,
		ItemType:          quota.QuotaType,
		Group:             quota.Group,
		ModelName:         quota.ModelName,
		QuotaName:         quota.QuotaName,
		SharedPoolID:      quota.SharedPoolID,
		RPM:               cloneIntPointer(quota.RPM),
		TPM:               cloneIntPointer(quota.TPM),
		Concurrency:       cloneIntPointer(quota.Concurrency),
		RemainRPM:         cloneIntPointer(quota.RemainRPM),
		RemainTPM:         cloneIntPointer(quota.RemainTPM),
		RemainConcurrency: cloneIntPointer(quota.RemainConcurrency),
		IsAvailable:       quota.IsAvailable,
		Children:          []ModelQuotaItem{},
		TokenRateLimits:   []ModelQuotaTokenRateLimit{},
	}
}

// attachTokenRateLimitsToModelQuotaItems 为普通项和共享池子项挂载真实 token 限流配置。
// 普通项直接挂自身，共享池父项保持空列表，具体规则挂到命中的子项上。
func attachTokenRateLimitsToModelQuotaItems(items *[]ModelQuotaItem) error {
	if items == nil || len(*items) == 0 {
		return nil
	}
	modelQuotaIDs := collectTokenRateLimitModelQuotaIDs(*items)
	if len(modelQuotaIDs) == 0 {
		return nil
	}
	relations, err := model.ListTokenModelQuotaRelationsByModelQuotaIDs(nil, modelQuotaIDs)
	if err != nil {
		return err
	}
	tokenIDs := make([]int, 0, len(relations))
	for _, relation := range relations {
		tokenIDs = append(tokenIDs, relation.TokenID)
	}
	tokens, err := model.GetTokensByIDs(nil, uniquePositiveInts(tokenIDs))
	if err != nil {
		return err
	}
	tokenNameByID := make(map[int]string, len(tokens))
	for _, token := range tokens {
		tokenNameByID[token.Id] = token.Name
	}
	tokenRateLimitsByQuotaID := make(map[int][]ModelQuotaTokenRateLimit)
	for _, relation := range relations {
		tokenRateLimitsByQuotaID[relation.ModelQuotaID] = append(
			tokenRateLimitsByQuotaID[relation.ModelQuotaID],
			ModelQuotaTokenRateLimit{
				TokenID:          relation.TokenID,
				TokenName:        tokenNameByID[relation.TokenID],
				ConcurrencyLimit: cloneIntPointer(relation.ConcurrencyLimit),
				RPMLimit:         cloneIntPointer(relation.RPMLimit),
				TPMLimit:         cloneIntPointer(relation.TPMLimit),
			},
		)
	}
	for index := range *items {
		if (*items)[index].ItemType == model.ModelQuotaTypeNormal {
			(*items)[index].TokenRateLimits = tokenRateLimitsByQuotaID[(*items)[index].ID]
			if (*items)[index].TokenRateLimits == nil {
				(*items)[index].TokenRateLimits = []ModelQuotaTokenRateLimit{}
			}
			continue
		}
		if (*items)[index].ItemType != model.ModelQuotaTypeSharedPool {
			continue
		}
		(*items)[index].TokenRateLimits = []ModelQuotaTokenRateLimit{}
		for childIndex := range (*items)[index].Children {
			childID := (*items)[index].Children[childIndex].ID
			(*items)[index].Children[childIndex].TokenRateLimits = tokenRateLimitsByQuotaID[childID]
			if (*items)[index].Children[childIndex].TokenRateLimits == nil {
				(*items)[index].Children[childIndex].TokenRateLimits = []ModelQuotaTokenRateLimit{}
			}
		}
	}
	return nil
}

// collectTokenRateLimitModelQuotaIDs 汇总需要挂载 token 限流信息的普通项与共享池子项 ID。
func collectTokenRateLimitModelQuotaIDs(items []ModelQuotaItem) []int {
	ids := make([]int, 0, len(items))
	for _, item := range items {
		if item.ItemType == model.ModelQuotaTypeNormal {
			ids = append(ids, item.ID)
			continue
		}
		if item.ItemType != model.ModelQuotaTypeSharedPool {
			continue
		}
		for _, child := range item.Children {
			ids = append(ids, child.ID)
		}
	}
	return uniquePositiveInts(ids)
}

// buildModelQuotaManageAuditContent 生成普通项/共享池项更新后的管理员审计文案。
func buildModelQuotaManageAuditContent(quota *model.ModelQuota) string {
	actionName := "编辑模型配额普通项"
	if quota.QuotaType == model.ModelQuotaTypeSharedPool {
		actionName = "编辑共享配额池"
	}
	return fmt.Sprintf(
		"管理员%s[%s](ID:%d)，新配置：%s",
		actionName,
		buildModelQuotaAuditLabel(quota),
		quota.Id,
		buildModelQuotaConfigSummary(quota),
	)
}

// buildSharedPoolManageAuditContent 生成共享池新增或编辑后的管理员审计文案。
func buildSharedPoolManageAuditContent(pool *model.ModelQuota, members []*model.ModelQuota, isCreate bool) string {
	actionName := "编辑"
	if isCreate {
		actionName = "新增"
	}
	return fmt.Sprintf(
		"管理员%s共享配额池[%s](ID:%d)，成员：%s，新配置：%s",
		actionName,
		buildModelQuotaAuditLabel(pool),
		pool.Id,
		buildSharedPoolMemberSummary(members),
		buildModelQuotaConfigSummary(pool),
	)
}

// buildModelQuotaAuditLabel 为审计日志生成稳定的人类可读标识。
func buildModelQuotaAuditLabel(quota *model.ModelQuota) string {
	if quota == nil {
		return ""
	}
	if quota.QuotaType == model.ModelQuotaTypeSharedPool {
		return quota.QuotaName
	}
	if strings.TrimSpace(quota.Group) == "" {
		return quota.ModelName
	}
	return fmt.Sprintf("%s/%s", quota.Group, quota.ModelName)
}

// buildModelQuotaConfigSummary 统一格式化额度配置，便于日志检索与人工审计。
func buildModelQuotaConfigSummary(quota *model.ModelQuota) string {
	return fmt.Sprintf(
		"RPM=%s，TPM=%s，并发=%s，剩余RPM=%s，剩余TPM=%s，剩余并发=%s",
		formatOptionalIntForAudit(quota.RPM),
		formatOptionalIntForAudit(quota.TPM),
		formatOptionalIntForAudit(quota.Concurrency),
		formatOptionalIntForAudit(quota.RemainRPM),
		formatOptionalIntForAudit(quota.RemainTPM),
		formatOptionalIntForAudit(quota.RemainConcurrency),
	)
}

// buildSharedPoolMemberSummary 输出共享池成员的“分组/模型”列表，保持日志内容稳定可读。
func buildSharedPoolMemberSummary(members []*model.ModelQuota) string {
	if len(members) == 0 {
		return "无"
	}
	memberLabels := make([]string, 0, len(members))
	for _, member := range members {
		memberLabels = append(memberLabels, buildModelQuotaAuditLabel(member))
	}
	sort.Strings(memberLabels)
	return strings.Join(memberLabels, "、")
}

// formatOptionalIntForAudit 将可空整数字段统一转换为审计日志字符串。
func formatOptionalIntForAudit(value *int) string {
	if value == nil {
		return "未设置"
	}
	return strconv.Itoa(*value)
}

// recordModelQuotaManageLog 统一落库模型配额页面的管理员审计日志。
func recordModelQuotaManageLog(operatorID int, content string) {
	if operatorID <= 0 || strings.TrimSpace(content) == "" {
		return
	}
	model.RecordLog(operatorID, model.LogTypeManage, content)
}

// findModelQuotaItemByID 在最新聚合结果中查找指定模型配额项，兼容共享池子项场景。
func findModelQuotaItemByID(id int) (*ModelQuotaItem, error) {
	items, err := ListModelQuotas("")
	if err != nil {
		return nil, err
	}
	for _, item := range items {
		if item.ID == id {
			return &item, nil
		}
		for _, child := range item.Children {
			if child.ID == id {
				return &child, nil
			}
		}
	}
	return nil, fmt.Errorf("模型配额不存在，id=%d", id)
}

// syncModelQuotaCandidates 将渠道能力增量同步到模型配额候选集中。
func syncModelQuotaCandidates() error {
	_, err, _ := modelQuotaCandidateSyncGroup.Do("sync", func() (interface{}, error) {
		return nil, syncModelQuotaCandidatesOnce()
	})
	return err
}

// syncModelQuotaCandidatesOnce 执行一次真实同步，供 singleflight 包装后复用原有同步逻辑。
func syncModelQuotaCandidatesOnce() error {
	candidates, err := model.ListEnabledModelQuotaCandidates(nil)
	if err != nil {
		return err
	}
	return model.DB.Transaction(func(tx *gorm.DB) error {
		existingQuotas, queryErr := model.ListCandidateModelQuotas(tx)
		if queryErr != nil {
			return queryErr
		}
		candidateSet := make(map[string]model.ModelQuotaCandidate, len(candidates))
		for _, candidate := range candidates {
			key := buildModelQuotaCandidateKey(candidate.GroupName, candidate.ModelName)
			candidateSet[key] = candidate
		}
		existingSet := make(map[string]*model.ModelQuota, len(existingQuotas))
		for _, quota := range existingQuotas {
			key := buildModelQuotaCandidateKey(quota.Group, quota.ModelName)
			existingSet[key] = quota
			available := false
			if _, exists := candidateSet[key]; exists {
				available = true
			}
			if quota.IsAvailable == available {
				continue
			}
			quota.IsAvailable = available
			if err = quota.Update(tx); err != nil {
				return err
			}
		}
		for key, candidate := range candidateSet {
			if _, exists := existingSet[key]; exists {
				continue
			}
			quota := &model.ModelQuota{
				QuotaType:   model.ModelQuotaTypeNormal,
				Group:       candidate.GroupName,
				ModelName:   candidate.ModelName,
				QuotaName:   candidate.ModelName,
				IsAvailable: true,
			}
			if err = quota.InsertIgnoreConflict(tx); err != nil {
				return err
			}
		}
		return nil
	})
}

// lockQuotaAndCurrentSharedPoolForUpdate 先锁共享池父项再锁目标行。
// 这个顺序用于避免移出成员时和 token 账本写入交叉。
func lockQuotaAndCurrentSharedPoolForUpdate(tx *gorm.DB, id int) (*model.ModelQuota, error) {
	snapshot, err := model.GetModelQuotaByID(tx, id)
	if err != nil {
		return nil, err
	}
	snapshotSharedPoolID := 0
	if snapshot.QuotaType == model.ModelQuotaTypeSharedPoolMember && snapshot.SharedPoolID != nil {
		snapshotSharedPoolID = *snapshot.SharedPoolID
	}
	if snapshotSharedPoolID > 0 {
		pool, lockErr := model.GetModelQuotaByIDForUpdate(tx, snapshotSharedPoolID)
		if lockErr != nil {
			return nil, lockErr
		}
		if pool.QuotaType != model.ModelQuotaTypeSharedPool {
			return nil, errors.New("共享池父项类型已变更，请重试")
		}
	}
	quota, err := model.GetModelQuotaByIDForUpdate(tx, id)
	if err != nil {
		return nil, err
	}
	currentSharedPoolID := 0
	if quota.QuotaType == model.ModelQuotaTypeSharedPoolMember && quota.SharedPoolID != nil {
		currentSharedPoolID = *quota.SharedPoolID
	}
	if currentSharedPoolID != snapshotSharedPoolID {
		return nil, errors.New("模型配额共享池关系已变更，请重试")
	}
	return quota, nil
}

// loadOrCreateSharedPool 统一处理共享配额池的新建与更新前加载。
func loadOrCreateSharedPool(tx *gorm.DB, poolID int, poolName string) (*model.ModelQuota, error) {
	if poolID <= 0 {
		return &model.ModelQuota{
			QuotaType:   model.ModelQuotaTypeSharedPool,
			QuotaName:   poolName,
			IsAvailable: true,
		}, nil
	}
	pool, err := model.GetModelQuotaByIDForUpdate(tx, poolID)
	if err != nil {
		return nil, err
	}
	if pool.QuotaType != model.ModelQuotaTypeSharedPool {
		return nil, errors.New("目标记录不是共享配额池")
	}
	return pool, nil
}

// assignModelQuotaToSharedPool 将模型项切换为共享池子项，并清空其自身额度配置。
func assignModelQuotaToSharedPool(quota *model.ModelQuota, sharedPoolID int) {
	quota.QuotaType = model.ModelQuotaTypeSharedPoolMember
	quota.SharedPoolID = &sharedPoolID
	quota.RPM = nil
	quota.TPM = nil
	quota.Concurrency = nil
	quota.RemainRPM = nil
	quota.RemainTPM = nil
	quota.RemainConcurrency = nil
}

// resetSharedPoolMemberToNormal 将共享池子项恢复为普通模型项。
func resetSharedPoolMemberToNormal(quota *model.ModelQuota) {
	quota.QuotaType = model.ModelQuotaTypeNormal
	quota.SharedPoolID = nil
	quota.QuotaName = quota.ModelName
	quota.RPM = nil
	quota.TPM = nil
	quota.Concurrency = nil
	quota.RemainRPM = nil
	quota.RemainTPM = nil
	quota.RemainConcurrency = nil
}

// validateModelQuotaConfigValues 统一校验三个总额度的最小合法范围。
func validateModelQuotaConfigValues(
	rpm *int,
	tpm *int,
	concurrency *int,
) error {
	if err := validateOptionalPositiveInt("RPM", rpm); err != nil {
		return err
	}
	if err := validateOptionalPositiveInt("TPM", tpm); err != nil {
		return err
	}
	if err := validateOptionalPositiveInt("并发上限", concurrency); err != nil {
		return err
	}
	return nil
}

// loadAllocatedModelQuotaLimits 汇总普通项或共享池项当前已被 token 模型限流占用的额度。
func loadAllocatedModelQuotaLimits(tx *gorm.DB, quota *model.ModelQuota) (modelQuotaAllocatedLimits, error) {
	allocatedLimits := modelQuotaAllocatedLimits{}
	relationQuotaIDs, err := collectTokenModelQuotaRelationIDs(tx, quota)
	if err != nil {
		return allocatedLimits, err
	}
	return loadAllocatedModelQuotaLimitsByRelationQuotaIDs(tx, relationQuotaIDs)
}

// loadAllocatedModelQuotaLimitsByRelationQuotaIDs 按作用域内的模型配额 ID 汇总已被 token 占用的额度。
func loadAllocatedModelQuotaLimitsByRelationQuotaIDs(tx *gorm.DB, relationQuotaIDs []int) (modelQuotaAllocatedLimits, error) {
	allocatedLimits := modelQuotaAllocatedLimits{}
	if len(relationQuotaIDs) == 0 {
		return allocatedLimits, nil
	}
	relations, err := model.ListTokenModelQuotaRelationsByModelQuotaIDs(tx, relationQuotaIDs)
	if err != nil {
		return allocatedLimits, err
	}
	for _, relation := range relations {
		if relation.RPMLimit != nil {
			allocatedLimits.RPM += *relation.RPMLimit
		}
		if relation.TPMLimit != nil {
			allocatedLimits.TPM += *relation.TPMLimit
		}
		if relation.ConcurrencyLimit != nil {
			allocatedLimits.Concurrency += *relation.ConcurrencyLimit
		}
	}
	return allocatedLimits, nil
}

// collectTokenModelQuotaRelationIDs 解析当前模型配额需要汇总的关联记录作用域。
// 普通项直接汇总自身；共享池项则汇总其全部子项记录。
func collectTokenModelQuotaRelationIDs(tx *gorm.DB, quota *model.ModelQuota) ([]int, error) {
	if quota == nil || quota.Id <= 0 {
		return []int{}, nil
	}
	if quota.QuotaType != model.ModelQuotaTypeSharedPool {
		return []int{quota.Id}, nil
	}
	members, err := model.ListSharedPoolMembers(tx, quota.Id)
	if err != nil {
		return nil, err
	}
	ids := make([]int, 0, len(members))
	for _, member := range members {
		ids = append(ids, member.Id)
	}
	return uniquePositiveInts(ids), nil
}

// deriveAllocatedDimensionRemain 根据总额度和已分配额度计算单个维度的剩余额度。
func deriveAllocatedDimensionRemain(fieldName string, total *int, allocated int) (*int, error) {
	if total == nil {
		if allocated > 0 {
			return nil, fmt.Errorf("%s 当前已分配 %d，不能清空总额度", fieldName, allocated)
		}
		return nil, nil
	}
	if *total < allocated {
		return nil, fmt.Errorf("%s 当前已分配额度 %d 已超过总额度 %d", fieldName, allocated, *total)
	}
	remain := *total - allocated
	return &remain, nil
}

// deriveModelQuotaRemainLimits 统一计算 RPM、TPM 和并发三个维度的剩余额度。
func deriveModelQuotaRemainLimits(
	rpm *int,
	tpm *int,
	concurrency *int,
	allocated modelQuotaAllocatedLimits,
) (modelQuotaRemainLimits, error) {
	remain := modelQuotaRemainLimits{}
	var err error
	if remain.RPM, err = deriveAllocatedDimensionRemain("RPM", rpm, allocated.RPM); err != nil {
		return modelQuotaRemainLimits{}, err
	}
	if remain.TPM, err = deriveAllocatedDimensionRemain("TPM", tpm, allocated.TPM); err != nil {
		return modelQuotaRemainLimits{}, err
	}
	if remain.Concurrency, err = deriveAllocatedDimensionRemain(
		"并发上限",
		concurrency,
		allocated.Concurrency,
	); err != nil {
		return modelQuotaRemainLimits{}, err
	}
	return remain, nil
}

// validateSharedPoolMemberChanges 在移出共享池或切换共享池前，阻断仍被 token 模型限流引用的成员。
func validateSharedPoolMemberChanges(
	tx *gorm.DB,
	targetPoolID int,
	existingMembers []*model.ModelQuota,
	nextMembers []*model.ModelQuota,
) error {
	nextMemberIDSet := make(map[int]struct{}, len(nextMembers))
	for _, member := range nextMembers {
		nextMemberIDSet[member.Id] = struct{}{}
	}
	for _, existingMember := range existingMembers {
		if _, exists := nextMemberIDSet[existingMember.Id]; exists {
			continue
		}
		if err := validateModelQuotaHasNoTokenReference(tx, existingMember, "移出当前共享配额池"); err != nil {
			return err
		}
	}
	for _, nextMember := range nextMembers {
		// 普通模型项一旦加入共享池，就会失去原有普通项身份，因此同样需要先阻断已有 token 引用。
		if nextMember.QuotaType == model.ModelQuotaTypeNormal {
			if err := validateModelQuotaHasNoTokenReference(tx, nextMember, "加入共享配额池"); err != nil {
				return err
			}
			continue
		}
		if nextMember.QuotaType != model.ModelQuotaTypeSharedPoolMember {
			continue
		}
		if nextMember.SharedPoolID == nil || *nextMember.SharedPoolID == targetPoolID {
			continue
		}
		if err := validateModelQuotaHasNoTokenReference(tx, nextMember, "切换共享配额池标签"); err != nil {
			return err
		}
	}
	return nil
}

// validateSharedPoolHasNoTokenReference 汇总共享池全部成员的引用令牌，命中时统一阻断整池删除。
func validateSharedPoolHasNoTokenReference(
	tx *gorm.DB,
	pool *model.ModelQuota,
	members []*model.ModelQuota,
) error {
	if pool == nil {
		return nil
	}
	tokenNames := []string{}
	for _, member := range members {
		memberTokenNames, err := listReferencingTokenNamesByQuota(tx, member)
		if err != nil {
			return err
		}
		tokenNames = append(tokenNames, memberTokenNames...)
	}
	tokenNames = uniqueStrings(tokenNames)
	if len(tokenNames) == 0 {
		return nil
	}
	return fmt.Errorf(
		"共享配额池[%s] 仍被令牌 %s 使用，不能删除共享配额池",
		buildModelQuotaAuditLabel(pool),
		strings.Join(tokenNames, "、"),
	)
}

// validateModelQuotaHasNoTokenReference 读取指定模型配额关联的令牌名称，用于输出阻断原因。
func validateModelQuotaHasNoTokenReference(tx *gorm.DB, quota *model.ModelQuota, actionName string) error {
	tokenNames, err := listReferencingTokenNamesByQuota(tx, quota)
	if err != nil {
		return err
	}
	if len(tokenNames) == 0 {
		return nil
	}
	return fmt.Errorf(
		"%s 仍被令牌 %s 使用，不能%s",
		buildModelQuotaAuditLabel(quota),
		strings.Join(tokenNames, "、"),
		actionName,
	)
}

// listReferencingTokenNamesByQuota 汇总某个模型配额作用域下全部引用令牌名称。
func listReferencingTokenNamesByQuota(tx *gorm.DB, quota *model.ModelQuota) ([]string, error) {
	relationQuotaIDs, err := collectTokenModelQuotaRelationIDs(tx, quota)
	if err != nil {
		return nil, err
	}
	if len(relationQuotaIDs) == 0 {
		return []string{}, nil
	}
	relations, err := model.ListTokenModelQuotaRelationsByModelQuotaIDs(tx, relationQuotaIDs)
	if err != nil {
		return nil, err
	}
	tokenIDs := make([]int, 0, len(relations))
	for _, relation := range relations {
		tokenIDs = append(tokenIDs, relation.TokenID)
	}
	tokens, err := model.GetTokensByIDs(tx, uniquePositiveInts(tokenIDs))
	if err != nil {
		return nil, err
	}
	tokenNames := make([]string, 0, len(tokens))
	for _, token := range tokens {
		if strings.TrimSpace(token.Name) == "" {
			continue
		}
		tokenNames = append(tokenNames, token.Name)
	}
	sort.Strings(tokenNames)
	return tokenNames, nil
}

// validateOptionalPositiveInt 校验可空正整数。
func validateOptionalPositiveInt(fieldName string, value *int) error {
	if value == nil {
		return nil
	}
	if *value < 1 {
		return fmt.Errorf("%s 必须大于等于 1", fieldName)
	}
	return nil
}

// cloneIntPointer 复制 int 指针，避免调用方与持久化对象共享可变引用。
func cloneIntPointer(value *int) *int {
	if value == nil {
		return nil
	}
	cloned := *value
	return &cloned
}

// uniquePositiveInts 过滤非法值并去重，避免重复成员关系导致重复更新。
func uniquePositiveInts(values []int) []int {
	if len(values) == 0 {
		return []int{}
	}
	seen := make(map[int]struct{}, len(values))
	result := make([]int, 0, len(values))
	for _, value := range values {
		if value <= 0 {
			continue
		}
		if _, exists := seen[value]; exists {
			continue
		}
		seen[value] = struct{}{}
		result = append(result, value)
	}
	return result
}

// uniqueStrings 去重并保持结果稳定有序，避免提示文案中出现重复令牌名称。
func uniqueStrings(values []string) []string {
	if len(values) == 0 {
		return []string{}
	}
	seen := make(map[string]struct{}, len(values))
	result := make([]string, 0, len(values))
	for _, value := range values {
		trimmed := strings.TrimSpace(value)
		if trimmed == "" {
			continue
		}
		if _, exists := seen[trimmed]; exists {
			continue
		}
		seen[trimmed] = struct{}{}
		result = append(result, trimmed)
	}
	sort.Strings(result)
	return result
}

// buildModelQuotaCandidateKey 为“分组 + 模型名”候选生成稳定键。
func buildModelQuotaCandidateKey(group string, modelName string) string {
	return model.BuildModelQuotaBusinessKey(group, modelName)
}

// modelQuotaSortWeight 控制页面主列表中的普通项/共享池项排序优先级。
func modelQuotaSortWeight(itemType string) int {
	switch itemType {
	case model.ModelQuotaTypeNormal:
		return 0
	case model.ModelQuotaTypeSharedPool:
		return 1
	default:
		return 2
	}
}
