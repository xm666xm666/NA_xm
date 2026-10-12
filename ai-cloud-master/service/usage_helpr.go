package service

import (
	"github.com/QuantumNous/new-api/common"
	"github.com/QuantumNous/new-api/constant"
	"github.com/QuantumNous/new-api/dto"
	"github.com/gin-gonic/gin"
)

//func GetPromptTokens(textRequest dto.GeneralOpenAIRequest, relayMode int) (int, error) {
//	switch relayMode {
//	case constant.RelayModeChatCompletions:
//		return CountTokenMessages(textRequest.Messages, textRequest.Model)
//	case constant.RelayModeCompletions:
//		return CountTokenInput(textRequest.Prompt, textRequest.Model), nil
//	case constant.RelayModeModerations:
//		return CountTokenInput(textRequest.Input, textRequest.Model), nil
//	}
//	return 0, errors.New("unknown relay mode")
//}

func ResponseText2Usage(c *gin.Context, responseText string, modeName string, promptTokens int) *dto.Usage {
	common.SetContextKey(c, constant.ContextKeyLocalCountTokens, true)
	usage := &dto.Usage{}
	usage.PromptTokens = promptTokens
	usage.CompletionTokens = EstimateTokenByModel(modeName, responseText)
	usage.TotalTokens = usage.PromptTokens + usage.CompletionTokens
	return usage
}

func ValidUsage(usage *dto.Usage) bool {
	return usage != nil && (usage.PromptTokens != 0 || usage.CompletionTokens != 0)
}

// SetTokenModelRequestUsage 将成功请求的 usage 写入上下文，供令牌模型 TPM 记账复用。
func SetTokenModelRequestUsage(c *gin.Context, usage *dto.Usage) {
	if c == nil || !ValidUsage(usage) {
		return
	}
	common.SetContextKey(c, constant.ContextKeyTokenModelRequestUsage, usage)
}

// SetTokenModelRealtimeRequestUsage 将 Realtime usage 转成通用 usage 后写入上下文，供请求结束时的 TPM 记账复用。
func SetTokenModelRealtimeRequestUsage(c *gin.Context, usage *dto.RealtimeUsage) {
	if c == nil || usage == nil {
		return
	}

	// Realtime 的输入/输出 token 语义分别映射到通用 usage 的 prompt/completion。
	inputTokenDetails := usage.InputTokenDetails
	SetTokenModelRequestUsage(c, &dto.Usage{
		PromptTokens:           usage.InputTokens,
		CompletionTokens:       usage.OutputTokens,
		TotalTokens:            usage.TotalTokens,
		PromptTokensDetails:    usage.InputTokenDetails,
		CompletionTokenDetails: usage.OutputTokenDetails,
		InputTokens:            usage.InputTokens,
		OutputTokens:           usage.OutputTokens,
		InputTokensDetails:     &inputTokenDetails,
	})
}
