# AI 网关大模型调用培训 PPT Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 生成一份经过内容和视觉验证的 15 分钟中文 AI 网关大模型调用培训 PPT。

**Architecture:** 使用单一 PptxGenJS 生成脚本维护主题、组件、12 页内容和讲者备注，输出到 `docs/AI网关大模型调用培训.pptx`。接口与参数信息只取自项目路由和 DTO；生成后通过文本提取、PDF 渲染和逐页图像检查完成至少一次修复闭环。

**Tech Stack:** Node.js、PptxGenJS 4.0.1、LibreOffice、Poppler、MarkItDown。

## Global Constraints

- 交付格式为 16:9 PowerPoint（`.pptx`），语言为简体中文。
- 正文 10 页、附录 2 页，讲解时长约 15 分钟。
- 视觉采用深灰主色、薄荷绿强调色和米白内容背景。
- 分组示例为 `cs-test`，模型示例为 `cs-test-glm-5.1`，令牌示例为 `cs-test-glm-5.1-揭昊`。
- 地址使用 `<AI_GATEWAY_BASE_URL>`，令牌使用 `<YOUR_TOKEN>`，不写入真实凭据。
- 生成代码必须包含职责和关键布局意图的注释。
- 使用 PptxGenJS 4.0.1 前，通过 Context7 查询对应版本 API。
- 不修改或提交用户现有的 `middleware/security-headers.go` 变更。

---

### Task 1: 核对接口与参数事实

**Files:**
- Read: `router/relay-router.go`
- Read: `dto/openai_request.go`
- Read: `relay/helper/valid_request.go`
- Reference: `docs/superpowers/specs/2026-07-17-ai-gateway-training-ppt-design.md`

**Interfaces:**
- Consumes: 项目实际路由、Chat Completions 请求结构和校验逻辑。
- Produces: 生成脚本使用的接口分组、核心参数、附录参数和调用示例。

- [ ] **Step 1: 提取项目已实现接口**

Run: `sed -n '1,240p' router/relay-router.go`

Expected: 区分调用 `controller.Relay` 的已实现接口与调用 `controller.RelayNotImplemented` 的接口。

- [ ] **Step 2: 提取 Chat Completions 请求字段与校验**

Run:

```bash
sed -n '1,330p' dto/openai_request.go
sed -n '200,290p' relay/helper/valid_request.go
```

Expected: 获得 `model`、`messages`、采样、输出长度、流式、工具调用、结构化输出等字段和约束。

- [ ] **Step 3: 固定兼容性口径**

课件使用以下原文：

```text
网关能够接收某个参数，不代表所有上游模型都以相同方式支持该参数；高级参数请结合所申请模型验证。
```

Expected: 不把“网关可接收”误写为“所有上游模型完整支持”。

### Task 2: 创建课件生成脚本

**Files:**
- Create: `scripts/generate_ai_gateway_training_ppt.js`
- Create: `docs/AI网关大模型调用培训.pptx`

**Interfaces:**
- Consumes: Task 1 的接口、参数和固定文案。
- Produces: `buildDeck(): Promise<void>`；辅助函数负责标题、页脚、卡片、代码面板、流程节点和讲者备注。

- [ ] **Step 1: 查询 PptxGenJS 4.0.1 API**

通过 Context7 解析 `PptxGenJS` 库标识，并查询 16:9 布局、主题字体、文本、形状、连接线、speaker notes 和 `writeFile` 的正确 API。

Expected: 核对 `layout`、`theme`、`addText`、`addShape`、`addNotes` 和 `writeFile` 后再编码。

- [ ] **Step 2: 实现主题和通用组件**

脚本定义以下接口，并为职责和关键布局添加中文注释：

```javascript
const OUTPUT_PATH = path.resolve(__dirname, '../docs/AI网关大模型调用培训.pptx');
const COLORS = {
  charcoal: '20252B', mint: '35D0A0', cream: 'F5F2E9',
  ink: '182028', slate: '53606B', white: 'FFFFFF', warning: 'F4B860',
};

function addHeader(slide, title, section, pageNumber) {}
function addFooter(slide, pageNumber) {}
function addCard(slide, options) {}
function addCodePanel(slide, options) {}
function addFlowNode(slide, options) {}
function addSpeakerNotes(slide, notes) {}
```

Expected: 正文页至少 0.5 英寸边距，标题不少于 32 磅，正文不少于 15 磅。

- [ ] **Step 3: 实现 10 页正文**

```text
01 AI 网关大模型调用培训
02 一次调用，经过哪些环节？
03 第一步：通过企微申请模型
04 管理员配置 ① 分组
05 管理员配置 ② 渠道
06 管理员配置 ③ 令牌
07 高负载场景：一个模型名，多条渠道
08 网关当前提供哪些接口？
09 /v1/chat/completions：核心参数
10 从请求到结果：调用示例与检查清单
```

