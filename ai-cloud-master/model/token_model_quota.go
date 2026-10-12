package model

import (
	"errors"
	"fmt"
	"sort"
	"strings"

	"github.com/QuantumNous/new-api/common"
	"gorm.io/gorm"
	"gorm.io/gorm/clause"
)

var (
	// tokenModelQuotaLedgerOrderHook 允许测试观测一次账本更新实际采用的加锁顺序。
	// 正常运行时保持为 nil，不参与业务逻辑。
	tokenModelQuotaLedgerOrderHook func([]int) error
)

// tokenModelQuotaDelta 表示单个模型配额账本的三维额度变化量。
// 正数表示需要额外扣减，负数表示需要回补。
type tokenModelQuotaDelta struct {
	RPM         int
	TPM         int
	Concurrency int
}

// isZero 返回当前差量是否不涉及任何额度维度。
func (delta tokenModelQuotaDelta) isZero() bool {
	return delta.RPM == 0 && delta.TPM == 0 && delta.Concurrency == 0
}

// subtract 计算“新配置 - 旧配置”的差量，便于后续统一扣减或回补。
func (delta tokenModelQuotaDelta) subtract(previous tokenModelQuotaDelta) tokenModelQuotaDelta {
	return tokenModelQuotaDelta{
		RPM:         delta.RPM - previous.RPM,
		TPM:         delta.TPM - previous.TPM,
		Concurrency: delta.Concurrency - previous.Concurrency,
	}
}

// tokenModelQuotaLedgerTarget 描述一条规则实际命中的模型配额账本。
// 当模型属于共享池子项时，账本目标会提升为共享池父项。
type tokenModelQuotaLedgerTarget struct {
	Quota *ModelQuota
	Label string
}

// TokenModelQuotaCapability 描述某个模型在当前分组下可用于令牌模型限流的维度能力。
type TokenModelQuotaCapability struct {
	ModelName             string `json:"model_name"`
	RPMConfigured         bool   `json:"rpm_configured"`
	TPMConfigured         bool   `json:"tpm_configured"`
	ConcurrencyConfigured bool   `json:"concurrency_configured"`
}

// TokenModelQuotaCandidate 描述令牌编辑页一级“关联配额池”选择框的候选项。
type TokenModelQuotaCandidate struct {
	QuotaID           int                              `json:"quota_id"`
	QuotaType         string                           `json:"quota_type"`
	Group             string                           `json:"group,omitempty"`
	ModelName         string                           `json:"model_name,omitempty"`
	QuotaName         string                           `json:"quota_name"`
	RPM               *int                             `json:"rpm,omitempty"`
	TPM               *int                             `json:"tpm,omitempty"`
	Concurrency       *int                             `json:"concurrency,omitempty"`
	RemainRPM         *int                             `json:"remain_rpm,omitempty"`
	RemainTPM         *int                             `json:"remain_tpm,omitempty"`
	RemainConcurrency *int                             `json:"remain_concurrency,omitempty"`
	Members           []TokenModelQuotaCandidateMember `json:"members,omitempty"`
}

// TokenModelQuotaCandidateMember 描述共享配额池二级“共享池子项模型”选择框的候选项。
type TokenModelQuotaCandidateMember struct {
	ModelQuotaID int    `json:"model_quota_id"`
	Group        string `json:"group,omitempty"`
	ModelName    string `json:"model_name"`
}

// getTokenForUpdate 在更新令牌前加锁读取旧值，保证差量计算与写入处于同一事务。
func getTokenForUpdate(tx *gorm.DB, tokenID int) (*Token, error) {
	if tokenID <= 0 {
		return nil, errors.New("token id 不能为空")
	}
	token := &Token{}
	err := tx.Clauses(clause.Locking{Strength: "UPDATE"}).
		First(token, "id = ?", tokenID).Error
	if err != nil {
		return nil, err
	}
	token.NormalizeTokenModelRateLimits()
	return token, nil
}

