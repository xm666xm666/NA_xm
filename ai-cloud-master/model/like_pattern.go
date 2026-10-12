package model

import "strings"

// likePatternReplacer 使用 ! 作为跨数据库一致的 LIKE 转义字符。
var likePatternReplacer = strings.NewReplacer(
	"!", "!!",
	"%", "!%",
	"_", "!_",
)

// escapeLikePattern 将用户输入中的 LIKE 特殊字符转换为字面量匹配。
func escapeLikePattern(value string) string {
	return likePatternReplacer.Replace(value)
}
