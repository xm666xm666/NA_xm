package common

import (
	"context"
	"net/http"
)

// RequestContext 返回请求上下文；当请求对象缺失时退回后台上下文，避免空指针。
func RequestContext(r *http.Request) context.Context {
	if r == nil {
		return context.Background()
	}
	return r.Context()
}

// IsRequestCanceled 判断请求上下文是否已经取消。
func IsRequestCanceled(r *http.Request) bool {
	return RequestContext(r).Err() != nil
}