// getTokenForDelete 在删除令牌前尽量补全令牌字段，避免回补时丢失旧配置。
func getTokenForDelete(tx *gorm.DB, token *Token) (*Token, error) {
	if token == nil {
		return nil, errors.New("token 不能为空")
	}
	if token.Id <= 0 {
		return token, nil
	}
	currentToken, err := getTokenForUpdate(tx, token.Id)
	if err != nil {
		return nil, err
	}
	// 删除后缓存清理仍依赖调用方持有的 key，这里同步回当前对象。
	token.Key = currentToken.Key
	return currentToken, nil
}

// applyTokenModelQuotaLedger 基于旧令牌与新令牌的差异，原子更新模型配额账本。
func applyTokenModelQuotaLedger(tx *gorm.DB, previousToken *Token, nextToken *Token) error {
	// 旧账本优先以派生关系表为真源，避免删除/切池时被当前模型配额关系错误重算。
	previousLedger, previousTargets, err := buildPreviousTokenModelQuotaLedgerMap(tx, previousToken)
	if err != nil {
		return err
	}
	nextLedger, nextTargets, err := buildTokenModelQuotaLedgerMap(tx, nextToken)
	if err != nil {
		return err
	}

	ledgerTargets := map[int]tokenModelQuotaLedgerTarget{}
	for quotaID, target := range previousTargets {
		ledgerTargets[quotaID] = target
	}
	for quotaID, target := range nextTargets {
		ledgerTargets[quotaID] = target
	}

	ledgerIDs := make([]int, 0, len(ledgerTargets))
	for quotaID := range ledgerTargets {
		ledgerIDs = append(ledgerIDs, quotaID)
	}
	sort.Ints(ledgerIDs)
	if tokenModelQuotaLedgerOrderHook != nil {
		// 复制一份切片，避免测试方意外修改当前事务内的排序结果。
		orderedIDs := append([]int(nil), ledgerIDs...)
		if hookErr := tokenModelQuotaLedgerOrderHook(orderedIDs); hookErr != nil {
			return hookErr
		}
	}

	for _, quotaID := range ledgerIDs {
		delta := nextLedger[quotaID].subtract(previousLedger[quotaID])
		if delta.isZero() {
			continue
		}
		target := ledgerTargets[quotaID]
		if err = applyModelQuotaRemainDelta(tx, target, delta); err != nil {
			return err
		}
	}
	return nil
}

// buildPreviousTokenModelQuotaLedgerMap 为已落库 token 构建“旧账本占用”映射。
// 对更新/删除场景，必须优先使用 token_model_quota_relations 中已保存的账本归属，
// 避免模型配额关系变化后，旧账被按当前关系重算到错误账本。
func buildPreviousTokenModelQuotaLedgerMap(
	tx *gorm.DB,
	token *Token,
) (map[int]tokenModelQuotaDelta, map[int]tokenModelQuotaLedgerTarget, error) {
	if token == nil {
		return map[int]tokenModelQuotaDelta{}, map[int]tokenModelQuotaLedgerTarget{}, nil
	}
	if token.Id <= 0 {
		return buildTokenModelQuotaLedgerMap(tx, token)
	}
	return buildTokenModelQuotaLedgerMapFromRelations(tx, token.Id)
}

// buildTokenModelQuotaLedgerMapFromRelations 按派生关系表聚合 token 已生效的历史账本占用。
// 这里不再依赖当前“分组 + 模型名”映射，确保回补时始终命中保存当时的真实账本。
func buildTokenModelQuotaLedgerMapFromRelations(
	tx *gorm.DB,
	tokenID int,
) (map[int]tokenModelQuotaDelta, map[int]tokenModelQuotaLedgerTarget, error) {
	ledgerMap := map[int]tokenModelQuotaDelta{}
	targets := map[int]tokenModelQuotaLedgerTarget{}
	if tokenID <= 0 {
		return ledgerMap, targets, nil
	}
	relations, err := ListTokenModelQuotaRelationsByTokenIDs(tx, []int{tokenID})
	if err != nil {
		return nil, nil, err
	}
	for _, relation := range relations {
		if relation == nil || relation.LedgerModelQuotaID <= 0 {
			continue
		}
		currentDelta := ledgerMap[relation.LedgerModelQuotaID]
		if relation.RPMLimit != nil {
			currentDelta.RPM += *relation.RPMLimit
		}
		if relation.TPMLimit != nil {
			currentDelta.TPM += *relation.TPMLimit
		}
		if relation.ConcurrencyLimit != nil {
			currentDelta.Concurrency += *relation.ConcurrencyLimit
		}
		ledgerMap[relation.LedgerModelQuotaID] = currentDelta
		targets[relation.LedgerModelQuotaID] = tokenModelQuotaLedgerTarget{
			// 旧账回补只依赖账本主键即可，真实行锁仍由后续更新阶段获取。
			Quota: &ModelQuota{Id: relation.LedgerModelQuotaID},
			Label: buildTokenModelQuotaRelationLedgerLabel(relation),
		}
	}
	return ledgerMap, targets, nil
}

