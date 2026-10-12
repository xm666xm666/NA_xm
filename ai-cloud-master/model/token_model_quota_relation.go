package model

import (
	"errors"
	"fmt"
	"strings"

	"github.com/QuantumNous/new-api/common"
	"gorm.io/gorm"
)

const tokenModelQuotaRelationUniqueIndexName = "uk_token_model_quota_relation_token_model"

// TokenModelQuotaRelation 保存 token 模型限流规则与模型配额项之间的派生关联。
// 该表是 token_model_rate_limits 的查询索引，不改变 token JSON 作为原始配置源的职责。
type TokenModelQuotaRelation struct {
	Id      int `json:"id"`
	TokenID int `json:"token_id" gorm:"index:idx_token_model_quota_relation_token_id;not null;uniqueIndex:uk_token_model_quota_relation_token_model,priority:1"`
	// ModelName 直接冗余 token 规则里的 model_name，用于落库层唯一约束与精确重建。
	ModelName string `json:"model_name" gorm:"size:255;not null;default:'';index:idx_token_model_quota_relation_model_name;uniqueIndex:uk_token_model_quota_relation_token_model,priority:2"`
	// LedgerModelQuotaID 记录真实余额账本目标；普通项记录自身 ID，共享池场景记录共享池父项 ID。
	LedgerModelQuotaID int `json:"ledger_model_quota_id" gorm:"index:idx_token_model_quota_relation_ledger_model_quota_id"`
	// ModelQuotaID 记录“令牌名 - 限流配置”的展示归属与引用阻断目标。
	// 普通项场景记录自身 ID，共享池场景记录保存时选中的共享池子项 ID。
	ModelQuotaID     int            `json:"model_quota_id" gorm:"index:idx_token_model_quota_relation_model_quota_id;not null"`
	ConcurrencyLimit *int           `json:"concurrency_limit,omitempty"`
	RPMLimit         *int           `json:"rpm_limit,omitempty"`
	TPMLimit         *int           `json:"tpm_limit,omitempty"`
	CreatedTime      int64          `json:"created_time" gorm:"bigint"`
	UpdatedTime      int64          `json:"updated_time" gorm:"bigint"`
	DeletedAt        gorm.DeletedAt `json:"-" gorm:"index"`
}

// ListModelQuotaRecordsByGroupAndModels 按“分组 + 模型名”批量读取普通项和共享池子项。
func ListModelQuotaRecordsByGroupAndModels(tx *gorm.DB, group string, modelNames []string) ([]*ModelQuota, error) {
	quotas := []*ModelQuota{}
	if strings.TrimSpace(group) == "" || len(modelNames) == 0 {
		return quotas, nil
	}
	err := useTokenModelQuotaRelationDB(tx).
		Where(quotedGroupColumn()+" = ?", group).
		Where("model_name IN ?", uniqueNonEmptyStrings(modelNames)).
		Where("quota_type IN ?", []string{ModelQuotaTypeNormal, ModelQuotaTypeSharedPoolMember}).
		Order("id ASC").
		Find(&quotas).Error
	return quotas, err
}

// ListTokenModelQuotaRelationsByModelQuotaIDs 批量读取模型配额项关联的 token 限流记录。
func ListTokenModelQuotaRelationsByModelQuotaIDs(tx *gorm.DB, modelQuotaIDs []int) ([]*TokenModelQuotaRelation, error) {
	relations := []*TokenModelQuotaRelation{}
	if len(modelQuotaIDs) == 0 {
		return relations, nil
	}
	err := useTokenModelQuotaRelationDB(tx).
		Where("model_quota_id IN ?", modelQuotaIDs).
		Order("model_quota_id ASC, token_id ASC, id ASC").
		Find(&relations).Error
	return relations, err
}

