FRONTEND_DIR = ./web
BACKEND_DIR = .
BACKEND_PORT ?= 3000
FRONTEND_PORT ?= 5173

.PHONY: all build-frontend start-backend dev

all: build-frontend start-backend

build-frontend:
	@# 构建前端产物，供 Go 在生产模式下嵌入并托管。
	@echo "Building frontend..."
	@cd $(FRONTEND_DIR) && bun install && DISABLE_ESLINT_PLUGIN='true' VITE_REACT_APP_VERSION=$(cat VERSION) bun run build

start-backend:
	@# 单独启动后端服务，默认监听 3000 端口。
	@echo "Starting backend dev server..."
	@cd $(BACKEND_DIR) && go run main.go &

dev:
	@# 本地联调模式：后台启动 Go，前台启动 Vite；退出时自动清理后端进程。
	@echo "Starting backend on http://localhost:$(BACKEND_PORT) and frontend on http://localhost:$(FRONTEND_PORT)..."
	@BACKEND_PID=""; \
	cleanup() { \
		if [ -n "$$BACKEND_PID" ] && kill -0 "$$BACKEND_PID" 2>/dev/null; then \
			echo "Stopping backend dev server ($$BACKEND_PID)..."; \
			kill "$$BACKEND_PID"; \
		fi; \
	}; \
	trap cleanup INT TERM EXIT; \
	cd $(BACKEND_DIR) && GIN_MODE=debug PORT=$(BACKEND_PORT) go run main.go & \
	BACKEND_PID=$$!; \
	echo "Backend started with PID $$BACKEND_PID"; \
	sleep 1; \
	cd $(FRONTEND_DIR) && bun install && bun run dev -- --host 0.0.0.0 --port $(FRONTEND_PORT)