// buildTokenModelQuotaRelationLedgerLabel 为旧账回补生成稳定提示文案，便于定位共享池与普通项。
func buildTokenModelQuotaRelationLedgerLabel(relation *TokenModelQuotaRelation) string {
	if relation == nil {
		return "模型配额账本"
	}
	if relation.ModelQuotaID != relation.LedgerModelQuotaID {
		return fmt.Sprintf("共享配额池账本[%d]", relation.LedgerModelQuotaID)
	}
	return fmt.Sprintf("模型配额账本[%d]", relation.LedgerModelQuotaID)
}

// buildTokenModelQuotaLedgerMap 将令牌中的模型级限流规则聚合成“账本 ID -> 额度占用”映射。
func buildTokenModelQuotaLedgerMap(
	tx *gorm.DB,
	token *Token,
) (map[int]tokenModelQuotaDelta, map[int]tokenModelQuotaLedgerTarget, error) {
	ledgerMap := map[int]tokenModelQuotaDelta{}
	targets := map[int]tokenModelQuotaLedgerTarget{}
	if token == nil {
		return ledgerMap, targets, nil
	}
	effectiveGroup, err := loadTokenModelQuotaRelationGroup(tx, token)
	if err != nil {
		return nil, nil, err
	}
	if effectiveGroup == "" {
		return ledgerMap, targets, nil
	}

	for _, rule := range token.GetTokenModelRateLimits() {
		delta := tokenModelQuotaDelta{}
		if getMapBool(rule, "rpm_limit_enabled") {
			delta.RPM, _ = getMapInt(rule, "rpm_limit")
		}
		if getMapBool(rule, "tpm_limit_enabled") {
			delta.TPM, _ = getMapInt(rule, "tpm_limit")
		}
		if getMapBool(rule, "concurrency_limit_enabled") {
			delta.Concurrency, _ = getMapInt(rule, "concurrency_limit")
		}
		if delta.isZero() {
			continue
		}

		selection, selectionErr := resolveTokenModelQuotaRuleSelection(tx, rule)
		if selectionErr != nil {
			return nil, nil, selectionErr
		}
		if selection.LedgerTarget.Quota == nil {
			return nil, nil, buildMissingTokenModelQuotaTargetError(effectiveGroup, rule)
		}
		currentDelta := ledgerMap[selection.LedgerTarget.Quota.Id]
		ledgerMap[selection.LedgerTarget.Quota.Id] = tokenModelQuotaDelta{
			RPM:         currentDelta.RPM + delta.RPM,
			TPM:         currentDelta.TPM + delta.TPM,
			Concurrency: currentDelta.Concurrency + delta.Concurrency,
		}
		targets[selection.LedgerTarget.Quota.Id] = selection.LedgerTarget
	}

	return ledgerMap, targets, nil
}

