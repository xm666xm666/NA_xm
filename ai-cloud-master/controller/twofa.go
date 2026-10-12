package controller

import (
	"errors"
	"fmt"
	"net/http"
	"strconv"

	"github.com/QuantumNous/new-api/common"
	"github.com/QuantumNous/new-api/model"

	"github.com/gin-contrib/sessions"
	"github.com/gin-gonic/gin"
)

// Setup2FARequest 设置2FA请求结构
type Setup2FARequest struct {
	Code string `json:"code" binding:"required"`
}

// Verify2FARequest 验证2FA请求结构
type Verify2FARequest struct {
	Code string `json:"code" binding:"required"`
}

// Setup2FAResponse 设置2FA响应结构
type Setup2FAResponse struct {
	Secret      string   `json:"secret"`
	QRCodeData  string   `json:"qr_code_data"`
	BackupCodes []string `json:"backup_codes"`
}

// pendingUserID 只接受密码登录流程写入的正整数用户 ID。
func pendingUserID(value any) (int, error) {
	userId, ok := value.(int)
	if !ok || userId <= 0 {
		return 0, errors.New("会话已过期，请重新登录")
	}
	return userId, nil
}

// requirePendingUserID 从服务端 session 读取待验证用户，拒绝客户端指定身份。
func requirePendingUserID(c *gin.Context) (int, bool) {
	userId, err := pendingUserID(sessions.Default(c).Get("pending_user_id"))
	if err != nil {
		c.JSON(http.StatusOK, gin.H{
			"success": false,
			"message": err.Error(),
		})
		return 0, false
	}
	return userId, true
}

// completePendingLogin 仅在 MFA 成功后创建隔离的正式会话。
func completePendingLogin(c *gin.Context, user *model.User) {
	setupLogin(user, c)
}

// Setup2FA 初始化2FA设置
func Setup2FA(c *gin.Context) {
	userId, ok := requirePendingUserID(c)
	if !ok {
		return
	}

	// 检查用户是否已经启用2FA
	existing, err := model.GetTwoFAByUserId(userId)
	if err != nil {
		common.ApiError(c, err)
		return
	}
	if existing != nil && existing.IsEnabled {
		c.JSON(http.StatusOK, gin.H{
			"success": false,
			"message": "用户已绑定 MFA，请完成验证码验证",
		})
		return
	}

	// 如果存在已禁用的2FA记录，先删除它
	if existing != nil && !existing.IsEnabled {
		if err := existing.Delete(); err != nil {
			common.ApiError(c, err)
			return
		}
		existing = nil // 重置为nil，后续将创建新记录
	}

	// 获取用户信息
	user, err := model.GetUserById(userId, false)
	if err != nil {
		common.ApiError(c, err)
		return
	}

	// 生成TOTP密钥
	key, err := common.GenerateTOTPSecret(user.Username)
	if err != nil {
		c.JSON(http.StatusOK, gin.H{
			"success": false,
			"message": "生成2FA密钥失败",
		})
		common.SysLog("生成TOTP密钥失败: " + err.Error())
		return
	}

	// 生成备用码
	backupCodes, err := common.GenerateBackupCodes()
	if err != nil {
		c.JSON(http.StatusOK, gin.H{
			"success": false,
			"message": "生成备用码失败",
		})
		common.SysLog("生成备用码失败: " + err.Error())
		return
	}

	// 生成二维码数据
	qrCodeData := common.GenerateQRCodeData(key.Secret(), user.Username)

	// 创建或更新2FA记录（暂未启用）
	twoFA := &model.TwoFA{
		UserId:    userId,
		Secret:    key.Secret(),
		IsEnabled: false,
	}

	if existing != nil {
		// 更新现有记录
		twoFA.Id = existing.Id
		err = twoFA.Update()
	} else {
		// 创建新记录
		err = twoFA.Create()
	}

	if err != nil {
		common.ApiError(c, err)
		return
	}

	// 创建备用码记录
	if err := model.CreateBackupCodes(userId, backupCodes); err != nil {
		c.JSON(http.StatusOK, gin.H{
			"success": false,
			"message": "保存备用码失败",
		})
		common.SysLog("保存备用码失败: " + err.Error())
		return
	}

	// 记录操作日志
	model.RecordLog(userId, model.LogTypeSystem, "开始设置两步验证")

	c.JSON(http.StatusOK, gin.H{
		"success": true,
		"message": "2FA设置初始化成功，请使用认证器扫描二维码并输入验证码完成设置",
		"data": Setup2FAResponse{
			Secret:      key.Secret(),
			QRCodeData:  qrCodeData,
			BackupCodes: backupCodes,
		},
	})
}

// Enable2FA 启用2FA
func Enable2FA(c *gin.Context) {
	var req Setup2FARequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusOK, gin.H{
			"success": false,
			"message": "参数错误",
		})
		return
	}

	userId, ok := requirePendingUserID(c)
	if !ok {
		return
	}

	// 获取2FA记录
	twoFA, err := model.GetTwoFAByUserId(userId)
	if err != nil {
		common.ApiError(c, err)
		return
	}
	if twoFA == nil {
		c.JSON(http.StatusOK, gin.H{
			"success": false,
			"message": "请先完成2FA初始化设置",
		})
		return
	}
	if twoFA.IsEnabled {
		c.JSON(http.StatusOK, gin.H{
			"success": false,
			"message": "2FA已经启用",
		})
		return
	}

	// 验证TOTP验证码
	cleanCode, err := common.ValidateNumericCode(req.Code)
	if err != nil {
		c.JSON(http.StatusOK, gin.H{
			"success": false,
			"message": err.Error(),
		})
		return
	}

	if !common.ValidateTOTPCode(twoFA.Secret, cleanCode) {
		c.JSON(http.StatusOK, gin.H{
			"success": false,
			"message": "验证码或备用码错误，请重试",
		})
		return
	}

	// 启用2FA
	if err := twoFA.Enable(); err != nil {
		common.ApiError(c, err)
		return
	}

	// 记录操作日志
	model.RecordLog(userId, model.LogTypeSystem, "成功启用两步验证")

	// 首次绑定成功后直接完成本次密码登录，用户无法停留在半登录状态。
	user, err := model.GetUserById(userId, false)
	if err != nil {
		common.ApiError(c, err)
		return
	}
	completePendingLogin(c, user)
}