// ListTokenModelQuotaRelationsByTokenIDs 批量读取指定 token 当前生效的派生关联。
// 删除与编辑旧账回补会以该结果作为真源，避免受当前模型配额关系变化影响。
func ListTokenModelQuotaRelationsByTokenIDs(tx *gorm.DB, tokenIDs []int) ([]*TokenModelQuotaRelation, error) {
	relations := []*TokenModelQuotaRelation{}
	if len(tokenIDs) == 0 {
		return relations, nil
	}
	err := useTokenModelQuotaRelationDB(tx).
		Where("token_id IN ?", tokenIDs).
		Order("token_id ASC, id ASC").
		Find(&relations).Error
	return relations, err
}

// GetTokensByIDs 批量读取 token 基础信息，供模型配额页面拼装“令牌名 - 限流配置”列。
func GetTokensByIDs(tx *gorm.DB, ids []int) ([]*Token, error) {
	tokens := []*Token{}
	if len(ids) == 0 {
		return tokens, nil
	}
	err := useTokenModelQuotaRelationDB(tx).
		Select("id", "name").
		Where("id IN ?", ids).
		Find(&tokens).Error
	return tokens, err
}

// tokenModelQuotaRuleSelection 描述单条规则最终选中的账本目标与展示归属目标。
type tokenModelQuotaRuleSelection struct {
	LedgerTarget  tokenModelQuotaLedgerTarget
	RelationQuota *ModelQuota
}

// ReplaceTokenModelQuotaRelations 按 token 当前 JSON 配置重建派生关联，保证列表查询读取真实限流数据。
func ReplaceTokenModelQuotaRelations(tx *gorm.DB, token *Token) error {
	if token == nil || token.Id <= 0 {
		return nil
	}
	if err := DeleteTokenModelQuotaRelationsByTokenIDs(tx, []int{token.Id}); err != nil {
		return err
	}

	limitMaps := token.GetTokenModelRateLimits()
	if len(limitMaps) == 0 {
		return nil
	}

	effectiveGroup, err := loadTokenModelQuotaRelationGroup(tx, token)
	if err != nil {
		return err
	}
	if strings.TrimSpace(effectiveGroup) == "" {
		return nil
	}

	now := common.GetTimestamp()
	relations := make([]*TokenModelQuotaRelation, 0, len(limitMaps))
	for _, limitMap := range limitMaps {
		modelName := strings.TrimSpace(getMapString(limitMap, "model_name"))
		if modelName == "" {
			// 兜底跳过无效规则，避免派生表写入空模型名破坏唯一约束。
			continue
		}
		selection, selectionErr := resolveTokenModelQuotaRuleSelection(tx, limitMap)
		if selectionErr != nil {
			return selectionErr
		}
		if err = validateResolvedTokenModelQuotaTarget(effectiveGroup, limitMap, selection); err != nil {
			return err
		}
		if selection.RelationQuota == nil || selection.LedgerTarget.Quota == nil {
			continue
		}
		relations = append(relations, &TokenModelQuotaRelation{
			TokenID:            token.Id,
			ModelName:          modelName,
			LedgerModelQuotaID: selection.LedgerTarget.Quota.Id,
			ModelQuotaID:       selection.RelationQuota.Id,
			// 关联表只接受当前规范字段，避免旧别名继续沉淀进持久化派生数据。
			ConcurrencyLimit: buildEnabledTokenModelQuotaLimitPointer(
				limitMap,
				"concurrency_limit_enabled",
				"concurrency_limit",
			),
			RPMLimit: buildEnabledTokenModelQuotaLimitPointer(
				limitMap,
				"rpm_limit_enabled",
				"rpm_limit",
			),
			TPMLimit: buildEnabledTokenModelQuotaLimitPointer(
				limitMap,
				"tpm_limit_enabled",
				"tpm_limit",
			),
			CreatedTime: now,
			UpdatedTime: now,
		})
	}
	if len(relations) == 0 {
		return nil
	}
	return useTokenModelQuotaRelationDB(tx).Create(&relations).Error
}

