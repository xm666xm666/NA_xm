package model

import (
	"fmt"
	"strings"

	"github.com/QuantumNous/new-api/common"
	"gorm.io/gorm"
	"gorm.io/gorm/clause"
)

const (
	// ModelQuotaTypeNormal 表示普通模型项。
	ModelQuotaTypeNormal = "normal"
	// ModelQuotaTypeSharedPool 表示共享配额池项。
	ModelQuotaTypeSharedPool = "shared_pool"
	// ModelQuotaTypeSharedPoolMember 表示共享配额池子项。
	ModelQuotaTypeSharedPoolMember = "shared_pool_member"
)

// ModelQuota 承载模型配额页面中的普通项、共享池项与共享池子项。
// 普通项与共享池子项都以“分组 + 模型名”为唯一业务维度持久化。
type ModelQuota struct {
	Id        int    `json:"id"`
	QuotaType string `json:"quota_type" gorm:"size:32;not null;index"`
	Group     string `json:"group,omitempty" gorm:"size:64;index"`
	ModelName string `json:"model_name,omitempty" gorm:"size:255;index"`
	// BusinessKey 仅给普通项和共享池子项填充，避免共享池父项因空分组/模型名互相冲突。
	BusinessKey       *string        `json:"-" gorm:"column:business_key;size:512;uniqueIndex:uk_model_quota_business_key"`
	QuotaName         string         `json:"quota_name" gorm:"size:255;not null;index"`
	SharedPoolID      *int           `json:"shared_pool_id,omitempty" gorm:"index"`
	RPM               *int           `json:"rpm,omitempty"`
	TPM               *int           `json:"tpm,omitempty"`
	Concurrency       *int           `json:"concurrency,omitempty"`
	RemainRPM         *int           `json:"remain_rpm,omitempty"`
	RemainTPM         *int           `json:"remain_tpm,omitempty"`
	RemainConcurrency *int           `json:"remain_concurrency,omitempty"`
	IsAvailable       bool           `json:"is_available" gorm:"default:true;index"`
	CreatedTime       int64          `json:"created_time" gorm:"bigint"`
	UpdatedTime       int64          `json:"updated_time" gorm:"bigint"`
	DeletedAt         gorm.DeletedAt `json:"-" gorm:"index"`
}

// ModelQuotaCandidate 表示从渠道能力中聚合出的“分组 + 模型名”候选。
type ModelQuotaCandidate struct {
	GroupName string `json:"group_name"`
	ModelName string `json:"model_name"`
}

// BuildModelQuotaBusinessKey 为“分组 + 模型名”生成数据库唯一键。
func BuildModelQuotaBusinessKey(group string, modelName string) string {
	// 使用长度编码而不是不可见分隔符，避免 PostgreSQL text 字段拒绝 NUL 字节。
	return fmt.Sprintf("%d:%s%d:%s", len(group), group, len(modelName), modelName)
}

// BeforeSave 确保所有入口写入时都会刷新业务唯一键。
// 这样可以覆盖直接调用 gorm Create 的测试和迁移场景。
func (quota *ModelQuota) BeforeSave(_ *gorm.DB) error {
	quota.refreshBusinessKey()
	return nil
}

// Insert 创建新的模型配额记录。
func (quota *ModelQuota) Insert(tx *gorm.DB) error {
	now := common.GetTimestamp()
	quota.CreatedTime = now
	quota.UpdatedTime = now
	quota.refreshBusinessKey()
	return useModelQuotaDB(tx).Create(quota).Error
}

// InsertIgnoreConflict 创建模型配额记录。
// 当业务唯一键已存在时忽略冲突，供多实例候选同步使用。
func (quota *ModelQuota) InsertIgnoreConflict(tx *gorm.DB) error {
	now := common.GetTimestamp()
	quota.CreatedTime = now
	quota.UpdatedTime = now
	quota.refreshBusinessKey()
	return useModelQuotaDB(tx).
		Clauses(clause.OnConflict{DoNothing: true}).
		Create(quota).Error
}

// Update 更新已有模型配额记录。
func (quota *ModelQuota) Update(tx *gorm.DB) error {
	quota.UpdatedTime = common.GetTimestamp()
	quota.refreshBusinessKey()
	return useModelQuotaDB(tx).
		Model(&ModelQuota{}).
		Where("id = ?", quota.Id).
		Select("*").
		Omit("created_time").
		Updates(quota).Error
}