Expected: 页面 4–6 使用同一命名示例；页面 7 明确用户模型名不变；页面 8 只列已实现能力；页面 9–10 包含认证头、请求体和响应读取方式。

- [ ] **Step 4: 实现 2 页附录**

```text
11 附录：Chat Completions 参数速查
12 附录：其他接口速查
```

Expected: 参数表逐项说明名称、是否必填、作用和兼容性；接口表逐项说明方法、路径、作用和典型输入。

- [ ] **Step 5: 生成 PPT**

Run:

```bash
NODE_PATH=/Users/zhilin.xie/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules \
  /Users/zhilin.xie/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node \
  scripts/generate_ai_gateway_training_ppt.js
```

Expected: 输出 `docs/AI网关大模型调用培训.pptx`，退出码为 0。

### Task 3: 内容验证

**Files:**
- Verify: `docs/AI网关大模型调用培训.pptx`
- Verify: `scripts/generate_ai_gateway_training_ppt.js`

**Interfaces:**
- Consumes: Task 2 的 PPT。
- Produces: 无占位符、无遗漏、接口和参数口径正确的课件。

- [ ] **Step 1: 提取 PPT 文本**

Run:

```bash
/Users/zhilin.xie/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  -m markitdown docs/AI网关大模型调用培训.pptx
```

Expected: 按 1–12 页顺序输出全部标题、正文、代码和附录内容。

- [ ] **Step 2: 扫描占位内容和敏感凭据**

Run: `rg -n -i 'TBD|TODO|xxxx|lorem|ipsum|sk-[A-Za-z0-9]{10,}' scripts/generate_ai_gateway_training_ppt.js`

Expected: 无匹配；示例占位符仅为 `<AI_GATEWAY_BASE_URL>` 和 `<YOUR_TOKEN>`。

- [ ] **Step 3: 对照源码人工复核**

Run: `git diff --no-index /dev/null scripts/generate_ai_gateway_training_ppt.js`

Expected: 每个接口都能在路由中找到，每个参数都能在请求 DTO 中找到，未实现接口未列为可用。

### Task 4: 视觉验证与修复闭环

**Files:**
- Verify: `docs/AI网关大模型调用培训.pptx`
- Modify: `scripts/generate_ai_gateway_training_ppt.js`
- Temporary: `/tmp/ai-gateway-training-render/`

**Interfaces:**
- Consumes: 通过内容验证的 PPT。
- Produces: 无重叠、溢出、裁切和低对比问题的最终课件。

- [ ] **Step 1: 渲染所有页面**

Run:

```bash
mkdir -p /tmp/ai-gateway-training-render
python /Users/zhilin.xie/.agents/skills/pptx/scripts/office/soffice.py \
  --headless --convert-to pdf --outdir /tmp/ai-gateway-training-render \
  docs/AI网关大模型调用培训.pptx
pdftoppm -jpeg -r 150 \
  /tmp/ai-gateway-training-render/AI网关大模型调用培训.pdf \
  /tmp/ai-gateway-training-render/slide
```

Expected: 生成 12 张 `slide-*.jpg`。

- [ ] **Step 2: 逐页检查并记录问题**

检查重叠、溢出、页边距、间距、对比度、标题换行、代码密度和占位符残留。

Expected: 第一轮至少记录一项可改进问题，并明确页码和修改动作。

- [ ] **Step 3: 修复并重新生成**

修改生成脚本，重新执行 Task 2 Step 5 和 Task 4 Step 1。

Expected: 受影响页面重新渲染成功，修改未引入新问题。

- [ ] **Step 4: 第二轮视觉检查**

再次检查全部 12 页，重点复核第一轮受影响页面。

Expected: 未发现新的重叠、溢出、裁切、低对比度或明显间距问题。

### Task 5: 最终校验与提交

**Files:**
- Add: `scripts/generate_ai_gateway_training_ppt.js`
- Add: `docs/AI网关大模型调用培训.pptx`

**Interfaces:**
- Consumes: 通过内容和视觉验证的最终文件。
- Produces: 可交付 PPT 和可复现生成脚本。

- [ ] **Step 1: 检查代码注释和变更范围**

Run:

```bash
rg -n '^\s*//|/\*|\*/' scripts/generate_ai_gateway_training_ppt.js
git status --short
git diff --check
```

Expected: 脚本包含必要注释；不包含用户现有文件的修改；无空白错误。

- [ ] **Step 2: 最终生成和文本复验**

Run: 重新执行 Task 2 Step 5 和 Task 3 Step 1。

Expected: 生成成功，文本按 12 页顺序完整输出。

- [ ] **Step 3: 提交交付物**

Run:

```bash
git add scripts/generate_ai_gateway_training_ppt.js
git add -f docs/AI网关大模型调用培训.pptx
git commit -m "docs: add AI gateway training presentation"
```

Expected: 提交只包含生成脚本和 PPT，不包含 `middleware/security-headers.go`。