// validateTokenModelQuotaDimensionAvailability 校验规则启用的维度在目标模型配额上已配置。
// 共享池子项场景会按共享池父项的额度配置口径做判断。
func validateTokenModelQuotaDimensionAvailability(tx *gorm.DB, token *Token) error {
	if token == nil {
		return nil
	}
	effectiveGroup, err := loadTokenModelQuotaRelationGroup(tx, token)
	if err != nil {
		return err
	}
	if effectiveGroup == "" {
		return nil
	}
	for _, rule := range token.GetTokenModelRateLimits() {
		selection, selectionErr := resolveTokenModelQuotaRuleSelection(tx, rule)
		if selectionErr != nil {
			return selectionErr
		}
		if err = validateResolvedTokenModelQuotaTarget(effectiveGroup, rule, selection); err != nil {
			return err
		}
		if err = validateTokenModelQuotaRuleAgainstTarget(rule, selection.LedgerTarget); err != nil {
			return err
		}
	}
	return nil
}

// validateResolvedTokenModelQuotaTarget 确保启用任一维度的规则一定能命中合法模型配额目标。
func validateResolvedTokenModelQuotaTarget(
	effectiveGroup string,
	rule map[string]any,
	selection tokenModelQuotaRuleSelection,
) error {
	if !tokenModelQuotaRuleHasEnabledDimension(rule) {
		return nil
	}
	if selection.LedgerTarget.Quota != nil && selection.RelationQuota != nil {
		return nil
	}
	return buildMissingTokenModelQuotaTargetError(effectiveGroup, rule)
}

// ListTokenModelQuotaCandidates 返回令牌编辑页关联配额池级联选择所需候选。
// 一级候选仅包含普通模型项与共享配额池项；共享池子项只出现在二级 members 中。
func ListTokenModelQuotaCandidates(tx *gorm.DB, group string, modelName string) ([]TokenModelQuotaCandidate, error) {
	candidates := []TokenModelQuotaCandidate{}
	trimmedModelName := strings.TrimSpace(modelName)
	if trimmedModelName == "" {
		return candidates, nil
	}
	trimmedGroup := strings.TrimSpace(group)
	normalQuotas := []*ModelQuota{}
	if err := useModelQuotaDB(tx).
		Where("quota_type = ?", ModelQuotaTypeNormal).
		Order(quotedGroupColumn() + " ASC, id ASC").
		Find(&normalQuotas).Error; err != nil {
		return nil, err
	}
	for _, quota := range normalQuotas {
		candidates = append(candidates, buildTokenModelQuotaCandidate(quota, nil))
	}

	allMembers := []*ModelQuota{}
	if err := useModelQuotaDB(tx).
		Where("quota_type = ?", ModelQuotaTypeSharedPoolMember).
		Order("shared_pool_id ASC, id ASC").
		Find(&allMembers).Error; err != nil {
		return nil, err
	}
	poolIDSet := make(map[int]struct{}, len(allMembers))
	memberByPoolID := make(map[int][]*ModelQuota)
	poolMatchWeight := make(map[int]int)
	for _, member := range allMembers {
		if member.SharedPoolID == nil {
			continue
		}
		poolID := *member.SharedPoolID
		poolIDSet[poolID] = struct{}{}
		memberByPoolID[poolID] = append(memberByPoolID[poolID], member)
		weight := tokenModelQuotaCandidateMatchWeight(member, trimmedGroup, trimmedModelName)
		currentWeight, exists := poolMatchWeight[poolID]
		if !exists || weight < currentWeight {
			poolMatchWeight[poolID] = weight
		}
	}
	if len(poolIDSet) == 0 {
		sortTokenModelQuotaCandidates(candidates, trimmedGroup, trimmedModelName, poolMatchWeight)
		return candidates, nil
	}
	poolIDs := make([]int, 0, len(poolIDSet))
	for poolID := range poolIDSet {
		poolIDs = append(poolIDs, poolID)
	}
	sort.Ints(poolIDs)
	pools := []*ModelQuota{}
	if err := useModelQuotaDB(tx).
		Where("id IN ? AND quota_type = ?", poolIDs, ModelQuotaTypeSharedPool).
		Order("id ASC").
		Find(&pools).Error; err != nil {
		return nil, err
	}
	for _, pool := range pools {
		candidates = append(candidates, buildTokenModelQuotaCandidate(pool, memberByPoolID[pool.Id]))
	}
	sortTokenModelQuotaCandidates(candidates, trimmedGroup, trimmedModelName, poolMatchWeight)
	return candidates, nil
}