// ListAllModelQuotas 返回全部模型配额记录。
func ListAllModelQuotas(tx *gorm.DB) ([]*ModelQuota, error) {
	quotas := []*ModelQuota{}
	groupColumn := quotedGroupColumn()
	err := useModelQuotaDB(tx).
		Order(fmt.Sprintf("quota_type ASC, quota_name ASC, %s ASC, model_name ASC, id ASC", groupColumn)).
		Find(&quotas).Error
	return quotas, err
}

// ListCandidateModelQuotas 返回普通模型项与共享池子项，用于候选同步。
func ListCandidateModelQuotas(tx *gorm.DB) ([]*ModelQuota, error) {
	quotas := []*ModelQuota{}
	err := useModelQuotaDB(tx).
		Where("quota_type IN ?", []string{ModelQuotaTypeNormal, ModelQuotaTypeSharedPoolMember}).
		Order("id ASC").
		Find(&quotas).Error
	return quotas, err
}

// GetModelQuotaByID 根据主键读取单条模型配额记录。
func GetModelQuotaByID(tx *gorm.DB, id int) (*ModelQuota, error) {
	quota := &ModelQuota{}
	err := useModelQuotaDB(tx).First(quota, "id = ?", id).Error
	return quota, err
}

// GetModelQuotaByIDForUpdate 加锁读取单条模型配额记录，供额度校验与写入在同一快照内完成。
func GetModelQuotaByIDForUpdate(tx *gorm.DB, id int) (*ModelQuota, error) {
	quota := &ModelQuota{}
	err := useModelQuotaDB(tx).
		Clauses(clause.Locking{Strength: "UPDATE"}).
		First(quota, "id = ?", id).Error
	return quota, err
}

// GetModelQuotasByIDs 批量读取指定 ID 的模型配额记录。
func GetModelQuotasByIDs(tx *gorm.DB, ids []int) ([]*ModelQuota, error) {
	quotas := []*ModelQuota{}
	if len(ids) == 0 {
		return quotas, nil
	}
	err := useModelQuotaDB(tx).Where("id IN ?", ids).Find(&quotas).Error
	return quotas, err
}

// GetModelQuotasByIDsForUpdate 按主键升序加锁读取多条模型配额记录。
// 固定锁顺序可以降低并发额度写入的死锁概率。
func GetModelQuotasByIDsForUpdate(tx *gorm.DB, ids []int) ([]*ModelQuota, error) {
	quotas := []*ModelQuota{}
	if len(ids) == 0 {
		return quotas, nil
	}
	err := useModelQuotaDB(tx).
		Clauses(clause.Locking{Strength: "UPDATE"}).
		Where("id IN ?", ids).
		Order("id ASC").
		Find(&quotas).Error
	return quotas, err
}

// DeleteModelQuotaByID 按主键删除单条模型配额记录。
func DeleteModelQuotaByID(tx *gorm.DB, id int) error {
	if id <= 0 {
		return nil
	}
	db := useModelQuotaDB(tx)
	// 软删除前释放业务唯一键，允许后续候选同步重新创建同一“分组 + 模型名”的账本。
	if err := db.
		Model(&ModelQuota{}).
		Where("id = ?", id).
		Update("business_key", gorm.Expr("NULL")).Error; err != nil {
		return err
	}
	return db.Delete(&ModelQuota{}, "id = ?", id).Error
}

// ListSharedPoolMembers 返回共享池下的全部子项模型。
func ListSharedPoolMembers(tx *gorm.DB, sharedPoolID int) ([]*ModelQuota, error) {
	quotas := []*ModelQuota{}
	groupColumn := quotedGroupColumn()
	err := useModelQuotaDB(tx).
		Where("quota_type = ? AND shared_pool_id = ?", ModelQuotaTypeSharedPoolMember, sharedPoolID).
		Order(fmt.Sprintf("%s ASC, model_name ASC, id ASC", groupColumn)).
		Find(&quotas).Error
	return quotas, err
}

