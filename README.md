> ## 分支与部署方式选择
>
> 本仓库采用三条分支分别承载说明、独立运行和容器化运行。请按实际部署目标选择分支；三条分支的 README 都保留完整项目说明，并在此处提供相同的选择指引。
>
> | 分支 | 作用与内容 | 何时选择 | 启动方式 |
> | --- | --- | --- | --- |
> | **`master`** | 仓库入口、完整功能文档与 [LICENSE](LICENSE)。为保持发布入口干净，仓库树只保留 README 和许可证，**不含可执行源码、配置示例或部署清单**。 | 只需了解产品、阅读许可和确定采用哪种部署路径。 | 不能直接运行；请切换到下方两个可执行分支之一。 |
> | **`stand-alone`** | 传统独立部署版本：完整应用源码、`run.bat`、`run.sh`、Python 依赖及配置模板。 | Windows 开发/运维机，或仅有一台 Linux / Rocky Linux 主机、希望直接通过 Python 运行。 | Windows 使用 `run.bat`；Linux / Rocky 使用 `./run.sh`。需由主机自行安装 Python。 |
> | **`container`** | 网站化与容器化版本：包含完整应用、登录/注册/忘记密码、超管/管理员/用户三角色权限，以及 Dockerfile、Compose、PostgreSQL 18、Redis 8、Kubernetes 清单。 | 多人协作、需要网站账户与权限控制，或需要 Docker/Podman、Rocky Linux 8/9、Kubernetes 部署。 | Docker/Podman 使用 `docker compose up -d --build`；Kubernetes 使用 `deploy/k8s/` 清单与 `kubectl apply`。 |
>
> **选择规则：**
>
> 1. 仅查看说明或许可证：留在 `master`。
> 2. 使用 BAT / SH 直接运行：切到 `stand-alone`。
> 3. 使用登录权限、PostgreSQL 18、Redis 8、Docker 或 Kubernetes：切到 `container`。
>
> ```bash
> git switch stand-alone  # 独立 Python 部署
> git switch container    # 网站化 / 容器化部署
> ```
>
> 不要混用分支部署文件：`run.bat` / `run.sh` 属于 `stand-alone`；`Dockerfile`、`compose.yaml`、`deploy/k8s/` 属于 `container`。切换分支后，请继续阅读下方完整项目说明与该分支内的部署章节。

> **安全说明：** 示例密钥、验证码和令牌均使用低熵、不可用占位符；仅验证格式的测试数据使用固定的短前缀，绝不构成可用凭据。真实凭据只能通过本地环境变量或部署 Secret 注入，严禁提交到 Git。

---

# NA 自动配置工具

