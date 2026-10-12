package model

import (
	"errors"
	"fmt"
	"time"

	"gorm.io/gorm/clause"
)

// SessionRevocation 只保存已经退出的会话标识，不保存完整 Cookie 或用户信息。
type SessionRevocation struct {
	SessionID string    `gorm:"primaryKey;type:varchar(64)"`
	ExpiresAt time.Time `gorm:"not null;index"`
}

// RevokeSession 持久化当前会话的撤销状态，使对应 Cookie 无法再次通过鉴权。
func RevokeSession(sessionID string, expiresAt time.Time) error {
	if sessionID == "" {
		return errors.New("session id 不能为空")
	}
	revocation := SessionRevocation{SessionID: sessionID, ExpiresAt: expiresAt}
	if err := DB.Clauses(clause.OnConflict{
		Columns:   []clause.Column{{Name: "session_id"}},
		DoUpdates: clause.AssignmentColumns([]string{"expires_at"}),
	}).Create(&revocation).Error; err != nil {
		return fmt.Errorf("persist session revocation: %w", err)
	}
	return nil
}

// DeleteExpiredSessionRevocations 清理已超过 Cookie 最长有效期的撤销记录。
func DeleteExpiredSessionRevocations() error {
	if err := DB.Where("expires_at <= ?", time.Now()).Delete(&SessionRevocation{}).Error; err != nil {
		return fmt.Errorf("delete expired session revocations: %w", err)
	}
	return nil
}

// IsSessionRevoked 判断会话是否存在尚未过期的撤销记录。
func IsSessionRevoked(sessionID string) (bool, error) {
	if sessionID == "" {
		return false, nil
	}
	var count int64
	err := DB.Model(&SessionRevocation{}).
		Where("session_id = ? AND expires_at > ?", sessionID, time.Now()).
		Count(&count).Error
	if err != nil {
		return false, fmt.Errorf("query session revocation: %w", err)
	}
	return count > 0, nil
}