// tokenModelQuotaCandidateMatchWeight 将当前模型/分组命中的候选排在前面，保留手动选择其它候选的能力。
func tokenModelQuotaCandidateMatchWeight(quota *ModelQuota, group string, modelName string) int {
	if quota == nil || strings.TrimSpace(quota.ModelName) != modelName {
		return 2
	}
	if strings.TrimSpace(group) != "" && strings.TrimSpace(quota.Group) == group {
		return 0
	}
	if strings.TrimSpace(group) == "" {
		return 0
	}
	return 1
}

// sortTokenModelQuotaCandidates 按当前分组/模型匹配度、候选类型和 id 稳定排序候选列表。
func sortTokenModelQuotaCandidates(candidates []TokenModelQuotaCandidate, group string, modelName string, poolMatchWeight map[int]int) {
	sort.SliceStable(candidates, func(i int, j int) bool {
		leftWeight := tokenModelQuotaCandidateWeight(candidates[i], group, modelName, poolMatchWeight)
		rightWeight := tokenModelQuotaCandidateWeight(candidates[j], group, modelName, poolMatchWeight)
		if leftWeight != rightWeight {
			return leftWeight < rightWeight
		}
		if candidates[i].QuotaType != candidates[j].QuotaType {
			return tokenModelQuotaCandidateTypeWeight(candidates[i].QuotaType) <
				tokenModelQuotaCandidateTypeWeight(candidates[j].QuotaType)
		}
		return candidates[i].QuotaID < candidates[j].QuotaID
	})
}

// tokenModelQuotaCandidateWeight 计算普通项或共享池在当前模型下的匹配优先级。
func tokenModelQuotaCandidateWeight(candidate TokenModelQuotaCandidate, group string, modelName string, poolMatchWeight map[int]int) int {
	if candidate.QuotaType == ModelQuotaTypeSharedPool {
		if weight, exists := poolMatchWeight[candidate.QuotaID]; exists {
			return weight
		}
		return 2
	}
	return tokenModelQuotaCandidateMatchWeight(&ModelQuota{
		Group:     candidate.Group,
		ModelName: candidate.ModelName,
	}, group, modelName)
}

// tokenModelQuotaCandidateTypeWeight 在匹配度相同时优先返回普通模型项，再返回共享池。
func tokenModelQuotaCandidateTypeWeight(quotaType string) int {
	if quotaType == ModelQuotaTypeNormal {
		return 0
	}
	return 1
}

// ListTokenModelQuotaCapabilities 按分组返回各模型可用于令牌模型限流的额度维度配置状态。
// 共享池子项会继承共享池父项的额度配置能力。
func ListTokenModelQuotaCapabilities(tx *gorm.DB, group string) ([]TokenModelQuotaCapability, error) {
	capabilities := []TokenModelQuotaCapability{}
	trimmedGroup := strings.TrimSpace(group)
	if trimmedGroup == "" {
		return capabilities, nil
	}
	quotas := []*ModelQuota{}
	err := useModelQuotaDB(tx).
		Where(quotedGroupColumn()+" = ?", trimmedGroup).
		Where("quota_type IN ?", []string{ModelQuotaTypeNormal, ModelQuotaTypeSharedPoolMember}).
		Order("model_name ASC, id ASC").
		Find(&quotas).Error
	if err != nil {
		return nil, err
	}
	seenModelNames := make(map[string]struct{}, len(quotas))
	for _, quota := range quotas {
		modelName := strings.TrimSpace(quota.ModelName)
		if modelName == "" {
			continue
		}
		if _, exists := seenModelNames[modelName]; exists {
			continue
		}
		targetQuota, targetErr := findTokenModelQuotaCapabilityTarget(tx, quota)
		if targetErr != nil {
			return nil, targetErr
		}
		seenModelNames[modelName] = struct{}{}
		capabilities = append(capabilities, TokenModelQuotaCapability{
			ModelName:             modelName,
			RPMConfigured:         targetQuota != nil && targetQuota.RPM != nil,
			TPMConfigured:         targetQuota != nil && targetQuota.TPM != nil,
			ConcurrencyConfigured: targetQuota != nil && targetQuota.Concurrency != nil,
		})
	}
	return capabilities, nil
}