// migrateTokenModelQuotaRelationSchema 处理关联表的自定义迁移顺序。
// 旧表升级时必须保留账本归属字段，避免共享池关系变化后回补到错误账本。
func migrateTokenModelQuotaRelationSchema(tx *gorm.DB) error {
	db := useTokenModelQuotaRelationDB(tx)

	if !db.Migrator().HasTable(&TokenModelQuotaRelation{}) {
		return db.AutoMigrate(&TokenModelQuotaRelation{})
	}

	if !db.Migrator().HasColumn(&TokenModelQuotaRelation{}, "model_name") {
		if err := db.Migrator().AddColumn(&TokenModelQuotaRelation{}, "ModelName"); err != nil {
			return err
		}
	}
	if err := backfillTokenModelQuotaRelationModelNames(db); err != nil {
		return err
	}
	return ensureTokenModelQuotaRelationIndexes(db)
}

// backfillTokenModelQuotaRelationModelNames 为旧关联表补齐 model_name，并在历史重复项上生成稳定兜底名。
func backfillTokenModelQuotaRelationModelNames(tx *gorm.DB) error {
	db := useTokenModelQuotaRelationDB(tx)

	relations := make([]TokenModelQuotaRelation, 0)
	if err := db.Unscoped().
		Order("token_id ASC, id ASC").
		Find(&relations).Error; err != nil {
		return err
	}

	seenByTokenID := make(map[int]map[string]struct{})
	for _, relation := range relations {
		modelName, err := legacyTokenModelQuotaRelationModelName(db, &relation)
		if err != nil {
			return err
		}
		modelName = uniqueLegacyTokenModelQuotaRelationModelName(
			seenByTokenID,
			relation.TokenID,
			relation.Id,
			modelName,
		)
		if strings.TrimSpace(relation.ModelName) == modelName {
			continue
		}
		if err = db.Unscoped().
			Model(&TokenModelQuotaRelation{}).
			Where("id = ?", relation.Id).
			Update("model_name", modelName).Error; err != nil {
			return fmt.Errorf("回填旧关联表模型名失败，relation_id=%d: %w", relation.Id, err)
		}
	}
	return nil
}

// ensureTokenModelQuotaRelationIndexes 为非破坏式升级后的旧表补齐关键查询索引与唯一约束。
func ensureTokenModelQuotaRelationIndexes(tx *gorm.DB) error {
	db := useTokenModelQuotaRelationDB(tx)
	indexNames := []string{
		"idx_token_model_quota_relation_token_id",
		"idx_token_model_quota_relation_model_name",
		"idx_token_model_quota_relation_ledger_model_quota_id",
		"idx_token_model_quota_relation_model_quota_id",
		tokenModelQuotaRelationUniqueIndexName,
	}
	for _, indexName := range indexNames {
		if db.Migrator().HasIndex(&TokenModelQuotaRelation{}, indexName) {
			continue
		}
		if err := db.Migrator().CreateIndex(&TokenModelQuotaRelation{}, indexName); err != nil {
			return fmt.Errorf("补齐旧关联表索引失败，index=%s: %w", indexName, err)
		}
	}
	return nil
}

// legacyTokenModelQuotaRelationModelName 尽量从旧 relation 指向的模型项或 token JSON 中恢复模型名。
func legacyTokenModelQuotaRelationModelName(tx *gorm.DB, relation *TokenModelQuotaRelation) (string, error) {
	if relation == nil {
		return "", nil
	}
	if modelName := strings.TrimSpace(relation.ModelName); modelName != "" {
		return modelName, nil
	}
	modelName, err := legacyTokenModelQuotaRelationModelNameFromQuota(tx, relation.ModelQuotaID)
	if err != nil {
		return "", err
	}
	if modelName != "" {
		return modelName, nil
	}
	modelName, err = legacyTokenModelQuotaRelationModelNameFromToken(tx, relation)
	if err != nil {
		return "", err
	}
	if modelName != "" {
		return modelName, nil
	}
	return fallbackLegacyTokenModelQuotaRelationModelName(relation.Id, 0), nil
}

