package logger

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sync"
	"time"

	"github.com/QuantumNous/new-api/common"
	"github.com/QuantumNous/new-api/setting/operation_setting"

	"github.com/gin-gonic/gin"
)

const (
	loggerINFO  = "INFO"
	loggerWarn  = "WARN"
	loggerError = "ERR"
	loggerDebug = "DEBUG"
)

const (
	logDateLayout   = "20060102"
	logTimeLayout   = "2006/01/02 - 15:04:05"
	systemRequestID = "SYSTEM"
)

var (
	// currentLogDate 记录当前生效日志文件对应的日期后缀，用于按天切换日志文件。
	currentLogDate string
	// currentLogFile 保存当前日期日志文件的句柄。
	currentLogFile *os.File
	// setupLogLock 用于保护日志文件切换过程。
	setupLogLock sync.Mutex
	// logWriteLock 用于串行化所有日志写入和按天切换操作。
	logWriteLock sync.Mutex
)

// dailyLogWriter 负责将日志同时写入标准输出/错误输出和当前日期的日志文件。
type dailyLogWriter struct {
	std io.Writer
}

// Write 在同一把锁内完成文件切换检查以及终端、文件的镜像写入。
func (w *dailyLogWriter) Write(p []byte) (int, error) {
	logWriteLock.Lock()
	defer logWriteLock.Unlock()

	now := time.Now()
	if err := ensureDailyLogFile(now); err != nil {
		// 这里直接写入标准错误输出，避免再次进入当前轮转写入器造成递归。
		_, _ = fmt.Fprintf(os.Stderr, "failed to ensure daily log file: %v\n", err)
		return w.std.Write(p)
	}

	n, err := w.std.Write(p)
	if currentLogFile == nil {
		return n, err
	}
	if _, fileErr := currentLogFile.Write(p); fileErr != nil && err == nil {
		err = fileErr
	}
	return n, err
}

// SetupLogger 安装按天切换的日志写入器，并在启用文件日志时打开当天日志文件。
func SetupLogger() {
	gin.DefaultWriter = &dailyLogWriter{std: os.Stdout}
	gin.DefaultErrorWriter = &dailyLogWriter{std: os.Stderr}

	if err := setupLoggerAt(time.Now()); err != nil {
		// 启动阶段直接写标准错误输出，避免初始化失败时依赖轮转写入器本身。
		_, _ = fmt.Fprintf(os.Stderr, "failed to setup logger: %v\n", err)
		os.Exit(1)
	}
}

// setupLoggerAt 在启用文件日志时将当前日志文件切换到指定日期对应的文件。
func setupLoggerAt(now time.Time) error {
	setupLogLock.Lock()
	defer setupLogLock.Unlock()

	if *common.LogDir == "" {
		if currentLogFile != nil {
			_ = currentLogFile.Close()
			currentLogFile = nil
		}
		currentLogDate = ""
		return nil
	}

	if err := os.MkdirAll(*common.LogDir, 0o755); err != nil {
		return fmt.Errorf("create log dir %q: %w", *common.LogDir, err)
	}

	logDate := now.Format(logDateLayout)
	if currentLogFile != nil && currentLogDate == logDate {
		return nil
	}

	logPath := filepath.Join(*common.LogDir, fmt.Sprintf("oneapi-%s.log", logDate))
	fd, err := os.OpenFile(logPath, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0o644)
	if err != nil {
		return fmt.Errorf("open log file %q: %w", logPath, err)
	}

	previousFile := currentLogFile
	currentLogFile = fd
	currentLogDate = logDate

	if previousFile != nil && previousFile != fd {
		_ = previousFile.Close()
	}

	return nil
}

// ensureDailyLogFile 确保每次写日志前都指向当天的日志文件。
func ensureDailyLogFile(now time.Time) error {
	if *common.LogDir == "" {
		return nil
	}
	return setupLoggerAt(now)
}

func LogInfo(ctx context.Context, msg string) {
	logHelper(ctx, loggerINFO, msg)
}

func LogWarn(ctx context.Context, msg string) {
	logHelper(ctx, loggerWarn, msg)
}

func LogError(ctx context.Context, msg string) {
	logHelper(ctx, loggerError, msg)
}

func LogDebug(ctx context.Context, msg string, args ...any) {
	if common.DebugEnabled {
		if len(args) > 0 {
			msg = fmt.Sprintf(msg, args...)
		}
		logHelper(ctx, loggerDebug, msg)
	}
}

// logHelper 格式化结构化服务日志，并通过按天切换的 gin 写入器输出。
func logHelper(ctx context.Context, level string, msg string) {
	writer := gin.DefaultErrorWriter
	if level == loggerINFO {
		writer = gin.DefaultWriter
	}
	id := any(systemRequestID)
	if ctx != nil {
		if ctxRequestID := ctx.Value(common.RequestIdKey); ctxRequestID != nil {
			id = ctxRequestID
		}
	}
	now := time.Now()
	_, _ = fmt.Fprintf(writer, "[%s] %v | %s | %s \n", level, now.Format(logTimeLayout), id, msg)
}

func LogQuota(quota int) string {
	// 新逻辑：根据额度展示类型输出
	q := float64(quota)
	switch operation_setting.GetQuotaDisplayType() {
	case operation_setting.QuotaDisplayTypeCNY:
		usd := q / common.QuotaPerUnit
		cny := usd * operation_setting.USDExchangeRate
		return fmt.Sprintf("¥%.6f 额度", cny)
	case operation_setting.QuotaDisplayTypeCustom:
		usd := q / common.QuotaPerUnit
		rate := operation_setting.GetGeneralSetting().CustomCurrencyExchangeRate
		symbol := operation_setting.GetGeneralSetting().CustomCurrencySymbol
		if symbol == "" {
			symbol = "¤"
		}
		if rate <= 0 {
			rate = 1
		}
		v := usd * rate
		return fmt.Sprintf("%s%.6f 额度", symbol, v)
	case operation_setting.QuotaDisplayTypeTokens:
		return fmt.Sprintf("%d 点额度", quota)
	default: // USD
		return fmt.Sprintf("＄%.6f 额度", q/common.QuotaPerUnit)
	}
}

func FormatQuota(quota int) string {
	q := float64(quota)
	switch operation_setting.GetQuotaDisplayType() {
	case operation_setting.QuotaDisplayTypeCNY:
		usd := q / common.QuotaPerUnit
		cny := usd * operation_setting.USDExchangeRate
		return fmt.Sprintf("¥%.6f", cny)
	case operation_setting.QuotaDisplayTypeCustom:
		usd := q / common.QuotaPerUnit
		rate := operation_setting.GetGeneralSetting().CustomCurrencyExchangeRate
		symbol := operation_setting.GetGeneralSetting().CustomCurrencySymbol
		if symbol == "" {
			symbol = "¤"
		}
		if rate <= 0 {
			rate = 1
		}
		v := usd * rate
		return fmt.Sprintf("%s%.6f", symbol, v)
	case operation_setting.QuotaDisplayTypeTokens:
		return fmt.Sprintf("%d", quota)
	default:
		return fmt.Sprintf("＄%.6f", q/common.QuotaPerUnit)
	}
}

// LogJson 仅供测试使用 only for test
func LogJson(ctx context.Context, msg string, obj any) {
	jsonStr, err := json.Marshal(obj)
	if err != nil {
		LogError(ctx, fmt.Sprintf("json marshal failed: %s", err.Error()))
		return
	}
	LogDebug(ctx, fmt.Sprintf("%s | %s", msg, string(jsonStr)))
}