// Get2FAStatus 获取用户2FA状态
func Get2FAStatus(c *gin.Context) {
	userId := c.GetInt("id")

	twoFA, err := model.GetTwoFAByUserId(userId)
	if err != nil {
		common.ApiError(c, err)
		return
	}

	status := map[string]interface{}{
		"enabled": false,
		"locked":  false,
	}

	if twoFA != nil {
		status["enabled"] = twoFA.IsEnabled
		status["locked"] = twoFA.IsLocked()
	}

	c.JSON(http.StatusOK, gin.H{
		"success": true,
		"message": "",
		"data":    status,
	})
}

// Verify2FALogin 登录时验证2FA
func Verify2FALogin(c *gin.Context) {
	var req Verify2FARequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusOK, gin.H{
			"success": false,
			"message": "参数错误",
		})
		return
	}

	// 从服务端 session 获取 pending 用户，禁止请求参数选择目标账户。
	userId, ok := requirePendingUserID(c)
	if !ok {
		return
	}
	// 获取用户信息
	user, err := model.GetUserById(userId, false)
	if err != nil {
		c.JSON(http.StatusOK, gin.H{
			"success": false,
			"message": "用户不存在",
		})
		return
	}

	// 获取2FA记录
	twoFA, err := model.GetTwoFAByUserId(user.Id)
	if err != nil {
		common.ApiError(c, err)
		return
	}
	if twoFA == nil || !twoFA.IsEnabled {
		c.JSON(http.StatusOK, gin.H{
			"success": false,
			"message": "用户未启用2FA",
		})
		return
	}

	// 验证TOTP验证码或备用码
	cleanCode, err := common.ValidateNumericCode(req.Code)
	isValidTOTP := false
	isValidBackup := false

	if err == nil {
		// 尝试验证TOTP
		isValidTOTP, err = twoFA.ValidateTOTPAndUpdateUsage(cleanCode)
		if err != nil {
			message := err.Error()
			if errors.Is(err, model.ErrTwoFAConfigurationChanged) {
				message = model.ErrTwoFAConfigurationChanged.Error()
			}
			c.JSON(http.StatusOK, gin.H{
				"success": false,
				"message": message,
			})
			return
		}
	}

	if !isValidTOTP {
		// 尝试验证备用码
		isValidBackup, err = twoFA.ValidateBackupCodeAndUpdateUsage(req.Code)
		if err != nil {
			message := err.Error()
			if errors.Is(err, model.ErrTwoFAConfigurationChanged) {
				message = model.ErrTwoFAConfigurationChanged.Error()
			}
			c.JSON(http.StatusOK, gin.H{
				"success": false,
				"message": message,
			})
			return
		}
	}

	if !isValidTOTP && !isValidBackup {
		c.JSON(http.StatusOK, gin.H{
			"success": false,
			"message": "验证码或备用码错误，请重试",
		})
		return
	}

	// 2FA 验证成功后才将 pending 会话提升为正式登录会话。
	completePendingLogin(c, user)
}

// Admin2FAStats 管理员获取2FA统计信息
func Admin2FAStats(c *gin.Context) {
	stats, err := model.GetTwoFAStats()
	if err != nil {
		common.ApiError(c, err)
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"success": true,
		"message": "",
		"data":    stats,
	})
}

// AdminResetTwoFA 管理员重置用户 MFA，使其下次密码登录时重新绑定。
func AdminResetTwoFA(c *gin.Context) {
	userIdStr := c.Param("id")
	userId, err := strconv.Atoi(userIdStr)
	if err != nil {
		c.JSON(http.StatusOK, gin.H{
			"success": false,
			"message": "用户ID格式错误",
		})
		return
	}

	// 检查目标用户权限
	targetUser, err := model.GetUserById(userId, false)
	if err != nil {
		common.ApiError(c, err)
		return
	}

	myRole := c.GetInt("role")
	if myRole <= targetUser.Role && myRole != common.RoleRootUser {
		c.JSON(http.StatusOK, gin.H{
			"success": false,
			"message": "无权操作同级或更高级用户的2FA设置",
		})
		return
	}

	// 重置会删除旧密钥和备用码，但不会让用户永久关闭 MFA。
	if err := model.ResetTwoFA(userId); err != nil {
		if errors.Is(err, model.ErrTwoFANotConfigured) {
			c.JSON(http.StatusOK, gin.H{
				"success": false,
				"message": "用户尚未配置 MFA",
			})
			return
		}
		common.ApiError(c, err)
		return
	}

	// 记录操作日志
	adminId := c.GetInt("id")
	model.RecordLog(userId, model.LogTypeManage,
		fmt.Sprintf("管理员(ID:%d)重置了用户的 MFA，下次登录必须重新绑定", adminId))

	c.JSON(http.StatusOK, gin.H{
		"success": true,
		"message": "MFA 已重置，用户下次登录必须重新绑定",
	})
}