// legacyTokenModelQuotaRelationModelNameFromQuota 从历史展示归属模型项恢复模型名。
func legacyTokenModelQuotaRelationModelNameFromQuota(tx *gorm.DB, modelQuotaID int) (string, error) {
	if modelQuotaID <= 0 {
		return "", nil
	}
	quota := &ModelQuota{}
	err := useTokenModelQuotaRelationDB(tx).
		Unscoped().
		Select("model_name").
		First(quota, "id = ?", modelQuotaID).Error
	if errors.Is(err, gorm.ErrRecordNotFound) {
		return "", nil
	}
	if err != nil {
		return "", fmt.Errorf("读取旧关联模型配额失败，model_quota_id=%d: %w", modelQuotaID, err)
	}
	return strings.TrimSpace(quota.ModelName), nil
}

// legacyTokenModelQuotaRelationModelNameFromToken 从 token JSON 中兜底恢复旧 relation 的模型名。
func legacyTokenModelQuotaRelationModelNameFromToken(tx *gorm.DB, relation *TokenModelQuotaRelation) (string, error) {
	if relation == nil || relation.TokenID <= 0 {
		return "", nil
	}
	token := &Token{}
	err := useTokenModelQuotaRelationDB(tx).
		Unscoped().
		Select("id", "token_model_rate_limits").
		First(token, "id = ?", relation.TokenID).Error
	if errors.Is(err, gorm.ErrRecordNotFound) {
		return "", nil
	}
	if err != nil {
		return "", fmt.Errorf("读取旧关联令牌失败，token_id=%d: %w", relation.TokenID, err)
	}
	for _, limitMap := range token.GetTokenModelRateLimits() {
		modelName := strings.TrimSpace(getMapString(limitMap, "model_name"))
		if modelName == "" {
			continue
		}
		if legacyTokenModelQuotaRuleMatchesRelation(limitMap, relation) {
			return modelName, nil
		}
	}
	return "", nil
}

// legacyTokenModelQuotaRuleMatchesRelation 判断旧 token JSON 中的规则是否能对应到当前旧 relation。
func legacyTokenModelQuotaRuleMatchesRelation(limitMap map[string]any, relation *TokenModelQuotaRelation) bool {
	if relation == nil {
		return false
	}
	if modelQuotaID, ok := getMapInt(limitMap, "model_quota_id"); ok && modelQuotaID == relation.ModelQuotaID {
		return true
	}
	if quotaID, ok := getMapInt(limitMap, "quota_id"); ok && quotaID == relation.ModelQuotaID {
		return true
	}
	return legacyTokenModelQuotaRuleLimitsMatchRelation(limitMap, relation)
}

// legacyTokenModelQuotaRuleLimitsMatchRelation 用限流值兜底匹配缺少显式 quota_id 的旧规则。
func legacyTokenModelQuotaRuleLimitsMatchRelation(limitMap map[string]any, relation *TokenModelQuotaRelation) bool {
	if relation == nil {
		return false
	}
	hasComparableLimit := false
	if getMapBool(limitMap, "rpm_limit_enabled") {
		hasComparableLimit = true
		rpmLimit, _ := getMapInt(limitMap, "rpm_limit")
		if relation.RPMLimit == nil || *relation.RPMLimit != rpmLimit {
			return false
		}
	}
	if getMapBool(limitMap, "tpm_limit_enabled") {
		hasComparableLimit = true
		tpmLimit, _ := getMapInt(limitMap, "tpm_limit")
		if relation.TPMLimit == nil || *relation.TPMLimit != tpmLimit {
			return false
		}
	}
	if getMapBool(limitMap, "concurrency_limit_enabled") {
		hasComparableLimit = true
		concurrencyLimit, _ := getMapInt(limitMap, "concurrency_limit")
		if relation.ConcurrencyLimit == nil || *relation.ConcurrencyLimit != concurrencyLimit {
			return false
		}
	}
	return hasComparableLimit
}