// ListSharedPoolMembersForUpdate 加锁读取共享池子项，供共享池结构调整前做并发保护。
func ListSharedPoolMembersForUpdate(tx *gorm.DB, sharedPoolID int) ([]*ModelQuota, error) {
	quotas := []*ModelQuota{}
	err := useModelQuotaDB(tx).
		Clauses(clause.Locking{Strength: "UPDATE"}).
		Where("quota_type = ? AND shared_pool_id = ?", ModelQuotaTypeSharedPoolMember, sharedPoolID).
		Order("id ASC").
		Find(&quotas).Error
	return quotas, err
}

// ListEnabledModelQuotaCandidates 基于渠道能力聚合出“分组 + 模型名”候选集。
func ListEnabledModelQuotaCandidates(tx *gorm.DB) ([]ModelQuotaCandidate, error) {
	candidates := []ModelQuotaCandidate{}
	groupColumn := quotedGroupColumn()
	err := useModelQuotaDB(tx).
		Table("abilities").
		Select(fmt.Sprintf("%s as group_name, model as model_name", groupColumn)).
		Where("enabled = ?", true).
		Group(fmt.Sprintf("%s, model", groupColumn)).
		Order(fmt.Sprintf("%s ASC, model ASC", groupColumn)).
		Scan(&candidates).Error
	return candidates, err
}

// quotedGroupColumn 返回当前数据库方言下可安全用于 SQL 的 group 列名。
func quotedGroupColumn() string {
	if strings.TrimSpace(commonGroupCol) != "" {
		return commonGroupCol
	}
	if common.UsingPostgreSQL {
		return `"group"`
	}
	return "`group`"
}

// useModelQuotaDB 在有事务时复用事务，没有事务时回落到全局 DB。
func useModelQuotaDB(tx *gorm.DB) *gorm.DB {
	if tx != nil {
		return tx
	}
	return DB
}

// refreshBusinessKey 根据配额类型刷新唯一键。
// 共享池父项不参与“分组 + 模型名”唯一约束。
func (quota *ModelQuota) refreshBusinessKey() {
	if quota == nil {
		return
	}
	if quota.QuotaType != ModelQuotaTypeNormal && quota.QuotaType != ModelQuotaTypeSharedPoolMember {
		quota.BusinessKey = nil
		return
	}
	businessKey := BuildModelQuotaBusinessKey(quota.Group, quota.ModelName)
	quota.BusinessKey = &businessKey
}

// migrateModelQuotaBusinessKeys 为旧数据回填业务唯一键。
// 历史重复项保留为空，避免升级时破坏存量数据。
func migrateModelQuotaBusinessKeys(tx *gorm.DB) error {
	db := useModelQuotaDB(tx)
	if !db.Migrator().HasColumn(&ModelQuota{}, "business_key") {
		return nil
	}
	if err := db.
		Model(&ModelQuota{}).
		Unscoped().
		Where(
			"quota_type NOT IN ? OR deleted_at IS NOT NULL",
			[]string{ModelQuotaTypeNormal, ModelQuotaTypeSharedPoolMember},
		).
		Update("business_key", gorm.Expr("NULL")).Error; err != nil {
		return err
	}

	quotas := []*ModelQuota{}
	if err := db.
		Where("quota_type IN ?", []string{ModelQuotaTypeNormal, ModelQuotaTypeSharedPoolMember}).
		Order("id ASC").
		Find(&quotas).Error; err != nil {
		return err
	}

	seen := make(map[string]struct{}, len(quotas))
	for _, quota := range quotas {
		businessKey := BuildModelQuotaBusinessKey(quota.Group, quota.ModelName)
		if _, exists := seen[businessKey]; exists {
			// 历史重复行不主动合并，留给管理员按实际引用关系处理。
			if quota.BusinessKey == nil {
				continue
			}
			if err := db.
				Model(&ModelQuota{}).
				Where("id = ?", quota.Id).
				Update("business_key", gorm.Expr("NULL")).Error; err != nil {
				return err
			}
			continue
		}
		seen[businessKey] = struct{}{}
		if quota.BusinessKey != nil && *quota.BusinessKey == businessKey {
			continue
		}
		if err := db.
			Model(&ModelQuota{}).
			Where("id = ?", quota.Id).
			Update("business_key", businessKey).Error; err != nil {
			return err
		}
	}
	return nil
}