// findTokenModelQuotaCapabilityTarget 为前端能力查询解析实际生效的额度配置目标。
func findTokenModelQuotaCapabilityTarget(tx *gorm.DB, quota *ModelQuota) (*ModelQuota, error) {
	if quota == nil {
		return nil, nil
	}
	if quota.QuotaType != ModelQuotaTypeSharedPoolMember {
		return quota, nil
	}
	if quota.SharedPoolID == nil {
		return nil, fmt.Errorf("共享池子项缺少共享池关联，group=%s model=%s", quota.Group, quota.ModelName)
	}
	poolQuota := &ModelQuota{}
	err := useModelQuotaDB(tx).First(poolQuota, "id = ?", *quota.SharedPoolID).Error
	if err != nil {
		return nil, err
	}
	return poolQuota, nil
}

// validateTokenModelQuotaRuleAgainstTarget 逐维校验当前规则是否引用了未配置的额度维度。
func validateTokenModelQuotaRuleAgainstTarget(
	rule map[string]any,
	target tokenModelQuotaLedgerTarget,
) error {
	if target.Quota == nil {
		return nil
	}
	modelName := strings.TrimSpace(getMapString(rule, "model_name"))
	if getMapBool(rule, "rpm_limit_enabled") && target.Quota.RPM == nil {
		return fmt.Errorf("模型 %s 关联的%s未配置 RPM，不能启用 RPM 限流", modelName, target.Label)
	}
	if getMapBool(rule, "tpm_limit_enabled") && target.Quota.TPM == nil {
		return fmt.Errorf("模型 %s 关联的%s未配置 TPM，不能启用 TPM 限流", modelName, target.Label)
	}
	if getMapBool(rule, "concurrency_limit_enabled") && target.Quota.Concurrency == nil {
		return fmt.Errorf("模型 %s 关联的%s未配置并发上限，不能启用并发限流", modelName, target.Label)
	}
	return nil
}

// tokenModelQuotaRuleHasEnabledDimension 判断当前规则是否至少启用了一个限流维度。
func tokenModelQuotaRuleHasEnabledDimension(rule map[string]any) bool {
	return getMapBool(rule, "rpm_limit_enabled") ||
		getMapBool(rule, "tpm_limit_enabled") ||
		getMapBool(rule, "concurrency_limit_enabled")
}

// buildMissingTokenModelQuotaTargetError 统一返回“规则启用但未命中合法模型配额目标”的保存错误。
func buildMissingTokenModelQuotaTargetError(effectiveGroup string, rule map[string]any) error {
	modelName := strings.TrimSpace(getMapString(rule, "model_name"))
	if strings.TrimSpace(effectiveGroup) == "" {
		return fmt.Errorf("模型 %s 未解析到有效分组，不能启用 token 模型限流", modelName)
	}
	return fmt.Errorf(
		"模型 %s 在分组 %s 下未匹配到合法模型配额目标，不能启用 token 模型限流",
		modelName,
		effectiveGroup,
	)
}

// buildTokenModelQuotaCandidate 将模型配额记录整理为前端级联选择候选。
func buildTokenModelQuotaCandidate(quota *ModelQuota, members []*ModelQuota) TokenModelQuotaCandidate {
	candidate := TokenModelQuotaCandidate{
		QuotaID:           quota.Id,
		QuotaType:         quota.QuotaType,
		Group:             quota.Group,
		ModelName:         quota.ModelName,
		QuotaName:         quota.QuotaName,
		RPM:               cloneTokenModelQuotaIntPointer(quota.RPM),
		TPM:               cloneTokenModelQuotaIntPointer(quota.TPM),
		Concurrency:       cloneTokenModelQuotaIntPointer(quota.Concurrency),
		RemainRPM:         cloneTokenModelQuotaIntPointer(quota.RemainRPM),
		RemainTPM:         cloneTokenModelQuotaIntPointer(quota.RemainTPM),
		RemainConcurrency: cloneTokenModelQuotaIntPointer(quota.RemainConcurrency),
		Members:           []TokenModelQuotaCandidateMember{},
	}
	for _, member := range members {
		candidate.Members = append(candidate.Members, TokenModelQuotaCandidateMember{
			ModelQuotaID: member.Id,
			Group:        member.Group,
			ModelName:    member.ModelName,
		})
	}
	return candidate
}