// uniqueLegacyTokenModelQuotaRelationModelName 保证迁移后 token_id + model_name 能满足新唯一约束。
func uniqueLegacyTokenModelQuotaRelationModelName(
	seenByTokenID map[int]map[string]struct{},
	tokenID int,
	relationID int,
	modelName string,
) string {
	if strings.TrimSpace(modelName) == "" {
		modelName = fallbackLegacyTokenModelQuotaRelationModelName(relationID, 0)
	}
	if _, exists := seenByTokenID[tokenID]; !exists {
		seenByTokenID[tokenID] = map[string]struct{}{}
	}
	seen := seenByTokenID[tokenID]
	candidate := strings.TrimSpace(modelName)
	suffix := 0
	for {
		if _, exists := seen[candidate]; !exists {
			seen[candidate] = struct{}{}
			return candidate
		}
		suffix++
		candidate = fallbackLegacyTokenModelQuotaRelationModelName(relationID, suffix)
	}
}

// fallbackLegacyTokenModelQuotaRelationModelName 为无法恢复模型名或重复的历史行生成稳定占位名。
func fallbackLegacyTokenModelQuotaRelationModelName(relationID int, suffix int) string {
	if suffix <= 0 {
		return fmt.Sprintf("legacy_relation_%d", relationID)
	}
	return fmt.Sprintf("legacy_relation_%d_%d", relationID, suffix)
}

// resolveTokenModelQuotaRuleSelection 解析单条规则显式选择的账本目标与展示归属目标。
func resolveTokenModelQuotaRuleSelection(
	tx *gorm.DB,
	limitMap map[string]any,
) (tokenModelQuotaRuleSelection, error) {
	if quotaID, ok := getMapInt(limitMap, "quota_id"); ok && quotaID > 0 {
		return resolveExplicitTokenModelQuotaRuleSelection(tx, quotaID, limitMap)
	}
	return tokenModelQuotaRuleSelection{}, fmt.Errorf(
		"模型 %s 的限流规则缺少 quota_id",
		strings.TrimSpace(getMapString(limitMap, "model_name")),
	)
}

// resolveExplicitTokenModelQuotaRuleSelection 处理前端显式传入 quota_id/model_quota_id 的场景。
func resolveExplicitTokenModelQuotaRuleSelection(
	tx *gorm.DB,
	quotaID int,
	limitMap map[string]any,
) (tokenModelQuotaRuleSelection, error) {
	selectedQuota, err := GetModelQuotaByIDForUpdate(tx, quotaID)
	if err != nil {
		return tokenModelQuotaRuleSelection{}, fmt.Errorf(
			"读取关联配额池失败，quota_id=%d: %w",
			quotaID,
			err,
		)
	}
	if selectedQuota.QuotaType == ModelQuotaTypeSharedPoolMember {
		return tokenModelQuotaRuleSelection{}, fmt.Errorf(
			"共享池子项不能作为一级关联配额池，quota_id=%d",
			quotaID,
		)
	}
	if selectedQuota.QuotaType == ModelQuotaTypeSharedPool {
		modelQuotaID, ok := getMapInt(limitMap, "model_quota_id")
		if !ok || modelQuotaID <= 0 {
			return tokenModelQuotaRuleSelection{}, fmt.Errorf(
				"共享配额池[%s] 缺少共享池子项 model_quota_id",
				selectedQuota.QuotaName,
			)
		}
		member, err := lockExplicitSharedPoolMemberForRuleSelection(tx, selectedQuota, modelQuotaID)
		if err != nil {
			return tokenModelQuotaRuleSelection{}, fmt.Errorf(
				"共享池子项不属于当前共享配额池，quota_id=%d model_quota_id=%d: %w",
				quotaID,
				modelQuotaID,
				err,
			)
		}
		return tokenModelQuotaRuleSelection{
			LedgerTarget: tokenModelQuotaLedgerTarget{
				Quota: selectedQuota,
				Label: fmt.Sprintf("共享配额池[%s]", selectedQuota.QuotaName),
			},
			RelationQuota: member,
		}, nil
	}
	return tokenModelQuotaRuleSelection{
		LedgerTarget: tokenModelQuotaLedgerTarget{
			Quota: selectedQuota,
			Label: fmt.Sprintf("模型配额[%s/%s]", selectedQuota.Group, selectedQuota.ModelName),
		},
		RelationQuota: selectedQuota,
	}, nil
}