面向 [New API](https://github.com/Calcium-Ion/new-api)（NA）的一体化配置工具。**单页 Web 应用**，顶栏九个入口（**无序号**）：工作台、智能提取、批量配置、平台信息、数据汇总、上游信息、上游账单、一表总览、智能体。打开即落地 **工作台**（`#workspace`），默认端口 `8765`。

源码仓库：[github.com/xm666xm666/NA_xm](https://github.com/xm666xm666/NA_xm)（公开，默认分支：`master`）。

> **公开仓库安全**：`env/sites.json`、`env/upstream.json`、本地 `.env`、日志、缓存、Python 虚拟运行环境与导出文件均由 `.gitignore` 排除；示例和测试中的凭据均为不可用占位符。请勿提交任何真实密钥、验证码或站点账号。

> **项目维护约定**：每次代码或配置更新都要同步检查并完善本 README，确保功能说明、配置方式和部署步骤与当前实现一致；更新完成后上传到 GitHub 的 `container` 分支。

> **许可证**：本项目采用 [NA_xm 个人使用与商业合作许可证（v1.0）](LICENSE)。自然人可免费用于个人、学习、研究和其他非商业用途；企业或其他商业使用者必须先通知作者，并取得书面合作或商业授权。未获得授权时，不得商业使用。

网关环境按 `env/sites.json` **已配置站点**循环。文案用集群名：**生产**（原 prod）、**非生产**（原 test / uat）。历史 Excel 工作表名、快捷按钮仍可能出现 `test` / `uat` / `prod`，与「有几套网关集群」不是同一件事；两站齐全即为覆盖完成，不必写满三站。

```text
打开应用 ──→ 工作台（待办 / 六任务卡 / 全局站点认证 / 产物）
                │
杂乱项目信息 / 令牌草稿 ──→ 智能提取（渠道 | 令牌）──→ 批量配置 ──→ NA 站点
                                    │                          │
                           渠道：规则 + 可选 AI          渠道·令牌·分组·启停·日志
                           令牌：规则拼接（无 LLM；可从渠道批量行反推）
                                    │
                                    └──→ 数据汇总 ──→ excel/ai网关令牌及渠道列表_年月日时分秒.xlsx

平台信息：按 test / uat / prod 读取服务端站点账号、密码与 TOTP，呈现 ai-cloud 渠道管理 / 令牌管理列表，均按 ID 降序排列。渠道列含 ID、名称、分组、类型（完整 56 种映射）、状态、响应时间、近一月活跃统计（按模型级别展示 RPM/TPM）、已用/剩余、优先级、权重、批量配置；令牌列含名称、状态（已启用/已禁用/已过期/已耗尽）、剩余额度/总额度、分组、密钥（掩码显示 `sk-` 前缀与尾号，点击复制完整值）、可用模型、模型限流条数、IP限制、创建时间、过期时间、批量配置。两列表格按屏幕宽度自适应；长名称、分组、活跃统计、模型白名单、IP限制等字段在悬浮时展示完整内容并提供复制，批量配置列可把当前记录转换为一键填入的批量行。编辑弹窗为结构化表单：渠道含名称、类型、Base URL、代理、分组、优先级、权重、模型列表、模型重定向、备注、状态、自动禁用；令牌含名称、分组、额度、过期时间、模型白名单、IP限制、状态。测试渠道后响应时间同步更新到列表

智能体：异步任务（LLM 规划 → 门禁确认 → 智能提取、批量配置、数据汇总，可选上游信息 / 一表总览 / 智能分析；Web / Jobs API / 兼容 /api/agent/run）
上游信息：采集云厂商资源（火山云 IAM + Azure OpenAI 服务主体；可一键写入同一工作簿；表末列为部署时间；表头可筛选）
上游账单：按账期起止采集火山云 / Azure 费用（可跨月，每月一份 Excel；也可一键写入同一工作簿四张费用表；表头可筛选）
一表总览：页内选择产物（禁止静默 latest）；按已配置站点拉渠道密钥；智能分析对照火山/Azure；建议表可筛选、全选/反选后预禁用；卫生策略可配置；写入 excel/智能分析表格_时间戳.xlsx

每次启动 → log/na_时间戳_模式_pid.txt（API 操作成功/失败/警告，便于审查）
```

---

## 目录

- [功能概览](#功能概览)
- [快速启动](#快速启动)
  - [环境要求](#环境要求)
  - [一键启动](#一键启动)
  - [手动启动](#手动启动)
  - [独立部署](#独立部署)
  - [Docker / Podman（Rocky Linux 8/9）](#docker--podmanrocky-linux-89)
  - [Kubernetes](#kubernetes)
- [网站账户、权限与安全](#网站账户权限与安全)
  - [角色矩阵](#角色矩阵)
  - [首个超管与用户管理](#首个超管与用户管理)
  - [认证与安全边界](#认证与安全边界)
- [界面说明](#界面说明)
  - [浏览器本地缓存（localStorage）](#浏览器本地缓存localstorage)
- [工作台](#工作台)
  - [全局站点认证](#全局站点认证)
  - [产物列表刷新](#产物列表刷新)
- [主题切换](#主题切换)
- [目录结构](#目录结构)
- [Excel 存放与浏览器下载](#excel-存放与浏览器下载)
- [推荐工作流](#推荐工作流)
  - [流程 A：渠道提取 → 批量创建](#流程-a渠道提取--批量创建)
  - [流程 A2：令牌提取 → 批量创建](#流程-a2令牌提取--批量创建)
  - [流程 A3：火山自动升级 → 更新原配置](#流程-a3火山自动升级--更新原配置)
  - [流程 B：直接批量](#流程-b直接批量)
  - [流程 C：多站点数据汇总](#流程-c多站点数据汇总)
  - [流程 D：导出使用日志](#流程-d导出使用日志)
  - [流程 E：按上游模型 / 类型启停渠道](#流程-e按上游模型--类型启停渠道)
  - [流程 E2：查询渠道已用 / 剩余余额](#流程-e2查询渠道已用--剩余余额)
  - [流程 F：全流程智能体（异步工作台）](#流程-f全流程智能体异步工作台)
  - [流程 G：采集火山云上游](#流程-g采集火山云上游)
  - [流程 H：采集 Azure OpenAI 上游](#流程-h采集-azure-openai-上游)
  - [流程 I：一次采集火山云 + Azure 汇总表](#流程-i一次采集火山云--azure-汇总表)
  - [流程 J：一表总览（网关 + 两侧上游）](#流程-j一表总览网关--两侧上游)
  - [流程 K：采集上游账单](#流程-k采集上游账单)
- [智能提取](#智能提取)
  - [输出格式（渠道）](#输出格式渠道)
  - [令牌智能提取](#令牌智能提取)
    - [输出格式（令牌）](#输出格式令牌)
    - [输入方式（令牌）](#输入方式令牌)
    - [渠道行转令牌](#渠道行转令牌)
    - [拼接规则摘要](#拼接规则摘要)
  - [输入方式（渠道）](#输入方式渠道)
  - [分组与模型推导](#分组与模型推导)
  - [载入示例（Web）](#载入示例web)
  - [更新提取（火山自动升级）](#更新提取火山自动升级)
  - [提取模式](#提取模式)
  - [支持的渠道类型](#支持的渠道类型)
  - [多条批量与分隔符](#多条批量与分隔符)
- [LLM 增强](#llm-增强)
- [批量配置](#批量配置)
  - [连接与认证](#连接与认证)
    - [登录两步验证（渠道 / 令牌）](#登录两步验证渠道--令牌)
    - [TOTP 原始密钥（sites.json）](#totp-原始密钥sitesjson)
    - [跳过 SSL 证书校验](#跳过-ssl-证书校验)
    - [环境快捷切换（已配置站点）](#环境快捷切换已配置站点)
  - [渠道管理](#渠道管理)
    - [更新原配置](#更新原配置)
    - [同步 Base URL 到备注](#同步-base-url-到备注)
  - [令牌管理](#令牌管理)
    - [有限额度创建](#有限额度创建)
    - [更新已有令牌额度](#更新已有令牌额度)
  - [分组设置](#分组设置)
    - [分组切换](#分组切换)
  - [渠道启停](#渠道启停)
  - [使用日志](#使用日志)
  - [上游信息](#上游信息)
    - [火山云导出列](#火山云导出列)
    - [token 匹配（方舟 API Key）](#token-匹配方舟-api-key)
    - [项目方：项目名-负责人](#项目方项目名-负责人)
    - [Azure OpenAI 配置与权限](#azure-openai-配置与权限)
    - [Azure OpenAI 导出列](#azure-openai-导出列)
    - [标记 1：项目-负责人1，负责人2](#标记-1项目-负责人1负责人2)
    - [env 参数获取](#env-参数获取)
  - [上游账单](#上游账单)
  - [一表总览](#一表总览)
    - [智能分析（上下游密钥）](#智能分析上下游密钥)
      - [页内分析建议](#页内分析建议)
      - [新部署放宽（卫生策略）](#新部署放宽卫生策略)
      - [批量禁用](#批量禁用)
  - [权限建议](#权限建议)
- [平台信息](#平台信息)
- [数据汇总](#数据汇总)
  - [网站列表与 env 自动识别](#网站列表与-env-自动识别)
  - [采集逻辑](#采集逻辑)
  - [验证码与全局认证](#验证码与全局认证)
  - [含渠道密钥导出（二次验证）](#含渠道密钥导出二次验证)
  - [输出文件](#输出文件)
  - [继续补全密钥](#继续补全密钥)
  - [工作表](#工作表)
  - [重复检测](#重复检测)
  - [渠道余额查询（多站点）](#渠道余额查询多站点)
- [全流程智能体](#全流程智能体)
  - [执行流程](#执行流程)
  - [二次验证（渠道 / 令牌 / 汇总）](#二次验证渠道--令牌--汇总)
  - [Web 使用](#web-使用)
  - [异步 Jobs API](#异步-jobs-api)
  - [兼容同步 API](#兼容同步-api)
- [命令行](#命令行)
  - [运行测试](#运行测试)
- [HTTP API](#http-api)
  - [智能提取 API](#智能提取-api)
  - [批量配置 API](#批量配置-api)
  - [平台信息 API](#平台信息-api)
  - [数据汇总 API](#数据汇总-api)
  - [上游信息 API](#上游信息-api)
  - [上游账单 API](#上游账单-api)
  - [一表总览 API](#一表总览-api)
  - [工作台 / 产物 / 卫生策略 API](#工作台--产物--卫生策略-api)
  - [全流程智能体 API](#全流程智能体-api)
- [架构说明](#架构说明)
- [启动日志（审查）](#启动日志审查)
  - [文件命名](#文件命名)
  - [行格式与级别](#行格式与级别)
  - [记录范围](#记录范围)
- [产品文档](#产品文档)
- [配置说明](#配置说明)
  - [env 文件怎么用](#env-文件怎么用)
  - [NA 站点参数（已配置站点）](#na-站点参数已配置站点)
  - [火山云 upstream.volc](#火山云-upstreamvolc)
  - [Azure OpenAI upstream.azure](#azure-openai-upstreamazure)
  - [其他配置文件（agent / batch）](#其他配置文件agent--batch)
- [示例文件](#示例文件)
  - [Agent（`examples/agent/`）](#agentexamplesagent)
  - [Batch CLI（`examples/batch/`）](#batch-cliexamplesbatch)
  - [批量 Web（`batch/static/`，「载入示例」）](#批量-webbatchstatic载入示例)
- [注意事项](#注意事项)
- [常见问题](#常见问题)
- [版本规划](#版本规划)

---



## 功能概览


| 模块           | 能力                                                                                 |
| ------------ | ---------------------------------------------------------------------------------- |
| **工作台**     | 默认落地页。待办来自最新分析表与盘点产物（无 Excel 时不显示假 0）；六任务卡：新项目接入、例行盘点、上游采集、上游账单、卫生清理、智能体跑通；**全局站点认证**写会话缓存；展示最近产物与进行中智能体任务 |
| **智能提取**   | **渠道**或**令牌**模式：渠道从杂乱文本/完整行/紧凑行提取；令牌支持三行/四行拼接，以及**令牌名(+人名) + 渠道批量行**反推分组与模型；多条批量；渠道可选 AI。渠道侧可先点「**更新**」再提取（不要求密钥，用于同步上游自动升级） |
| **渠道管理**   | 批量创建 / **预更新·确认更新（原配置）** / 全量同步 Base URL 到备注 / 预删除·预禁用·预启用（名称+分组）；类型识别、去重、创建/更新模板锁定 |
| **令牌管理**   | 批量创建令牌、模型限制与可选额度；**预更新·确认更新额度**、预删除·预禁用·预启用（名称+分组）；创建/更新模板锁定、导出名称+密钥 |
| **平台信息**   | 位于批量配置右侧；按 **test / uat / prod** 统一呈现 ai-cloud / New API 的**渠道管理**与**令牌管理**列表；支持分页、长文本悬浮查看完整值和复制、测试/启停/编辑/删除，并可把行转换为批量配置格式后一键填入；测试失败同步上游错误且不清空响应时间；编辑时读取并保存完整原始 JSON 字段，账号、密码和 `totp_secret` 始终只由服务端读取 |
| **分组设置**   | 批量创建 / 删除分组；**分组切换**（勾选或全选，将该分组下渠道 / 令牌改到目标分组；需 Root 建分组） |
| **渠道启停**   | 按上游模型 / 类型全部 / 勾选 ID 启用禁用；可视化清单；全选反选；单条操作；默认自定义渠道可改类型                              |
| **渠道查询**   | 在**数据汇总**页：按已配置站点查询已用/剩余；常用区间；**配置时间段**（1/3/5/15/30/60/180/365 天或自定义）；**近一月活跃**按模型逐项填写（失败/无信息为 N/A）；导出写入 `excel/渠道余额_时间戳.xlsx`；点「下载 Excel」获取完整文件；按环境分表（历史表名仍可能是 `uat-渠道余额` 等） |
| **使用日志**   | 按时间范围导出 CSV / Excel 到 `excel/`；后台任务 + 进度轮询；可**终止**；完成后点「下载 Excel」取最新一份；NA 每页最多 100 条 |
| **数据汇总**   | 多站点全量采集渠道 + 令牌（渠道含管理员备注）；工作台已认证或已预置 TOTP 时**不再弹审查窗**，仅缺码站点弹 30 秒临时码；**每次一键采集新建** `ai网关令牌及渠道列表_时间戳.xlsx`；全部站点写完后再点「下载 Excel」；「继续补全密钥」才更新最新一份（不含总览文件） |
| **智能体** | 异步任务 + SSE + 提取门禁 + 渠道/令牌写入；可选上游、总览（不含密钥）、智能分析；登录 2FA 可在连接、门禁确认、重试时刷新；与批量页共用连接；完成后分别下载数据汇总、上游信息、一表总览/分析表 |
| **上游信息**   | 采集云厂商资源：**火山云**与 **Azure OpenAI**。可「一键采集全部上游」写入同一工作簿（工作表 `火山云`、`Azure OpenAI`）；也可按厂商单独导出。火山云列 **TPM 在 RPM 前**。两表**最后一列均为部署时间**，**按部署时间降序（最新在上）**。表头开启列筛选，首行冻结 |
| **上游账单**   | 按账期采集火山云费用中心 / Azure Cost Management。可选账期起止，**每月各写一份 Excel**（不把多月并进同一文件，一次最多 24 个月）。可「一键采集全部账单」写入同一工作簿（`火山云-按天` / `火山云-按月` / `Azure-按天` / `Azure-按月`）；也可按厂商单独导出。费用列 `费用（¥）`，表末 `SUM` 合计。表头开启列筛选（不含合计行） |
| **一表总览**   | 把数据汇总网关表 + 火山/Azure 合成总览（默认含渠道密钥）。页内**选择**总览/分析/余额文件（下拉默认最新，请求必须带所选 id）。**智能分析**对照上下游。建议表可按级别/站点/类别筛选，**全选 / 反选**后 **预禁用**（宽限期内默认跳过，勾「仍要执行」才纳入）。分析表 `建议处置` 右侧仍有 `批量禁用` 粘贴列。写入独立的 `excel/智能分析表格_时间戳.xlsx`（不覆盖总览） |
| **启动日志**     | 每次启动在 `log/` 生成独立 `.txt`；记录 API 操作、成功/失败/警告、登录限流等（敏感字段脱敏）                           |


通用能力：

- 账号密码或 Access Token 双模式认证；连续操作复用会话缓存（约 2 小时），降低登录 429
- 账号开启**登录两步验证**时，可填认证器 6 位码、8 位备用码，或认证器**原始密钥**（`totp_secret`）；测试连接、渠道/令牌批量、智能体写入均会带上；一次性验证码不写入 localStorage
- 内网网关证书 Hostname mismatch 时可勾选「跳过 SSL 证书校验」（**默认校验证书**）
- New API 地址自动规范化（`/console`、`/api` 路径自动转为站点根地址）
- **环境快捷切换**：配置 `env/sites.json` 后，批量配置连接配置与 **智能体** 按**已配置站点**显示快捷按钮（历史 key 仍可能叫 test / uat / prod）；密码与 TOTP 密钥也可由服务端按地址自动补齐，页面可留空
- 智能提取结果一键填入批量配置（渠道 → 渠道管理；令牌 → 令牌管理），并同步连接配置
- **更新提取**（先点「更新」再点「智能提取」）结果一键「填入更新原配置」，不走批量创建
- 删除 / 更新 / 启停须先预检或确认，示例数据防误点创建
- **明暗双主题**（右上角切换，iframe 子页同步），默认暗色
- 九个顶栏入口单页切换，**名称保留原模块名、仅去掉序号**（工作台仍叫工作台；智能体在最右）。打开应用默认 `#workspace`。数据汇总 / 上游信息 / 上游账单 / 一表总览 / 批量·使用日志提供产物下拉，旁有「刷新」；下载与分析须指定文件，禁止静默 latest
- 统一 UI 组件（`na-theme.css`、`na-components.css`、`na-ui.js`）
- 操作可追溯：见 [启动日志（审查）](#启动日志审查)

---



## 快速启动



### 环境要求

- Python **3.10+**（容器镜像固定 Python 3.12）
- 依赖见 `requirements.txt`：原有 `flask`、`requests`、`openpyxl`，以及网站化所需的 `SQLAlchemy`、`psycopg`、`redis`、`Flask-Session`、`argon2-cffi`、`alembic`、`gunicorn`



### 一键启动

**Windows**

```bat
run.bat
```

**Linux / macOS**

```bash
chmod +x run.sh
./run.sh
```

启动后访问：**[http://127.0.0.1:8765/](http://127.0.0.1:8765/)**

脚本会自动创建 `.venv`、安装依赖并启动服务。`run.bat` 使用纯 ASCII 输出，避免中文编码导致闪退。

启动成功后终端会打印：

- 服务地址（如 `http://0.0.0.0:8765/`）
- **本次启动日志**路径：`log/na_YYYYMMDD_HHMMSS_serve_pidXXXX.txt`（详见 [启动日志（审查）](#启动日志审查)）

### 手动启动

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate
# Linux / macOS
source .venv/bin/activate

pip install -r requirements.txt
python app.py                  # 默认 0.0.0.0:8765，自动打开浏览器
python app.py --port 9000      # 自定义端口
python app.py --no-browser     # 不自动打开浏览器
```



### 独立部署

复制整个项目目录到目标机器，执行 run.bat 或 run.sh 即可，无需额外构建步骤。首次执行 Windows run.bat 时，会在本机生成被 Git 忽略的 .env、随机初始超管密码与 SQLite 网站数据库配置；控制台会显示一次 admin 的初始密码，并将其保存到 .env。请立即保存该密码，首次登录后按页面提示修改。run.bat 不会覆盖 .env 中已有的非空密码；若 .env 丢失但本机 SQLite 管理员库仍存在，也不会生成误导性的新密码。如需重新初始化，请先停止程序，再删除本机 .cache/website.db 与 .env，然后重新运行 run.bat。真实凭据请在目标机单独填写 env/sites.json（不要把含密钥的文件拷进共享盘）；各字段从哪抄见 [配置说明](#配置说明)。

### Docker / Podman（Rocky Linux 8/9）

生产部署使用三项容器服务：Web、**PostgreSQL 18**（`postgres:18`）和 **Redis 8**（`redis:8`）。数据库保存账户、恢复验证码哈希、审计记录及后续任务/产物元数据；Redis 只保存服务端会话。渠道、令牌及上游凭据仍按原有 `env/` 文件挂载，不会迁入账户数据库。

1. 在 Rocky Linux 8 或 9 安装并启动 Docker Compose v2，或使用兼容 Compose 的 Podman 4+；主机无需安装 Python、PostgreSQL 或 Redis。
2. 复制 `.env.example` 为 `.env`，逐项替换密码和密钥。`APP_SECRET_KEY`、`POSTGRES_PASSWORD`、`BOOTSTRAP_ADMIN_PASSWORD` 必填，且不能保留示例值。
3. 确认 `env/sites.json` / `env/upstream.json` 已在服务器本地创建；这些文件不会进入镜像或 Git。

```bash
cp .env.example .env
# 编辑 .env 后启动；Compose 文件已为 SELinux 主机的 bind mount 加 :Z 标签。
docker compose up -d --build
docker compose logs -f web
```

Podman 环境可将最后两行替换为 `podman compose up -d --build`、`podman compose logs -f web`。服务就绪后访问 `http://服务器地址:8000/`；请由反向代理统一终止 TLS。数据库迁移由 Web 容器启动时执行。生产环境禁止使用 `docker compose down -v` / `podman compose down -v`，否则会删除 PostgreSQL 与 Redis 持久卷。

### Kubernetes

`deploy/k8s/` 提供 PostgreSQL 18 / Redis 8 StatefulSet、Web Deployment、PVC、就绪/存活探针、Ingress 和 Kustomize 清单。先将两个 `ghcr.io/replace-me/na-xm:container` 镜像占位符换成实际镜像，并确认集群已有默认 StorageClass 和 NGINX Ingress Controller。

```bash
# 机密文件只在部署机生成，绝不提交。
cp deploy/k8s/secret.example.yaml deploy/k8s/secret.yaml
# 编辑 secret.yaml：POSTGRES_PASSWORD 与 DATABASE_URL 中的密码必须一致。
kubectl apply -f deploy/k8s/namespace.yaml
kubectl apply -f deploy/k8s/configmap.yaml
kubectl apply -f deploy/k8s/secret.yaml
kubectl apply -f deploy/k8s/postgres.yaml
kubectl apply -f deploy/k8s/redis.yaml
kubectl apply -f deploy/k8s/web.yaml
kubectl apply -f deploy/k8s/ingress.yaml
```

Web Pod 的 initContainer 会执行 `alembic upgrade head`，因此只有数据库可用后应用才会启动。生产集群请额外配置 PostgreSQL 备份、镜像仓库拉取凭据、TLS 证书和资源配额；示例 PVC 并不等同于备份策略。

---

## 网站账户、权限与安全

网站层保留原有 Flask 单体与业务 API，但新增了本地网站账户。New API / 云厂商凭据与网站登录账户相互独立，密码不会写入日志或审计详情。

### 角色矩阵

| 权限来源 | 超管 | 管理员 | 用户 |
| --- | --- | --- | --- |
| 功能模块 | 全部功能固定可用 | 智能提取 + 超管批准的额外功能 | 默认仅智能提取 |
| 用户管理（创建账户、重置密码、功能权限、启停、删除） | 可管理 | 不可管理 | 不可管理 |

新注册账户默认角色为「用户」，只拥有「智能提取」。超管在「管理用户」中逐账户开通或取消工作台、批量配置、平台信息、数据汇总、上游信息、上游账单、一表总览和智能体等额外功能；只要拥有任一额外功能，角色就自动变为「管理员」，取消全部额外功能后回到「用户」。超管自身固定拥有全部功能。

普通用户或管理员可从右上角账户菜单进入「申请功能权限」，选择模块并查看简要说明后通知超管 admin。超管菜单会显示待处理申请数，并可在用户管理页逐项批准或拒绝；批准时可只开通申请中的部分功能。权限同时保护导航、iframe、工作台动态内容、页面路由和 API，不能通过直接访问 URL 绕过。

工作台仅在账户没有任何可见功能栏目时显示「尚未分配功能权限」提示；超管拥有全部功能，因此不会看到该提示。功能权限加载完成后，界面按账户权限显示栏目，并隐藏无权限的提示和内容。

工作台摘要也按能力拆分：每个账户只会收到并渲染已授权模块的数据和产物；未授权的总览/分析、账单、智能体任务及卫生策略不会返回给该账户。通用产物接口按 `kind` 授权（数据汇总/余额、上游、总览/分析、账单、使用日志分别归属对应功能），专用下载接口还会验证所选文件的真实类型，不能通过手工拼接 `file` 参数跨栏目下载。

### 首个超管与用户管理

首次生产部署时，将 BOOTSTRAP_ADMIN_PASSWORD 与可选 BOOTSTRAP_ADMIN_EMAIL 写入 .env 或 Kubernetes Secret。首次迁移后系统只会创建一次保留账户 admin，角色为 superadmin；它不可通过注册页面创建，也不可被降权、停用或删除。本机 Windows 的 run.bat 会在没有该配置时自动生成随机初始密码并在控制台显示一次；Docker 或 Kubernetes 生产部署不会自动生成密码，仍必须显式注入 Secret。初始超管首次登录后会被强制跳转到账户设置页修改初始密码，修改前无法调用业务 API。

注册页只能创建 `user` 角色，默认仅开通智能提取。超管在右上角账户菜单的“管理用户”页面可处理权限申请、创建普通用户或管理员、修改其他用户密码、逐账户勾选功能权限、启用、停用或软删除账户；额外功能权限会自动决定管理员角色，不能通过角色下拉直接授予管理员或超管。该页使用独立的全宽数据工作区：桌面显示完整用户表，手机端自动转为逐用户操作卡。软删除会立即使会话失效并保留审计痕迹；超管不能修改自己。测试或重置部署环境时，只有在删除网站数据库后才会重新触发引导超管创建。超管创建的其他用户和重置密码后的用户不需要强制修改初始密码，可直接进入控制台；新密码应通过安全渠道告知用户，并建议用户登录后自行修改。

### 认证与安全边界

- 密码使用 **Argon2id** 哈希；连续 5 次失败会锁定账户 15 分钟。
- 生产环境仅接受 PostgreSQL `DATABASE_URL` 与 Redis `REDIS_URL`；Redis 保存服务端会话，Cookie 为 `HttpOnly`、`SameSite=Lax`、`Secure`。
- `alembic.ini` 保留无凭据的 SQLite 本地回退，注释使用 ASCII 以兼容 Windows 系统区域编码。本地开发启动时会自动执行 Alembic 迁移，更新已有 SQLite 账户库；容器入口与 Kubernetes initContainer 也会执行迁移。生产仍必须配置 PostgreSQL 与 Redis；真实 `DATABASE_URL` 只能通过环境变量或 Secret 注入，不能写入 Git。
- 所有写 API 需要会话和 `X-CSRF-Token`；页面表单使用同源 CSRF 令牌。前端脚本会自动附带该头。
- `/api/*` 使用显式功能映射；未登记的新 API 默认拒绝，而不会自动继承“批量配置”权限。页面、iframe 和 API 均独立验证，不能通过直接访问 URL 绕过。
- 工作台的“退出登录”使用同源 `POST /logout` 及 CSRF 令牌清除会话；仅在服务端确认退出成功后跳转至 `/login`，不会返回仍受会话保护的工作台。
- 注册成功、修改密码成功或忘记密码成功时，系统会生成一份**12 位恢复验证码**（格式如 `ABCD-EFGH-JKLM`），明文仅在当次页面显示；数据库只保存 Argon2id 哈希。忘记密码必须同时提交账户与恢复码，连续 5 次失败会锁定该恢复码 15 分钟；成功后旧码立即失效并换发新码。
- 网站账户不再发送注册验证或密码重置邮件，也不需要配置 `SMTP_*`、`WEB_PUBLIC_URL` 或 `REQUIRE_EMAIL_VERIFICATION`。历史邮件链接只会跳转到恢复验证码页面，不能作为重置凭据。
- 功能权限申请与审批、功能权限变更、启停和删除均写入 `web_audit_logs`。默认网站数据库在开发模式位于 `.cache/website.db`，生产必须执行 Alembic 迁移到 PostgreSQL。

### 登录、注册与恢复验证码

- 登录、注册、密码找回和账户设置共用一套 NA 浅色认证主题，支持用户名或邮箱、显示/隐藏密码、错误提示及恢复入口；桌面、移动端与低高度窗口均使用完整可滚动视口，关键按钮不会被页面底部裁切。
- 注册完成后先保存屏幕上展示的恢复验证码，再进入登录。恢复码不是邮件验证码、不会发到邮箱，也不能通过管理员日志找回；遗失时需使用仍可登录的账户在「账户设置」中重新生成，或由超管按组织流程处理。
- 忘记密码页一次完成账户识别、恢复码验证和新密码设置。验证码可含或不含连字符，大小写不敏感；更新密码、或在账户设置中**验证当前登录密码后**换发恢复码，都会立即作废旧码。

---



## 界面说明


| Tab          | 内容                           | 页面文件 / 路由                                                                   |
| ------------ | ---------------------------- | ---------------------------------------------------------------------- |
| **工作台**     | 待办、最近产物、六任务卡、全局站点认证 | `static/index.html` 本页；hash `#workspace`（默认） |
| **智能提取**   | 渠道/令牌模式切换、原始输入、LLM（仅渠道）、提取结果、一键填入 | `static/index.html`；hash `#extract` |
| **批量配置**   | 连接配置、渠道/令牌/分组/启停/使用日志 | `batch/static/index.html`（iframe 经 `/static/batch_ui.html?embed=1` 代理）；hash `#write` |
| **平台信息**   | test / uat / prod 的 ai-cloud / New API 渠道管理、令牌管理列表；分页、悬浮复制、完整记录编辑、测试/启停/删除、批量配置转换 | `static/platform_ui.html`（iframe 经 `/static/platform_ui.html?embed=1` 代理）；hash `#platform` |
| **数据汇总**   | 多站点采集、渠道余额查询、Excel 导入/导出、历史产物下拉 | `static/summary_ui.html`（iframe `?embed=1`）；hash `#inventory` |
| **上游信息**   | 云厂商上游采集（一键汇总 / 火山云 / Azure OpenAI）、历史产物下拉；导出表头可筛选 | `static/upstream_ui.html`（iframe `?embed=1`）；hash `#upstream` |
| **上游账单**   | 账期起止采集火山云 / Azure 费用（跨月则每月一份；一键汇总或分厂商）；导出表头可筛选 | `static/bill_ui.html`（iframe `?embed=1`）；hash `#bill` |
| **一表总览**   | 网关 + 两侧上游合成总览；智能分析；页内建议表（筛选、全选/反选、预禁用）；卫生策略 | `static/overview_ui.html`（iframe `?embed=1`）；hash `#hygiene` |
| **智能体** | 异步任务、计划画布、提取门禁、取消/重试、连接与站点对齐 | `static/agent_ui.html`（iframe `?embed=1`）；hash `#pipeline` |


九个顶栏入口共用同一后端 `app.py`（端口 `8765`），无需启动多个服务。顶栏文案为原模块全称、**不带序号**。顺序：工作台 → 智能提取 → 批量配置 → **平台信息** → 数据汇总 → 上游信息 → **上游账单** → 一表总览 → 智能体。Tab 与主题按钮之间有一句 5–10 字短句，**每次刷新随机更换**（窗口较窄时隐藏）。内部 hash 兼容旧名（`#extract` / `#write` / `#inventory` / `#hygiene` 等）。

> **静态资源代理**：`app.py` 将 `/static/batch_ui.html` 映射到 `batch/static/index.html`；`?embed=1` 会隐藏批量页顶部 Hero 区。



### 浏览器本地缓存（localStorage）


| 键名                           | 用途                                         |
| ---------------------------- | ------------------------------------------ |
| `na_ui_theme`                | 明暗主题（`dark` / `light`），右上角切换按钮持久化          |
| `na_agent_llm_config`        | 智能提取页 LLM 配置（仅渠道模式）                      |
| `na_extract_mode`            | 智能提取模式：`channel` / `token`                 |
| `na_batch_connection_config` | 批量配置连接信息（优先级高于 `batch/config.json`）        |
| `na_data_summary_sites`      | 数据汇总站点列表；若为空且存在 `env/sites.json` 则自动填入 |
| `na_flow_progress`           | 历史键：曾记录提取/批量/汇总链式完成状态；顶栏已不再显示步骤圆圈，可忽略 |
| `na_onboarding_dismissed`    | 首次引导是否已关闭                                  |


---



## 工作台

打开应用默认进入顶栏 **工作台**（`#workspace`）。待办数字来自最新智能分析表与盘点产物；**没有对应 Excel 时不显示假 0**，卡片会引导先去做数据汇总或一表总览分析。

| 区域 | 说明 |
| ---- | ---- |
| 待办 | 待处置高优先级条数、宽限期暂缓条数、进行中智能体任务数；无分析表时提示去生成 |
| 最近产物 | `GET /api/workspace/summary` 返回的最新数据汇总 / 上游 / 账单 / 总览 / 分析文件名与时间。橙色 **含密钥** 仅当「密钥 / API Key」等列**单元格有值**（空列、`N/A`、分析表密钥摘要不算） |
| 任务卡 | **新项目接入** → 智能提取；**例行盘点** → 数据汇总；**上游采集** → 上游信息；**上游账单** → 账单页；**卫生清理** → 一表总览（可带分析表 id）；**智能体跑通** → 智能体 |
| 认证与策略 | **全局站点认证**（见下）；卫生策略可在此编辑，或跳到总览 |
| 环境芯片 | 按 `env/sites.json` **已配置站点**显示。标签用集群名（**生产** / **非生产**）；历史 key 仍可能是 test / uat / prod。芯片：已认证 / 需临时验证码 / TOTP 已预置 / 需手填验证码 |
| 顶栏短句 | Tab 右侧一句 5–10 字，刷新随机换一条，不重复上一句 |

数据接口：`GET /api/workspace/summary`（`env_sites[]` 含 `session_ready`、`cluster`）。卫生策略摘要一并返回，完整读写见 [工作台 / 产物 / 卫生策略 API](#工作台--产物--卫生策略-api)。

旧版顶栏步骤圆圈已隐藏。智能体计划画布里的步骤标签仍可用于勾选流水线，那不是顶栏 Tab 名。

### 全局站点认证

工作台「认证与策略」里的 **全局站点认证**，按已配置站点登录并写入约 **2 小时**会话缓存（进程内 + 磁盘），**不**把 TOTP 密钥下发到浏览器。

1. 点 **全局站点认证** 打开抽屉，查看各站芯片状态
2. 点 **认证全部** → `POST /api/workspace/auth`。已预置 `totp_secret` 的站点自动出码；无 TOTP 且未认证的站点显示临时 6 位码输入（约 30 秒有效）
3. 成功后芯片为 **已认证**。之后数据汇总、一表总览拉密钥时，会话或 TOTP 已就绪则**跳过审查弹窗**，仅仍 `needs_otp_prompt` 的站点再要 30 秒码

也可点「去批量配置」用手填连接。Access Token 站点一般不需要登录 OTP。审查接口仍会调用 `POST /api/data-summary/inspect-auth`（只看缓存是否还活，不无故打网关登录）。

### 产物列表刷新

各业务 Tab 多为 iframe，历史下拉原先只在首次进入时拉 `GET /api/artifacts`。现在：

- 采集 / 导出成功后，子页调用 `notifyArtifactsChanged(kinds)`，父页广播 `na-artifacts-changed` 给所有 `iframe.na-iframe`，并刷新工作台摘要
- 切 Tab 时会对当前 iframe 再发一次
- 数据汇总、上游信息、上游账单、一表总览、批量·使用日志的历史下拉旁有 **刷新**；工作台本身有刷新按钮

不必为了看到刚导出的文件而整页重载。

---



## 主题切换

顶栏**右上角**提供主题按钮，可在**暗色**与**明亮**两套 UI 间切换：


| 主题         | 风格                |
| ---------- | ----------------- |
| **暗色**（默认） | 赛博深空、青色光晕、半透明玻璃面板 |
| **明亮**     | 日间纸感、白卡片、靛蓝强调色    |


- 偏好保存在 `localStorage`（`na_ui_theme`）
- **批量配置 / 数据汇总 / 智能体 / 上游信息 / 上游账单 / 一表总览** iframe 通过 `postMessage` 实时同步主题，无需刷新
- 相关文件：`static/na-theme.css`、`na-theme.js`、`na-components.css`、`na-ui.js`
- 批量页嵌入时使用 `na-legacy-bridge.css` 桥接旧版样式

---



## 目录结构

> `ai-cloud-master/`（以及其他 `ai-cloud*` / `ai-could*` 目录）为本机上游参考源码，**不属于本工具公开仓库**；`docs/` 与 `.cursor/` 也仅保留在本机，不会提交到 GitHub。部署与开发时均可忽略这些目录。

```text
NA_xm_auto_configuration_new/
├── app.py                          # 融合 Web 服务（唯一入口，支持 serve/extract/batch 子命令）
├── run.bat / run.sh                # 一键启动脚本
├── requirements.txt
├── Dockerfile / compose.yaml        # Web + PostgreSQL 18 + Redis 8 容器部署
├── .env.example                     # 生产环境变量模板（不含真实凭据）
├── alembic.ini / migrations/        # 网站账户与恢复验证码数据库迁移
├── README.md
│
├── env/                            # 多环境快捷连接 + 上游凭证（可选）
│   ├── sites.example.json          # 模板：复制为 sites.json 后填写
│   ├── sites.json                  # 真实凭据（勿提交，gitignore）
│   └── upstream.json               # 可选：独立上游凭证（优先于 sites.json 的 upstream.volc / upstream.azure）
│
├── static/                         # 融合首页与主题（必须）
│   ├── index.html                  # 主导航 + 智能提取
│   ├── summary_ui.html             # 数据汇总
│   ├── agent_ui.html               # 智能体
│   ├── upstream_ui.html            # 上游信息
│   ├── bill_ui.html                # 上游账单
│   ├── overview_ui.html            # 一表总览
│   ├── na-theme.css                # 统一 UI 主题（含明暗两套）
│   ├── na-components.css           # 步骤条、Toast、空状态等组件
│   ├── na-ui.js                    # Toast、步骤状态、首次引导
│   ├── na-legacy-bridge.css        # 批量页 embed 样式桥接
│   ├── na-theme.js                 # 主题切换与 iframe 同步
│   ├── auth-shell.js               # 会话感知、导航授权与 API CSRF 头
│   ├── auth-pages.css              # 自适应登录 / 注册 / 恢复码页面样式
│   ├── auth-pages.js               # 密码显隐与恢复码复制交互
│   └── favicon.svg                 # 浏览器图标（N Logo）
│
├── templates/                      # 登录、注册、恢复码重置、账户、超管用户管理
├── webapp/identity.py              # 账户、Argon2 恢复码、RBAC、审计与 CSRF
├── deploy/k8s/                     # K8s StatefulSet / Deployment / Ingress 模板
├── tests/test_web_identity.py      # 网站账户与权限回归测试
│
├── docs/                           # 产品介绍（可选阅读）
│   ├── introduction.html           # 功能介绍页
│   ├── README.md                   # 文档说明
│   └── presentation/               # 18 页 HTML 演示稿 + PPT/PDF 导出
│
├── pipeline_runner.py              # 智能体分步流水线（短路 / 门禁 / 求交）
├── agent_jobs.py                   # 智能体异步任务状态机 + SSE 事件
│
├── excel/                          # 全站 Excel 存放目录（自动生成；导出走浏览器下载）
│   ├── ai网关令牌及渠道列表_YYYYMMDDHHmmss.xlsx
│   ├── ai网关令牌及渠道列表_一表总览_YYYYMMDDHHmmss.xlsx
│   ├── 智能分析表格_YYYYMMDDHHmmss.xlsx
│   ├── 渠道余额_YYYYMMDDHHmmss.xlsx
│   ├── usage_logs_YYYYMMDD_HHMMSS.xlsx
│   ├── 上游信息_汇总_YYYYMMDDHHmmss.xlsx
│   ├── 上游信息_火山云_YYYYMMDDHHmmss.xlsx
│   ├── 上游信息_Azure_YYYYMMDDHHmmss.xlsx
│   ├── 上游账单_汇总_9月_YYYYMMDDHHmmss.xlsx
│   ├── 上游账单_火山云_9月_YYYYMMDDHHmmss.xlsx
│   └── 上游账单_Azure_9月_YYYYMMDDHHmmss.xlsx
│
├── log/                            # 启动会话日志（自动生成）
│   └── na_YYYYMMDD_HHMMSS_serve_pidXXXX.txt
│
├── na_logger.py                    # 按次启动文件日志
├── agent/                          # 智能提取（必须）
│   ├── main.py
│   ├── config.example.json
│   ├── lib/
│   │   ├── channel_extractor.py
│   │   ├── token_extractor.py      # 令牌智能提取（名-人拼接 / 渠道行转令牌）
│   │   ├── channel_line_parser.py  # 完整行 + 紧凑行（无重定向）解析
│   │   ├── rule_extractor.py
│   │   ├── block_parser.py
│   │   ├── text_splitter.py
│   │   ├── llm_client.py / llm_agent.py
│   │   ├── formatter.py / patterns.py
│   │   ├── group_deriver.py        # 分组截到环境段；模型列 ASCII 核心
│   │   ├── type_registry.py
│   │   └── pipeline_llm.py         # 智能体 LLM 规划器
│   └── tests/
│       ├── test_cli.py
│       ├── test_llm_enhance.py
│       ├── test_channel_line_parser.py
│       ├── test_extract_for_update.py
│       ├── test_token_extractor.py
│       ├── test_group_deriver.py
│       ├── test_pipeline_llm.py
│       ├── test_pipeline_runner.py
│       └── test_agent_auth_refresh.py
│
├── batch/                          # 批量配置（必须）
│   ├── main.py
│   ├── config.example.json
│   ├── lib/
│   │   ├── api_client.py           # NA HTTP 客户端（会话缓存 / 429 重试 / SSL）
│   │   ├── totp.py                 # TOTP：原始密钥 → 当前 6 位码
│   │   ├── batch_processor.py      # 渠道批量创建
│   │   ├── channel_batch_update.py # 渠道预更新 / 确认更新（原配置）
│   │   ├── channel_batch_delete.py # 渠道预删除 / 确认删除
│   │   ├── channel_batch_status.py # 按上游/类型/ID/名称+分组 启停渠道
│   │   ├── channel_balance_query.py# 渠道已用/剩余余额查询
│   │   ├── channel_types.py        # 渠道类型清单
│   │   ├── token_batch_processor.py
│   │   ├── token_batch_delete.py / token_batch_status.py / token_export.py
│   │   ├── group_batch_processor.py
│   │   ├── log_exporter.py         # 使用日志导出（分页 / 可取消）
│   │   ├── data_summary.py         # 采集、重复检测、字段映射
│   │   ├── data_summary_exporter.py# Excel 读写、样式、时间戳命名
│   │   ├── upstream_volc.py        # 火山云 OpenAPI 采集
│   │   ├── azure_arm.py            # Azure ARM 客户端（Token + Cognitive Services）
│   │   ├── upstream_azure.py       # Azure OpenAI 采集
│   │   ├── upstream_exporter.py    # 上游信息 Excel（表头筛选、首行冻结）
│   │   ├── volc_billing.py         # 上游账单 · 火山云费用中心
│   │   ├── azure_billing.py        # 上游账单 · Azure Cost Management
│   │   ├── bill_combined.py        # 上游账单汇总（四张费用表）
│   │   ├── overview_exporter.py    # 一表总览（网关表 + 两侧上游）
│   │   ├── overview_analyzer.py    # 智能分析（上下游对照、渠道余额、新部署放宽）
│   │   ├── hygiene_policy.py       # 卫生策略
│   │   ├── hygiene_actions.py      # 页内预禁用
│   │   └── url_utils.py            # 站点地址规范化
│   ├── static/                     # 批量配置 UI（含渠道启停）
│   └── tests/
│       ├── test_data_summary.py
│       ├── test_data_summary_exporter.py
│       ├── test_channel_batch_status.py
│       ├── test_channel_batch_update.py
│       ├── test_channel_batch_delete.py
│       ├── test_token_batch_status.py
│       ├── test_channel_balance_query.py
│       ├── test_overview_exporter.py
│       ├── test_overview_analyzer.py
│       ├── test_upstream_volc.py
│       ├── test_upstream_azure.py
│       ├── test_deploy_time.py
│       ├── test_volc_billing.py
│       ├── test_azure_billing.py
│       └── test_bill_combined.py
│
└── examples/                       # CLI 样例（Web 不依赖）
    ├── agent/                      # 智能提取
    │   ├── volcano/input.txt
    │   ├── volcano-upgrade/input.txt  # 自动升级申请（无密钥）
    │   ├── azure/input.txt
    │   ├── custom/input.txt
    │   └── multi/input.txt
    └── batch/                      # 批量配置（与 batch/static/example_* 内容对齐）
        ├── mixed/input.tsv         # 混合渠道
        ├── azure/input.tsv         # 纯 Azure
        ├── tokens/input.txt        # 令牌批量
        └── groups/input.txt        # 分组批量
```


| 路径                          | Web 运行 | 说明                     |
| --------------------------- | ------ | ---------------------- |
| `app.py`                    | **必须** | 唯一服务入口                 |
| `static/`、`agent/`、`batch/` | **必须** | 九个顶栏入口全部依赖             |
| `examples/`                 | 可选     | CLI / 联调样例，Web 不依赖     |
| `excel/`                    | 自动生成   | **全站导出存放目录**：数据汇总网关汇总（`ai网关令牌及渠道列表_时间戳.xlsx`）、一表总览（`ai网关令牌及渠道列表_一表总览_时间戳.xlsx`，与数据汇总互不覆盖）、智能分析（`智能分析表格_时间戳.xlsx`，不覆盖总览）、渠道余额、使用日志、上游信息、**上游账单**（`上游账单_汇总_9月_时间戳.xlsx` / `_火山云_9月_` / `_Azure_9月_`，月份为账期）。每次新建时间戳文件；数据汇总「继续补全密钥」只更新最新一份**网关汇总**；一表总览「继续补全密钥」只更新最新一份**总览**（不改分析表）。页面「下载 Excel / 下载分析表」由浏览器下载，不改磁盘文件 |
| `log/`                      | 自动生成   | **每次启动**一个详细审查用 `.txt` |
| `ai-cloud*/`、`ai-could*/`、`docs/`、`.cursor/` | **排除** | 本机上游参考源码、文档与编辑器资源，不提交公开仓库 |
| `.cache/`、`.venv/`、`venv/`、`ENV/`、`.pytest_cache/` 等 | **排除** | 本地缓存、Python 虚拟运行环境与测试/静态检查缓存；保留项目 `env/` 中的示例配置 |


---



## Excel 存放与浏览器下载

全站需要导出的表格**一律写入项目根下的 `excel/`**（只做存放，不覆盖历史时间戳文件）。采集 / 导出过程中**不会**自动触发浏览器下载；只有点击「下载 Excel」或一表总览的「下载分析表」才会下载**已写完的完整文件**。数据汇总、上游信息、上游账单、一表总览页提供**产物下拉**（默认选最新一份），下载与智能分析须把所选文件 id 传给 API，**禁止静默 latest**（脚本可用 `allow_latest=1` 显式放开）。同名前缀多份按**文件名时间戳**取最新，不以资源管理器修改时间为准。下载二次确认只针对**单元格里真有密钥**的文件（有「密钥」列但全空不算）。


| 入口 | 生成按钮 | 下载按钮 | 磁盘文件名 |
| ---- | -------- | -------- | ---------- |
| 数据汇总 | 「一键采集并写入 Excel」 | 「下载 Excel」（全部站点写完后再点） | `ai网关令牌及渠道列表_YYYYMMDDHHmmss.xlsx`（不含带 `_一表总览_` 的总览文件） |
| 渠道余额 | 「导出 Excel」（查询结果分表） | 「下载 Excel」（最新一份余额表） | `渠道余额_YYYYMMDDHHmmss.xlsx` |
| 使用日志 | 「导出使用日志」 | 「下载 Excel」（最新一份，xlsx 或 csv） | `usage_logs_YYYYMMDD_HHMMSS.xlsx` |
| 智能体 · 汇总步 | 任务内汇总 | 「下载数据汇总」 | 与数据汇总网关汇总相同 |
| 智能体 · 上游/总览/分析 | 勾选上游信息、一表总览/分析后任务内生成 | 「下载上游」「下载总览」「下载分析表」 | 与汇总表、总览、智能分析表相同 |
| 一表总览 | 「一键生成总览表」/「智能分析」 | 「下载 Excel」总览；「下载分析表」 | `ai网关令牌及渠道列表_一表总览_时间戳.xlsx`；分析为 `智能分析表格_时间戳.xlsx` |
| 上游汇总 | 「一键采集全部上游」 | 「下载汇总 Excel」 | `上游信息_汇总_YYYYMMDDHHmmss.xlsx`（工作表：火山云、Azure OpenAI） |
| 上游火山云 | 「一键采集火山云」 | 「下载 Excel」 | `上游信息_火山云_YYYYMMDDHHmmss.xlsx` |
| 上游 Azure OpenAI | 「一键采集 Azure OpenAI」 | 「下载 Excel」 | `上游信息_Azure_YYYYMMDDHHmmss.xlsx` |
| 上游账单汇总 | 「一键采集全部账单」 | 「下载汇总 Excel」 | `上游账单_汇总_9月_YYYYMMDDHHmmss.xlsx`（跨月则每月一份；月份为账期，不补零；工作表：火山云-按天 / 火山云-按月 / Azure-按天 / Azure-按月） |
| 上游账单火山云 | 「一键采集火山云」 | 「下载 Excel」 | `上游账单_火山云_9月_YYYYMMDDHHmmss.xlsx`（跨月则每月一份；工作表：按天 / 按月） |
| 上游账单 Azure | 「一键采集 Azure OpenAI」 | 「下载 Excel」 | `上游账单_Azure_9月_YYYYMMDDHHmmss.xlsx`（跨月则每月一份；工作表：按天 / 按月） |


接口：`GET /api/artifacts?kind=`、`GET /api/artifacts/download?file=`（或 `id=`）；以及 `GET /api/data-summary/download`、`POST /api/channel-balance-export`（只落盘）、`GET /api/channel-balance/download`、`GET /api/logs-export/download`、`GET /api/overview/download`、`GET /api/overview/analyze/download`、`GET /api/upstream/download`、`GET /api/upstream/volc/download`、`GET /api/upstream/azure/download`、`GET /api/upstream/bill/download`、`GET /api/upstream/azure/bill/download`、`GET /api/upstream/bill/combined/download`（均可带 `?file=` / `?id=` 指定产物）。

---



## 推荐工作流



### 流程 A：渠道提取 → 批量创建

1. **智能提取**：确认模式为「渠道智能提取」，粘贴杂乱信息或已格式化渠道行
2. （可选）勾选「启用 LLM 增强」并配置 AI
3. 点击「智能提取」→「填入批量配置 →」
4. **批量配置**：测试连接 → 渠道管理 → 开始批量创建

### 流程 A2：令牌提取 → 批量创建

1. **智能提取**：切换到「令牌智能提取」
2. 粘贴令牌草稿，任选其一：
   - 三行/四行：`令牌名-人名` / 分组 / 模型列表
   - **渠道行转令牌**：令牌名（人名可分行）+ 已提取好的渠道批量行（见 [渠道行转令牌](#渠道行转令牌)）
   - 或点击示例卡片（含「渠道行转令牌」）
3. 「智能提取」→「填入令牌管理 →」（写入批量配置令牌文本框，非渠道框）
4. **批量配置 → 令牌管理**：测试连接 → 开始批量创建令牌；智能提取会自动把块内单独的纯数字行识别为第 4 列 `额度(tokens)`，也可在每行末尾手工补列

> 令牌提取为纯规则，**不调用 LLM**；高级选项面板在令牌模式下会隐藏。  
> 典型链路：先用渠道模式提取渠道行 → 再切到令牌模式，贴上令牌名与渠道行，一键生成令牌模型限制。

### 流程 A3：火山自动升级 → 更新原配置

火山方舟 / 豆包等上游可能**自动升级模型版本**（例如 GLM-4.7 → GLM-5.2）。未收到升级申请单时，**不要改 AI 网关配置**；网关汇总表只反映当前登记，实际调用以上游当前版本为准。收到申请后：

1. **智能提取**：渠道模式，粘贴升级申请或点示例「火山自动升级」
2. 先点「智能提取」右侧的 **「更新」**（按钮亮起），再点 **「智能提取」**（此模式**不要求密钥**）
3. 「填入更新原配置 →」（写入渠道文本框并滚到更新区；**不要**点「开始批量创建」）
4. **渠道管理**：测试连接 → **预更新** → **确认更新**

> 默认「智能提取」（未点「更新」）仍按**创建**处理，缺密钥会失败，避免误走更新逻辑。  
> 更新按 **名称 + 分组** 匹配已有渠道，覆盖模型与「模型→上游」映射；**不修改密钥**。

### 流程 B：直接批量

- **Web**：进入 **批量配置**，手动粘贴或「载入示例」/「导入文件」
- **CLI**：配置 `batch/config.json` 后执行  
  `python app.py batch -c batch/config.json -f examples/batch/mixed/input.tsv`  
  （更多样例见 [Batch CLI](#batch-cliexamplesbatch)）

### 流程 C：多站点数据汇总

1. **数据汇总**：填写已配置站点（若已配置 `env/sites.json` 会自动识别填入；也可点「从 env 载入」）。各站可预置 `totp_secret`。建议先在工作台做一次 [全局站点认证](#全局站点认证)
2. （可选）勾选「包含渠道密钥」（含密钥采集同样**新建**一份 Excel）
3. 「一键采集并写入 Excel」→ 会话或 TOTP 已就绪则**跳过审查弹窗**；仅无 TOTP 且未认证的站点弹 30 秒临时码 → 成功后**新建**带时间戳文件到 `excel/`（同一次多站写入同一份）。全部写完后再点「下载 Excel」取完整文件
4. 若密钥因限流未拉完：点「继续补全密钥」→ 同样跳过已就绪站点的弹窗；未预置 TOTP 的站点再弹窗 → 更新 **excel/ 下最新一份**（无文件时请先采集）



### 流程 D：导出使用日志

1. **批量配置 → 使用日志**：测试连接，选择时间范围与筛选条件（默认「今天」；模型名支持模糊）
2. 导出格式默认 **Excel（.xlsx）**（含内外框；全空列自动剔除）；亦可选 CSV
3. 「导出使用日志」→ 页面显示 **已拉取 x / y** 进度；可点红色「终止」
4. 完成后写入 `excel/usage_logs_*.xlsx`（或 csv）；再点「下载 Excel」取完整文件

> NA 列表接口每页最多 **100** 条；翻页间隔约 **1 秒**（请求已超过间隔则不再空等）。Flask 在 Windows 上会缓冲长连接，因此导出改为后台任务 + 轮询，避免进度卡住。

### 流程 E：按上游模型 / 类型启停渠道

1. **批量配置 → 渠道启停**：测试连接，选择渠道类型（默认「自定义渠道」）
2. **类型全部禁用 / 启用**：对该类型下全部渠道一键操作（需确认）
3. 或填写上游模型 →「按上游模型加载」；或「加载类型清单」查看可视化列表
4. 清单内 **全选 / 反选**，再「禁用所选 / 启用所选」；也可对单行点启用/禁用

### 流程 E2：多站点查询渠道已用 / 剩余余额

1. **数据汇总**：配置已填写的站点卡片（历史 key 仍可能是 test / uat / prod）
2. 下方 **渠道余额查询**：勾选「已用」和/或「剩余」，点选常用区间；可选 **配置时间段**（全部 / 1、3、5、15、30、60、180、365 天，或自定义起止）
3. 「多站点查询余额」→ 工作台会话或 TOTP 已就绪则直接查；仅缺码站点弹 30 秒临时码 → 结果含环境列；可排除已禁用 / 全选 / 反选
4. 「导出 Excel」→ 写入 `excel/渠道余额_时间戳.xlsx`（不自动下载）；工作表按环境命名（如 `test-渠道余额`、`uat-渠道余额`、`prod-渠道余额`）。再点「下载 Excel」取完整余额表



### 流程 F：全流程智能体（异步工作台）

1. **智能体**：填写原文、LLM。NA 连接与汇总站点可从 `env/sites.json` 取账号密码与 `totp_secret`（页面可留空；也可点已配置站点快捷按钮或「从 env 载入」）。也可先工作台 [全局站点认证](#全局站点认证)。未预置密钥时再填登录 2FA
2. 建议先点「测试连接」建立会话缓存；勾选步骤（提取 / 渠道 / 令牌 / 汇总默认开；上游、总览、智能分析默认关）；可选试运行
3. 只跑 上游信息、一表总览/分析时请**取消勾选提取**（空原文会在提取步失败）。总览只从已有数据汇总、上游信息文件提取，**不含**渠道明文密钥
4. 「启动智能体」→ SSE 推送时间线；**已预置 TOTP 时门禁可留空**，否则请在确认前填认证器当前验证码（提取可能超过 30 秒，旧码会过期）
5. 完成后按步骤下载：**下载数据汇总** / **下载上游** / **下载总览** / **下载分析表**
6. 失败可「从失败步重试」，重试时同样带上最新验证码
7. CI 可用 `POST /api/agent/run`（默认同步、跳过门禁，请求体可带 `connection.otp_code`）

适合：需要可控一键上线、人工复核渠道后再写入，或把数据汇总、上游信息、一表总览也串进同一任务的场景。上游信息、一表总览 与分析默认关闭。无上游凭证、无数据汇总、上游信息文件、无总览时对应步骤**跳过**，不把整任务打成失败。智能分析规则（含部署未满 10 天放宽）与一表总览页相同。

### 流程 G：采集火山云上游

1. 复制 `env/sites.example.json` 为 `env/sites.json`（或另建 `env/upstream.json`）
2. 按 [火山云 upstream.volc](#火山云-upstreamvolc) 填写 IAM Access Key（`AKLT…`），**不要**填方舟推理 API Key
3. **上游信息**：可点「从 env 载入」→「测试连接」→「一键采集火山云」
4. 点「下载 Excel」：浏览器下载 `excel/上游信息_火山云_时间戳.xlsx`（与数据汇总网关汇总文件分开存放；采集过程不会自动下载）。**最后一列「部署时间」** 来自接入点 `CreateTime`，没有则从部署名 `ep-YYYYMMDDHHmmss` 解析。表头可下拉筛选，首行冻结

Excel **项目方**列按控制台约定写成 `项目名-负责人`（从 IAM `DisplayName` 解析）。控制台只有项目名、没有负责人时填 `N/A`，例如 `demo-research-N/A`。详见 [项目方：项目名-负责人](#项目方项目名-负责人)、[火山云导出列](#火山云导出列)。

凭证获取：<https://console.volcengine.com/iam/keymanage>

### 流程 H：采集 Azure OpenAI 上游

**不要**用 Foundry / OpenAI Studio 里每个项目的模型 API Key，也**不要**给每个账号单独申请 IAM。采集打的是订阅级 ARM，全订阅共用 **一个** Entra 应用注册。

1. 按 [Azure OpenAI upstream.azure](#azure-openai-upstreamazure) 创建 **一个** Entra 应用，记下 `tenant_id` / `client_id` / `client_secret`
2. 在**每一个要采集的订阅** IAM 给该应用分配 **读者** + **认知服务用户**（几个订阅做几遍，详见 [Azure OpenAI 配置与权限](#azure-openai-配置与权限)）
3. 把各订阅 GUID 按内部「订阅1～4」顺序写入 `subscription_ids`：点进该订阅（或其中任一资源），从浏览器**地址栏链接**里 `/subscriptions/` 后面那段 GUID 复制（不要整段 URL、不要订阅显示名；或上游信息页每行一个）
4. **上游信息 → Azure OpenAI**：「从 env 载入」→「测试连接」→「一键采集 Azure OpenAI」
5. 「下载 Excel」：`excel/上游信息_Azure_时间戳.xlsx`（工作表 **`Azure OpenAI`**；与火山云、数据汇总网关汇总分开）。「项目」「负责人」来自账号标记名 `1`：按**最后一个** `-` 拆开（项目名可含多个 `-`，负责人永远在最后一段，如 `AI-Product-金鑫` → 项目 `AI-Product`、负责人 `金鑫`）。**最后一列「部署时间」** 来自 ARM `systemData.createdAt`（东八区），未返回则留空。表头可下拉筛选，首行冻结。详见 [标记 1：项目-负责人1，负责人2](#标记-1项目-负责人1负责人2)、[Azure OpenAI 导出列](#azure-openai-导出列)

改 Python 后须重启 `run.bat`。RBAC 刚加完请等 1～2 分钟再测。

### 流程 I：一次采集火山云 + Azure 汇总表

1. 先按流程 G、H 配好 `upstream.volc` 与 `upstream.azure`（或上游信息页两侧都填好）
2. **上游信息** 顶部「全部上游汇总」：可点「从 env 载入」→ **一键采集全部上游**
3. 服务端依次拉火山云、Azure，写入 **同一文件** `excel/上游信息_汇总_时间戳.xlsx`（工作表 **`火山云`**、**`Azure OpenAI`**，列结构与分厂商导出相同，**最后一列均为部署时间**，表头可筛选）
4. 点「下载汇总 Excel」。一侧失败时仍会保留另一侧已拉到的数据；分厂商按钮仍可单独采集

采集过程不会自动下载。改 Python 后须重启 `run.bat`。

### 流程 J：一表总览（网关 + 两侧上游）

1. 配好 `env/sites.json` 的**已配置站点**（数据汇总用）以及 `upstream.volc` / `upstream.azure`（上游信息用）。若 `excel/` 里已有数据汇总、上游信息结果，也可直接进第 2 步
2. 顶栏 **一表总览** → 在产物下拉中确认要用的网关/上游文件（默认最新）→ **一键生成总览表**
3. **已有文件则提取，没有才连网**：
   - 网关：`ai网关令牌及渠道列表_时间戳.xlsx` 与以往总览里，取**文件名时间戳最新**一份
   - 火山云 / Azure：汇总表、分厂商表、以往总览里，取时间戳最新且该工作表有数据的一份
   - 同名前缀多份（如 `_20260825100000` 与 `_20260825120000`）**永远取数字更大的那份**，不以资源管理器里的修改时间为准
   - 某一侧完全没有可提取文件时，才现场采集该侧
   - **已配置站点默认获取渠道密钥**（需 Root + 二次验证）。工作台已认证或已预置 `totp_secret` 时不再弹审查窗；仅缺码站点要 30 秒临时码
   - 拉密钥会一直请求直到上游 **429** 再停。详细日志会写出每站「已获取 / 仍缺」。等窗口恢复后点 **「继续补全密钥」**（只改最新一份总览，不改数据汇总网关汇总）
4. 每次仍写入**新的** `excel/ai网关令牌及渠道列表_一表总览_时间戳.xlsx`，不覆盖数据汇总、上游信息原文件
5. 点 **智能分析**：读取**所选总览**（请求须带 `source_overview` / `source`），对照火山/Azure 与已配置站点渠道，写入新的 `excel/智能分析表格_时间戳.xlsx`（不覆盖总览、不改网关）。页内 **分析建议** 可筛选、**全选 / 反选** 后 **预禁用**（宽限期内默认跳过，勾「仍要执行」才纳入）；也可仍复制 `批量禁用` 列到批量配置。卫生阈值见 `env/hygiene_policy.json`（页面可改）
   - **下游无上游（高）**：网关已有火山/Azure 渠道，上游找不到对应密钥或部署 → 视为过期/禁用，建议在该站点禁用或删除。**部署时间未满 10 天则降为中**，暂缓禁用
   - **上游无下游（中）**：上游有接入点/部署，已配置站点都没有对应渠道。**部署时间未满 10 天则降为低**
   - 外部渠道（DeepSeek / GLM / 阿里云等）不对照过期；分析表只写密钥摘要。**有** `excel/渠道余额_时间戳.xlsx` 时：已用 = $0 视为不用，已用 < $1 视为不常用；**不常用且近一月无活跃升为中**（可进批量禁用）；新部署未满 10 天时不用从中降为低。**没有该文件则不识别用量**。新余额表含「近一月活跃」时，**全部模型近一月无活跃**才允许用量类禁用；任一模型有活跃或 N/A 则只记在分析表「渠道余额」，**不进建议处置、不禁渠道/令牌**（旧余额表无该列时不常用仍为低）。分析表 `建议处置` 只含尚未禁用的项；渠道和相关令牌均已禁用的写入 `已禁用建议`。再右侧为 `批量禁用`：按 test/uat/prod 给出渠道、令牌粘贴列；一条令牌挂多条渠道、只有一条不用时**只禁那条渠道，不牵连令牌和其它渠道**。匹配规则与各工作表见 [智能分析（上下游密钥）](#智能分析上下游密钥)
6. 「下载 Excel」取下拉所选总览；「下载分析表」取所选分析文件
   - 与数据汇总的 `ai网关令牌及渠道列表_时间戳.xlsx` **不是同一份**：中间多了 `_一表总览_`；数据汇总「下载 Excel / 继续补全密钥」也不会把它当成网关汇总
   - 工作表 **`总览`**：其余各表名称与行数
   - 原有各环境「渠道管理 / 令牌管理」及重复对照表
   - **`火山云`**、**`Azure OpenAI`**（列结构与相同，含 Azure「项目」「负责人」，**最后一列为部署时间**）

改 Python 后须重启 `run.bat`。网关登录若开了 2FA，请在 `sites.json` 预置 `totp_secret`，或先在工作台做 [全局站点认证](#全局站点认证)。

### 流程 K：采集上游账单

与「上游信息」（资源清单）分开：账单页按**账期**拉费用，不改网关、不需要 NA 验证码。凭证与上游信息相同（`upstream.volc` / `upstream.azure`）。

1. 配好火山 IAM、Azure 服务主体（流程 G / H）。Azure 账单额外需要每个订阅 IAM 给该应用加 **成本管理读取者（Cost Management Reader）**，可与上游信息已有的「读者」并存
2. 顶栏 **上游账单**（或工作台任务卡）。选账期起、账期止（`type=month`，默认上一自然月；相同则只导出一个月）
3. **全部汇总**：「一键采集全部账单」按月依次拉火山云、Azure，每月写入一份 `excel/上游账单_汇总_9月_时间戳.xlsx`（月份取该月账期；四张费用表）。一侧失败仍保留另一侧；某月失败会继续后续月份
4. 也可切到 **火山云** / **Azure OpenAI** 单独采集：`上游账单_火山云_9月_` / `上游账单_Azure_9月_`（同样每月一份；各两张表：按天、按月）。一次最多 24 个月
5. 费用列标注 `费用（¥）`，表末行为 `SUM` 合计。表头可下拉筛选（不含合计行），首行冻结。火山云会排除空项目 / 默认项目。点「下载 Excel」取下拉所选文件；历史下拉旁可 **刷新**。已有旧文件不会自动带上筛选，须重新采集

改 Python 后须重启 `run.bat`。采集过程不会自动下载。

---



## 智能提取

智能提取页支持两种模式（顶部分段切换）：

- **渠道智能提取**：从运维文档、聊天记录、门户文字或**已格式化的渠道行**提取 NA 渠道批量格式。默认为**创建**（需密钥）；先点「**更新**」再提取则按**更新原配置**（不要求密钥）
- **令牌智能提取**：从「令牌名-人名 / 分组 / 模型」、人名分行，或**令牌名 + 渠道批量行**拼成令牌批量行；单独纯数字行自动写入第 4 列额度，可一键填入批量配置令牌管理

### 输出格式（渠道）

**无需表头**，空格分隔：

```text
名称 分组 类型 模型 模型->上游 base_url [API版本] 秘钥
```

示例（火山方舟）：

```text
demo-alpha-test-model-a demo-alpha-test 字节火山方舟、豆包通用 demo-alpha-test-model-a demo-alpha-test-model-a->ep-20260101000000-demo1 https://ark.example.com ark-xxxx
```



### 令牌智能提取

将运维粘贴的令牌草稿拼成**令牌管理**可用的批量行。纯规则引擎，**不调用 LLM**。

实现：`agent/lib/token_extractor.py` · 接口：`POST /api/extract-token`（或 `POST /api/extract` 且 `extract_mode=token`）。

#### 输出格式（令牌）

与 [令牌管理](#令牌管理) 一致：**无需表头**，推荐 Tab 分隔（空格亦可）：

```text
令牌名-人名	分组名	模型名1,模型名2	额度(tokens，可选)
```

模型列表统一为**英文逗号**；输入中的 `，` `、` `;` `；` 会自动归一。块中出现单独一行非负整数（或 `额度(tokens)：1000000`）时，会被识别为令牌额度，自动放入输出第 4 列；不会进入模型列表。

#### 输入方式（令牌）

| 输入类型 | 说明 |
| -------- | ---- |
| **三行标准** | 第 1 行已是 `令牌名-人名`；第 2 行分组；第 3 行模型列表；可选追加一行纯数字额度 |
| **四行拼接** | `令牌名` / `人名` / `分组` / `模型` → 自动拼成 `令牌名-人名`（已含 `-人名` 不重复追加） |
| **渠道行转令牌** | `令牌名-人名` 或 `令牌名` + `人名` 分行，其后粘贴一条或多条**渠道批量行** → 自动取分组与「模型」列 |
| **带标签** | 支持 `令牌名：` `人名：` `分组：` `模型：` 等前缀（全角/半角冒号均可） |
| **已格式化单行** | `名称 分组 模型1,模型2 [额度(tokens)]`（空格或 Tab）直接透传规范化 |
| **多条批量** | 空行分隔多块；纯渠道行空行和纯额度数字行会被并入上一令牌块 |

常见输入：

```text
demo-alpha-uat-gpt-x-张三
demo-alpha-uat
demo-alpha-uat-gpt-x，demo-alpha-uat-gpt-y
```

人名与令牌名分行（自动拼接）：

```text
demo-alpha-uat-gpt-x
张三
demo-alpha-uat
demo-alpha-uat-gpt-x，demo-alpha-uat-gpt-y
```

提取输出：

```text
demo-alpha-uat-gpt-x-张三	demo-alpha-uat	demo-alpha-uat-gpt-x,demo-alpha-uat-gpt-y
```

带额度的输入：

```text
demo-alpha-uat-gpt-x-张三
demo-alpha-uat
demo-alpha-uat-gpt-x，demo-alpha-uat-gpt-y
500000
```

提取输出：

```text
demo-alpha-uat-gpt-x-张三	demo-alpha-uat	demo-alpha-uat-gpt-x,demo-alpha-uat-gpt-y	500000
```

带标签示例：

```text
令牌名：demo-beta-test-claude
人名：李四
分组：demo-beta-test
模型：demo-beta-test-claude-sonnet
```

→ `demo-beta-test-claude-李四	demo-beta-test	demo-beta-test-claude-sonnet`

#### 渠道行转令牌

适用于：渠道已提取（或已有批量行），需要再为某人建一条「模型限制 = 这些渠道模型」的令牌。

| 行序 | 内容 | 说明 |
| ---- | ---- | ---- |
| 1（推荐） | `令牌名` / `令牌名-人名` / **仅人名** | 仅人名时自动拼到**首个渠道模型**后 |
| 2（可选） | 人名（2～12 个汉字） | 与令牌名分行时自动拼成 `令牌名-人名` |
| 其后 | 渠道批量行 | 须可被渠道行解析器识别（含 `https://`、类型、密钥等） |

亦支持：**不写独立令牌名行**，把渠道「名称」写成 `模型-人名`（模型列仍为无后缀的模型名）。

规则：

- **模型**：取每条渠道行的「模型」列（通常等于渠道名），去重保序，英文逗号拼接
- **分组**：优先用渠道行中的分组；一致时取众数；否则从令牌名按 [分组与模型推导](#分组与模型推导) 截到环境段
- 渠道行之间的**空行**会并入同一令牌块（不会拆成多条令牌）
- 密钥 / URL 仅用于识别渠道行，**不会**写入令牌输出

完整示例（节选）：

```text
demo-gamma-uat-gpt-x
张三
demo-gamma-uat-product-gpt-x demo-gamma-uat Azure OpenAI demo-gamma-uat-product-gpt-x demo-gamma-uat-product-gpt-x->gpt-x-sol https://demo-….openai.azure.com 2025-04-01-preview <key>
demo-gamma-uat-project-gpt-x demo-gamma-uat Azure OpenAI demo-gamma-uat-project-gpt-x demo-gamma-uat-project-gpt-x->gpt-x-sol https://demo-….openai.azure.com 2025-04-01-preview <key>
```

→

```text
demo-gamma-uat-gpt-x-张三	demo-gamma-uat	demo-gamma-uat-product-gpt-x,demo-gamma-uat-project-gpt-x
```

亦可写成一行令牌名：`demo-gamma-uat-gpt-x-张三`，其后紧跟渠道行，效果相同。

仅人名 + 渠道行：

```text
张三
demo-omega-prod-doubao-seed demo-omega-prod 字节火山方舟、豆包通用 … ->ep-… https://ark.… ark-…
```

→ `demo-omega-prod-doubao-seed-张三	demo-omega-prod	demo-omega-prod-doubao-seed`

渠道名称已含人名（无独立令牌名行）：

```text
demo-omega-prod-doubao-seed-张三 demo-omega-prod 字节火山方舟、豆包通用 demo-omega-prod-doubao-seed …->ep-… https://ark.… ark-…
```

→ 同上。

#### 拼接规则摘要

- **人名**：2～12 个汉字（可含 `·`），识别为独立人名行并拼到令牌名后（三行/四行与渠道行模式均适用）
- **模型行**：优先识别含 `，` / `,` / `、` 等分隔符的行；无分隔符时默认**块末行**为模型（避免把 `demo-b-test` 这类分组名误判为模型）
- **渠道行模式**：见上一节；块内只要出现可解析渠道行即走此路径
- **分组（非渠道行模式）**：模型行之上的最后一行（通常含 `-uat` / `-test` / `-prod` 等）
- **Web**：切换「令牌智能提取」后可用示例卡片（含「渠道行转令牌」）；「填入令牌管理 →」调用批量页 `__naBatchApplyTokenText`

### 输入方式（渠道）


| 输入类型      | 说明                                                |
| --------- | ------------------------------------------------- |
| **杂乱文本**  | 渠道名、版本标注、`ark-` 密钥、`ep-` 模型、RPM/TPM 噪声行等混排        |
| **火山空格单行** | `名称 [类型] ep-… ark-…`（无 URL）与换行四行块**等效**；类型名中的顿号不会误拆 |
| **完整渠道行** | 含 `模型->上游`、`https://` URL、密钥的单行；支持**空格或 Tab** 分隔  |
| **紧凑渠道行** | 无重定向：`名称 [分组] 类型 上游模型 URL [版本] 秘钥`；自动补全为 `名称->上游` |
| **升级申请**  | 渠道名 + 类型 + `模型->新上游`（**可无密钥**）；须先点「更新」再提取，见 [更新提取](#更新提取火山自动升级) |
| **多条批量**  | 空行分隔多条；或点击「载入示例」加载双渠道样例                           |


已格式化行支持的字段顺序：

- 完整标准：`名称 分组 类型 模型 模型->上游 …`
- 完整常见：`名称 类型 模型 模型->上游 …`（分组由名称推导）
- **紧凑（无** `->`**）**：`名称 类型 上游模型 URL 秘钥` 或 `名称 分组 类型 上游模型 URL 秘钥`

紧凑行规则（与批量样例一致）：

- **模型列** = 渠道名称的 ASCII 核心（去掉中文备注）
- **模型重定向** = `ASCII模型->上游模型`（输入中的短模型名作为上游）
- **分组** = 从名称推导（截到环境段，见 [分组与模型推导](#分组与模型推导)）

示例输入：

```text
demo-delta-uat-glm-5.1 自定义渠道 glm-5.1 https://ai-model.example.com/glm/v1/chat/completions sk-xxxx
```

提取输出：

```text
demo-delta-uat-glm-5.1 demo-delta-uat 自定义渠道 demo-delta-uat-glm-5.1 demo-delta-uat-glm-5.1->glm-5.1 https://ai-model.example.com/glm/v1/chat/completions sk-xxxx
```

### 分组与模型推导

实现：`agent/lib/group_deriver.py`（渠道提取、紧凑行、令牌渠道行模式共用）。

**命名约定**：`{项目}-{环境}-[业务段-]{模型…}[-中文备注]`

| 规则 | 说明 | 示例 |
| ---- | ---- | ---- |
| **分组截到环境** | 环境段为整段精确匹配：`test` / `uat` / `prd` / `prod` / `stg` / `dev`（不会把 `product`、`development` 误当成 `prod`/`dev`） | `demo-gamma-uat-product-gpt-x` → **`demo-gamma-uat`** |
| **模型列（ASCII）** | 去掉中文备注后的渠道名核心 | `demo-…-kimi-k3-中文备注` → 模型列 `demo-…-kimi-k3`（名称原样保留） |
| **无环境段时** | 尝试剥常见模型族后缀（`glm`/`gpt`/`qwen`…），再兜底去掉最后一段 | `demo-model-glm-x` → `demo-model` |

更多示例：

```text
demo-camp-uat-qwen-x-中文备注  → 分组 demo-camp-uat
demo-delta-uat-glm-5.1                     → 分组 demo-delta-uat
demo-alpha-test-glm-x                    → 分组 demo-alpha-test
demo-gamma-uat-agent-gpt-x        → 分组 demo-gamma-uat
```

### 载入示例（Web）

智能提取页按当前模式显示不同示例卡片：

| 模式 | 示例卡片 | 说明 |
| ---- | -------- | ---- |
| **渠道** | 火山方舟 / **火山自动升级** / 多条混排 / 完整示例 | 脱敏渠道草稿（含 `ark-` / `ep-`）；自动升级示例**无密钥**，须先点「更新」再提取 |
| **令牌** | 令牌名-人名 / 名与人分行 / **渠道行转令牌** / 多条令牌 | 三行标准、四行拼接、令牌名+人名+渠道行、空行多块 |

渠道「完整示例」片段：

```text
demo-alpha-test-model-a
Model-A｜260101
EXAMPLE_ARK_KEY
ep-20260101000000-demo1
        15,000 RPM1,500,000 TPM

demo-beta-test-model-b
Model-B｜260102
…
```

### 更新提取（火山自动升级）

「智能提取」右侧有独立按钮 **「更新」**（令牌模式隐藏）。**默认关闭**，不影响创建提取。

| 步骤 | 说明 |
| ---- | ---- |
| 1. 点「更新」 | 按钮亮起，表示下一次提取按**更新原配置**处理 |
| 2. 点「智能提取」 | 请求带 `for_update: true`，**不要求密钥**，输出行不含秘钥列 |
| 3. 「填入更新原配置 →」 | 写入渠道框并定位到「更新原配置」区；此时「填入批量配置」不可用 |
| 再点一次「更新」 | 取消，恢复普通创建提取（需密钥） |

升级申请示例（与 `examples/agent/volcano-upgrade/input.txt`、Web「火山自动升级」卡片一致）：

```text
# 火山方舟自动升级申请：原 GLM-4.7 → GLM-5.2，不改密钥
demo-alpha-test-glm-4.7
字节火山方舟、豆包通用
demo-alpha-test-glm-4.7->GLM-5.2
```

提取输出（无密钥）：

```text
demo-alpha-test-glm-4.7 demo-alpha-test 字节火山方舟、豆包通用 demo-alpha-test-glm-4.7 demo-alpha-test-glm-4.7->GLM-5.2 https://ark.cn-beijing.volces.com
```

未点「更新」时，上述示例会报 `缺少: api_key`。含密钥的火山/Azure 创建提取行为不变。

CLI 等价：`python app.py extract` 默认为创建；程序内 `extract_channels(..., require_key=False)` 或 HTTP `for_update: true`。

### 提取模式


| 模式             | 适用     | 说明                                       |
| -------------- | ------ | ---------------------------------------- |
| `rules`        | 渠道     | 仅规则引擎，离线可用                               |
| `llm`          | 渠道     | 用户勾选 LLM 且 AI 已参与                        |
| `llm_failed`   | 渠道     | 勾选 LLM 但配置缺失或调用失败                        |
| `token_rules`  | 令牌     | 令牌智能提取固定为此模式（无 LLM）                      |


> **渠道模式**：未勾选「启用 LLM 增强」时不会调用 AI，即使本地已配置 LLM。  
> **令牌模式**：始终 `token_rules`，页面不展示 LLM 高级选项。



### 支持的渠道类型


| 类型           | 输入特征                 | 自动行为                                       |
| ------------ | -------------------- | ------------------------------------------ |
| 火山方舟 / 豆包    | 含 `ep-` 模型 ID；空格单行或换行块均可 | 补全类型 + `https://ark.cn-beijing.volces.com` |
| 火山升级申请       | 名称 + 类型 + `模型->新上游`（可无 `ep-` / 密钥） | 须 [更新提取](#更新提取火山自动升级)；映射目标为新上游（如 `GLM-5.2`） |
| **OpenAI**     | 显式写入 `OpenAI` / `openai` | 按 OpenAI 识别（不被 `sk-`+URL 误判为自定义） |
| Azure OpenAI | 含 `Azure`，或 `*.openai.azure.com`，或未写 openai | 默认 Azure；解析 Base URL 与 `api-version`；上游可为 `gpt-4o`、`text-embedding-ada-002` 等 |
| 自定义渠道        | `sk-` 密钥 + 非 Azure/火山 URL，且无显式其它类型 | 识别部署模型（如 `glm-5.1`、`kimi-k3`） |
| 完整 / 紧凑渠道行   | 含类型标签 + URL + 密钥     | 直接解析；紧凑行自动补 `名称->上游`                       |




### 多条批量与分隔符


| 分隔方式               | 说明                           |
| ------------------ | ---------------------------- |
| 换行 / Tab / 逗号 / 顿号 | **渠道**：字段内可混用（千分位逗号、类型名中的顿号如「字节火山方舟、豆包通用」不会误拆） |
| 中英文逗号 / 顿号 / 分号     | **令牌**：模型列表分隔符，输出统一为英文逗号       |
| 空行                 | 渠道与令牌均用空行分隔多条记录              |
| 版本标注行              | **渠道**：如 `GLM-5.2｜260617` 标志新块 |


---



## LLM 增强

适用于**渠道智能提取**（令牌模式无此选项）。规则引擎默认可离线工作。**仅当勾选「启用 LLM 增强」时**才会调用 AI API。

### 行为说明

- 勾选后**真实调用**所选 AI API；AI 结果优先于规则引擎
- 未勾选时始终为纯规则模式（`mode: rules`），不会静默调用 LLM
- 勾选但未配置 API 时返回 `400`，`mode: llm_failed`
- `llm.invoked = true` 表示 AI 已真实参与
- 切换到「令牌智能提取」时不展示本面板，也不会调用 LLM



### 支持的厂商


| 厂商       | `llm_provider` | 默认 API 地址                                           |
| -------- | -------------- | --------------------------------------------------- |
| OpenAI   | `openai`       | `https://api.openai.com/v1`                         |
| DeepSeek | `deepseek`     | `https://api.deepseek.com/v1`                       |
| 阿里云百炼    | `dashscope`    | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| 火山方舟     | `volcengine`   | `https://ark.cn-beijing.volces.com/api/v3`          |
| 智谱 AI    | `zhipu`        | `https://open.bigmodel.cn/api/paas/v4`              |
| Moonshot | `moonshot`     | `https://api.moonshot.cn/v1`                        |
| 硅基流动     | `siliconflow`  | `https://api.siliconflow.cn/v1`                     |
| 小米 MiMo  | `mimo`         | `https://api.xiaomimimo.com/v1`                     |
| Ollama   | `ollama`       | `http://127.0.0.1:11434/v1`（Key 可留空）                |
| 自定义      | `custom`       | 自行填写                                                |


配置方式：Web 界面（存 `localStorage`）、`agent/config.json`、或 API/CLI 参数。

---



## 批量配置

进入 **批量配置** Tab（`batch/static/index.html`，经 `/static/batch_ui.html?embed=1` 嵌入）。顶部为**连接配置**，下方按子 Tab 切换：渠道管理 → 令牌管理 → 分组设置 → **渠道启停** → 使用日志。

### 连接与认证


| 方式              | 说明                                                         |
| --------------- | ---------------------------------------------------------- |
| **账号密码**        | 调用 NA 登录接口；会话缓存约 **2 小时**（进程内 + 磁盘），减少连续操作反复登录触发 **429** |
| **登录两步验证**     | 见下一小节。可填当前码，或预置 TOTP 原始密钥；**Access Token** 模式跳过登录口，一般不必填 |
| **Access Token** | 填 Token + User ID，跳过登录口，适合限流场景或自动化                          |
| **地址规范化**       | 粘贴控制台地址（含 `/console`、`/api`）会自动转为站点根 URL                   |
| **跳过 SSL**        | 默认关闭。仅内网证书 Hostname mismatch 时勾选 |


连接信息优先读 `localStorage`（`na_batch_connection_config`），其次 `batch/config.json`。建议先点「测试连接」再执行批量操作。二次验证码**不会**写入 localStorage。

#### 登录两步验证（渠道 / 令牌）

NA 账号若在「个人设置 → 安全设置」启用了登录 2FA，密码登录会返回 `mfa_action`（`setup` / `verify`；旧字段 `require_2fa` 仍兼容），必须再提交认证器码。`setup` 表示尚未绑定，需先到 NA 控制台完成绑定。

| 入口 | 怎么填 |
| ---- | ------ |
| **批量配置** | 连接配置 → 账号密码 →「二次验证码」；测试连接、渠道创建/更新/删除、令牌批量都会带上 |
| **智能体** | 网关连接同一字段（可留空走 env）；**门禁「确认并继续」**、**从失败步重试** 可再填当前码；已预置 `totp_secret` 时不必填 |
| **数据汇总** | 采集 / 余额查询会检查会话与 TOTP（见 [验证码与全局认证](#验证码与全局认证)）；工作台已认证则不再弹审查窗；含密钥导出另走 `/api/verify` |
| **CLI** | `python app.py batch channel --otp-code 123456 …`（令牌批量同样支持 `--otp-code`） |

要点：

- 支持认证器 **6 位 TOTP**、**8 位备用码**，或 **Base32 原始密钥**（见下一小节）；TOTP 约 **30 秒**一变
- **一次性验证码**不写入 `localStorage` / 日志（`otp_code` 已脱敏）
- **原始密钥**可预置在 `env/sites.json` 的 `totp_secret`（该文件本身勿提交仓库）
- 先「测试连接」成功后，会话缓存可让后续渠道/令牌操作在约 2 小时内不必反复填码
- 智能体提取 + 门禁往往超过 30 秒：未预置密钥时，请在**确认写入前**看认证器填最新码
- 多站点汇总：各站 **各用各的验证器 / 密钥**，不要把同一码填到所有环境。建议先工作台 [全局站点认证](#全局站点认证)
- 这与「查看渠道密钥」的 `/api/verify` 是两套流程；智能体默认汇总**不含**渠道明文密钥

#### TOTP 原始密钥（sites.json）

二次验证绑定时拿到的 **Base32 密钥**可预写进 `env/sites.json`。请求当下按 RFC 6238 / Google Authenticator 生成当前 6 位码。获取方式见 [NA 站点参数](#na-站点参数已配置站点)。

```json
"prod": {
  "base_url": "https://ai-gateway.example.com",
  "username": "admin",
  "password": "change-me",
  "totp_secret": "把认证器原始密钥填在这里"
}
```

| 写法 | 行为 |
| ---- | ---- |
| `totp_secret` | 推荐。登录、`/api/verify`、数据汇总在需要时自动生成当前码 |
| `otp_code` 填同一串密钥 | 同样识别为 TOTP 密钥并生成 |
| `otpauth://totp/...?secret=…` | 从 URI 取出 secret |
| 6 位数字 / 8 位备用码 | 仍按一次性验证码原样提交 |

地址能对上 `sites.json` 时，批量配置测试连接 / 批量、数据汇总采集与补密钥会**自动带上**该密钥，不必每次手抄认证器。密钥**不下发到浏览器**（`GET /api/env-sites` 只返回 `has_totp_secret`），也不写入 localStorage。

已预置密钥或工作台会话仍有效时，数据汇总 / 一表总览**不再弹窗**要验证码。未预置且会话过期时，再在页面二次验证框粘贴密钥或当前码。

实现：`batch/lib/totp.py`。

#### 跳过 SSL 证书校验

**默认关闭**（校验证书）。仅当 Python 报 `CERTIFICATE_VERIFY_FAILED` / `Hostname mismatch`（内网网关证书域名对不上访问主机名）时，在 **批量配置连接配置**勾选「跳过 SSL 证书校验」。只影响本工具发出的请求；浏览器打开该站点仍可能提示证书风险。

#### 环境快捷切换（已配置站点）

连接配置标题右侧按 `env/sites.json` **已填写 `base_url` 的站点**显示快捷按钮（历史 key 仍可能叫 test / uat / prod）：

```bash
cp env/sites.example.json env/sites.json
# 编辑 sites.json：base_url / username / password；可选 totp_secret
```

| 行为 | 说明 |
| ---- | ---- |
| **未配置** | 无 `env/sites.json`，或已配置站点均无有效 `base_url` → **按钮整组隐藏** |
| **部分配置** | 仅显示/启用已填写的站点；未填的不出现。两站齐全即为覆盖完成，不必写满三站 |
| **点击** | 立即填入地址、账号密码（或 Token），并写入 `localStorage` |
| **数据汇总** | 本地站点列表为空时**自动识别**同一文件并填入卡片；也可点「从 env 载入」覆盖 |
| **智能体** | 网关连接同样显示快捷按钮；汇总站点与数据汇总共用列表，为空时自动载入；密码与 `totp_secret` 也可不填，服务端按地址补齐 |

示例结构见 `env/sites.example.json`（含 `_comment_totp`）。也支持某环境使用 `access_token` + `user_id`（不填 username/password 时按 Token 模式填入）。`GET /api/env-sites` 不会返回 `totp_secret` 明文。

接口：`GET /api/env-sites`（批量配置快捷按钮、网站列表、智能体共用）。

测试连接、批量写入、智能体任务在页面未填密码 / TOTP 时，会按 `base_url`（或站点 `env`）从 `env/sites.json` 补齐 `username`、`password`、`access_token`、`totp_secret`。已手填的字段不会被覆盖。`GET /api/env-sites` 仍不返回 `totp_secret` 明文，只给 `has_totp_secret`。

### 渠道管理

```text
名称 分组 类型 模型 模型->上游 base_url [API版本] 秘钥
```

- 分组不存在时自动创建（需 Root）
- **本站唯一**：渠道名、模型名（`models` 及重定向左侧）全站不可重复；批量内重复则跳过，与已有冲突则拒绝创建
- 新建渠道时，规范化后的 `base_url` 会同时写入 New API 的管理员 `remark`（备注）
- 删除 / 禁用 / 启用均按「名称 + 分组」匹配；批量文本可只写 `名称 分组`（完整创建行也可）；须先「预删除 / 预禁用 / 预启用」再确认。禁用可再启用；删除不可撤销
- 载入示例后「开始创建」按钮锁定，修改内容后解锁

#### 更新原配置

用于火山 / 豆包等**上游自动升级**后，在收到升级申请单时同步网关登记（不新建渠道）。

行格式与创建相同；**更新不需要、也不会改密钥**（行末秘钥列可省略；即使粘贴了 `sk-` / `ark-` 也会忽略）。改渠道名时名称列写 `原名称=>新名称`（中间不要空格）。

```text
demo-alpha-test-glm-4.7 demo-alpha-test 字节火山方舟、豆包通用 demo-alpha-test-glm-4.7 demo-alpha-test-glm-4.7->GLM-5.2 https://ark.cn-beijing.volces.com
```

- 按 **名称 + 分组** 匹配已有渠道
- 覆盖：模型、`model_mapping`、base_url、类型、分组；备注为空时自动写入本行规范化后的 `base_url`
- 若已有备注且与本行 `base_url` 不同，预更新会统计并在点击「确认更新」后弹窗选择：点「确定」覆盖原备注，点「取消」保留原备注并继续更新其他配置
- 须先 **预更新** 查看变更，再 **确认更新**（内容改过会作废确认）
- 可点 **导入更新模板** 载入 `example_batch_update.tsv`；模板不含密钥，填入后会锁定所有写操作，必须修改为实际数据后才能预更新
- 示例数据锁定时拦截更新
- `PUT /api/channel/` 不传 `key` 时上游保留原密钥

也可从智能提取[更新提取](#更新提取火山自动升级) 一键填入。接口：`POST /api/batch-update-channels`（`dry_run`）。

#### 同步 Base URL 到备注

渠道管理的 **一键同步 Base URL 到备注** 会读取当前连接站点的**全部渠道**，先展示预览，确认后把地址写入 New API 渠道编辑页「高级设置 → 备注」（仅管理员可见）。不依赖上方的批量文本，也不会修改密钥、模型、分组、状态或其他渠道配置。

- 常规渠道读取 `base_url`；Azure（类型 `3`）只读取渠道 API 配置中的 **`AZURE_OPENAI_ENDPOINT`**，其底层同样是 `base_url` 字段；不会写入 Azure API 版本。
- 原备注为空时写入地址；原备注已有内容时以**换行**在末尾追加地址。
- 备注中已经有相同地址的一整行时跳过，因此可安全地重复运行而不重复追加。
- 上游源码的备注上限为 **255 个字符**。追加后超过上限、没有有效渠道 ID、或未填写地址时，该渠道不会更新；预览和执行日志均会明确显示 `渠道「名称」（ID=…）备注同步未完成：原因`，其余可处理渠道仍可继续确认同步。
- 先点「一键同步 Base URL 到备注」查看清单，再点「确认同步备注」。确认前若切换了 New API 地址或认证配置，必须重新预览。

接口：`POST /api/channel-remark-sync`，请求体为 `base_url`、认证字段与 `dry_run`（默认 `true`）。

### 令牌管理

```text
名称 [Tab/空格] 令牌分组 [Tab/空格] 模型1、模型2 [Tab/空格] 额度(tokens，可选)
```

- 第 4 列 `额度(tokens)` 是非负整数，直接写入 New API 的 `remain_quota`；填写后创建有限额度令牌（`unlimited_quota=false`），省略该列则创建无限额度令牌（`unlimited_quota=true`）
- 支持批量创建；预删除 / 预禁用 / 预启用 / 确认（按名称+分组；可只写 `名称 分组`，完整创建行也可）
- **本站唯一**：令牌名全站不可重复（分组或模型限制不同也不允许同名）；批量内同名跳过
- 删除 / 禁用 / 启用仍按「名称 + 分组」匹配；禁用可再启用；已过期或额度用尽的令牌可能无法启用
- 可导出站点令牌为「名称 + 密钥」文本（需相应权限）
- 已有令牌改分组：见 [分组切换](#分组切换)
- 草稿格式不统一时，可先在智能提取用 [令牌智能提取](#令牌智能提取) 拼成标准行，再「填入令牌管理 →」

#### 有限额度创建

`额度(tokens)` 以令牌的可用 token 额度为单位。`0` 合法，但表示有限额度为 0，令牌会因额度用尽而无法调用；不需要限制时请**省略该列**，而不是填 `0`。

| 目标 | 输入示例 | 创建结果 |
| ---- | -------- | -------- |
| 无限额度 | `demo-a  team-a  model-a` | `unlimited_quota=true`，`remain_quota=0` |
| 50 万 tokens | `demo-b  team-a  model-a、model-b  500000` | `unlimited_quota=false`，`remain_quota=500000` |
| 100 万 tokens | `demo-c<Tab>team-a<Tab>model-c<Tab>1000000` | `unlimited_quota=false`，`remain_quota=1000000` |

列可用 Tab、空格或英文逗号分隔；模型列表仍支持顿号、中文逗号或英文逗号。额度必须为不超过 New API 上限的非负整数；负数、小数或非数值会被工具拒绝。

#### 更新已有令牌额度

用于为历史无限额度令牌补设额度，或调整已有有限额度。入口位于 **令牌管理 → 更新令牌额度**，操作必须经过「预更新 → 确认更新」两步：

1. 在令牌管理文本框粘贴要更新的行，或点击 **导入更新模板**。可使用完整四列格式，或仅写精简三列 `名称 分组 额度(tokens)`。
2. 点击 **预更新**，检查每条令牌的 ID 及 `无限额度 / 旧额度 → 新额度` 变更；确认按钮在预览成功且存在变更时才可点击。
3. 点击 **确认更新**。文本内容只要发生变化，确认即失效，必须重新预更新。

```text
# 精简更新格式：名称 分组 额度(tokens)
legacy-token-a  team-a  500000
legacy-token-b  team-b  1000000

# 也可使用完整创建行；更新时仅读取第 4 列额度
legacy-token-c  team-c  model-c、model-d  2000000
```

更新时**必须显式填写额度**。旧三列创建行没有额度时会被拒绝，不会把现有令牌改成无限额度。按名称+分组找不到令牌、额度没有变化或批量内重复时会跳过。

导入的 `example_batch_token_update.txt` 是仅含「名称、分组、额度」的安全示例；载入后所有写操作会锁定，修改为实际令牌数据后才可预更新，避免将示例行提交到站点。

为避免 New API 的 `PUT /api/token/` 覆盖字段，工具会先读取令牌详情再提交完整请求体。更新仅修改 `remain_quota` 与 `unlimited_quota`，并保留名称、分组、状态、模型白名单、模型级限流、IP 白名单、过期时间、跨分组重试和密钥。

> 若令牌当前状态为「额度用尽」，补充额度后状态不会自动改为启用；请再使用下方 **预启用 → 确认启用** 恢复启用状态。



### 分组设置

- 批量创建分组（一行一个分组名，或不存在时由渠道创建自动补建）
- 预删除 / 确认删除分组
- 可「刷新已有分组」查看当前站点已有分组
- **创建 / 删除分组建议使用 Root 账号**

#### 分组切换

位于 **批量配置 → 分组设置**。把某个分组下的**渠道**或**令牌**改到另一个已有分组（不新建、不删除分组本身）。

1. 「刷新已有分组」→ 选择**源分组**、**目标分组**（不能相同）
2. 「加载该分组渠道 / 令牌」→ 两个清单默认全选
3. 可手动勾选，或「全选 / 反选」
4. 「切换所选渠道」或「切换所选令牌」（浏览器确认）

| 对象 | 行为 |
| ---- | ---- |
| **渠道** | 渠道 `group` 可为逗号分隔多分组：只把源分组名替换为目标分组，其它分组保留；已含目标则去重 |
| **令牌** | 令牌通常单分组：整段替换为目标分组；额度、模型限制、过期时间等其余字段不变 |
| **目标分组** | 必须已存在；没有则先在上方创建 |
| **更新接口** | 渠道 `PUT /api/channel/`（不传 key，保留原密钥）；令牌 `PUT /api/token/` |

接口：`POST /api/groups-members`（加载清单）、`POST /api/groups-switch`（`kind=channel\|token` + `ids[]`）。


### 渠道启停

位于批量配置模块 Tab：**分组设置** 与 **使用日志** 之间。按站点渠道的 `model_mapping` **右侧上游**、或按**渠道类型全部**、或按清单**勾选 ID** 批量启用 / 禁用。

若已有「名称 分组」清单（如智能分析工作表 `批量禁用`），到 **渠道管理 / 令牌管理** 文本框粘贴后用 **预禁用 / 预启用**，不必进本 Tab。一条令牌挂多条渠道时，粘贴列只含确定要禁的渠道，不会把整条令牌带上。

#### 操作方式


| 操作              | 说明                    |
| --------------- | --------------------- |
| **类型全部禁用 / 启用** | 对该类型下全部渠道一键操作（浏览器确认）  |
| **加载类型清单**      | 拉取该类型全部渠道到可视化列表（不改状态） |
| **按上游模型加载**     | 按输入的上游模型精确匹配后展示列表     |
| **全选 / 反选**     | 勾选列表中的渠道              |
| **禁用所选 / 启用所选** | 仅对勾选行操作               |
| **单条启用 / 禁用**   | 每行独立按钮 + 状态徽章         |


- 默认类型：**自定义渠道**（type=`8`）；可改为其他类型（**必须指定**）
- 上游模型：每行一个，也支持逗号 / 空格分隔
- 已是目标状态的渠道会**跳过**
- 状态值：启用=`1`，手动禁用=`2`（循环调用 NA `PUT /api/channel/`）



#### 匹配规则


| `match_mode`   | 匹配范围                            | 上游模型   |
| -------------- | ------------------------------- | ------ |
| `upstream`（默认） | 指定类型 + `model_mapping` 右侧命中输入模型 | **必填** |
| `type`         | 指定类型下全部渠道                       | 不需要    |
| `ids`          | 指定渠道 ID 列表（可选再按类型过滤）            | 不需要    |


匹配示例：输入上游 `glm-5.1`、类型「自定义渠道」时，

- `model_mapping = {"demo-delta-uat-glm-5.1":"glm-5.1"}` → **命中**
- 仅 `models` 含 `glm-5.1`、映射右侧不是 → **不命中**
- 无 `model_mapping` → **不命中**



### 使用日志

按时间范围从 NA 拉取使用日志并导出（分页抓取至 `total` 收齐或短页结束）：

| 项 | 说明 |
| -- | ---- |
| **格式** | 默认 **Excel (.xlsx)**；可选 CSV（纯文本，无边框样式） |
| **Excel 样式** | 宋体 11、深蓝表头。大批量用 `write_only` 写出，**不再逐格套边框**（数十万行否则会卡很久）；CSV 仍为纯文本 |
| **空列剔除** | 某一列在全部数据行均为空时不导出（仅表头有字的列会去掉） |
| **分页** | 上游硬上限 **每页 100 条**（更大 page_size 会被截成 100） |
| **节奏** | 两次列表请求启动间隔约 **1.05 秒**；单次请求已超过间隔则不再空等 |
| **进度** | `POST /api/logs-export` 立即返回 `job_id`；前端轮询 `GET /api/logs-export/jobs/<id>`，展示「已拉取 x / y」 |
| **终止** | 页面红色「终止」→ `POST /api/logs-export/jobs/<id>/cancel`；分页等待可中断 |
| **权限** | 建议 Admin；普通用户走 `/api/log/self`（无渠道名 / Admin 扩展列） |
| **筛选** | 默认时间「今天」；填了模型名会先拉全量再本地模糊筛选 |

导出列对齐上游 `Log` 结构及 `other` JSON（见 `ai-cloud-test/model/log.go`、`service/log_info_generate.go`），包括：

- 顶层：日志ID、用户ID、时间戳/时间、类型、渠道ID/名称、用户、令牌/令牌ID、分组、模型、流式、用时、输入/输出 Tokens、额度 quota、花费(USD)、IP、内容
- `other` 扁平：模型/分组/补全倍率、缓存与 Claude 缓存创建、上游映射、请求路径、首字延迟、音频/图像/搜索计费等
- Admin：重试渠道链、多 Key、本地计 Token；另附 **other原文** 与 **计费摘要** 便于核对

> 上游无独立「导出」API，由本工具分页聚合后本地生成文件。Windows 上 Flask 自带服务器会缓冲长连接，故不用一次流式响应。

### 上游信息

顶栏 **上游信息**（`static/upstream_ui.html`）。采集**云厂商**资源清单，与数据汇总 AI 网关渠道/令牌汇总**相互独立**（不合并进网关表）。页顶 **一键采集全部上游** 把两家写入同一工作簿；其下 Tab 仍可只采火山或只采 Azure。

当前支持：

| 厂商 | 凭证 | 配置位置 |
| ---- | ---- | -------- |
| **火山云** | IAM Access Key（ID 通常以 `AKLT` 开头），**不是**方舟推理 API Key | `env/upstream.json` 或 `env/sites.json` 的 `upstream.volc` |
| **Azure OpenAI** | Entra **应用注册**（tenant / client_id / client_secret），**不是** Foundry 部署页上的模型 Key | 同上文件的 `azure` / `upstream.azure` |

凭证优先读 `env/upstream.json`，否则读 `env/sites.json`。`sites.example.json` 只是模板，程序**不会**读取它。

火山采集逻辑：`ListProjects` → 各项目 `ListEndpoints`（可选 `ListApiKeys` + `GetRawApiKey`）。TPM/RPM（**TPM 在前**）优先取接入点自定义限流，否则按基础模型匹配 `ListModelRateLimit`。token 默认 `prd`/`prod`、`uat`/`dev`、`test`/`demo` 分别互通；同项目同时有 uat Key 与 dev Key 时改为 uat↔uat、dev↔dev。对不上时默认用项目里一把（项目内通用）。

火山、Azure 两张表**最后一列均为「部署时间」**（总览里的上游表相同），**行按部署时间降序，最新在最上面**；没有时间或解析失败的排最后。Excel **首行冻结**，表头开启列筛选（打开后列头有下拉箭头）。旧文件没有「部署时间」列、没有筛选、或仍按项目/订阅排序时须重新采集。智能分析才会对未满 10 天的部署降一级。时间来源见 [火山云导出列](#火山云导出列)、[Azure OpenAI 导出列](#azure-openai-导出列)。

Azure 采集逻辑与权限见 [Azure OpenAI 配置与权限](#azure-openai-配置与权限)。

接口：`GET /api/upstream/config`；汇总 `POST /api/upstream/collect`、`GET /api/upstream/info|download`；火山 `POST /api/upstream/volc/test|collect`、`GET /api/upstream/volc/info|download`；Azure `POST /api/upstream/azure/test|collect`、`GET /api/upstream/azure/info|download`。

#### 火山云导出列

工作表名 **`火山云`**，文件 `excel/上游信息_火山云_YYYYMMDDHHmmss.xlsx`。

| 列 | 来源 | 说明 |
| -- | ---- | ---- |
| 接入点名称 | `ListEndpoints.Name` | 控制台接入点名称 |
| 部署名 | `ListEndpoints.Id` | 如 `ep-…` |
| 模型服务 | `FoundationModel.Name｜ModelVersion` | 模型名 + 版本 |
| API Key | `GetRawApiKey` | 按下方规则匹配到的方舟密钥明文；对不上则默认用项目里一把 |
| TPM | 接入点 `RateLimit` 或模型默认限流 | **在 RPM 前面**。未设置 / `-1` 视为空 |
| RPM | 同上 | 未设置 / `-1` 视为空 |
| 项目方 | IAM `ProjectName` + `DisplayName` | **`项目名-负责人`**，无负责人则为 **`项目名-N/A`** |
| 联系人 | 同上解析出的负责人 | 有则填人名；没有则为 `N/A` |
| API Key汇总 | 该项目 `ListApiKeys` + `GetRawApiKey` | 控制台「查看 API Key」全量：每行 `名称 | API Key`；同一项目各行相同 |
| 部署时间 | `ListEndpoints.CreateTime` | `YYYY-MM-DD HH:MM:SS`（东八区）。没有 CreateTime 时从部署名 `ep-YYYYMMDDHHmmss` 解析。**行按本列降序，最新在上** |

#### token 匹配（方舟 API Key）

按**接入点名称**里的环境词，匹配**同一项目**下 API Key 的名称，再 `GetRawApiKey` 拉明文：

| 接入点环境 | 名称中出现 | 去对 Key 名 |
| ---------- | ---------- | ----------- |
| **prd** | `prd` 或 `prod` | 含 `prd` / `prod` 的 Key |
| **uat** | `uat` 或 `dev` | 含 `uat` / `dev` 的 Key |
| **test** | `test` 或 `demo` | 含 `test` / `demo` 的 Key |

- 项目里**只有一把** Key：不论接入点有没有环境词，都用这一把
- **默认**（不极端）：`uat` 与 `dev` 互通，`prd` 与 `prod` 互通，`test` 与 `demo` 互通
- **极端情况**：同一项目里**同时**有 uat Key 和 dev Key 时，改为精确对应——接入点 `uat` 只对 uat Key，接入点 `dev` 只对 dev Key（prd/prod、test/demo 同理）
- 接入点名称**没有**环境词、或对不上任何 Key：项目内 Key 通用，**默认用已有明文且 Id 最小（最老）的一把**（没有明文才留空）
- 没有 test Key 时：test 接入点改用 uat/dev Key，避免误落到 prd；uat/dev **不会**回退到 test Key
- 项目里只有一把环境 Key、其余是通用 Key 时（如某个项目）：该环境只把**最新**接入点挂到这把 Key，旧接入点仍用通用 Key
- 若 `excel/火山真实数据.xlsx` 存在：采集结束后按**部署名**把 API Key 改成真实表中的值（方舟 Key 项目内通用，以现网用法为准）

#### 项目方：项目名-负责人

火山控制台项目下拉通常显示 `项目名(项目名-负责人)`，例如 `demo-proj-a(demo-proj-a-张三)`。本工具把 **DisplayName** 里 `项目名-` 后面那一段当作负责人，写入 Excel：

| 控制台显示 | 项目方 | 联系人 |
| ---------- | ------ | ------ |
| `demo-proj-a(demo-proj-a-张三)` | `demo-proj-a-张三` | `张三` |
| `demo-proj-b(demo-proj-b-李四)` | `demo-proj-b-李四` | `李四` |
| `demo-research`（无人名） | `demo-research-N/A` | `N/A` |
| `default(默认项目)` | `default-N/A` | `N/A` |

规则要点：

- 调用 OpenAPI 仍用原始 `ProjectName`（如 `demo-proj-a`），只在导出/测试连接芯片上写成 `项目名-负责人`
- DisplayName 为空、等于项目名、或仅为「默认项目」等占位时，负责人填 **`N/A`**（不会出现空后缀，也不会写成 `项目名-N/A-N/A`）
- 实现：`batch/lib/upstream_volc.py` 的 `format_project_party` / `extract_project_owner`

请在火山项目设置里把 DisplayName 改成 `项目名-负责人`（与控制台下拉一致），采集结果才会带上人名。

#### Azure OpenAI 配置与权限

采集走 **Azure Resource Manager（ARM）管控面**，一次可扫配置里列出的全部订阅。和 [ai.azure.com](https://ai.azure.com) 上「所有资源 / 部署详情」看到的是同一批数据，但**不要爬网页、也不要给每个 Foundry 项目申请一把 IAM**。

各字段从哪抄、怎么填，见 [Azure OpenAI upstream.azure](#azure-openai-upstreamazure)。模板：`env/sites.example.json`（占位符，程序不会读取）；真实值只写 `env/sites.json` 或 `env/upstream.json`。

##### 不要用这些

| 你在门户里看到的 | 为什么不是 |
|------------------|------------|
| Foundry / OpenAI Studio 部署页上的 **密钥 / API Key** | 模型推理 Key，不能列订阅资源 |
| 每个 Hub / 项目再申请一个身份 | 订阅级一个服务主体即可覆盖全部账号 |
| 资源组/订阅 IAM 里给**个人账号**加读者 | 采集用的是**应用**，不是 admin 登录账号 |
| 「安全读取者」「备份读取者」「成本管理读取器」等带前缀的读者 | 只管某一类服务，**没有** `Microsoft.CognitiveServices/accounts/read`。**上游信息**不要用它们代替通用「读者」。**上游账单**须**另外**加「成本管理读取者」，与「读者」并存，见 [流程 K](#流程-k采集上游账单) |

##### 第一步：注册一个应用（只要一次）

1. [Azure 门户](https://portal.azure.com) → **Microsoft Entra ID**（概述页本身不能申请，只确认租户 ID）
2. 左侧 **管理 → 应用注册 → 新注册**
3. 名称例如 `na-upstream-collector`
4. **受支持的帐户类型**：选 **仅此组织目录中的帐户**（单个租户）。不要选多租户 / 允许所有租户
5. **重定向 URI**：空着（这是 client_credentials 后台应用，没有登录跳转）
6. 点 **注册**

注册完成后的对应关系：

| 门户字段 | 上游信息页 / `upstream.azure` | 是否填写 |
|----------|-------------------------|----------|
| **目录(租户) ID** | `tenant_id` | 要 |
| **应用程序(客户端) ID** | `client_id` | 要 |
| **对象 ID**（应用注册概述里那条） | — | **不要填** |
| **证书和密码 → 客户端密码 → 值（Value）** | `client_secret` | 要（复制 **值**，不是「机密 ID」） |
| 订阅 ID | `subscription_ids`（数组，可多个） | 要；**点进该订阅后从浏览器地址栏** `/subscriptions/` 后面复制 GUID（见下方）；兼容旧字段 `subscription_id` |

客户端密码只在创建当下能完整复制；若 Value 已变成 `***`，点 **+ 新客户端密码** 再生成一把。过期后采集会登录失败，需轮换并更新 `env/upstream.json`。

**订阅 ID 从网页链接抄（不要抄订阅显示名）：**

1. 打开 [Azure 门户](https://portal.azure.com)，**点进某一个订阅**（或该订阅下任意资源 / Azure OpenAI 账号）。停在「订阅」列表页时，地址栏往往没有 GUID，抄不到
2. 看浏览器**地址栏**，找到 `/subscriptions/`
3. 复制其后、下一个 `/` 之前的那段 GUID（`xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`）
4. 四个订阅就打开四个页面各抄一次，按内部「订阅1～4」顺序写入 `subscription_ids`

```text
https://portal.azure.com/#@xxxx.onmicrosoft.com/resource/subscriptions/00000000-0000-0000-0000-000000000001/overview
                                                                      └──────────── 只抄这一段 GUID ────────────┘
```

##### 第二步：给这个应用加订阅角色（每个订阅各一次）

应用建好后**还不能读资源**。Token 能拿到、ARM 返回 403，就是缺这一步。**应用注册只做一次；读者 + 认知服务用户要按订阅各加一遍。**

| 做什么 | 次数 |
|--------|------|
| Entra **应用注册**（`na-upstream-collector` + Client ID / Secret） | **1 次**（整个租户共用） |
| 订阅 IAM：**读者** + **认知服务用户** | **每个订阅各 1 次**（4 个订阅就做 4 遍，成员都选同一个应用） |
| 订阅 IAM：**成本管理读取者**（仅上游账单） | **每个订阅各 1 次**；与「读者」并存。不加则账单页 Cost Management 会失败 |
| `env` 里的 `subscription_ids` | 把 4 个订阅 GUID **都写进数组**，一次采集扫完全部 |

1. 打开要采集的那个**订阅**（点进后地址栏应出现 `/subscriptions/{GUID}/`）→ **访问控制(IAM)** → **添加角色分配**
2. 角色搜并选择通用 **读者（Reader）**，说明为「查看所有资源，但不允许进行任何更改」
3. 成员选 **用户、组或服务主体** → 搜应用名 `na-upstream-collector`，或客户端 ID，或报错里的 object id（企业应用程序对象 ID，可能和应用注册概述里的对象 ID 不同）
4. **不要选个人 admin 账号**
5. **必须再分配一次** **认知服务用户**（`Cognitive Services User`）：采集要拉「密钥一」，没有这个角色 `listKeys` 会 403，Excel 密钥列为空
6. 对其余 3 个订阅 **重复步骤 1～5**（仍赋给 `na-upstream-collector`）

只想锁在某个资源组时，把「读者 + 认知服务用户」做到该资源组即可，仍然是同一个应用。

配置示例与字段获取见 [Azure OpenAI upstream.azure](#azure-openai-upstreamazure)。数组顺序即 Excel「订阅」列：**第 1 个 GUID → 订阅1**，第 2 个 → 订阅2。ARM 调用仍用 GUID，表里不写 GUID。兼容旧字段 `subscription_id`（单个字符串，导出为订阅1）。上游信息页订阅框为多行，每行一个 GUID。

| 角色 | 覆盖能力 | 必须？ |
|------|----------|--------|
| **读者（Reader）** | `Microsoft.CognitiveServices/accounts/read` 及部署只读；「测试连接」列出账号 | **必须**（上游信息） |
| **认知服务用户** | `accounts/listKeys`；Excel「密钥一」 | **必须**（本期要拉密钥；不加则密钥一为空或 403） |
| **成本管理读取者** | Cost Management Query；上游账单按天/按月 | **上游账单必须**；与「读者」并存。不加则账单采集失败 |
| 安全/备份/存储等「xx 读取者」 | 与 OpenAI 无关 | **不要加**（不要用它们代替通用「读者」） |
| Cognitive Services 参与者 / 所有者 | 可改资源 | 采集不需要 |

RBAC 不是瞬时生效，加完请等 **1～2 分钟** 再点「测试连接」。

##### 采集调用的接口

鉴权：`POST https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token`，`scope=https://management.azure.com/.default`。

随后（`api-version=2024-10-01`）：

1. `GET /subscriptions/{sub}/providers/Microsoft.CognitiveServices/accounts`
2. `GET .../resourceGroups/{rg}/providers/Microsoft.CognitiveServices/accounts/{name}/deployments`
3. `POST .../accounts/{name}/listKeys`（账号级，同一账号下所有部署共用 key1）

只收录 `kind` 为 OpenAI / AIServices（或名称含 openai）的账号。Foundry 的 Hub / 项目行不是部署表目标。账号**标记**名 `1`（门户「标记」页）写入「项目」「负责人」：按**最后一个** `-` 拆开，项目名可含多个 `-`，负责人在最后一段；功能、备注本期不采集。

实现：`batch/lib/azure_arm.py`、`batch/lib/upstream_azure.py`。

##### 常见报错

| 现象 | 含义 | 处理 |
|------|------|------|
| Azure 登录失败 401 / invalid client | Secret 错、抄了机密 ID、或密码已过期 | 重新生成客户端密码 Value |
| `ARM HTTP 403` + `accounts/read` + client id | 登录成功，**订阅没给该应用「读者」** | 按上表加角色，等 1～2 分钟 |
| 测试连接成功但密钥一为空 / `listKeys` 403 | 缺 Cognitive Services 用户 | 同一应用再加该角色 |
| 订阅下未找到 Azure OpenAI 账号 | 角色挂错订阅，或账号 kind 不是 OpenAI | 核对地址栏 `/subscriptions/` 后的 GUID 是否写对；确认资源在该订阅下 |
| 扫错订阅 / Excel「订阅」列对不上 | 填了订阅显示名，或整段 URL，或停在列表页没点进去 | 只抄地址栏 `/subscriptions/` 与下一个 `/` 之间的 GUID |

#### Azure OpenAI 导出列

工作表名 **`Azure OpenAI`**（旧文件若仍叫 `openai` 也能被读取），文件 `excel/上游信息_Azure_YYYYMMDDHHmmss.xlsx`。

| 列 | 来源 | 说明 |
| -- | ---- | ---- |
| 订阅 | `subscription_ids` 填写顺序 | 第 1 个 GUID → **订阅1**，第 2 个 → **订阅2**，以此类推（Excel 不写 GUID） |
| 区域 | 账号 `location` | 如 `eastus2` → `East US2` |
| Azure OpenAI | 账号名 | 如 `demo-openai-acct` |
| 部署名 | `deployments.name` | 如 `gpt-x-sol` |
| 模型名 / 模型版本 | `properties.model` | |
| 部署类型 | `sku.name` | `Standard`→标准，`GlobalStandard`→全局标准 |
| TPM | `sku.capacity × 1000` | 对齐门户「令牌限制」 |
| RPM | `rateLimits` 中非 token 的 request | 对齐门户「速率限制」 |
| 接口 | 按终结点拼接 | embedding 用 `/openai/deployments/{名}/embeddings?api-version=2023-05-15`；其它用 `/openai/responses?api-version=2025-04-01-preview`（Foundry 详情页「目标 URI」多为 `chat/completions`，与网关样表不一致时以本列规则为准） |
| 密钥一 | `listKeys.key1` | **账号级**，该账号下各部署相同 |
| 项目 | 账号标记名 **`1`** 的值，按**最后一个** `-` 拆开，前面整段为项目名 | 如 `示例项目组`、`AI-Product`；**没有标记 1**（或值为空）时填 **`N/A`**。紧挨「密钥一」之后 |
| 负责人 | 同一标记 `1` 里**最后一个** `-` 后面的人名 | 如 `张三` 或 `张三，李四`；多人分隔符认 `，` / `,` / `、`，导出统一 `，`；没有标记 1 时填 **`N/A`** |
| 部署时间 | `systemData.createdAt` | `YYYY-MM-DD HH:MM:SS`（东八区）。ARM 未返回创建时间则留空。**行按本列降序，最新在上** |

#### 标记 1：项目-负责人1，负责人2

Azure OpenAI 账号在门户 **标记（Tags）** 里约定一条：

| 门户字段 | 填什么 |
| -------- | ------ |
| **名称（Name）** | 固定为 **`1`**（就这一个字） |
| **值（Value）** | **`项目名-负责人`**。项目名里可以有多个 `-`（如 `AI-Product-金鑫`），工具按**最后一个** `-` 拆开，最后一段才是负责人。多名负责人中间可用 **中文逗号 `，`、英文逗号 `,`、顿号 `、`**（可混用）；导出「负责人」列统一写成中文逗号 |

采集时读这条标记，拆成 Excel 两列，放在 **「密钥一」后面**。单独采集、「一键采集全部上游」、一表总览里的 `Azure OpenAI` 工作表都是同一套列；同一账号下各部署行相同。

| 标记 `1` 的值 | 项目 | 负责人 |
| ------------- | ---- | ------ |
| `示例项目组-张三` | `示例项目组` | `张三` |
| `示例项目组-张三，李四` | `示例项目组` | `张三，李四` |
| `示例项目组-张三,李四` | `示例项目组` | `张三，李四`（英文逗号会换成 `，`） |
| `示例项目组-张三、李四` | `示例项目组` | `张三，李四`（顿号会换成 `，`） |
| `示例项目组-张三, 李四、王五` | `示例项目组` | `张三，李四，王五` |
| `AI-Product-金鑫` | `AI-Product` | `金鑫`（项目名里可以有多个 `-`，负责人永远是最后一段） |
| 没有名称 `1` 的标记，或值为空 | `N/A` | `N/A` |

规则要点：

- 打开该 OpenAI 账号（如 `demo-openai-acct`）→ 左侧 **标记**，不要去订阅/资源组上找
- 只认标记**名称**为 `1` 的那条；其它标记名不采集
- 值按**最后一个** `-` 拆开：前面整段写「项目」（可含多个 `-`），最后一段为人名。多名负责人可用 `，` / `,` / `、` 分隔，导出统一为 `，`
- 没有标记 `1` 时两列都填 **`N/A`**，不要留空
- 实现：`batch/lib/upstream_azure.py` 的 `parse_tag_project_owner`

请在门户把标记 `1` 写成 `项目名-负责人`（负责人在最后一个 `-` 之后），重新采集后 Excel 才会带上项目和人名。旧文件须重新采集才会按新规则拆开。

#### env 参数获取

`env/sites.example.json` 只是脱敏模板，程序**不会**读取它。真实值只写 `env/sites.json` 或 `env/upstream.json`。

| 你要填的 | 去哪抄 | 详见 |
| -------- | ------ | ---- |
| NA 的 `base_url` / 账密 / `totp_secret` | 浏览器地址栏 + NA「个人设置」 | [NA 站点参数](#na-站点参数已配置站点) |
| 火山 `access_key_id` / `secret_access_key` | IAM 密钥管理（`AKLT…`） | [火山云 upstream.volc](#火山云-upstreamvolc) |
| Azure `tenant_id` / `client_id` / `client_secret` | Entra **应用注册**概述 + 证书和密码 **Value** | [Azure OpenAI upstream.azure](#azure-openai-upstreamazure) |
| Azure `subscription_ids` | **点进该订阅**（或其中任一资源），从浏览器**地址栏链接**里 `/subscriptions/` 后面那段 GUID 复制；不要停在订阅列表页 | 同上 |

文件怎么复制、程序读哪个文件，见 [env 文件怎么用](#env-文件怎么用)。

### 上游账单

顶栏 **上游账单**（`static/bill_ui.html`，hash `#bill`）。按**账期**拉云厂商费用，与「上游信息」资源清单、数据汇总网关表都**相互独立**。页顶可一次采两侧写入同一工作簿；其下 Tab 仍可只采火山或只采 Azure。跨月导出时**每月各写一份 Excel**，不把多月合并进同一个文件。

| 项 | 说明 |
| -- | ---- |
| 凭证 | 与上游信息相同：火山 IAM Access Key（`AKLT…`）；Azure Entra 应用 + `subscription_ids`。优先 `env/upstream.json`，否则 `env/sites.json` 的 `upstream.*` |
| 账期 | 页面「账期起 / 账期止」，默认上一自然月。起止相同则一个月；跨月则按月循环导出，一次最多 24 个月。请求体也可传 `bill_periods` 列表 |
| 汇总文件 | `excel/上游账单_汇总_9月_YYYYMMDDHHmmss.xlsx`（月份为该月账期，如 8 月则为 `_8月_`）。工作表 **`火山云-按天`**、**`火山云-按月`**、**`Azure-按天`**、**`Azure-按月`**，另有 **`说明`**。一侧失败仍保留另一侧 |
| 分厂商 | `上游账单_火山云_9月_时间戳.xlsx` / `上游账单_Azure_9月_时间戳.xlsx`（工作表 **`按天`**、**`按月`**，另有 **`说明`**） |
| Excel 样式 | 深蓝表头、首行冻结、列头下拉筛选。费用表筛选范围到最后一行数据为止，**不含**末行 `SUM` |
| 费用列 | 表头写成 `费用（¥）`；表末行为 `SUM` 合计 |
| 火山云列 | 日期、项目名、产品、配置名称、分拆项ID、费用（¥）。调费用中心 OpenAPI（不是控制台爬取）；排除空项目 / 默认项目 |
| Azure 列 | 日期、项目名、项目负责人、模型名、配置名称、地区、订阅、费用（¥）。走 Cost Management Query（门户对照：成本分析，分组依据「资源」）。项目名 / 项目负责人与上游信息相同：账号标记 `1`，按**最后一个** `-` 拆。每个订阅须给该应用加 **成本管理读取者**，可与上游信息的「读者」并存 |
| 产物 | 历史下拉须先选文件再下载；旁有「刷新」。`kind`：`bill_combined` / `bill` / `bill_azure` |

按钮：**一键采集全部账单** / 分厂商采集 →「下载 Excel」。接口见 [上游账单 API](#上游账单-api)。实现：`batch/lib/volc_billing.py`、`azure_billing.py`、`bill_combined.py`。

### 一表总览

顶栏 **一表总览**（`static/overview_ui.html`）。把 **数据汇总** 各 NA 站点的渠道/令牌表，和 **上游信息** 的火山云 + Azure OpenAI，写进**同一个工作簿**。

| 项 | 说明 |
| -- | ---- |
| 文件 | `excel/ai网关令牌及渠道列表_一表总览_YYYYMMDDHHmmss.xlsx`。每次新建，**不覆盖**数据汇总的 `ai网关令牌及渠道列表_时间戳.xlsx` 与上游文件。旧名 `一表总览_*.xlsx` 仍可识别下载 |
| 与数据汇总区分 | 文件名中间多 `_一表总览_`。数据汇总「最新一份网关汇总」**不会**把总览文件算进去；补全密钥只改数据汇总文件，一表总览补全密钥只改最新总览 |
| 首页 | 工作表 **`总览`**：分类 / 工作表名 / 行数 / 说明 |
| 网关部分 | 与数据汇总相同：`test-渠道管理`、`test-令牌管理`、uat/prod 对应表、`重复模型`、`重复模型相关令牌`（含 **密钥** 列） |
| 上游部分 | 工作表 **`火山云`**、**`Azure OpenAI`**（列与单独导出一致，含 Azure「项目」「负责人」，**最后一列为部署时间**；表头可筛选、首行冻结） |
| 来源 | **已有文件则提取**：数据汇总网关汇总、上游文件、以往总览。某一侧没有可提取文件时才连网 |
| 怎么比新旧 | 看文件名末尾 `YYYYMMDDHHmmss`，数字更大的为准；**不看**文件修改时间。例：`…_20260825100000.xlsx` 与 `…_20260825120000.xlsx` → 取 `120000` 那份 |
| 网关取哪份 | `ai网关令牌及渠道列表_时间戳.xlsx` 与以往总览之间取时间戳最新（数据汇总「最新网关」本身不含带 `_一表总览_` 的文件） |
| 火山云取哪份 | `上游信息_汇总_*`、`上游信息_火山云_*`、以往总览中，时间戳最新且工作表 `火山云` 有数据的一份 |
| Azure 取哪份 | `上游信息_汇总_*`、`上游信息_Azure_*`、以往总览中，时间戳最新且工作表 `Azure OpenAI` 有数据的一份 |
| 渠道密钥 | **默认获取**已配置站点渠道密钥。已有表密钥已齐则只提取、不再连网拉密钥；缺的再按会话/TOTP 补拉（工作台已认证则不弹审查窗）。需 Root，`env/sites.json` 可预置 `totp_secret` |
| 429 / 继续补全 | 拉密钥直到上游 429 再停。页面「继续补全密钥」写入**最新一份总览**（不改数据汇总）。详细日志按环境写 `密钥 已获取/总数，仍缺 n` |
| 现场采集 | 仅缺的一侧连网。NA 来自 `env/sites.json`；上游来自 `upstream.volc` / `upstream.azure` |
| 智能分析 | 见下一节。点「智能分析」读**所选**总览（须传文件 id）；若有所选/最新 `渠道余额_时间戳.xlsx` 则判定不用/不常用，并按模型评估近一月活跃。宽限期与用量阈值由卫生策略决定。写入独立的 `excel/智能分析表格_时间戳.xlsx`，不覆盖总览、不改网关。页内 **分析建议** 可筛选、全选/反选后预禁用。Excel 里 `建议处置` 只含未禁用项；已禁用在 `已禁用建议`；再右侧 `批量禁用` 按站点给出粘贴列；多渠道令牌只禁不用的那条渠道 |
| 回退 | 现场仍失败且没有可提取文件时，该侧表为空；其它侧仍写入 |

按钮：**一键生成总览表** →（密钥未齐时）**继续补全密钥** → **智能分析** → 页内建议表 **全选 / 反选** → **按勾选预禁用**（或仍「下载分析表」复制 `批量禁用` 列）。生成/分析/下载均须指定产物文件。接口：`POST /api/overview/collect`（可选 `source_summary` / `source_upstream`）、`POST /api/overview/fill-keys`、`POST /api/overview/analyze`（须 `source_overview` 或 `source`）、`GET /api/overview/info|download`、`GET /api/overview/analyze/download`、`GET /api/hygiene/actions`、`POST /api/hygiene/preview-disable`、`POST /api/hygiene/confirm-disable`。

实现：`batch/lib/overview_exporter.py`（选文件）、`batch/lib/overview_analyzer.py`（智能分析）、`batch/lib/hygiene_policy.py`（策略）、`batch/lib/hygiene_actions.py`（页内预禁用）、`batch/lib/data_summary.py` 的 `scan_channel_key_status` / `fill_missing_channel_keys`。

#### 智能分析（上下游密钥）

上游（火山云、Azure OpenAI）信息已经齐了之后，在一表总览页点 **智能分析**。分析的是**所选总览**里的网关渠道 vs 两侧上游，用来找过期、未接入、环境缺口。**只读总览、只写分析表**，不会改总览文件，也不会改 NA 站点。分析完成后页内加载 **分析建议**；可筛选、全选/反选后 **预禁用**（`POST /api/hygiene/preview-disable` / `confirm-disable`），不必先复制到批量配置。宽限期内的项默认不纳入，须勾「仍要执行宽限期项」。

| 项 | 说明 |
| -- | ---- |
| 前置 | 先「一键生成总览表」。渠道密钥尽量齐（缺密钥时密钥匹配会漏，可先点「继续补全密钥」）。用量判定依赖导出的 `渠道余额_时间戳.xlsx`，没有则跳过 |
| 文件 | `excel/智能分析表格_YYYYMMDDHHmmss.xlsx`。每次新建时间戳文件，不覆盖总览、不覆盖上一份分析 |
| 下载 | 「下载分析表」取文件名时间戳最新的一份（同样不看修改时间） |
| 密钥 | 分析表只写**密钥摘要**（前 6 + 后 4）；完整密钥仍在总览原表 |
| 渠道余额 | 读取 `excel/` 下最新一份 `渠道余额_时间戳.xlsx`。**没有该文件则不识别用量**。已用 = $0 视为**不用**（中）；0 < 已用 < $1 视为**不常用**。**近一月活跃**按模型逐项评估：全部无活跃才允许用量类禁用；**不常用且近一月无活跃升为中**（可进批量禁用）。任一模型有活跃或 N/A 则不进 `建议处置`，避免误禁渠道/令牌。旧表无该列时不常用仍为低。渠道和相关令牌均已禁用时不进建议处置，改写入 `已禁用建议` |
| 新部署放宽 | 见下节。网关渠道或上游「部署时间」距今**小于 10 天**（恰好满 10 天不放宽）时，建议处置降一级，暂缓禁用/停用。没有部署时间则不放宽 |
| 不对照 | 外部渠道（自定义 / OpenAI / DeepSeek / GLM / 阿里云等）**不判过期**，计入「外部渠道」即可 |

##### 页内分析建议

不必打开 Excel 即可处置。表头下方为当前所选分析文件的未处理项。

| 操作 | 说明 |
| ---- | ---- |
| 筛选 | 级别、站点、类别、状态（仅未处理 / 宽限期 / 全部）。全选与反选只作用于**当前筛选结果** |
| 仍要执行宽限期项 | 勾选后宽限期行才可勾、才纳入预禁用。默认跳过 |
| 全选 | 勾上当前筛选里所有**可操作**行 |
| 反选 | 翻转这些可操作行 |
| 按勾选预禁用 | 先预览各环境将禁用的渠道/令牌，再确认。走现有预检，不会静默改网关 |

宽限期未解锁时，全选/反选不会勾上这些行。已禁用建议在下方折叠区，仅供对照。

##### 新部署放宽（卫生策略）

刚上线的接入点或渠道容易被判成「下游无上游」或「不用」。默认：**部署时间距今小于 10 天**时，建议处置**降一级**（高→中、中→低），暂缓禁用/停用。天数、是否放宽、不用/不常用美元阈值、外部渠道是否纳入对照，均可在一表总览页或 `PUT /api/policy/hygiene` 修改，写入 `env/hygiene_policy.json`（下次分析生效）。默认：`new_deploy_days=10`、`unused_used_usd=0`、`uncommon_used_usd=1`、`relax_on_new_deploy=true`、`external_vendors_in_scope=false`。`uncommon_used_usd` 不能小于 `unused_used_usd`。恰好满宽限期天数、没有部署时间、或时间解析失败，都不放宽。旧 Excel 没有「部署时间」列时须重新采集数据汇总、上游信息再生成总览。

| 类别 | 用哪一列时间 |
| ---- | ------------ |
| 下游无上游；渠道余额「不用 / 不常用」 | 网关渠道「部署时间」（数据汇总渠道 `created_time`） |
| 上游无下游 | 火山云 / Azure 表最后一列「部署时间」 |
| 环境覆盖（缺一站或跨站密钥不一致） | 已有站点里**最新**的那条渠道部署时间 |

时间格式按 `YYYY-MM-DD HH:MM:SS`（也认日期-only）。放宽后：问题列前缀「新部署未满 10 天，评估已放宽。」；建议末尾补「部署未满 10 天，暂缓禁用/停用，观察后再处置」。`建议处置` **最后一列是部署时间**。分析表「说明」工作表有同名规则备忘。

**怎么判定「对得上」**

| 上游 | 网关渠道怎么认 | 命中任一即匹配 |
| ---- | -------------- | -------------- |
| 火山云 | 类型含「火山」「豆包」，或 `base_url` 含 `volces.com` / `arkcn` | **密钥**：网关常为无 `ark-` 前缀的 UUID，上游为 `ark-<uuid>-后缀`，按 UUID / 去前缀 / 子串相容匹配。**部署名**：模型列表、重定向或渠道名含 `ep-…`。**名称**：渠道名 = 接入点名称 |
| Azure OpenAI | 类型含 azure，或 `base_url` 含 `openai.azure.com` | **密钥一**相等（忽略大小写）；或**部署名**出现在渠道名 / 模型列表 / 重定向；或**接口主机**相同 |

**工作表**

| 工作表 | 内容 |
| ------ | ---- |
| `分析总览` | 渠道数、已匹配、外部渠道、高/中/低建议条数、渠道余额文件。部分数量用 `COUNTIF` / `COUNTA` 公式，打开 Excel 即可刷新 |
| `建议处置` | 待处理建议合表。列：级别 / 类别 / 站点 / **渠道名称** / **令牌名称** / **密钥摘要** / … / **近一月活跃** / **部署时间**（末列）。级别着色：高红、中黄、低绿。渠道及列出的令牌均已禁用时不写本表 |
| `已禁用建议` | 紧挨建议处置右侧，列结构相同。存放渠道已禁用、且相关非无限制令牌也全部已禁用（或没有这类令牌）的原建议，以及已禁用令牌。便于对照，不必再处置 |
| `批量禁用` | 紧挨已禁用建议右侧。test/uat/prod 的**渠道**、**令牌**粘贴列，格式 `名称[Tab]分组`，复制到批量配置即可预禁用。规则见下节 [批量禁用](#批量禁用) |
| `下游无上游` | 网关已有火山/Azure 渠道，上游找不到密钥或部署 → **高**：建议在该站点禁用或删除；部署未满 10 天降为**中**。末列部署时间 |
| `上游无下游` | 上游有接入点/部署，test/uat/prod **都没有**对应渠道 → **中**：确认是否下线；仍有效则补登记，否则可停用上游密钥。部署未满 10 天降为**低**。末列部署时间 |
| `环境覆盖` | 只报「至少两站有、缺一站」或「同名渠道密钥跨站不一致」。当前配置多为 test/uat/prod；后期收成生产/非生产两集群后，覆盖按已配置站点计，不再假定必须三站齐。新部署未满 10 天同样降一级 |
| `密钥共用` | 同一密钥被 **3 个及以上**渠道使用（轮换/泄露影响面） |
| `令牌对照` | 令牌引用了本环境已不存在的渠道、或带明确过期时间。「永不过期」不报；**已禁用**令牌不进建议处置，改写入 `已禁用建议`（本表仍可看到） |
| `渠道余额` | 有 `渠道余额_时间戳.xlsx` 时写入。判定：不用 / 不常用 / 常用。含 **近一月活跃**（多模型分行；失败或无信息为 N/A）。无该文件则本表为空。末列部署时间；不用为中；不常用且近一月无活跃升为中并进建议处置；任一模型有活跃或 N/A 则不进建议处置 |
| `匹配明细` | 每个网关渠道一行：是否匹配、匹配方式、上游对象，便于核对误报 |
| `说明` | 规则备忘 |

**建议级别**

| 级别 | 典型情况 | 建议动作 |
| ---- | -------- | -------- |
| 高 | 下游无上游（火山/Azure 渠道在上游找不到） | 在对应 test/uat/prod **禁用或删除**该渠道 |
| 中 | 上游无下游；同名渠道密钥跨站不一致；令牌引用丢失；**不用**（已用 = $0）；**不常用且近一月无活跃**；新部署放宽后的原「高」项 | 补登记、核对密钥，或停用未使用的上游/网关渠道；新部署先观察 |
| 低 | 环境缺一站；多渠道共用密钥；**不常用**但无近一月无活跃（或旧余额表无该列）；新部署放宽后的原「中」项。渠道/令牌已禁用的原建议在 `已禁用建议` | 确认是否保留；三站应对齐时再补；新部署暂缓禁用/停用 |

分析**不会**自动改网关。推荐在一表总览页勾选建议后点 **预禁用**（先预览再确认）。也可打开分析表工作表 `批量禁用`，复制对应环境的渠道列或令牌列，到批量配置 **渠道管理 / 令牌管理** 粘贴（格式 `名称` Tab `分组`），先「预禁用」再确认。规则见 [批量禁用](#批量禁用)。

##### 批量禁用

`建议处置` 右侧先是 `已禁用建议`，再是 **`批量禁用`**。只生成粘贴文本，**不改 NA**。

| 列 | 用途 |
| -- | ---- |
| `test渠道` / `uat渠道` / `prod渠道` | 复制整列 → 渠道管理 → 预禁用 |
| `test令牌` / `uat令牌` / `prod令牌` | 复制整列 → 令牌管理 → 预禁用 |

格式一律 **`名称` + Tab + `分组`**（渠道名带空格时也用 Tab，不要只靠空格拆）。完整创建行不必写。

**渠道列写什么**

- 纳入：`建议处置` 里 **高 / 中**，且类别为 **下游无上游**、**渠道余额（不用）**、**渠道余额（不常用且近一月无活跃）** 的网关渠道
- 不纳入：上游无下游（那是云侧密钥）、环境覆盖、新部署暂缓（建议含「暂缓禁用/停用」）、已经「已禁用」的渠道、渠道余额「不常用」但无近一月无活跃（级别仍为低）、近一月仍有活跃或活跃为 N/A 的用量项

**令牌列写什么（不牵连仍在用的渠道）**

一条令牌的「包含渠道」可以有多条。禁用清单按**渠道**收，不因为令牌还引用它就把整条令牌带上：

| 情况 | 渠道列 | 令牌列 | 其它渠道 |
| ---- | ------ | ------ | -------- |
| 令牌挂了 A、B；只有 A 不用 / 过期 | 只写 **A** | **不写**该令牌 | **不写 B** |
| 令牌挂的仍启用渠道 **全部** 都在本次渠道禁用清单里（禁完后没有还能用的渠道） | 写这些渠道 | **才写**该令牌 | — |
| 「包含渠道」为无限制 / 无限（如分组共享令牌） | 仍可写对应渠道 | **不写**该令牌 | — |
| 令牌本身已禁用 | — | **不写** | — |
| `令牌对照`（引用已不存在的渠道等，级别高/中） | 不因此多写渠道 | 可写该令牌 | — |

例：`demo-platform-*-model-a&model-b` 同时包含 `model-a`（已用 = $0）和 `model-b`（仍启用）→ 只把 model-a 写入对应环境的**渠道**列；令牌列和 model-b 都不写。`demo-lab-gpt-x` / `demo-assistant-dev` 同时包含 `demo-dev-gpt-x` 与 `demo-dev-gpt-x-codex` 时同样只禁不用的那条渠道。

实现：`batch/lib/overview_analyzer.py`（`build_batch_disable_rows`）；测试：`batch/tests/test_overview_analyzer.py`（含新部署放宽、多渠道令牌不牵连）。

### 权限建议


| 操作                  | 建议账号     |
| ------------------- | -------- |
| 渠道 / 启停 / 日志 / 数据汇总 | Admin    |
| 总览拉取渠道密钥 | **Root** |
| 智能分析（只读 Excel） | 不连网关；有总览文件即可 |
| 分组创建 / 删除           | **Root** |


---



## 平台信息

进入批量配置右侧的 **平台信息** Tab（`#platform`）。此模块用于在一个页面切换 **test / uat / prod**，展示 ai-cloud / New API 管理端的渠道管理与令牌管理。两类列表均按 ID 降序排列，采用全宽自适应布局，窄屏下保留横向滚动。

| 管理页 | 列 | 操作 |
| --- | --- | --- |
| 渠道管理 | ID、名称、分组、类型、状态、响应时间、近一月活跃统计、已用/剩余、优先级、权重、批量配置 | 测试、启用/禁用、编辑、删除、转换并填入更新原配置 |
| 令牌管理 | 名称、状态、剩余额度/总额度、分组、密钥、可用模型、模型限流、IP限制、创建时间、过期时间、批量配置 | 启用/禁用、编辑、删除、转换并填入令牌创建 |

- **分页**：每页支持 50 / 100 / 200 / 全部；左侧显示记录区间和总数，右侧显示紧凑页码、省略号跳页、上一页/下一页。
- **长文本展示**：名称、分组、活跃统计、模型白名单、IP 限制等过长字段在悬浮时显示完整内容，并提供复制按钮；令牌密钥仅掩码显示，悬浮不展示明文，但每行都提供复制按钮并复制完整值。
- **渠道测试**：成功后把上游返回的响应时间写回当前行；失败时页面和提示同步展示上游错误信息，并且不会把已有响应时间改回“未测试”。
- **编辑与保存**：编辑弹窗读取完整原始 JSON 字段，保存时固定 URL 中的记录 ID，避免 JSON 内误填 ID 改写其它记录。
- **批量配置转换**：新增「批量配置」列。渠道行会转换为不含密钥的 `名称 / 分组 / 类型 / 模型 / 模型重定向 / Base URL [API版本]` 行，用于「更新原配置」；令牌行会转换为 `名称 / 分组 / 模型白名单 [额度(tokens)]` 行，用于令牌创建。每行可复制完整批量行，也可一键填入批量配置对应输入区。

1. 复制 `env/sites.example.json` 为 `env/sites.json`，为需要管理的 `test`、`uat`、`prod` 分别填写 `base_url`、`username`、`password`；账号开启登录两步验证时填入该环境自己的 `totp_secret`。
2. 请让该环境账号具备 ai-cloud 管理端权限（New API 的 Admin 或更高角色）。渠道管理接口要求管理员权限；令牌管理也按上游站点的实际授权返回。
3. 超管在「管理用户」中给网站账户授予“平台信息”功能后，用户才能看到此 Tab；每次读取和保存均同时受页面、API 和 CSRF 校验保护。
4. 选择环境后，切换「渠道管理」或「令牌管理」，点“编辑”读取单条完整记录；如需清理废弃记录，可在对应行使用删除按钮并二次确认。

凭据、一次性验证码与 `totp_secret` 不会传给浏览器。平台信息只从服务器本地的 `env/sites.json` 创建上游会话，并复用项目已有的两小时登录会话缓存。列表与编辑接口会返回上游实际错误，例如环境未配置、登录失败、TOTP 无效或上游账号无管理权限。

## 数据汇总

从多个 NA 站点一键采集**渠道 + 令牌**，导出为 Excel。

### 网站列表与 env 自动识别

| 优先级 | 来源 | 说明 |
| ------ | ---- | ---- |
| 1 | `localStorage`（`na_data_summary_sites`） | 已有填写过的站点地址时优先使用 |
| 2 | `env/sites.json` | 本地为空且文件已配置时，自动填入**已配置站点**卡片 |
| 3 | 空白卡片 | 无本地、无 env 时显示空卡片；历史环境列仍可能是 test / uat / prod |

已配置 env 时工具栏显示「从 env 载入」，可随时覆盖当前卡片。与批量配置连接配置快捷按钮共用同一文件与 `GET /api/env-sites`。

### 采集逻辑


| 项目        | 说明                                   |
| --------- | ------------------------------------ |
| **分页拉取**  | 渠道 `status=all` 全状态；分页直至 `total` 收齐  |
| **排序**    | 各环境主表按渠道/令牌 **ID 升序**（小 ID 在上）       |
| **同名渠道**  | 按 **ID** 区分，不因名称相同而丢失（如 UAT 85 条全保留） |
| **无名称记录** | 显示为 `(未命名#ID)`                       |
| **环境归属**  | 由站点表格「环境」列指定（历史 key 多为 test/uat/prod），勿填错地址    |
| **登录验证码** | 采集 / 补全密钥 / 余额查询会检查会话与 TOTP。工作台已认证或已预置密钥时**跳过审查弹窗**；仅无 TOTP 且无有效会话才弹 30 秒临时码。勾选含密钥或补全密钥时，即使登录无 2FA 仍需二次验证（可用 totp_secret） |
| **渠道密钥**  | 列表 API 不含明文；勾选「包含渠道密钥」后走二次验证再逐条拉取（见下节）；含密钥采集同样**新建** Excel |
| **Excel**     | **一键采集每次新建**时间戳文件（同一次点击多站写入同一新文件）；**只有「继续补全密钥」**才基于最新一份更新 |


采集日志示例：

```text
[uat] https://ai-cloud-uat.example.com → 拉取渠道 85 / 令牌 40
写入主表渠道 [test:90, uat:85, prod:16]
跨环境同名渠道 [test:61, uat:61]，已另写入「重复模型」表（主表保留全量）
```

### 验证码与全局认证

部分站点开启登录两步验证，部分没有。数据汇总「一键采集」「继续补全密钥」「多站点查询余额」以及一表总览拉密钥，会调用 `POST /api/data-summary/inspect-auth`（**不带一次性验证码**试探；已有会话则不打登录口；已预置 `totp_secret` 则自动生成码）。

**前端不再默认弹出审查确认窗。** 工作台 [全局站点认证](#全局站点认证) 已写会话，或站点已预置 TOTP 时，直接执行；仅 `needs_otp_prompt` 的站点再要 30 秒临时码。

| 审查结果 | 后续 |
| -------- | ---- |
| **会话已就绪**（`session_ready`） | 跳过弹窗，直接采集 / 查询 |
| **无需验证码**（`ready`） | 同上；探测成功会写入会话缓存 |
| **需要登录 2FA**（`need_otp`）且未预置 TOTP | 弹窗输入该站认证器 6 位码、8 位备用码，或 TOTP 原始密钥 |
| **已预置 totp_secret** | `needs_otp_prompt=false`，登录/导出密钥自动生成当前码 |
| **尚未绑定 MFA**（`setup`） | 不可采集；请先在 NA 控制台完成绑定 |
| **限流**（`rate_limited`） | 不可采集；约 15～20 分钟后再试 |
| **账号/地址错误**（`error`） | 不可采集；修正卡片后再审 |

勾选「包含渠道密钥」或点「继续补全密钥」时：登录无需 2FA 的站点审查仍可能标为**需要二次验证**（`/api/verify` 必须带码）。已预置 `totp_secret` 或会话仍有效时**不再弹窗**。未预置密钥的站点再按站弹窗（补密钥必须 verify）。

审查本身会计入登录配额；已有有效会话时不会再打登录接口。Access Token 站点一般不需要登录 OTP。建议例行盘点前先在工作台点一次「认证全部」。


### 含渠道密钥导出（二次验证）

对齐 NA 控制台「查看密钥」流程（`ai-cloud-test`：`POST /api/verify` → `POST /api/channel/{id}/key`）：

1. 数据汇总页勾选 **包含渠道密钥（需二次验证，Root 账号）**
2. 点击采集后检查各站会话 / TOTP；工作台已认证则直接拉密钥。仅对需要二次验证且**未预置 totp_secret、无有效会话**的站点填写认证器 6 位码（约 30 秒刷新，亦可用备用码或原始密钥）。登录无 2FA 时导出密钥仍要验证
3. 服务端用账号密码登录（保留 session）→ `POST /api/verify` → 批量 `POST /api/channel/{id}/key`
4. **新建**一份带时间戳 Excel，渠道表增加 **密钥** 列；验证有效约 5 分钟，一次验证可拉完全站渠道
5. 若本窗配额不够、密钥未拉完：用「继续补全密钥」写回**最新那份**（见下节）

| 要求 | 说明 |
| ---- | ---- |
| **Root** | 上游 `GetChannelKey` 需 Root（role≥100）；普通 Admin 无法拉密钥 |
| **账号密码** | 须用站点卡片中的用户名密码（依赖 cookie session）；勿仅靠 Access Token |
| **登录 2FA** | 若登录也要求两步验证，同一验证码（或 totp_secret 生成的当前码）会先用于 `POST /api/user/login/2fa` |
| **多站点** | 各站独立 2FA，**不要**把同一验证码填到所有环境；建议先工作台认证 |
| **上游限流** | `CriticalRateLimit` 默认约 **20 次 / 20 分钟**（登录、`/api/verify`、`/channel/{id}/key` 共用同一 **ClientIP** 桶）。工具侧：会话落盘复用、验证未过期跳过 `/api/verify`、**按剩余配额一次拉满**（不再固定砍成 15 条）、仅真限流/配额用尽才提示等待。运维可提高 `CRITICAL_RATE_LIMIT` |

接口：`POST /api/data-summary/inspect-auth`（采集前审查）；`POST /api/data-summary/collect`（`include_keys` + 各站 `otp_code` / `totp_secret`；同一次多站可传 `output_path` 写入同一新文件）；续传：`POST /api/data-summary/fill-keys`（每次 1 个站点，更新最新 Excel）。服务端也会按站点地址从 `env/sites.json` 补齐 `totp_secret`。


### 输出文件

```text
excel/ai网关令牌及渠道列表_YYYYMMDDHHmmss.xlsx
```

「下载 Excel」指向 `excel/` 下**文件名时间戳最新**的**网关汇总**（`ai网关令牌及渠道列表_时间戳.xlsx`；同名前缀多份不看修改时间）。总览文件名是 `ai网关令牌及渠道列表_一表总览_时间戳.xlsx`，**不会**被当成最新一份，也不会被「继续补全密钥」改写。一键采集分站写入同一新文件，全部站点结束后再点下载，避免拿到半成品。采集过程不会自动触发浏览器下载。


| 操作 | 文件行为 |
| ---- | -------- |
| 打开汇总页 | 仅查询是否已有文件，**不**自动创建空模板 |
| **一键采集**（不勾密钥） | **每次新建**带时间戳文件；**不覆盖、不合并**上一份 |
| **一键采集**（勾选「包含渠道密钥」） | 同样**每次新建**；渠道表带密钥列 |
| 同一次点击、多站点 | 分站写入同一份 `.part.xlsx`（不进入「最新一份」）；全部结束后再发布为正式文件，之后才能下载 |
| 采集全部失败 | **不落盘**（不新建、不改旧文件） |
| **继续补全密钥** | **唯一**按上一份更新的入口：读写 `excel/` 下最新文件；无文件时提示先采集 |


### 继续补全密钥

应对上游 `CriticalRateLimit`（约 20 次 / 20 分钟）导致含密钥采集中途停住：

1. 先完成至少一次成功的「一键采集」（建议勾选含密钥，或已有带渠道列表的 Excel）
2. 点「继续补全密钥」→ **先审查**各站（已预置 `totp_secret` 也先审）→ 确认后再启动
3. 未预置密钥的站点再弹窗输入**当前**二次验证码（或原始密钥）；已预置的站点审查通过后直接补全
4. 服务端读取**最新一份** Excel：该环境已有渠道则只补空密钥；**工作表为空**则从该站拉取渠道、令牌和密钥，**追加进同一文件**（不覆盖其它环境）
5. 旧表没有「密钥」列时会自动补空列再填

无 Excel 时不会凭空建空表。每次只处理 1 个站点。任意环境表为空（不只是 test/uat 有、prod 空）时，只要用户点了继续，都会按上述规则写入已有工作簿。


### 工作表


| 工作表                  | 内容      |
| -------------------- | ------- |
| `test/uat/prod-渠道管理` | 各环境渠道主表 |
| `test/uat/prod-令牌管理` | 各环境令牌主表 |
| `重复模型`               | 跨环境同名渠道 |
| `重复模型相关令牌`           | 跨环境同名令牌 |




### 渠道列（10 列，含密钥时为 11 列）

默认：`名称`、`分组`、`类型`、`状态`、`响应时间`、`模型列表`、`模型重定向`、`base_url`、`备注`、`部署时间`

`备注` 来自 New API 渠道的管理员备注字段（`remark`），固定紧跟在 `base_url` 右侧；数据汇总的各环境渠道表、重复模型表和一表总览中的同名渠道表均会保留该列。一表总览从所选数据汇总文件复制渠道表：旧汇总生成的总览会自动补空列；要带入历史渠道的实际备注，请先重新执行一次数据汇总采集。

校验规则：备注中存在与 `base_url` **完全相同的一行**即视为匹配（可保留其他备注文本）；`base_url` 有值但备注没有该行，或 `base_url` 为空而备注有内容时，仅将**备注单元格字体标为紫色**，与“已禁用”使用的红色字体区分。不会改变原有分组底色或 `base_url` 的样式；两者都为空时不标记。

勾选含密钥采集后，在 `备注` 与 `部署时间` 之间增加 **`密钥`**。

> **部署时间**：来自渠道 `created_time`（创建/配置时间），格式 `YYYY-MM-DD HH:MM:SS`。智能分析用这一列判断是否在卫生策略宽限期内（见 [新部署放宽（卫生策略）](#新部署放宽卫生策略)）。

### 令牌列（10 列）

`名称`、`项目环境`、`状态`、`剩余额度`、`分组`、`可用模型`、`包含渠道`、`IP限制`、`创建时间`、`过期时间`


| 字段          | 来源                                       |
| ----------- | ---------------------------------------- |
| **分组**      | API `group`                              |
| **项目环境**    | 与「分组」相同                                  |
| **剩余额度**    | 无限额度显示「无限额度」；否则 `剩余/总额`                  |
| **可用模型**    | 令牌模型限制；无限制显示「无限制」                        |
| **包含渠道**    | 按分组与模型匹配关联渠道名                            |
| **IP限制**    | `allow_ips`；空为「无限制」                      |
| **创建/过期时间** | 格式 `YYYY-MM-DD HH:MM:SS`；过期 `-1` 为「永不过期」 |


列表字段不全时，会自动调用令牌详情 API 补全。

### Excel 样式


| 样式     | 说明                      |
| ------ | ----------------------- |
| 表头     | 深蓝底（`#2F5496`）、白字、加粗    |
| **边框** | 外框加粗 + 内部网格细线 + 表头底部分隔线 |
| 冻结     | 首行冻结                    |
| **分色** | 见下表                     |

上游信息、上游账单、一表总览里的 **火山云 / Azure OpenAI** 表同样深蓝表头、首行冻结，并开启**列头下拉筛选**。账单费用表的筛选范围不含末行合计。已有旧文件须重新采集才会带上筛选。



| 工作表       | 分色依据           |
| --------- | -------------- |
| 渠道管理（各环境） | 相同 **分组** 同色   |
| 令牌管理（各环境） | 相同 **分组** 同色   |
| **重复模型**  | 相同 **模型列表** 同色 |
| 重复模型相关令牌  | 相同 **分组** 同色   |




### 重复检测

同一**名称**在 ≥2 个环境（test/uat/prod）出现时：

- **各环境主表仍保留全量**（与网站拉取数量一致）
- **另写入**「重复模型」「重复模型相关令牌」工作表（含来源、重复序号），便于对照排查



### 使用步骤

1. **数据汇总**：填写已配置站点（**环境列**务必选对，地址填对应站点根 URL）。建议先工作台 [全局站点认证](#全局站点认证)
2. （可选）勾选「包含渠道密钥」
3. 「一键采集并写入 Excel」→ 会话/TOTP 就绪则跳过弹窗 → **新建**带时间戳文件到 `excel/`（多站写入同一份）→ 全部完成后点「下载 Excel」
4. 密钥未拉完时：「继续补全密钥」→ 同样只对缺码站点弹窗 → 更新最新那份

### 渠道余额查询（多站点）

位于数据汇总页下方，**复用同一套网站列表**，可一次查询多个环境。

| 指标 | 字段 | 说明 |
| ---- | ---- | ---- |
| **已用** | `used_quota` | 按 `quota_per_unit` 换算为美元 |
| **剩余** | `balance` | 美元 |
| **配置时间** | `created_time` | 渠道创建/配置时间 |
| **近一月活跃** | `/api/channel/activity_stats` | 按渠道已配置模型逐项填写（`test_model` + `models` 去重）。有请求/活跃分钟/均 RPM/TPM 记「有活跃」；接口有返回但该模型无统计记「近一月无活跃」；抓取失败、无模型或无信息写 `N/A`。多个模型在同一单元格分行 |

- 勾选「已用」和/或「剩余」+ 常用美元区间
- **配置时间段**：按 `created_time` 筛选。快捷项为含今天在内的近 N 个自然日（1 / 3 / 5 / 15 / 30 / 60 / 180 / 365 天），也可填开始/结束时间；「全部」表示不限。无配置时间的渠道在选定时间段时不会命中
- 「多站点查询余额」：工作台会话或 TOTP 已就绪则直接查询；仅缺码站点弹 30 秒临时码
- **导出 Excel** 写入 `excel/渠道余额_YYYYMMDDHHmmss.xlsx`，再点「下载 Excel」；按环境分表，表名示例：
  - `test-渠道余额`
  - `uat-渠道余额`
  - `prod-渠道余额`
- 「下载 Excel」始终指向 `excel/` 下最新一份余额表
- 支持排除已禁用、全选、反选

接口：`POST /api/channel-balance-query`（传 `sites`）、`POST /api/channel-balance-export`（落盘 + 附件下载）、`GET /api/channel-balance/download`

---



## 全流程智能体

**智能体** Tab（`static/agent_ui.html`）为异步任务工作台：LLM 规划、可视化步骤开关、提取后人工门禁、渠道/令牌写入、SSE 真进度、取消 / 从失败步重试。连接与批量 Tab 共用 `na_batch_connection_config`（**不含**二次验证码），站点与汇总 Tab 共用 `na_data_summary_sites`。

网关连接与汇总站点均可从 `env/sites.json` 读取账号密码与二次验证密钥：页面可留空，服务端按地址补齐；已配置 env 时连接区显示已配置站点快捷按钮，汇总区可点「从 env 载入」（本地无站点地址时自动载入）。已预置 `totp_secret` 时，测试连接、写入与门禁确认都不必再填 6 位码。

> 任务保存在**进程内存**中，重启服务后丢失。


### 执行流程


| 步骤 | 说明 |
| ---- | ---- |
| **PLAN** | LLM 分析目标与输入；最终步骤 = 用户勾选 ∩ LLM 计划。规划上下文会脱敏，**不会把验证码/密码送给 LLM** |
| **extract** | 强制 LLM 增强提取，输出标准渠道行 |
| **gate** | 默认开启：编辑/确认渠道行后再写入；此处可刷新登录 2FA |
| **batch** | 连接 NA 并批量创建渠道（本站渠道名、模型名须唯一） |
| **token** | 按「渠道名-用户名」为每条渠道生成令牌（需填写令牌用户名） |
| **token_export** | 导出站点令牌明文（列表 API 可能脱敏） |
| **summary** | 多站点采集写入 **新** 时间戳 Excel（与手动一键采集相同，不覆盖历史文件）；站点开了登录 2FA 时卡片需填该站验证码。默认**不含**渠道密钥 |
| **upstream** | 可选。一键采集火山云 + Azure，写入 `excel/上游信息_汇总_时间戳.xlsx`。读 `env/upstream.json` 或 `env/sites.json` 的 `upstream.*`。无凭证或未采到数据则**跳过**（不失败） |
| **overview** | 可选。从已有数据汇总、上游信息文件生成一表总览，**不含**渠道明文密钥、不弹 OTP。没有可提取文件则**跳过** |
| **analyze** | 可选。读取最新总览写入 `excel/智能分析表格_时间戳.xlsx`。规则与一表总览页相同（含部署未满 10 天放宽）。无总览则**跳过**，不把整任务打成失败 |


### 二次验证（渠道 / 令牌 / 汇总）

智能体写入网关与手动批量走同一套登录：`connection.otp_code` → `POST /api/user/login/2fa`。

| 时机 | 行为 |
| ---- | ---- |
| 启动任务 | 把连接里的验证码带给后续 batch / token / token_export；未填时按地址从 `env/sites.json` 补密码与 `totp_secret` |
| 测试连接 | 建议先测通，写入会话缓存，减少门禁后再登录；密码与 TOTP 可留空走 env |
| 门禁确认 | `POST .../confirm` 可带 `otp_code` / `connection` / `sites`；页面有「写入前刷新」输入框；已预置 TOTP 可留空 |
| 失败重试 | `POST .../retry` 同样可带最新验证码，并再次从 env 补齐空字段 |
| 汇总站点 | 各卡片「登录 2FA」仅用于该站登录；密码与 TOTP 可留空由 env 补齐；手填验证码**不写入本地缓存** |
| 与密钥导出的区别 | 数据汇总「包含渠道密钥」走 `/api/verify`；智能体汇总默认不做密钥拉取 |

Web：网关连接可先填一次；确认渠道行时再看认证器填**当前**码（提取往往超过 30 秒）。多环境站点请逐张卡片填写。


### Web 使用

1. 顶栏切换到 **智能体**
2. 填写原文与 LLM；连接可用账号密码（+ 登录 2FA）或 Access Token。密码与 TOTP 可留空，使用 `env/sites.json`；也可点已配置站点快捷按钮填入。建议先「测试连接」或工作台全局认证
3. 勾选 提取 / 渠道 / 令牌创建 / 令牌导出 / 汇总；可选 上游、总览、智能分析；可选试运行、提取后确认。**只跑 上游信息、一表总览/分析时请取消勾选提取**（空原文会在提取步失败）
4. 令牌创建须填写「令牌用户名」（生成 `{渠道名}-{用户名}`）
5. 「启动智能体」→ SSE 时间线；门禁态编辑渠道行，已预置 TOTP 可直接确认，否则刷新二次验证码后再「确认并继续」
6. 运行中可取消；失败后可从失败步重试（重试前可改验证码）。完成后分别点「下载数据汇总」「下载上游」「下载总览」「下载分析表」



### 异步 Jobs API


| 方法      | 路径                             | 说明                                                |
| ------- | ------------------------------ | ------------------------------------------------- |
| `POST`  | `/api/agent/jobs`              | 创建任务；`auto_start` 默认 true                         |
| `GET`   | `/api/agent/jobs/<id>`         | 任务快照                                              |
| `GET`   | `/api/agent/jobs/<id>/events`  | SSE（`step` / `status` / `log` / `error` / `done`） |
| `PATCH` | `/api/agent/jobs/<id>/plan`    | 修改 steps / channel_lines / options；可附带 `otp_code` / `connection` / `sites` |
| `POST`  | `/api/agent/jobs/<id>/confirm` | 门禁确认；`auto_resume` 可继续；可刷新 `otp_code` / `sites` |
| `POST`  | `/api/agent/jobs/<id>/start`   | 启动或从 checkpoint 续跑                                |
| `POST`  | `/api/agent/jobs/<id>/cancel`  | 协作式取消（步骤边界生效）                                     |
| `POST`  | `/api/agent/jobs/<id>/retry`   | 从失败步重试（保留已成功步）；请求体可带最新 `otp_code` |




### 兼容同步 API

`POST /api/agent/run`：内部创建任务并等待终态；默认 `require_confirm=false`（适合 CI）。响应额外包含 `job_id`。

```bash
curl -X POST http://127.0.0.1:8765/api/agent/run \
  -H "Content-Type: application/json" \
  -d '{
    "goal": "提取并写入 uat，再汇总三站",
    "raw_text": "demo-alpha-test-model-a\nark-xxxx\nep-xxxx",
    "llm_api_base": "https://api.openai.com/v1",
    "llm_api_key": "sk-...",
    "llm_model": "gpt-4o-mini",
    "connection": {
      "base_url": "https://na-uat.example.com",
      "username": "admin",
      "password": "your-password",
      "otp_code": "123456"
    },
    "sites": [
      {"env": "test", "base_url": "https://na-test.example.com", "username": "admin", "password": "xxx", "totp_secret": "把认证器原始密钥填在这里"},
      {"env": "uat", "base_url": "https://na-uat.example.com", "username": "admin", "password": "xxx", "otp_code": "222222"}
    ],
    "options": {"dry_run": true}
  }'
```

**必填**：`raw_text` 或 `sites` 至少其一（仅令牌导出 / 上游 / 总览或分析时可都空）；`llm_api_base`

**常用 options**：


| 字段                                          | 说明                                 |
| ------------------------------------------- | ---------------------------------- |
| `run_extract` / `run_batch` / `run_summary` | 是否执行各步（默认 true） |
| `run_token` / `run_token_export` | 令牌创建 / 令牌导出（默认 false） |
| `run_upstream` / `run_overview` / `run_analyze` | 上游采集 / 总览 / 智能分析（默认 false）。无凭证或无文件则跳过；分析规则与一表总览页相同（含新部署放宽） |
| `token_usernames` | 令牌用户名（多值逗号或换行）；生成 `{渠道名}-{用户名}` |
| `dry_run` | 试运行，默认 false |
| `use_llm_plan` | 是否 LLM 规划（默认 true） |
| `require_confirm` | 提取后门禁；Jobs 默认 true，`/run` 默认 false |


**响应**：`success`、`message`、`steps[]`、`channel_lines`、`plan`、`job_id`、`job_status`

### 相关模块


| 文件                          | 说明              |
| --------------------------- | --------------- |
| `agent/lib/pipeline_llm.py` | LLM 规划器         |
| `pipeline_runner.py`        | 分步执行、短路、门禁、步骤求交 |
| `agent_jobs.py`             | 异步任务状态机与事件      |
| `static/agent_ui.html`      | Web 工作台         |


---



## 命令行

统一入口 `app.py`（默认子命令等价于 `serve`）：

```bash
# Web 服务
python app.py
python app.py serve --port 9000 --no-browser

# 渠道智能提取
python app.py extract -f examples/agent/multi/input.txt
python app.py extract -f input.txt --json -o result.json
python app.py extract --use-llm --llm-provider mimo --llm-api-key sk-xxx -f input.txt

# 令牌智能提取（规则拼接，无 LLM）
python app.py extract-token -t "demo-a-uat-m1
张三
demo-a-uat
m1，m2"
# 亦可：令牌名(+人名分行) + 渠道批量行 → 自动识别分组与模型
python app.py extract-token -f draft.txt --json -o tokens.tsv
# 等价：python app.py extract --mode token -f draft.txt

# 批量创建渠道（默认；样例见 examples/batch/）
python app.py batch -c batch/config.json -f examples/batch/mixed/input.tsv
python app.py batch channel -c batch/config.json -f examples/batch/azure/input.tsv
python app.py batch channel --otp-code 123456 -c batch/config.json -f examples/batch/mixed/input.tsv

# 批量创建令牌 / 分组
python app.py batch token -c batch/config.json -f examples/batch/tokens/input.txt
python app.py batch group -c batch/config.json -f examples/batch/groups/input.txt --ratio 1.0
# 快捷别名：
python app.py token-batch -c batch/config.json -f examples/batch/tokens/input.txt
python app.py group-batch -c batch/config.json -f examples/batch/groups/input.txt

# 亦可在子目录直接调用
cd agent && python main.py --mode token -f ../examples/batch/tokens/input.txt
cd batch && python main.py token -c config.json -f ../examples/batch/tokens/input.txt
```

| 子命令 | 说明 |
| ------ | ---- |
| `extract` | 渠道提取；加 `--mode token` 可令牌提取 |
| `extract-token` | 令牌提取快捷入口 |
| `batch` / `batch channel` | 渠道批量（无子命令时默认 channel） |
| `batch token` / `token-batch` | 令牌批量 |
| `batch group` / `group-batch` | 分组批量 |

更多参数：`python app.py extract -h`、`python app.py extract-token -h`、`python app.py batch -h`。

### 运行测试

```bash
python tests/test_web_identity.py
python agent/tests/test_channel_line_parser.py
python agent/tests/test_extract_for_update.py
python agent/tests/test_token_extractor.py
python agent/tests/test_group_deriver.py
python agent/tests/test_llm_enhance.py
python batch/tests/test_data_summary.py
python batch/tests/test_data_summary_exporter.py
python batch/tests/test_channel_batch_status.py
python batch/tests/test_channel_batch_update.py
python batch/tests/test_channel_batch_delete.py
python batch/tests/test_token_batch_status.py
python batch/tests/test_channel_balance_query.py
python batch/tests/test_overview_exporter.py
python batch/tests/test_overview_analyzer.py
python batch/tests/test_upstream_volc.py
python batch/tests/test_upstream_azure.py
python batch/tests/test_deploy_time.py
python batch/tests/test_volc_billing.py
python batch/tests/test_azure_billing.py
python batch/tests/test_bill_combined.py
python batch/tests/test_log_model_fuzzy.py
python batch/tests/test_log_export_columns.py
python batch/tests/test_totp.py
python batch/tests/test_inspect_auth.py
python batch/tests/test_login_2fa.py
python batch/tests/test_channel_key_2fa.py
python batch/tests/test_duplicate_uniqueness.py
python agent/tests/test_agent_auth_refresh.py
python agent/tests/test_pipeline_llm.py
python agent/tests/test_pipeline_runner.py
```

---



## HTTP API



### 智能提取 API


| 方法     | 路径                   | 说明                                                                 |
| ------ | -------------------- | ------------------------------------------------------------------ |
| `GET`  | `/api/llm-presets`   | LLM 厂商预设                                                           |
| `POST` | `/api/extract`       | 渠道智能提取（`use_llm` 默认 false）；`for_update: true` 时不要求密钥；传 `extract_mode=token` 时等价于令牌提取 |
| `POST` | `/api/extract-token` | 令牌智能提取（规则拼接，无 LLM）                                                  |
| `GET`  | `/api/batch-config`  | 默认 NA 连接配置                                                         |
| `GET`  | `/api/env-sites`     | test/uat/prod 快捷连接；无 `env/sites.json` 时 `configured=false`；含 `has_totp_secret`，不含密钥明文 |


#### `POST /api/extract`（渠道）

请求体常用字段：`raw_text`、`use_llm`、`llm_provider`、`llm_api_base`、`llm_api_key`、`llm_model`。  
更新提取：`for_update: true`（或 `require_key: false`）时不要求 `api_key`，输出行无秘钥列。默认创建提取仍缺密钥即失败。  
成功时返回 `channel_lines`、`items[]`（含 `channel_line`、`fields`）、`mode`（`rules` / `llm` / …）。

#### `POST /api/extract-token`（令牌）

三行/四行示例：

```json
{ "raw_text": "demo-a-uat-m1\n张三\ndemo-a-uat\nm1，m2" }
```

渠道行转令牌时，`raw_text` 为「令牌名\\n[人名\\n]渠道批量行…」（与 Web 粘贴相同）。

响应要点：

| 字段 | 说明 |
| ---- | ---- |
| `success` / `message` / `count` | 是否成功、摘要、成功条数 |
| `mode` | 固定 `token_rules` |
| `token_lines` | 多行批量文本（Tab 分隔）；亦兼容填充 `channel_lines` 便于同一前端渲染 |
| `items[]` | 每条含 `name`、`group`、`models`、`token_line`、`fields`、`success` |
| `warnings` | 部分块失败时的说明 |

示例响应片段：

```json
{
  "success": true,
  "mode": "token_rules",
  "count": 1,
  "token_lines": "demo-a-uat-m1-张三\tdemo-a-uat\tm1,m2",
  "items": [
    {
      "index": 1,
      "success": true,
      "name": "demo-a-uat-m1-张三",
      "group": "demo-a-uat",
      "models": "m1,m2",
      "token_line": "demo-a-uat-m1-张三\tdemo-a-uat\tm1,m2",
      "fields": { "名称": "demo-a-uat-m1-张三", "分组": "demo-a-uat", "模型": "m1,m2" }
    }
  ]
}
```


### 批量配置 API


| 方法     | 路径                           | 说明                      |
| ------ | ---------------------------- | ----------------------- |
| `POST` | `/api/test-connection`       | 测试连接                    |
| `POST` | `/api/batch-create`          | 批量创建渠道                  |
| `POST` | `/api/batch-update-channels` | 渠道预更新 / 确认更新（`dry_run`；不改密钥） |
| `POST` | `/api/channel-remark-sync`   | 预览 / 确认将全部渠道 Base URL 追加到备注（`dry_run`） |
| `POST` | `/api/batch-delete-channels` | 渠道预删除 / 确认删除（`dry_run`） |
| `POST` | `/api/batch-channel-status`  | 按上游 / 类型 / ID / **名称+分组** 启停渠道 |
| `POST` | `/api/channel-balance-query` | 查询渠道已用 / 剩余余额（美元区间 + 配置时间段） |
| `POST` | `/api/channel-balance-export`| 导出渠道余额 Excel：写入 `excel/` 后作为附件下载 |
| `GET`  | `/api/channel-balance/download` | 下载 `excel/` 下最新一份渠道余额 Excel |
| `POST` | `/api/token-batch-create`    | 批量创建令牌                  |
| `POST` | `/api/token-batch-update`    | 预览 / 确认更新已有令牌额度         |
| `POST` | `/api/token-batch-delete`    | 令牌预删除 / 确认删除            |
| `POST` | `/api/token-batch-status`    | 令牌预禁用 / 预启用（`action` + `dry_run`；名称+分组） |
| `POST` | `/api/token-export`          | 导出令牌名称 + 密钥文本           |
| `POST` | `/api/groups-list`           | 列出站点分组                  |
| `POST` | `/api/groups-members`        | 列出某分组下的渠道与令牌           |
| `POST` | `/api/groups-switch`         | 将勾选渠道/令牌切换到目标分组       |
| `POST` | `/api/groups-create`         | 批量创建分组                  |
| `POST` | `/api/groups-delete`         | 分组预删除 / 确认删除            |
| `POST` | `/api/logs-export`           | 启动使用日志导出任务，立即返回 `job_id` / 进度 |
| `GET`  | `/api/logs-export/jobs/<id>` | 轮询导出进度（`fetched` / `total` / `state`） |
| `POST` | `/api/logs-export/jobs/<id>/cancel` | 终止导出 |
| `GET`  | `/api/logs-export/info` | 最新使用日志文件是否已生成 |
| `GET`  | `/api/logs-export/download` | 下载 `excel/` 下最新一份使用日志 |
| `GET`  | `/api/logs-export/file/<filename>` | 按文件名下载已完成文件 |
| `POST` | `/api/channel-models`        | 渠道模型目录（令牌用）             |
| `GET`  | `/api/channel-types`         | 渠道类型列表                  |

账号密码认证可附带 `otp_code`（6 位、8 位备用码，或 TOTP 原始密钥）以及 `totp_secret`。服务端会按 `base_url` 从 `env/sites.json` 补齐 `totp_secret`。Access Token 模式一般不需要登录 OTP。请求体可带 `verify_ssl`（默认 `true`）。

`POST /api/batch-update-channels` **请求体：** `base_url`、认证字段、`batch_text`、`dry_run`（默认 `true` 仅预览）和确认执行时可传的布尔值 `overwrite_remark`。**不读取、不覆盖密钥**；备注为空时自动写入本行规范化后的 `base_url`，已有备注仅当 `overwrite_remark=true` 才覆盖。预更新固定按“将覆盖”的结果展示差异，并返回 `remark_overwrite_candidates` 供页面弹窗确认。按名称+分组匹配；名称列支持 `原名称=>新名称`。  
**响应** `data`：`matched_count`、`updated_count`、`skipped_count`、`failed_count`、`remark_overwrite_candidates`、`dry_run`、`items[]`。

`POST /api/channel-remark-sync` **请求体：** `base_url`、认证字段、`dry_run`（默认 `true`）。扫描该站点全部渠道，常规渠道取 `base_url`，Azure 取同字段所代表的 `AZURE_OPENAI_ENDPOINT`；只以 `PUT /api/channel/` 提交 `id` 与 `remark`。原备注非空时换行追加，同一地址已存在则跳过。备注追加后超过 **255** 个字符、缺少地址或渠道 ID 时，该渠道不提交更新，`items[]` 会返回对应名称和失败原因；其他渠道可继续完成。

`POST /api/token-batch-update` **请求体：** `base_url`、认证字段、`batch_text`、`dry_run`（默认 `true`）。`batch_text` 支持完整四列 `名称 分组 模型列表 额度(tokens)` 或精简三列 `名称 分组 额度(tokens)`；每条都必须明确给出额度。接口按名称+分组匹配，更新仅写入 `remain_quota` 和 `unlimited_quota=false`，并保留其余令牌配置。  
**预览示例：**

```json
{
  "base_url": "https://na.example.com",
  "username": "admin",
  "password": "***",
  "batch_text": "legacy-token-a\tteam-a\t500000",
  "dry_run": true
}
```

**响应** `data`：`total`、`matched_count`、`updated_count`、`skipped_count`、`failed_count`、`dry_run`、`items[]`。预览成功后以相同 `batch_text` 将 `dry_run` 改为 `false` 执行确认更新。

`POST /api/batch-channel-status` **请求体：**


| 字段                      | 说明                                |
| ----------------------- | --------------------------------- |
| `base_url` / 认证字段       | 同其他批量接口                           |
| `channel_type`          | 渠道类型标签或编号（`upstream` / `type` 必填；`name` 不需要） |
| `action`                | `enable` 或 `disable`              |
| `dry_run`               | `true` 仅返回匹配清单；`false` 执行更新       |
| `match_mode`            | `upstream`（默认）/ `type` / `ids` / **`name`（名称+分组）** |
| `model_text` 或 `models` | 上游模型列表（`match_mode=upstream` 时必填） |
| `channel_ids`           | 渠道 ID 数组（`match_mode=ids` 时必填）    |
| `batch_text`            | 批量文本（`match_mode=name` 时必填，格式同删除：`名称 分组`） |


**响应** `data`**：** `matched_count`、`updated_count`、`skipped_count`、`failed_count`、`dry_run`、`items[]`（含 `target_id`、`name`、`group`、`current_status`、`status_label`、`matched_upstreams`、`enabled` 等）

`POST /api/token-batch-status` **请求体：** `base_url`、认证字段、`batch_text`（`名称 分组` 或完整令牌行）、`action`（`enable` / `disable`）、`dry_run`。按名称+分组匹配；已是目标状态则跳过。已过期或额度用尽的令牌启用可能失败。

`POST /api/groups-members` **请求体：** `source_group`。**响应** `data`：`channels[]`、`tokens[]`（`id`、`name`、`group`、`status_label`）。

`POST /api/groups-switch` **请求体：**


| 字段 | 说明 |
| ---- | ---- |
| `source_group` / `target_group` | 源分组、目标分组（须已存在且不相同） |
| `kind` | `channel` 或 `token` |
| `ids` | 要切换的 ID 数组（勾选结果） |
| `dry_run` | `true` 仅预览 |


**响应** `data`：`updated_count`、`skipped_count`、`failed_count`、`items[]`（含 `old_group` / `new_group`）。

`POST /api/channel-balance-query` **请求体：**


| 字段 | 说明 |
| ---- | ---- |
| `query_used` / `query_remain` | 是否查询已用 / 剩余（至少其一为 true） |
| `used_preset` / `remain_preset` | 常用区间键，如 `ge10`、`eq0`、`le1`（≤$1）、`le5`（≤$5）、`r1_10` |
| `used_min` / `used_max` 等 | 自定义美元上下限（有值时覆盖预设） |
| `time_preset` | 配置时间快捷项：`all`、`1d`、`3d`、`5d`、`15d`、`30d`、`60d`、`180d`、`365d`（含今天的近 N 个自然日） |
| `start_timestamp` / `end_timestamp` | 配置时间起止 Unix 秒；有值时覆盖 `time_preset` |
| `channel_type` / `group` / `keyword` / `status` | 可选过滤 |


**响应** `data.items[]`：`id`、`name`、`group`、`type_label`、`status_label`、`used_usd_label`、`remain_usd_label` 等

### 平台信息 API

这些接口均只接受已经授予“平台信息”功能的本网站账户。环境限定为 `test`、`uat`、`prod`；上游账号、密码和 TOTP 不在请求体中传递，而是从服务器的 `env/sites.json` 获取。

| 方法 | 路径 | 说明 |
| ---- | ---- | ---- |
| `GET` | `/api/platform/sites` | 返回 test / uat / prod 是否已配置及其地址，不返回账号、密码或 TOTP |
| `GET` | `/api/platform/<env>/channels` | 以该环境管理端账号读取 ai-cloud 渠道管理列表（含近一月活跃统计） |
| `GET` | `/api/platform/<env>/channels/<id>` | 读取一条完整渠道记录 |
| `PUT` | `/api/platform/<env>/channels/<id>` | 保存 `{ "record": { ...完整渠道记录... } }`；路径 ID 覆盖记录中的 `id`
| `POST` | `/api/platform/<env>/channels/<id>/test` | 测试指定渠道连通性（与 ai-cloud「测试」按钮一致）
| `PUT` | `/api/platform/<env>/channels/<id>/status` | 更新渠道状态：`{ "status": 1 }` 启用 / `{ "status": 2 }` 禁用 |
| `DELETE` | `/api/platform/<env>/channels/<id>` | 删除指定渠道 |
| `GET` | `/api/platform/<env>/tokens` | 读取该环境全部令牌管理记录 |
| `GET` | `/api/platform/<env>/tokens/<id>` | 读取一条完整令牌记录 |
| `PUT` | `/api/platform/<env>/tokens/<id>` | 保存 `{ "record": { ...完整令牌记录... } }`；保留模型级限流字段 |
| `PUT` | `/api/platform/<env>/tokens/<id>/status` | 更新令牌状态：`{ "status": 1 }` 启用 / `{ "status": 2 }` 禁用 |
| `DELETE` | `/api/platform/<env>/tokens/<id>` | 删除指定令牌 |

模型编辑调用上游 `/api/models/`，令牌编辑调用上游 `/api/token/`。模型和令牌的列表、详情与保存结果使用上游原始字段，兼容 ai-cloud / New API 的版本差异。模型、令牌的保存操作会写入本网站审计日志，但审计内容仅记录环境和记录 ID，不记录令牌或凭据。

### 数据汇总 API


| 方法     | 路径                           | 说明                 |
| ------ | ---------------------------- | ------------------ |
| `GET`  | `/api/data-summary/info`     | Excel 状态（不自动创建空文件；指向最新一份**网关汇总**，不含总览文件） |
| `POST` | `/api/data-summary/inspect-auth` | 采集 / 补全密钥 / 余额查询前检查会话与 TOTP；`session_ready` 或已预置 totp 则前端不弹审查窗 |
| `POST` | `/api/data-summary/collect`  | **新建**时间戳 Excel；可传 `include_keys`、各站 `otp_code` / `totp_secret`、同一次多站的 `output_path` |
| `POST` | `/api/data-summary/fill-keys` | 先经页面审查后调用；**更新最新一份**中该环境空密钥；每次 1 个站点，须验证码或 totp_secret |
| `GET`  | `/api/data-summary/download` | 下载最新网关汇总 `ai网关令牌及渠道列表_时间戳.xlsx`（不含 `_一表总览_`）         |


**inspect-auth 请求体：** `sites[]`（与采集相同）、可选 `include_keys`。

**inspect-auth `data.items[]`：**


| 字段 | 说明 |
| ---- | ---- |
| `status` | `ready` / `need_otp` / `setup` / `rate_limited` / `error` |
| `collectable` | 是否可继续采集或查询 |
| `session_ready` | 内存/磁盘会话缓存仍有效（约 2 小时），不必再登录 |
| `needs_otp_prompt` | 前端是否应弹窗要验证码（已预置 totp_secret 或 `session_ready` 时为 false） |
| `needs_login_otp` | 登录接口需要 2FA |
| `needs_verify_otp` | 勾选含密钥时为 true（`/api/verify`） |
| `has_totp_secret` | 该站可用 TOTP 密钥自动生成验证码 |
| `message` | 审查结论文案 |


**collect 请求体补充：** `output_path` 为相对项目根、且必须位于 `excel/` 下的 `.xlsx` 路径。Web 一键采集多站时，第一站成功后把返回的 `file` 传给后续站，保证同一次点击只生成**一份新文件**。不传则每次请求新建。

**collect 响应字段**：


| 字段                                        | 说明                                                       |
| ----------------------------------------- | -------------------------------------------------------- |
| `file`                                    | 相对项目根的新文件路径（如 `excel/ai网关令牌及渠道列表_….xlsx`）              |
| `filename`                                | 仅文件名，便于浏览器下载                                               |
| `site_results[]`                          | 每站点：`env`、`base_url`、`channels_fetched`、`tokens_fetched` |
| `channels_in_sheet` / `tokens_in_sheet`   | 写入各环境主表的行数                                               |
| `channels_skipped_by_env`                 | 各环境参与跨环境同名的条数（信息性，主表仍保留）                                 |
| `duplicate_channels` / `duplicate_tokens` | 重复组数                                                     |
| `errors[]`                                | 失败站点及原因                                                  |


### 上游信息 API


| 方法     | 路径 | 说明 |
| ------ | ---- | ---- |
| `GET`  | `/api/upstream/config` | 是否已配置火山 / Azure 凭证（脱敏） |
| `POST` | `/api/upstream/collect` | 一次采集两侧，写入 `excel/上游信息_汇总_*.xlsx`（两张工作表） |
| `GET`  | `/api/upstream/info` | 最新汇总 Excel 摘要 |
| `GET`  | `/api/upstream/download` | 下载最新汇总 Excel |
| `GET`  | `/api/upstream/volc/info` | 火山上游 Excel 摘要 |
| `POST` | `/api/upstream/volc/test` | 测试 IAM 连接 |
| `POST` | `/api/upstream/volc/collect` | 采集并写入 `excel/` |
| `GET`  | `/api/upstream/volc/download` | 下载最新火山上游 Excel |
| `GET`  | `/api/upstream/azure/info` | Azure 上游 Excel 摘要 |
| `POST` | `/api/upstream/azure/test` | 测试 ARM 连接（需订阅「读者」） |
| `POST` | `/api/upstream/azure/collect` | 采集部署 / listKeys 并写入 `excel/` |
| `GET`  | `/api/upstream/azure/download` | 下载最新 Azure 上游 Excel |


凭证优先 `env/upstream.json`，否则 `env/sites.json` 的 `upstream.volc` / `upstream.azure`。

- 火山：须为 IAM Access Key（`AKLT…`），不是方舟推理 Key。采集结果中 **项目方** 为 `项目名-负责人`，无负责人则为 `项目名-N/A`。**最后一列「部署时间」** 来自接入点 `CreateTime`，没有则从 `ep-YYYYMMDDHHmmss` 解析。详见 [项目方：项目名-负责人](#项目方项目名-负责人)。
- Azure：须为 Entra 应用注册 + 订阅 IAM。Excel **项目 / 负责人** 来自账号标记名 `1`，按**最后一个** `-` 拆开（项目名可含 `-`，负责人在最后一段）；没有该标记则两列均为 `N/A`。**最后一列「部署时间」** 来自 ARM `systemData.createdAt`（东八区），未返回则留空。详见 [Azure OpenAI 配置与权限](#azure-openai-配置与权限)。

### 上游账单 API

| 方法 | 路径 | 说明 |
| ---- | ---- | ---- |
| `GET` | `/api/upstream/bill/info` | 最新火山云账单 Excel 摘要；含默认账期 |
| `POST` | `/api/upstream/bill/collect` | 按账期采集火山云费用，每月写入一份 `excel/上游账单_火山云_9月_*.xlsx`（按天 / 按月） |
| `GET` | `/api/upstream/bill/download` | 下载最新火山云账单 Excel |
| `GET` | `/api/upstream/azure/bill/info` | 最新 Azure 账单 Excel 摘要 |
| `POST` | `/api/upstream/azure/bill/collect` | 按账期采集 Azure Cost Management，每月写入一份 `excel/上游账单_Azure_9月_*.xlsx` |
| `GET` | `/api/upstream/azure/bill/download` | 下载最新 Azure 账单 Excel |
| `GET` | `/api/upstream/bill/combined/info` | 最新汇总账单摘要 |
| `POST` | `/api/upstream/bill/collect-all` | 按月采集两侧，每月写入一份 `excel/上游账单_汇总_9月_*.xlsx`（四张费用表） |
| `GET` | `/api/upstream/bill/combined/download` | 下载最新汇总账单 Excel |

凭证与上游信息相同。Azure 账单须订阅 IAM **成本管理读取者**。请求体可带：

- `bill_period` / `period`：单月 `YYYY-MM`
- `bill_period_from` + `bill_period_to`：闭区间（起止颠倒会自动对调）
- `bill_periods`：月份列表或逗号分隔字符串

一次最多 24 个月，**每月仍各写一份 Excel**。成功时 `data.files` 为各月文件，`data.failed` 为失败账期，`data.bill_periods` 为已写出的月份；预览字段对应该次**最近一月**。下载接口未指定 `file`/`id` 时回退该类型最新一份。

### 一表总览 API

| 方法 | 路径 | 说明 |
| ---- | ---- | ---- |
| `GET` | `/api/overview/info` | 最新总览摘要；`sources` 为将要提取的文件名；`key_status` 为已配置站点密钥已获取/仍缺；`analysis_exists` / `analysis_file` / `analysis_summary` 为最新智能分析；`latest_balance` 为将纳入的渠道余额文件（没有则为空，用量不识别） |
| `POST` | `/api/overview/collect` | 已有数据汇总、上游信息/总览则按时间戳最新提取；可传 `source_summary` / `source_upstream` 指定文件。**默认含渠道密钥**（`include_keys` 默认 true）。缺密钥时按会话/TOTP 补拉。写入新的 `excel/ai网关令牌及渠道列表_一表总览_*.xlsx` |
| `POST` | `/api/overview/fill-keys` | 对最新总览补全 **1 个**环境的空密钥（应对 429）。不改数据汇总网关汇总、不改分析表 |
| `POST` | `/api/overview/analyze` | **必须**传 `source_overview` 或 `source`（所选总览文件名）；仅当 `allow_latest=1` 时才回退到最新一份。对照上下游密钥/部署；有渠道余额表则判定不用/不常用。宽限期与阈值读卫生策略。写入新的 `excel/智能分析表格_*.xlsx`（不覆盖总览）。无总览时返回错误 |
| `GET` | `/api/overview/analyze/download` | 下载智能分析 Excel。可传 `file` / `id`；未传时回退最新一份 |
| `GET` | `/api/overview/download` | 下载总览 Excel（只取总览文件名，不是数据汇总的 `ai网关令牌及渠道列表_时间戳.xlsx`）。可传 `file` / `id`；未传时回退最新一份 |

`POST /api/overview/collect`：某一侧已有文件则**不连网**只读盘（密钥已齐时也不再拉密钥）。没有文件的一侧才现场采集。已配置站点默认含密钥，须 Root + 二次验证（`env/sites.json` 可预置 `totp_secret`；工作台已认证则不弹审查窗）。可选 `sites`（同数据汇总）、`include_keys: false` 关闭拉密钥。不传 `sites` 时用 `env/sites.json`。

### 工作台 / 产物 / 卫生策略 API

| 方法 | 路径 | 说明 |
| ---- | ---- | ---- |
| `GET` | `/api/workspace/summary` | 工作台摘要：待办计数、最近产物（含账单）、进行中智能体任务、`env_sites[]`（`cluster` / `has_totp_secret` / `session_ready`）、当前卫生策略摘要。无分析表时 `pending_high` 等为 `null`（前端不显示假 0） |
| `POST` | `/api/workspace/auth` | 按已配置站点登录并写会话缓存。请求体可选 `{ "sites": [{ "env", "otp_code" }] }`。返回各站 `session_ready` / `needs_otp_prompt` |
| `GET` | `/api/artifacts` | 列出 `excel/` 产物。必填 `kind`：`summary` / `balance` / `upstream` / `overview` / `analysis` / `bill` / `bill_azure` / `bill_combined` 等；`limit` 默认 20。`has_secrets` 仅当「密钥 / API Key」等列**单元格有值**（空列、`N/A`、密钥摘要不算） |
| `GET` | `/api/artifacts/download` | 按 `file` 或 `id` 下载，路径必须落在 `excel/*.xlsx` |
| `GET` | `/api/policy/hygiene` | 读取卫生策略（缺省文件则返回内置默认值） |
| `PUT` | `/api/policy/hygiene` | 保存到 `env/hygiene_policy.json`。字段：`new_deploy_days`（0–3650）、`unused_used_usd`、`uncommon_used_usd`（不得小于 unused）、`relax_on_new_deploy`、`external_vendors_in_scope`。下次分析生效 |
| `GET` | `/api/hygiene/actions` | 加载分析表建议。须 `file`/`id`，或 `allow_latest=1` |
| `POST` | `/api/hygiene/preview-disable` | 按勾选 `keys` 预览将禁用的渠道/令牌文本。宽限期项默认跳过，`force_hold: true` 才纳入 |
| `POST` | `/api/hygiene/confirm-disable` | 按预览结果对各环境执行预禁用（可 `dry_run`）。连接从 `env/sites.json` 与请求体 `sites` 合并 |

产物列表与下载**不会**在未指定文件时偷偷取 latest；页面下拉默认选中最新一项，但请求始终带该 id。

### 全流程智能体 API


| 方法      | 路径                             | 说明                         |
| ------- | ------------------------------ | -------------------------- |
| `POST`  | `/api/agent/jobs`              | 创建异步任务（推荐）；`auto_start` 默认真 |
| `GET`   | `/api/agent/jobs/<id>`         | 任务快照                       |
| `GET`   | `/api/agent/jobs/<id>/events`  | SSE 逐步事件                   |
| `PATCH` | `/api/agent/jobs/<id>/plan`    | 修改 steps / 渠道行 / options；可刷新 `otp_code` |
| `POST`  | `/api/agent/jobs/<id>/confirm` | 门禁确认；可带 `otp_code` / `sites` |
| `POST`  | `/api/agent/jobs/<id>/start`   | 启动或从 checkpoint 续跑         |
| `POST`  | `/api/agent/jobs/<id>/cancel`  | 取消                         |
| `POST`  | `/api/agent/jobs/<id>/retry`   | 从失败步重试；可带最新 `otp_code` |
| `POST`  | `/api/agent/run`               | 兼容：创建并同步等到终态               |


**agent/run 响应字段**：`success`、`steps[]`、`channel_lines`、`plan`、`job_id`、`job_status`

---



## 架构说明

网站化部分仍为一个 Flask 进程：`webapp/identity.py` 在应用创建时注册认证 Blueprint、加载账户会话与全局 API 守卫；业务模块保持原有 `app.py` 路由。生产时 Web 使用 PostgreSQL 18 存储账户、恢复验证码哈希、审计/任务/产物元数据，Redis 8 存储会话，Alembic 管理表结构。`/healthz` 是存活探针，`/readyz` 会验证账户数据库连接。容器镜像基于 Linux Python 3.12，因而可在 Rocky Linux 8/9 的 Docker 或 Podman 主机上运行。

`agent` 与 `batch` 共用 Python 包名 `lib`。`app.py` 通过 `_pin_lib_root()` 在加载前清空 `lib.*` 缓存并从 `sys.path` 移除另一侧目录，确保每次仅有一侧 `lib` 在 `[0]` 位置；并用 `threading.RLock` 串行化加载，避免多 Tab 并发请求（如 `/api/llm-presets` 与 `/api/data-summary/info` 同时发起）导致 `ModuleNotFoundError`。


| 场景                                  | 处理                                         |
| ----------------------------------- | ------------------------------------------ |
| 启动                                  | 先加载 batch → agent → 再加载 batch              |
| `/api/extract`、`/api/extract-token`、`/api/llm-presets` | 锁定后 `_pin_lib_root(AGENT_DIR)`，加载 agent 模块 |
| `/api/data-summary/*`               | 锁定后 `_pin_lib_root(BATCH_DIR)`，重载 batch 模块 |
| `/api/agent/run`、`/api/agent/jobs*` | 持锁加载 deps；后台线程执行流水线，SSE 推送进度               |


因此可在同一页面自由切换各 Tab。**修改 Python 代码后须重启** `run.bat`，不要仅刷新浏览器。

---



## 启动日志（审查）

便于事后排查与审计：每次进程启动（Web `serve` / CLI `extract` / `batch`）都会在项目根目录 **`log/`** 下生成**一个独立** `.txt`。

### 文件命名

```text
log/na_YYYYMMDD_HHMMSS_<模式>_pidXXXX.txt
```

| 模式        | 场景                |
| --------- | ----------------- |
| `serve`   | `python app.py` Web 服务 |
| `extract` | `python app.py extract …` |
| `batch`   | `python app.py batch …`   |


启动时终端会打印：`本次启动日志: <绝对路径>`。实现模块：`na_logger.py`。

### 行格式与级别

```text
[2026-07-29 11:22:17.666] [1785295337.666] [OK] API 响应 ← POST /api/batch-channel-status | …
```

| 部分     | 说明                          |
| ------ | --------------------------- |
| 可读时间   | 本地时间，含毫秒                    |
| Unix 戳 | 便于脚本对齐 / 排序                 |
| 级别     | `INFO` / `OK` / `WARN` / `FAIL` / `ERROR` |


### 记录范围

- 全部 `/api/*` 请求与响应摘要（含耗时、`success`、条目统计）
- 批量结果中逐条 **成功 / 失败 / 警告（跳过）**
- 登录成功、会话缓存复用、登录 **429** 退避重试
- 渠道启停、提取、采集、删除等具体操作
- **敏感字段脱敏**：密码、Token、API Key、密钥等不会明文写入

> `log/*.txt` 默认列入 `.gitignore`，仅本地保留；目录由 `log/.gitkeep` 占位。

---



## 产品文档

除本 README 外，项目自带浏览器可读的产品材料：


| 文件                                                           | 说明                            |
| ------------------------------------------------------------ | ----------------------------- |
| [docs/introduction.html](docs/introduction.html)             | 功能介绍页（工作台 + 六个业务 Tab（含上游账单）+ 智能体 + 快速启动）     |
| [docs/presentation/index.html](docs/presentation/index.html) | **18 页** HTML 演示稿（概览墙 + 全屏翻页） |
| [docs/README.md](docs/README.md)                             | 文档目录、动画编辑、PPT/PDF 导出说明        |


演示稿导出（在 `docs/presentation/` 目录）：

```bash
npm install
npx playwright install chromium
node scripts/export_deck_pptx_lossless.mjs   # → output/NA-自动配置工具-介绍.pptx
node scripts/export_deck_pdf.mjs           # → output/NA-自动配置工具-介绍.pdf
```

---



## 配置说明

| 文件 | 用途 | 是否提交 |
| ---- | ---- | -------- |
| `agent/config.json` | 渠道 LLM / 智能体规划用的大模型 | **勿提交** |
| `batch/config.json` | 默认 NA 连接（无 `sites.json`、无页面缓存时兜底） | **勿提交** |
| `env/sites.json` | 已配置站点快捷连接 + 可选 `upstream.volc` / `upstream.azure`（过渡期 key 仍可能是 test / uat / prod） | **勿提交** |
| `env/sites.example.json` | 脱敏模板（含 `_comment`）。程序**不会**读取 | 可提交 |
| `env/upstream.json` | 可选：只放火山 IAM + Azure 服务主体，**优先于** `sites.json` 里的 `upstream` | **勿提交** |
| `env/hygiene_policy.json` | 卫生策略（宽限期天数、用量阈值等）；缺省用内置默认 | **勿提交** |
| `excel/_hygiene_status.json` | 一表总览页预禁用勾选状态 | **勿提交** |
| `batch/data/token_keys.json` | 令牌密钥缓存 | **勿提交** |
| `excel/*.xlsx` / `excel/*.csv` | 汇总 / 余额 / 日志 / 上游导出 | 已 gitignore |
| `log/*.txt` | 启动会话审查日志 | **勿提交** |

```bash
cp agent/config.example.json agent/config.json
cp batch/config.example.json batch/config.json
cp env/sites.example.json env/sites.json   # 快捷按钮 + 上游凭证都写这里
```

改 JSON 后**不必**重启服务（接口每次请求都会重读文件）。改 Python 后必须重启 `run.bat`。

### env 文件怎么用

1. 复制模板：`cp env/sites.example.json env/sites.json`（Windows 可用资源管理器复制后改名）。
2. 把占位符换成真实值。`xxxxxxxx-…`、`AKLT****`、`00000000-…0001` 都是脱敏样例，**不能原样用来采集**。
3. `sites.json` / `upstream.json` 已在 `.gitignore`，不要提交仓库、不要贴到聊天/工单。
4. 上游信息页可点「从 env 载入」把已填字段铺到输入框；密钥类字段服务端有则不必再手填。

程序读上游凭证的顺序：

| 优先级 | 文件 | 识别哪些键 |
| ------ | ---- | ---------- |
| 1 | `env/upstream.json` | 顶层 `volc` / `azure`，或包在 `upstream` 里；也可把火山字段直接写在根上 |
| 2 | `env/sites.json` | `upstream.volc`、`upstream.azure`（与 test/uat/prod 同文件） |

两处都配了同一厂商时，**只用 `upstream.json` 里那套**（先读到即停）。`sites.example.json` 永远不参与读取。

`upstream.json` 也可单独建（不必复制整份 sites 模板），最小形态：

```json
{
  "volc": {
    "access_key_id": "AKLT…",
    "secret_access_key": "……",
    "region": "cn-beijing"
  },
  "azure": {
    "tenant_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "client_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "client_secret": "客户端密码的 Value",
    "subscription_ids": [
      "00000000-0000-0000-0000-000000000001",
      "00000000-0000-0000-0000-000000000002"
    ]
  }
}
```

兼容别名：火山 `ak` / `sk`；Azure `tenant` / `app_id` / `secret` / `subscription_id`（单个）/ `subscriptions`。上游信息页手填会覆盖文件里的同名字段。

### NA 站点参数（已配置站点）

给 **批量配置连接快捷按钮、平台信息、数据汇总卡片、智能体、工作台全局认证** 用。`env/sites.json` 按**实际站点**填写（过渡期 key 仍可能是 test / uat / prod），**不要把生产验证器填到非生产**。至少填 `base_url` 该站点按钮才会出现。两站齐全即为覆盖完成，不必写满三站。

网关现为 **两套集群**：**非生产**（原 test + uat）、**生产**（原 prod）。工具继续识别旧 key；新功能按「已配置站点」循环。分组名里的 test/uat/prod 与「有几套集群」不是同一件事。

| 字段 | 从哪获取 | 填什么 | 不要填 |
| ---- | -------- | ------ | ------ |
| `base_url` | 浏览器打开 NA 后看地址栏 | 站点**根地址**，如 `https://na-uat.example.com` | 不要带 `/console`、`/api`、末尾路径；工具会尽量剥掉，但请直接填根 URL |
| `username` | NA 登录页使用的账号 | 能管渠道/令牌的账号（汇总建议 Admin） | 不要填邮箱别名若站点不认 |
| `password` | 该账号密码 | 明文写在 `sites.json`（本机文件，已 gitignore） | 不要写进 `sites.example.json` 再提交 |
| `totp_secret` | **绑定 2FA 当时**显示的 Base32 密钥。路径：NA **个人设置 → 安全设置 → 两步验证 / 身份验证器**。若当时没抄：认证器 App「查看密钥 / 密钥」，或解绑后重新绑定再抄 | 一长串大写字母+数字（Base32）。也可写 `otpauth://totp/...?secret=…` | **不要**填当前闪烁的 6 位码（约 30 秒就过期）；不要多个站点共用一把密钥 |
| `default_key` | 可选。某条已有渠道的上游 API Key | 渠道行没写密钥时的兜底 `sk-…` | 不是 NA 登录密码，也不是 TOTP |
| `access_token` | NA **个人设置 → 系统访问令牌**（或管理员签发的 Token） | 与 `user_id` 一起用，**可代替** username/password | 不要和账密混填同一套（填了 Token 且未填账密时按 Token 模式） |
| `user_id` | 同上，创建 Token 时显示的用户 ID；或 NA 用户管理里的数字 ID | 整数 | 不要填用户名 |

`GET /api/env-sites` **不会**把 `totp_secret` / `password` 明文下发到浏览器，只给 `has_totp_secret`。测试连接、批量、汇总、智能体在页面留空时，服务端按 `base_url`（或站点 `env`）从本文件补齐。平台信息则完全不接收浏览器传来的上游认证字段：它仅按所选 `test` / `uat` / `prod` 从本文件建立服务端会话。

未开登录 2FA 的环境：`totp_secret` 可留空。但**含渠道密钥导出** 仍要走 `/api/verify`，未预置密钥时会弹窗要码。

### 火山云 upstream.volc

给 **上游信息 → 火山云** 用。打的是火山 **IAM OpenAPI**，不是方舟聊天 Completions。

| 字段 | 从哪获取 | 填什么 | 不要填 |
| ---- | -------- | ------ | ------ |
| `access_key_id` | [IAM 密钥管理](https://console.volcengine.com/iam/keymanage) → **新建密钥** 或查看已有 Access Key | 通常以 **`AKLT`** 开头 | 方舟控制台「API Key」页的推理 Key（`sk-` / 一长串、名称像 `prd-xxx`） |
| `secret_access_key` | 同上。**只在创建当下完整显示**，之后只见掩码 | 创建时复制的 Secret | 不要把 Access Key ID 再贴一遍；丢失则新建一把 IAM 密钥 |
| `region` | 方舟所在地域 | 国内默认 **`cn-beijing`**。接入点不在北京再改成控制台地域代码 | 不要填资源组名、项目名 |

该 IAM 用户/角色需要能调：`ListProjects`、`ListEndpoints`、`ListModelRateLimit`、`ListApiKeys`、`GetRawApiKey`（否则测试连接失败或 Excel 缺 Key）。权限不够时找火山管理员给「方舟 / 项目管理」只读 + 查看 API Key，不要用个人登录 Cookie。

Excel **API Key** 列才是方舟推理密钥，由本工具用 IAM 拉明文，不必事先写进 env。

### Azure OpenAI upstream.azure

给 **上游信息 → Azure OpenAI** 用。打的是 **ARM 管控面**，一套服务主体扫 `subscription_ids` 里列出的全部订阅。申请步骤与角色见 [Azure OpenAI 配置与权限](#azure-openai-配置与权限)；下面只写 **每个字段从门户哪一页抄**。

| 字段 | 从哪获取 | 填什么 | 不要填 |
| ---- | -------- | ------ | ------ |
| `tenant_id` | [Azure 门户](https://portal.azure.com) → **Microsoft Entra ID** → **概述** → **目录(租户) ID**。应用注册概述页也有同一项 | GUID（xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx） | Entra **对象 ID**；主域名（`xxx.onmicrosoft.com`）本工具当 ID 用不了，请填 GUID |
| `client_id` | **Entra ID → 应用注册** → 点开 `na-upstream-collector`（或你起的名字）→ **概述** → **应用程序(客户端) ID** | 应用的 Client ID（GUID） | 企业应用程序对象 ID；订阅 ID |
| `client_secret` | 同一应用 → **证书和密码** → **客户端密码** → **+ 新客户端密码** → 复制 **值（Value）** | 创建当下那一长串密码 | **机密 ID**（那是编号）；Foundry / Studio 部署页上的模型 Key；个人账号密码 |
| `subscription_ids` | **点进**要采集的那个订阅（或该订阅下任意资源 / OpenAI 账号），看浏览器**地址栏链接**：复制 `/subscriptions/` **后面那一段 GUID**（到下一个 `/` 为止）。停在「订阅」列表页时链接里通常没有 GUID。四个订阅就打开四个页面各抄一次 | JSON 数组，**每项一个 GUID**；上游信息页也可用多行文本，每行一个 | 订阅**显示名称**；完整 URL；对象 ID；`resourceGroups` 后面的资源组名 |

必须**点进**该订阅（或其中任一资源）后，地址栏才会出现 `/subscriptions/{GUID}/`。停在订阅列表页抄不到。只抄 GUID，不要整段 URL：

```text
https://portal.azure.com/#@xxxx.onmicrosoft.com/resource/subscriptions/00000000-0000-0000-0000-000000000001/overview
                                                                      └──────────── 这一段写入 subscription_ids ────────────┘

https://portal.azure.com/#@xxxx/resource/subscriptions/00000000-0000-0000-0000-000000000002/resourceGroups/rg-openai/...
                                                      └──────────── 订阅2 的 GUID ────────────┘
```

**`subscription_ids` 填写顺序 = Excel「订阅」列：**

| 数组位置 | Excel 单元格 |
| -------- | ------------ |
| 第 1 个 GUID | 订阅1 |
| 第 2 个 GUID | 订阅2 |
| 第 3 个 GUID | 订阅3 |
| 第 4 个 GUID | 订阅4 |

内部怎么称呼「订阅1～4」就按那个顺序写，不要打乱。ARM 调用仍用 GUID，表里不写 GUID。只扫一个订阅时数组里留一项即可；旧字段 `subscription_id`（字符串）仍兼容，导出为订阅1。

客户端密码只在创建页能完整复制；Value 变成 `***` 后只能 **+ 新客户端密码** 再生成，然后更新 `sites.json` / `upstream.json`。过期后「测试连接」会登录失败（401 / invalid client）。

角色提醒（字段填对仍 403 时）：每个订阅 IAM 给**该应用**加通用 **读者** + **认知服务用户（Cognitive Services User）**，不要加「安全读取者」等带前缀的读者，也不要赋给个人 admin 账号。

### 其他配置文件（agent / batch）

**`agent/config.json`**（勾选 LLM 增强、智能体必填）：从 `agent/config.example.json` 复制。

| 字段 | 从哪获取 | 说明 |
| ---- | -------- | ---- |
| `llm_provider` | 下表厂商英文名 | 如 `openai`、`volcengine`、`ollama` |
| `llm_api_base` | 厂商 OpenAI 兼容地址 | 见 [支持的厂商](#支持的厂商)；Ollama 默认本机 `11434` |
| `llm_api_key` | 该厂商控制台的 API Key | Ollama 可留空 |
| `llm_model` | 控制台模型名 | 如 `gpt-4o-mini` |
| `llm_timeout` | 秒 | 默认 60 |

也可只在 Web 页填写（存浏览器 `localStorage`），不必落盘。

**`batch/config.json`**：从 `batch/config.example.json` 复制。字段与 NA 站点相同（`base_url` / `username` / `password` / `default_key`，或 `access_token` + `user_id`）。有 `env/sites.json` 时，批量配置快捷按钮与服务端补齐优先走 env；本文件只作单站点兜底。

---




## 示例文件

项目内有两套批量样例来源，**内容对齐**（脱敏演示数据，密钥请自行替换）：

| 用途 | 路径 | 说明 |
| ---- | ---- | ---- |
| **CLI** | `examples/agent/`、`examples/batch/` | 命令行联调；Web 不依赖 |
| **Web** | `batch/static/example_*` | 批量配置页「载入示例」 |


### Agent（`examples/agent/`）


| 文件                  | 场景                                  |
| ------------------- | ----------------------------------- |
| `multi/input.txt`   | 双渠道批量（与 Web「载入示例」一致） |
| `volcano/input.txt` | 单条火山方舟                              |
| `volcano-upgrade/input.txt` | 火山自动升级申请（无密钥；须 `for_update` / `require_key=False`） |
| `azure/input.txt`   | Azure 门户链接                          |
| `custom/input.txt`  | 自定义 `sk-` 渠道                        |

```bash
python app.py extract -f examples/agent/multi/input.txt
python app.py extract -f examples/agent/volcano/input.txt --json
```


### Batch CLI（`examples/batch/`）


| 文件 | 对应 Web 样例 | 场景 | 用法 |
| ---- | ------------- | ---- | ---- |
| `mixed/input.tsv` | `example_batch.tsv` | 混合渠道（OpenAI / 自定义 / Azure） | `python app.py batch -f …` |
| `azure/input.tsv` | `example_batch_azure.tsv` | 纯 Azure（含表头） | 同上 |
| `tokens/input.txt` | `example_batch_tokens.txt` | 令牌批量（名称 / 分组 / 模型 / 可选额度 tokens） | `batch token` / `token-batch` |
| `groups/input.txt` | `example_groups.txt` | 分组批量（一行一个；`#` 注释） | `batch group` / `group-batch` |

```bash
# 需已配置 batch/config.json；样例密钥请替换
python app.py batch -c batch/config.json -f examples/batch/mixed/input.tsv
python app.py batch -c batch/config.json -f examples/batch/azure/input.tsv --json -o result.json
python app.py token-batch -c batch/config.json -f examples/batch/tokens/input.txt
python app.py group-batch -c batch/config.json -f examples/batch/groups/input.txt

# 令牌草稿 → 提取 → 再批量
python app.py extract-token -f draft.txt -o tokens.tsv
python app.py token-batch -c batch/config.json -f tokens.tsv
```

> 令牌 / 分组行格式与批量配置页一致；也可用「令牌智能提取」或 `extract-token` 生成后再创建。


### 批量 Web（`batch/static/`，「载入示例」）


| 文件                         | 场景 | 对齐 CLI |
| -------------------------- | ---- | -------- |
| `example_batch.tsv`        | 混合渠道 | `examples/batch/mixed/input.tsv` |
| `example_batch_azure.tsv`  | 纯 Azure | `examples/batch/azure/input.tsv` |
| `example_batch_tokens.txt` | 令牌批量 | `examples/batch/tokens/input.txt` |
| `example_batch_update.tsv` | 渠道更新原配置（无密钥） | — |
| `example_batch_token_update.txt` | 令牌额度更新（精简三列） | — |
| `example_groups.txt`       | 分组批量 | `examples/batch/groups/input.txt` |


---



## 注意事项

1. **秘钥安全**：勿提交 `config.json`、密码、`batch/data/`
2. **单端口**：九个顶栏入口共用 `8765`，同进程
3. **LLM**：**渠道**模式仅勾选时调用；**令牌**模式从不调用；**智能体 Tab 始终需要 LLM**（规划 + 提取）
4. **填入批量配置**：渠道提取结果会**替换**渠道文本框；令牌提取结果会**替换**令牌文本框（均非追加）。「填入更新原配置」同样替换渠道框，但走更新区，不要点「开始批量创建」
5. **数据汇总 / Excel**：所有导出都写入 `excel/`。采集 / 导出过程**不会**自动下载，须点「下载 Excel」获取完整文件。每次「一键采集」（含/不含密钥）**新建** `ai网关令牌及渠道列表_时间戳.xlsx`，不覆盖历史；同一次多站写入同一新文件。**只有「继续补全密钥」**更新最新一份网关汇总（不含总览文件）。写入 `ai网关令牌及渠道列表_一表总览_时间戳.xlsx`；智能分析另写 `智能分析表格_时间戳.xlsx`，不覆盖总览。全部失败不落盘。打开汇总页**不会**自动创建空模板
6. **跨 Tab 切换**：若遇模块导入错误，重启服务即可
7. **代码更新后**：务必重启 `run.bat`，不要仅刷新浏览器
8. **智能体试运行**：`dry_run: true` 不会写入 NA 网关或 Excel，适合预览规划与提取结果
9. **渠道启停**：类型全部 / 勾选批量会真实调用 NA 改状态，操作前请确认类型与清单
10. **启动日志**：审查请查看 `log/` 下本次启动的 txt，勿仅依赖浏览器控制台
11. **登录 429**：短时间多次账号密码登录会被限流；可等待 1–2 分钟、改用 Access Token，或依赖会话缓存（需使用已含该能力的代码并重启服务）
12. **使用日志导出**：需要表格内外框时请选 Excel；CSV 无单元格边框。全空列会被自动剔除。大导出请看进度并可终止；不要理解为「180 次就停」（那是管理 API 限流窗口，不是页数上限）
13. **秘钥粘贴**：渠道行转令牌时密钥只用于识别行格式，不会写入令牌批量文本；仍勿把真实密钥提交到仓库
14. **含密钥汇总**：一次性验证码勿写入日志；Excel 含明文密钥，下载后妥善保管。`totp_secret` 只放 `env/sites.json`（已 gitignore），勿提交仓库
15. **登录 2FA**：6 位码约 30 秒有效，勿写入本地缓存；已预置 `totp_secret` 时自动生成当前码。智能体未预置密钥时请在门禁确认或重试时填**当前**码。规划请求不会把验证码/密钥发给 LLM
16. **跳过 SSL**：默认关闭。仅内网证书 Hostname mismatch 时再开；浏览器访问该站点仍可能提示证书风险
17. **渠道/令牌重名**：本站渠道名、模型名、令牌名须唯一；冲突时创建失败并写明已占用 ID
18. **上游自动升级**：未收到申请单不要改网关；更新原配置不改密钥。模型汇总表反映网关登记，实际调用以上游当前版本为准
19. **上游信息（火山）**：必须用火山 IAM Access Key（`AKLT…`），不要填方舟推理 API Key。项目方为 `项目名-负责人`，控制台未填负责人时导出 `项目名-N/A`。**最后一列「部署时间」** 来自接入点 `CreateTime`，没有则从 `ep-YYYYMMDDHHmmss` 解析。导出表头可筛选、首行冻结
20. **上游信息（Azure）**：必须用 Entra **应用注册**（1 次）+ 每个订阅 IAM（通用 **读者** + **认知服务用户**）。`subscription_ids` 可填多个 GUID，从门户**网页地址栏** `/subscriptions/` 后复制（点进订阅后再抄，不要抄显示名或整段 URL）。账号标记名 `1` 写入「项目」「负责人」：按**最后一个** `-` 拆开（如 `AI-Product-金鑫` → 项目 `AI-Product`、负责人 `金鑫`），没有该标记则两列均为 `N/A`。不要填 Foundry 模型 Key。`client_secret` 抄密码 **Value** 不是机密 ID。403 `accounts/read` 表示该订阅还没给应用加「读者」。**最后一列「部署时间」** 来自 ARM `systemData.createdAt`（东八区），未返回则留空。字段从哪抄见 [Azure OpenAI upstream.azure](#azure-openai-upstreamazure)，角色步骤见 [Azure OpenAI 配置与权限](#azure-openai-配置与权限)。导出表头可筛选、首行冻结
21. **一表总览**：写入 `ai网关令牌及渠道列表_一表总览_时间戳.xlsx`。点「智能分析」须指定总览文件，再写 `智能分析表格_时间戳.xlsx`（不覆盖总览）。页内分析建议可筛选、全选/反选后预禁用。宽限期与用量阈值见卫生策略。详见 [一表总览](#一表总览)、[页内分析建议](#页内分析建议) 与 [智能分析（上下游密钥）](#智能分析上下游密钥)
22. **上游账单**：选账期起止；跨月则**每月一份** Excel（一次最多 24 个月，不把多月并进同一文件）。文件名带 `_N月_`。费用列 `费用（¥）`，表末 `SUM`。表头可筛选（不含合计行）。Azure 另加「成本管理读取者」。改 Python 后须重启再采集。详见 [流程 K](#流程-k采集上游账单)

---



## 常见问题

**Q: 提取后怎么创建渠道？**  
保持「渠道智能提取」→「填入批量配置 →」→ 测试连接 → 渠道管理批量创建。

**Q: 火山/豆包模型自动升级了，怎么改网关登记？**  
未收到升级申请单则不要改。收到后：点「更新」→「智能提取」→「填入更新原配置 →」→ **预更新** → **确认更新**。不填密钥，也不会改原密钥。详见 [流程 A3](#流程-a3火山自动升级--更新原配置)。

**Q: 升级示例提取报缺少 api_key？**  
未点「更新」时按创建处理，必须有密钥。请先点「智能提取」右侧「更新」（按钮亮起），再点「智能提取」。

**Q: 更新会不会把渠道密钥改掉？**  
不会。更新接口不传 `key`，行内或全局秘钥都会忽略。

**Q: 提取后怎么创建令牌？**  
切到「令牌智能提取」→ 粘贴草稿或「渠道行转令牌」→「填入令牌管理 →」→ 测试连接 → 令牌管理批量创建。

**Q: 怎样给之前创建的无限额度令牌补设 tokens？**  
进入「批量配置 → 令牌管理」，粘贴 `名称 分组 额度(tokens)`，点击「预更新」核对变更后再点「确认更新」。更新不改模型限制、过期时间或密钥；若令牌已显示「额度用尽」，更新后再执行「预启用 → 确认启用」。

**Q: CLI 批量样例在哪？与 Web「载入示例」一样吗？**  
在 `examples/batch/`（mixed / azure / tokens / groups），与 `batch/static/example_*` **内容对齐**。渠道可用 `python app.py batch -f examples/batch/mixed/input.tsv`；令牌/分组样例供 Web 或 API。

**Q: 怎么从杂乱文本批量创建令牌？**  
切换「令牌智能提取」→ 粘贴「令牌名 / 人名 / 分组 / 模型」或「令牌名-人名」三行 →「填入令牌管理 →」→ 令牌管理批量创建。详见 [流程 A2](#流程-a2令牌提取--批量创建)。

**Q: 令牌名和人名分两行会怎样？**  
自动拼成 `令牌名-人名`；若第一行已以 `-人名` 结尾，不会重复追加。

**Q: 令牌提取要开 LLM 吗？**  
不需要。令牌模式固定规则拼接（`token_rules`），页面也不显示 LLM 选项。

**Q: 已有一条完整的 Azure 渠道行，还要 LLM 吗？**  
不需要。直接粘贴到智能提取（渠道模式），未勾选 LLM 即可解析。

**Q: 只有「名称 类型 上游 URL 密钥」这种紧凑行能提取吗？**  
可以。例如 `demo-delta-uat-glm-5.1 自定义渠道 glm-5.1 https://… sk-…` 会解析为模型列=渠道名、重定向=`名称->上游`。

**Q: 分组是怎么来的？**  
从渠道/令牌**名称**截到环境段：`test` / `uat` / `prd` / `prod` / `stg` / `dev`（整段匹配）。  
例：`demo-gamma-uat-product-gpt-x` → `demo-gamma-uat`（不会把 `product` 当成 `prod`）。已格式化行若已写分组则优先用行内分组。详见 [分组与模型推导](#分组与模型推导)。

**Q: 令牌智能提取能直接吃渠道批量行吗？**  
能。第一行写令牌名（人名可分行），后面贴渠道行即可自动带出分组与模型列表。见 [渠道行转令牌](#渠道行转令牌)。

**Q: 使用日志 Excel 为什么少了很多列？**  
导出时会**剔除全部数据行都为空的列**（如未发生缓存时的缓存相关列）。需要完整列时可对照 `other原文`，或查看代码中的列定义。

**Q: 使用日志为什么没有表格边框？**  
请确认导出格式为 **Excel (.xlsx)**（默认）。CSV 用 Excel 打开只有网格线，没有单元格内外框。

**Q: 使用日志进度卡住 / 条数偏少 / 很慢？**  
进度靠后台任务轮询，请用已重启的 `run.bat` 并 Ctrl+F5。NA **每页最多 100 条**；「180 次/180 秒」是管理 API 限流，不是 180 页就停。默认时间是「今天」。翻页约 1 页/秒。可点「终止」取消。

**Q: 报 Hostname mismatch / CERTIFICATE_VERIFY_FAILED？**  
内网网关证书域名与访问主机名不一致。在勾选「跳过 SSL 证书校验」（默认校验证书）。勾选后立即生效，无需改 `env/sites.json`。

**Q: 二次验证能否预置密钥、自动出码？**  
可以。把认证器原始密钥（Base32）写入 `env/sites.json` 的 `totp_secret`，登录和导出密钥时自动生成当前 6 位码。也可把密钥粘贴到页面二次验证框。获取路径见 [NA 站点参数](#na-站点参数已配置站点)。工作台 **全局站点认证** 会把会话写入约 2 小时缓存，之后汇总 / 总览不再弹审查窗。

**Q: 如何批量禁用某上游模型对应的自定义渠道？**  
批量配置 → **渠道启停** → 类型选「自定义渠道」→ 填入上游模型（如 `glm-5.1`）→「按上游模型加载」→ 勾选后「禁用所选」，或直接「类型全部禁用」。

**Q: 数据汇总如何导出渠道 API Key？**  
勾选「包含渠道密钥」→ 工作台已认证或已预置 totp 则直接拉密钥；仅缺码站点弹窗 → **新建**一份带密钥列的 Excel。需 **Root** 账号密码。未拉完时用「继续补全密钥」更新最新那份。详见 [含渠道密钥导出（二次验证）](#含渠道密钥导出二次验证)。

**Q: 含密钥采集提示需要 Root / 验证失败？**  
`POST /api/channel/{id}/key` 仅 Root 可用。验证码错误或过期（约 30 秒）请重开弹窗输入新码，或预置 `totp_secret`；多站点请分别配置密钥。

**Q: 数据汇总打开页面会生成空 Excel 吗？**  
不会。仅在「一键采集」**至少有一个站点成功**后**新建**带时间戳文件；全部失败不落盘。无文件时下载按钮不可用。

**Q: 一键采集是新建还是改上一份？**  
**一键采集（含/不含「包含渠道密钥」）每次都新建。** 同一次点击里多个站点写入**同一份新文件**。只有「继续补全密钥」读取并更新 `excel/` 下最新一份；没有文件时会提示先采集，不会凭空建空表。全部站点写完后再点「下载 Excel」，不会在采集过程中自动下载。

**Q: 工作台给没有密钥的表打了「含密钥」？**  
橙色标签看的是单元格有没有值，不是「有没有密钥列」。勾选含密钥采集但因 429 没拉到、或总览默认带空「密钥」列，都**不会**打标。`N/A` 和智能分析的「密钥摘要」也不算。下载二次确认同一规则。重启服务后刷新工作台即可。

**Q: 继续补全密钥时某环境工作表是空的怎么办？**  
只要已有一份汇总 Excel，该环境表为空也会继续：从该站拉取渠道、令牌和密钥，**追加进同一文件**，不覆盖其它环境。不限于「test/uat 有数据、prod 为空」这一种情况。

**Q: 为什么有的站点要验证码、有的不要？**  
采集 / 补全密钥 / 余额查询会检查会话与 TOTP。工作台已认证、无登录 2FA、或已预置密钥的站点直接执行；仅无 TOTP 且无有效会话才弹 30 秒临时码。勾选含密钥或补全密钥时，即使登录无 2FA 仍要二次验证。详见 [验证码与全局认证](#验证码与全局认证)。

**Q: 未勾选 LLM 为什么之前还会走 AI？**  
旧版存在「配置齐全则自动补全」逻辑，已改为**仅勾选时调用**。

**Q: 智能提取报** `Unexpected token '<'`**？**  
多为 `/api/extract` 或 `/api/extract-token` 返回 500 HTML。查看终端日志或 `log/` **下本次启动的 txt**；常见原因：切换 Tab 后 agent 模块未加载，**重启服务**。

**Q: 操作记录存在哪里？**  
项目根目录 `log/`。每次启动一个 txt，内含时间戳、具体 API 操作及成功/失败/警告明细。详见 [启动日志（审查）](#启动日志审查)。

**Q: 渠道启停时报登录 429 / 过于频繁？**  
短时间多次密码登录触发限流。可：等待 1–2 分钟；改用 Access Token；使用已含会话缓存的版本并**重启服务**后再操作。

**Q: 数据汇总 / 批量创建报** `No module named 'lib.rate_budget'` **、** `lib.data_summary_exporter` **或** `lib.channel_types`**？**  
batch 与 agent 共用包名 `lib`。首页加载 LLM 预设会切到 agent。请使用最新代码（批量接口会自动切回 batch）并**重启** `run.bat`。若页面仍只显示英文模块名，刷新后再试。

**Q:** `/api/llm-presets` **报** `No module named 'lib.llm_client'`**？**  
多为 agent/batch 的 `lib` 包在并发请求下竞态加载。请使用最新代码（已加 `_LIB_LOCK`）并**重启服务**；若仍出现，刷新页面重试。

**Q: 顶栏为什么没有 ①②③ 步骤圆圈了？**  
已改为原模块全称、去掉序号。打开应用默认进入 **工作台**。Tab 右侧短句每次刷新不同；窗口窄时隐藏。提取 → 批量 → 汇总 仍可按任务卡或顶栏手动切换。

**Q: 分析建议怎么一次勾很多行？**  
用 **全选 / 反选**。只作用于当前筛选结果里可勾选的行；宽限期项须先勾「仍要执行宽限期项」。然后再点「按勾选预禁用」。

**Q: 智能体与手动 Tab 有什么区别？**  
手动 Tab 逐步操作；智能体为异步工作台（计划画布、门禁确认、取消/重试）。连接与站点配置共用；登录 2FA 在智能体里还可于门禁/重试时刷新。可勾选上游、总览、智能分析；只跑这些步骤时请取消提取。完成后分别下载数据汇总、上游信息、一表总览/分析表。

**Q: 智能体必须先配置 LLM 吗？**  
是。Jobs / `/api/agent/run` 均要求 `llm_api_base`。可先 `dry_run: true` 预览。任务在进程内存中，重启服务会清空。

**Q: 智能体报「账号启用了登录两步验证」？**  
在网关连接填写认证器当前 6 位码或 TOTP 原始密钥，也可在 `env/sites.json` 预置 `password` 与 `totp_secret`（页面可留空，服务端按地址补齐），建议先「测试连接」。提取耗时长且未预置密钥时，到门禁「确认并继续」前再填最新码；失败重试同样带上。Access Token 模式一般不需要登录 2FA。汇总多站点请各环境分别配置密钥（不要共用同一码）。

**Q: 批量创建提示渠道名/模型名/令牌名已存在？**  
本站内这三类名称各自必须唯一（与分组无关）。改名后再创建；删除仍按名称+分组匹配。

**Q: 如何把某分组下的渠道或令牌改到另一个分组？**  
批量配置 → **分组设置** → 刷新分组 → 选源/目标 →「加载该分组渠道 / 令牌」→ 勾选或全选 →「切换所选渠道」或「切换所选令牌」。目标分组须已存在。详见 [分组切换](#分组切换)。

**Q: 上游 Excel 里项目方为什么是 `demo-research-N/A`？**  
火山项目 DisplayName 没有负责人时按约定补 `N/A`。控制台写成 `demo-proj-a-张三` 这类 `项目名-负责人` 才会导出人名。把项目显示名改好后重新采集即可。详见 [项目方：项目名-负责人](#项目方项目名-负责人)。

**Q: Azure OpenAI 每个项目都要申请一个 IAM 吗？**  
不要。**应用注册 1 次**；**读者 + 认知服务用户按订阅各加一遍**（4 个订阅就 4 遍，都赋给 `na-upstream-collector`）。`env` 的 `subscription_ids` 把 4 个 GUID 写齐，一次采集全部扫完。Foundry 的 Hub / 项目、部署页 API Key 都不是这套凭证。详见 [Azure OpenAI 配置与权限](#azure-openai-配置与权限)。

**Q: Azure 订阅 ID 从网页哪里抄？**  
点进该订阅（或该订阅下任意资源），看浏览器**地址栏**。链接里 `/subscriptions/` 后面、下一个 `/` 之前那一段 GUID 就是订阅 ID。不要整段 URL，不要订阅显示名；停在「订阅」列表页时地址栏往往没有 GUID。四个订阅就打开四个页面各抄一次。示例见 [Azure OpenAI upstream.azure](#azure-openai-upstreamazure)。

**Q: Azure Excel 的项目、负责人从哪来？**  
来自该 OpenAI 账号门户 **标记** 里名称为 **`1`** 的那条。值按**最后一个** `-` 拆开：前面整段是项目名（可以有多个 `-`），最后一段才是负责人。例如 `AI-Product-金鑫` → 项目 `AI-Product`、负责人 `金鑫`。多名负责人写在最后一段，可用中文逗号 `，`、英文逗号 `,`、顿号 `、`（例如 `示例项目组-张三，李四`）；导出「负责人」列统一为中文逗号。同一账号下各部署行相同。没有标记 `1` 时两列都填 `N/A`。旧 Excel 须重新采集才会按新规则拆。详见 [标记 1：项目-负责人1，负责人2](#标记-1项目-负责人1负责人2)。

**Q: 怎么把火山云和 Azure 采到同一张 Excel？**  
上游信息页顶部点 **一键采集全部上游**，生成 `excel/上游信息_汇总_时间戳.xlsx`（工作表 `火山云`、`Azure OpenAI`）。两侧凭证需已配置。一侧失败时仍会写入另一侧数据。分厂商按钮仍可单独导出。详见 [流程 I](#流程-i一次采集火山云--azure-汇总表)。

**Q: 怎么把火山云和 Azure 账单采到同一张 Excel？**  
顶栏 **上游账单** → **一键采集全部账单**，生成 `excel/上游账单_汇总_9月_时间戳.xlsx`（月份为账期；跨月则每月一份，不合并成一个文件）。表头可筛选。Azure 须加「成本管理读取者」。详见 [流程 K](#流程-k采集上游账单)。

**Q: 上游账单一次能导几个月？会并进一个文件吗？**  
页面选账期起、账期止，一次最多 **24** 个月。每个月仍各写一份 Excel（文件名带 `_N月_`），不会把多月叠进同一工作簿。某月失败会继续后面的月份。

**Q: 为什么打开上游 Excel 表头没有筛选箭头？**  
须用当前代码**重新采集**。已经落盘的旧文件不会自动补筛选。账单费用表的筛选不含末行合计。改了 Python 请先重启 `run.bat`。

**Q: 怎么把网关各站和两侧上游合成一张总表？**  
顶栏 **一表总览** → **一键生成总览表**（工作台已认证则不弹审查窗）。再点 **智能分析** 对照上下游，得到 `excel/智能分析表格_时间戳.xlsx`。网关火山/Azure 渠道在上游找不到密钥时，建议在对应站点禁用或删除；**部署未满 10 天则降一级、暂缓处置**。详见 [流程 J](#流程-j一表总览网关--两侧上游)、[智能分析（上下游密钥）](#智能分析上下游密钥)。

**Q: 智能分析分析什么、会不会改网关？**  
只读**所选**总览，写出独立分析表，**不改总览、不改 NA**。若 `excel/` 有 `渠道余额_时间戳.xlsx`，已用 = $0 视为不用、已用 < $1 视为不常用；**不常用且近一月无活跃升为中**。没有该文件则不识别用量。新余额表含「近一月活跃」时，须**每个模型都近一月无活跃**才允许用量类禁用；任一模型有活跃或 N/A 不禁渠道/令牌。页内建议表可勾选预禁用；也可看工作表 `建议处置`：高优先级多为「下游无上游」。渠道和相关令牌均已禁用的原建议在右侧 `已禁用建议`，不必再处置。再右侧 `批量禁用` 按 test/uat/prod 生成渠道、令牌粘贴列（`名称` Tab `分组`），复制到批量配置即可预禁用。**一条令牌挂多条渠道、只有一条不用时，只禁那条渠道，不牵连令牌和其它渠道。** 宽限期内会降一级（高→中、中→低）。DeepSeek/GLM 等外部渠道默认不对照过期。分析表只有密钥摘要。渠道密钥未齐时请先「继续补全密钥」再分析。详见 [智能分析（上下游密钥）](#智能分析上下游密钥)、[批量禁用](#批量禁用)。

**Q: 智能分析为什么把「高」变成「中」？**  
部署时间距今小于卫生策略里的宽限期天数（默认 **10 天**）会降一级（高→中、中→低），暂缓禁用/停用。恰好满天数、没有部署时间、或旧 Excel 没有该列，都不放宽。`建议处置` 末列是部署时间，问题列会带前缀「新部署未满 N 天，评估已放宽。」详见 [新部署放宽（卫生策略）](#新部署放宽卫生策略)。

**Q: 一条令牌挂了多条渠道，其中一条不用，会不会把令牌也禁掉？**  
不会。`批量禁用` 只写确定不用/过期的**渠道**；令牌和其它仍启用的渠道不进粘贴列。只有该令牌仍启用的「包含渠道」全部进入本次渠道禁用清单时，才写令牌列。无限制共享令牌（如分组「无限制」）本来就不写令牌列。详见 [批量禁用](#批量禁用)。

**Q: 部署时间从哪来？旧 Excel 没有这一列怎么办？**  
网关渠道来自 `created_time`；火山来自接入点 `CreateTime`，没有则从部署名 `ep-YYYYMMDDHHmmss` 解析；Azure 来自 ARM `systemData.createdAt`（写成东八区）。都在表的**最后一列**。旧文件须重新采集数据汇总、上游信息再生成总览，智能分析才会对新部署放宽。

**Q: 智能体只想跑上游、总览或智能分析？**  
取消勾选 **提取**（空原文会在提取步失败）。上游信息、一表总览/分析默认关闭，需手动勾选。总览只从已有数据汇总、上游信息文件提取、**不含**渠道明文密钥。无凭证或无文件则**跳过**，不把整任务打成失败。完成后分别点「下载数据汇总 / 下载上游 / 下载总览 / 下载分析表」。分析规则（含 10 天放宽）与一表总览页相同。

**Q: Azure「测试连接」报 ARM HTTP 403 accounts/read？**  
登录已成功，缺订阅权限。在订阅 IAM 给该**应用**（不要给个人账号）加通用 **读者**，不要加「安全读取者」等带前缀的读者。刚加完等 1～2 分钟再测。拉密钥还必须再加 **Cognitive Services 用户**。

**Q: env 里各参数从哪获取？**  
复制 `env/sites.example.json` 为 `env/sites.json` 后按字段填写。NA 账密与 TOTP、火山 IAM、Azure 服务主体的完整获取路径见 [配置说明](#配置说明)。`sites.example.json` 只是模板，程序不会读取。

**Q: Azure 客户端密码该抄「值」还是「机密 ID」？**  
抄 **值（Value）**。机密 ID 是编号，填了会登录失败。Value 离开创建页后可能不再完整显示，需新生成一把。获取步骤见 [Azure OpenAI upstream.azure](#azure-openai-upstreamazure)。

**Q: Excel 文件名是什么？**  
全部在 `excel/`：
- 网关汇总：`ai网关令牌及渠道列表_YYYYMMDDHHmmss.xlsx`（每次一键采集新文件名；补全密钥不改文件名；**不含**带 `_一表总览_` 的总览文件）
- 渠道余额：`渠道余额_YYYYMMDDHHmmss.xlsx`
- 使用日志：`usage_logs_YYYYMMDD_HHMMSS.xlsx`（或 `.csv`）
- 上游汇总（火山+Azure）：`上游信息_汇总_YYYYMMDDHHmmss.xlsx`（工作表 `火山云`、`Azure OpenAI`；**最后一列均为部署时间**；表头可筛选）
- 一表总览（网关+两侧上游）：`ai网关令牌及渠道列表_一表总览_YYYYMMDDHHmmss.xlsx`（工作表 `总览` + 各环境表 + `火山云` + `Azure OpenAI`，上游表末列为部署时间、表头可筛选；与数据汇总网关汇总不是同一份）。生成时若 `excel/` 已有数据汇总、上游信息或以往总览，按**文件名时间戳最新**提取，缺的一侧才连网；同名前缀多份不以修改时间为准
- 智能分析：`智能分析表格_YYYYMMDDHHmmss.xlsx`（对照最新总览；不覆盖总览；「下载分析表」取最新一份；`建议处置` 只含未禁用项，已禁用写入 `已禁用建议`；再右侧 `批量禁用` 为 test/uat/prod 渠道与令牌粘贴列，多渠道令牌只禁不用的那条渠道；新部署未满 10 天降一级）
- 上游火山云：`上游信息_火山云_YYYYMMDDHHmmss.xlsx`（末列部署时间；表头可筛选）
- 上游 Azure OpenAI：`上游信息_Azure_YYYYMMDDHHmmss.xlsx`（末列部署时间；表头可筛选）
- 上游账单汇总：`上游账单_汇总_9月_YYYYMMDDHHmmss.xlsx`（月份为该月账期，不补零；跨月则每月一份。工作表：火山云-按天 / 火山云-按月 / Azure-按天 / Azure-按月；表头可筛选，不含合计行）
- 上游账单火山云：`上游账单_火山云_9月_YYYYMMDDHHmmss.xlsx`
- 上游账单 Azure：`上游账单_Azure_9月_YYYYMMDDHHmmss.xlsx`

页面「下载 Excel」指向对应类型的最新一份完整文件（采集/导出过程不会自动下载）。

**Q: 令牌表为什么有些列是空的？**  
需 Admin 权限；部分字段需详情 API 补全。分组为空则项目环境也为空，列仍保留。

**Q: 重复模型为 0？**  
需至少 2 个环境有同名记录；仅采集 test 时为 0 属正常。

**Q: UAT 渠道数和网站不一致？**  
查看采集日志「拉取渠道 X」：若 X 与网站一致但主表偏少，可能是旧版按名称去重导致（已修复为按 ID）。若「拉取」本身就少，检查 Admin 权限与站点地址。

**Q: 为什么有「重复模型」表，主表也有同名渠道？**  
主表保留各环境**全量**；「重复模型」表额外列出跨环境同名项，便于对照，二者并存。

**Q: Excel 行顺序是什么？**  
数据汇总网关渠道/令牌按 **ID 升序**。上游信息 / 一表总览里的 **火山云、Azure OpenAI** 两张上游表按 **部署时间降序**（最新在上；无时间的排最后）。上游账单按天表按日期，按月表按账期月份。

**Q: 数据汇总重复项去哪了？**  
主表保留全量；跨环境同名记录**同时**出现在「重复模型」「重复模型相关令牌」工作表，便于对照。

**Q: 明亮主题下某些按钮看不清？**  
已在连接配置、分组创建等页面加强对比度；仍有问题可反馈具体位置。

---



## 版本规划

- [x] 渠道智能提取（火山 / Azure / 自定义 / 已格式化行）
- [x] **紧凑渠道行**解析（无 `模型->上游` 时自动补全 `名称->上游`）
- [x] 多条批量提取；从名称推导分组
- [x] **分组切换**（源/目标分组；勾选或全选渠道、令牌；`POST /api/groups-members`、`/api/groups-switch`）
- [x] **渠道启停**（按上游模型 / 类型全部 / 勾选 ID；可视化清单；单条操作）
- [x] **按名称+分组批量禁用/启用**（渠道管理、令牌管理；预览后确认；与删除共用文本框）
- [x] **渠道查询**（迁入 **数据汇总**；多站点 test/uat/prod；导出分表 `环境-渠道余额`；近一月活跃按模型逐项填写）
- [x] 单页九个顶栏入口（工作台、智能提取、批量配置、平台信息、数据汇总、上游信息、上游账单、一表总览、智能体；**原名、无序号**）+ 一键填入批量配置
- [x] **工作台**默认落地（`#workspace`；待办不显示假 0；六任务卡；**全局站点认证**写会话缓存）
- [x] **产物选择器 + 刷新**（数据汇总 / 上游信息 / 上游账单 / 一表总览 / 使用日志；下载与分析须带文件 id，禁止静默 latest；iframe 间 `na-artifacts-changed` 同步）
- [x] **一表总览页内建议表 + 预禁用**（筛选；全选 / 反选；宽限期默认跳过；`force_hold` 才纳入）
- [x] **卫生策略可配置**（`GET/PUT /api/policy/hygiene` → `env/hygiene_policy.json`）
- [x] LLM 多厂商；**渠道**模式仅勾选时调用；令牌模式无 LLM
- [x] 数据汇总（多站点、**每次采集新建**时间戳 Excel、重复检测；**不自动创建空模板**；补全密钥才更新最新一份）
- [x] **上游账单**（火山云费用中心 + Azure Cost Management；按天/按月；账期起止可跨月、每月一份；可汇总同一工作簿；表头筛选不含合计行）
- [x] 智能体（异步 Jobs + SSE + 门禁 + 取消/重试 + Web/API；可选上游 / 总览 / 智能分析）
- [x] Excel 表格外框 + 网格边框与分色
- [x] 令牌 10 列完整导出；项目环境 = 分组
- [x] 主表全量 + 重复表对照；按 ID 升序；同名渠道按 ID 保留
- [x] agent/batch `lib` 模块隔离、请求时重载与并发锁（`_LIB_LOCK`）
- [x] 顶栏去掉步骤序号圆圈（信息架构改为工作台 + 原模块全称；右侧短句刷新随机更换）
- [x] 明暗双主题切换（`na-theme.js`）与 favicon
- [x] 18 页 HTML 产品演示稿（含智能体专页）
- [x] **按次启动文件日志**（`log/` + `na_logger.py`；API 操作明细与脱敏）
- [x] 登录会话缓存 + 429 退避重试（降低连续启停触发限流）
- [x] **令牌智能提取**（三行/四行拼接、带标签、多条；独立纯数字额度行写入第 4 列；`POST /api/extract-token`；填入令牌管理）
- [x] **令牌可选额度与预更新**（创建第 4 列 `额度(tokens)`；历史令牌按名称+分组预览、确认更新额度并保留其他配置）
- [x] **渠道 / 令牌更新模板导入**（更新区可载入无密钥 / 精简额度模板；示例载入后需修改才可预更新）
- [x] **渠道行转令牌**（令牌名(+人名分行) + 渠道批量行 → 自动识别分组与模型）
- [x] **分组截到环境段**（`uat`/`test`/`prod`…；业务段如 `product` 不误伤）
- [x] 使用日志 Excel：内外框、默认 xlsx、**全空列自动剔除**、对齐 Log/`other` 全量字段；后台任务 + 进度轮询 + 可终止；写入 `excel/` 后点「下载 Excel」
- [x] **全站 Excel 统一存放 `excel/`**，各页均有「下载 Excel」；采集/导出不自动下载，点按钮才下载完整文件
- [x] `examples/batch/` CLI 样例（mixed / azure / tokens / groups，与 `batch/static` 对齐）
- [x] 连接配置 test/uat/prod 快捷切换（`env/sites.json`，未配置则隐藏）
- [x] **TOTP 原始密钥**（`totp_secret` / 粘贴 Base32；不落 localStorage）
- [x] **跳过 SSL 证书校验**（默认关闭；批量配置连接配置勾选）
- [x] **上游信息**（火山云 IAM；Azure OpenAI 服务主体；**一键采集全部上游**写入同一工作簿两张工作表；火山云 **TPM 在 RPM 前**；**最后一列部署时间**；表头筛选、首行冻结）
- [x] **一表总览**（提取数据汇总、上游信息；默认含密钥；**智能分析**对照上下游；卫生策略默认部署未满 10 天降一级暂缓；有渠道余额表时判定不用/不常用，并按模型评估近一月活跃（有活跃或 N/A 不禁渠道/令牌）；页内预禁用 + Excel `批量禁用` 粘贴列不牵连仍在用的令牌/渠道 → `智能分析表格_时间戳.xlsx`，不覆盖总览）
- [x] 令牌提取 CLI（`extract-token` / `extract --mode token`）
- [x] 令牌 / 分组批量 CLI（`batch token|group`、`token-batch`、`group-batch`）
- [x] **数据汇总含渠道密钥**（审查后二次验证 → `/api/verify` → 批量 `/api/channel/{id}/key`；Root；采集新建、补全写回最新）
- [x] **登录 2FA**（批量连接 / 智能体门禁与重试 / 汇总先审查再按需弹窗；一次性码不落盘；兼容 `mfa_action`；可预置 totp_secret）
- [x] **本站渠道名、模型名、令牌名唯一**（创建校验；删除仍按名称+分组）
- [x] **渠道更新原配置**（预更新 / 确认更新；不改密钥；已有备注弹窗确认后才覆盖为本行 `base_url`；`POST /api/batch-update-channels`）
- [x] **全量同步渠道 Base URL 到备注**（预览 / 确认；Azure 只取 `AZURE_OPENAI_ENDPOINT`；已有备注换行追加；255 字符超限按渠道报错）
- [x] **智能提取「更新」模式**（先点更新再提取；火山自动升级示例；`for_update`）
- [x] **平台信息 New API 管理端**（test / uat / prod 渠道与令牌；分页、悬浮复制、结构化编辑、测试/启停/删除；批量配置行转换与一键填入；测试失败回传上游错误；凭据仅服务端读取）
- [x] **完整网站账户与 RBAC**（自适应登录 / 注册 / 恢复验证码重置；超管、管理员、用户三角色；超管用户管理；Argon2id、Redis 会话、CSRF、审计）
- [x] **PostgreSQL 18 + Redis 8 容器化部署**（Docker / Podman Rocky Linux 8/9 兼容；Alembic；Kubernetes StatefulSet / Deployment / Ingress 模板）