// cloneTokenModelQuotaIntPointer 复制可空整数字段，避免调用方误改原始模型对象。
func cloneTokenModelQuotaIntPointer(value *int) *int {
	if value == nil {
		return nil
	}
	cloned := *value
	return &cloned
}

// applyModelQuotaRemainDelta 对单个模型配额账本执行扣减或回补，并保持 updated_time 同步更新。
func applyModelQuotaRemainDelta(
	tx *gorm.DB,
	target tokenModelQuotaLedgerTarget,
	delta tokenModelQuotaDelta,
) error {
	if target.Quota == nil || delta.isZero() {
		return nil
	}
	// 在事务内锁定当前账本行，避免并发提交基于过期剩余额度重复分配。
	lockedQuota, err := getModelQuotaForLedgerUpdate(tx, target.Quota.Id)
	if err != nil {
		return fmt.Errorf("%s 加锁失败: %w", target.Label, err)
	}

	updates := map[string]any{
		"updated_time": common.GetTimestamp(),
	}
	if err := appendModelQuotaRemainDelta(
		updates,
		target.Label,
		"剩余 RPM",
		"remain_rpm",
		lockedQuota.RemainRPM,
		delta.RPM,
	); err != nil {
		return err
	}
	if err := appendModelQuotaRemainDelta(
		updates,
		target.Label,
		"剩余 TPM",
		"remain_tpm",
		lockedQuota.RemainTPM,
		delta.TPM,
	); err != nil {
		return err
	}
	if err := appendModelQuotaRemainDelta(
		updates,
		target.Label,
		"剩余并发",
		"remain_concurrency",
		lockedQuota.RemainConcurrency,
		delta.Concurrency,
	); err != nil {
		return err
	}
	if len(updates) == 1 {
		return nil
	}
	return useModelQuotaDB(tx).
		Model(&ModelQuota{}).
		Where("id = ?", target.Quota.Id).
		Updates(updates).Error
}

// getModelQuotaForLedgerUpdate 在账本更新前锁定目标模型配额行，保证校验与写入看到同一份最新余额。
func getModelQuotaForLedgerUpdate(tx *gorm.DB, quotaID int) (*ModelQuota, error) {
	if quotaID <= 0 {
		return nil, errors.New("model quota id 不能为空")
	}
	quota := &ModelQuota{}
	err := useModelQuotaDB(tx).
		Clauses(clause.Locking{Strength: "UPDATE"}).
		First(quota, "id = ?", quotaID).Error
	if err != nil {
		return nil, err
	}
	return quota, nil
}

// appendModelQuotaRemainDelta 统一处理单个剩余额度字段的扣减/回补表达式构建与边界校验。
func appendModelQuotaRemainDelta(
	updates map[string]any,
	targetLabel string,
	fieldLabel string,
	columnName string,
	currentValue *int,
	delta int,
) error {
	if delta == 0 {
		return nil
	}
	if delta > 0 {
		if currentValue == nil {
			return fmt.Errorf("%s 未配置%s，无法分配", targetLabel, fieldLabel)
		}
		if *currentValue < delta {
			return fmt.Errorf("%s 的%s不足，当前=%d，需分配=%d", targetLabel, fieldLabel, *currentValue, delta)
		}
		updates[columnName] = gorm.Expr(columnName+" - ?", delta)
		return nil
	}
	if currentValue == nil {
		return nil
	}
	updates[columnName] = gorm.Expr(columnName+" + ?", -delta)
	return nil
}