// lockExplicitSharedPoolMemberForRuleSelection 在父池已锁定后锁定子项，并复验子项仍属于该父池。
func lockExplicitSharedPoolMemberForRuleSelection(
	tx *gorm.DB,
	poolQuota *ModelQuota,
	modelQuotaID int,
) (*ModelQuota, error) {
	if poolQuota == nil || poolQuota.Id <= 0 {
		return nil, fmt.Errorf("共享配额池无效，model_quota_id=%d", modelQuotaID)
	}
	member, err := GetModelQuotaByIDForUpdate(tx, modelQuotaID)
	if err != nil {
		return nil, err
	}
	if member.QuotaType != ModelQuotaTypeSharedPoolMember ||
		member.SharedPoolID == nil ||
		*member.SharedPoolID != poolQuota.Id {
		return nil, fmt.Errorf("共享池子项关系已变更，请重新选择")
	}
	return member, nil
}

// DeleteTokenModelQuotaRelationsByTokenIDs 删除指定 token 的全部派生关联。
// 该表仅作查询索引，因此删除时直接硬删除，避免残留历史记录影响重建。
func DeleteTokenModelQuotaRelationsByTokenIDs(tx *gorm.DB, tokenIDs []int) error {
	if len(tokenIDs) == 0 {
		return nil
	}
	return useTokenModelQuotaRelationDB(tx).
		Unscoped().
		Where("token_id IN ?", tokenIDs).
		Delete(&TokenModelQuotaRelation{}).Error
}

// loadTokenModelQuotaRelationGroup 返回 token 关联模型配额时使用的最终分组。
func loadTokenModelQuotaRelationGroup(tx *gorm.DB, token *Token) (string, error) {
	if token == nil {
		return "", nil
	}
	if strings.TrimSpace(token.Group) != "" {
		return strings.TrimSpace(token.Group), nil
	}
	if token.UserId <= 0 {
		return "", nil
	}
	user := &User{}
	err := useTokenModelQuotaRelationDB(tx).
		Select(quotedGroupColumn()).
		First(user, "id = ?", token.UserId).Error
	if err != nil {
		return "", err
	}
	return strings.TrimSpace(user.Group), nil
}

// buildEnabledTokenModelQuotaLimitPointer 仅在对应维度启用时返回限流值指针。
func buildEnabledTokenModelQuotaLimitPointer(limitMap map[string]any, enabledKey string, valueKeys ...string) *int {
	if !getMapBool(limitMap, enabledKey) {
		return nil
	}
	value, ok := getMapInt(limitMap, valueKeys...)
	if !ok || value < 1 {
		return nil
	}
	cloned := value
	return &cloned
}

// uniqueNonEmptyStrings 去除空字符串和重复值，避免生成无效 IN 条件。
func uniqueNonEmptyStrings(values []string) []string {
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
	return result
}

// useTokenModelQuotaRelationDB 在有事务时复用事务，没有事务时回落到全局 DB。
func useTokenModelQuotaRelationDB(tx *gorm.DB) *gorm.DB {
	if tx != nil {
		return tx
	}
	return DB
}
