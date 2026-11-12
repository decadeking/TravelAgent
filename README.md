# 交互式旅行规划智能体 · TravelAgent

> 基于 **FastAPI + Vue 3 + LangGraph 风格状态图** 的对话式智能旅行规划系统。
> 覆盖 **Agent 编排 / Function Calling / RAG / SSE 流式 / 限流·熔断·幂等·分布式锁** 全套技术点。
> **零外部服务即可运行与测试**（SQLite + 内存 KV + Mock LLM），生产形态配置齐备（MySQL / Redis / pgvector / Docker）。

---

## 一、它做什么

一个「**旅行风光社区 + 智能体规划 + 行程管理**」三位一体的全栈应用，左侧单列导航（仿 Trae，可折叠）：

| 栏目 | 说明 |
|---|---|
| **旅行吧** | 登录后默认进入。像 QQ 动态一样的旅行风光信息流：图文帖子、点赞、收藏、留言、城市筛选、帖子详情、发布动态 |
| **新建规划** | 智能体对话：SSE 流式呈现「查天气 → 搜景点 → 算路线 → 估预算」+ 当前时间与**行程提醒**工具，右侧实时生成行程 + **真实地图**；输入框仿 Trae 排版（左下角工具/skill 选择器 + 右下角模型切换、语音输入、语音播报、绿色发送键）；可一键「保存为行程」。对话尾部标注**真实模型 / 离线模拟**、RAG 引用数与工具调用数 |
| **个人行程** | 我的行程管理（增删改查）、查看去过的目的地与保存的方案 |
| **消息** | 消息中心：他人点赞/评论/回复/关注、收藏回执、Token 用量提醒、行程提醒聚合于此；含**好友**（关注即好友）、**我的收藏**、**我的评论**、**Token 用量与提醒阈值**；左侧导航与右上角铃铛均显示未读红点，点消息直达动态详情或消息页 |
| **管理**（仅管理员） | 内容审核、大模型/向量模型/知识库参数配置、知识库管理、图片资源、系统概览 |

同时提供**双角色**（`user` / `admin`）、**真实数据工具**（Open-Meteo 实时天气、OSRM 真实路线、真实城市坐标）、**可配置的 RAG 知识库**（pgvector 向量库 + 可配向量模型），以及**图片本地化**（风景配图与头像文件保存在后端图片文件夹 `backend/static/uploads`，数据库只存元数据与路径，由 `/api/media/{id}` 提供，不依赖外部图床）。

用户输入一句「我要去成都玩 4 天，预算 3000 元，带小孩，不想爬山」，系统以 **SSE 流式**呈现规划过程，并在右侧实时生成按天编排、可编辑、可保存的行程；不满意可继续对话修订（「第二天换个便宜点的」）。

```
用户输入 → [状态图] intake → plan → tool_call → reflect → respond
                          ↑______ 修订回环（≤3次）______|
                              ↘ clarify（槽位缺失时反问）
```

---

## 二、技术栈

| 层面 | 技术 |
|---|---|
| 前端 | Vue 3、Vite、TypeScript、Pinia、Vue Router、原生 fetch SSE |
| 后端 | FastAPI、Pydantic v2、Uvicorn、SQLAlchemy 2.0(async) |
| Agent | 自研 StateGraph（对齐 LangGraph：节点/条件边/checkpointer/interrupt） |
| 模型 | httpx + OpenAI 兼容协议（DeepSeek/通义）；**mock 离线兜底** |
| RAG | 两级结构切片 + 可配置 Embedding（hash/openai）+ pgvector HNSW（内存双后端自动回落） |
| 稳定性 | 熔断器 / 有限重试 / 幂等 / 分布式锁 / 双层限流 / Token 配额 / cache-aside 缓存 |
| 存储 | SQLite(默认) / MySQL 8；内存 KV(默认) / Redis 7；向量库 pgvector；图片文件落盘 static/uploads |
| 可观测 | JSON 日志、Span 追踪、Prometheus 指标、故障注入演练 |

---

## 三、快速开始（零依赖）

**前置**：Python 3.12、Node 18+。已提供虚拟环境 `.venv`（若缺失见下方"重新安装"）。

```powershell
# 1) 启动后端（默认 http://127.0.0.1:8000）
cd backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# 2) 启动前端（另开终端，默认 http://localhost:5173，已代理 /api 到后端）
cd frontend
npm install
npm run dev
```

浏览器打开 http://localhost:5173 ，使用演示账号登录（登录后默认进入「旅行吧」）：

- 普通用户 `demo` / `demo123`（可发帖、点赞留言、规划行程、管理自己内容）
- 管理员 `admin` / `admin123`（额外可见「管理」栏目：内容审核 + 系统设置 + 知识库管理）

**重新安装后端依赖**（可选）：
```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

---

## 四、运行测试

```powershell
cd backend
..\.venv\Scripts\python.exe -m pytest -q      # 61 项：稳定性机制 / RAG / 接口 / Agent 链路 / 旅行吧 / 消息中心与好友 / 管理端 / 真实工具 / 图片入库 / 模型兜底 / ReAct 对照 / 并发幂等 / 时间与提醒工具 / 密钥加密
```

---

## 五、目录结构

```
TravelAgent/
├── backend/
│   ├── app/
│   │   ├── main.py                 # 入口：装配中间件与各微服务路由
│   │   ├── common/                 # 配置/上下文/KV/熔断/重试/幂等/锁/限流/安全/日志/指标/追踪/配额/故障注入
│   │   ├── gateway/                # 网关：JWT 鉴权依赖、trace 中间件、统一异常
│   │   ├── db/                     # SQLAlchemy 模型 / 会话 / 种子数据
│   │   ├── schemas/                # Pydantic 模型
│   │   └── services/
│   │       ├── user_service/       # 注册登录 / 资料与头像 / 偏好 / Token 用量
│   │       ├── trip_service/       # 行程三级结构 CRUD + 乐观锁
│   │       ├── feed_service/       # ★ 旅行吧：动态/评论/点赞/收藏 + 管理员审核
│   │       ├── media_service/      # ★ 图片入库：上传/读取/外链同步（BLOB 存库）
│   │       ├── tool_service/       # 天气(Open-Meteo)/景点/路线(OSRM)/预算/搜索/定位（真实源 + mock 降级）
│   │       ├── agent_service/      # ★ AgentCore
│   │       │   ├── core/           # state_graph.py / nodes.py / graph.py
│   │       │   ├── llm/            # 模型适配器（mock + openai，支持模型选择）
│   │       │   ├── rag/            # 切片 / Embedding / 向量库 / 检索（DB 驱动、可重建）
│   │       │   ├── memory/         # 短期会话 + 长期偏好
│   │       │   ├── guard/          # Prompt 防护
│   │       │   └── sse/            # SSE 连接管理
│   │       └── admin_service/      # 系统设置(LLM/向量/知识库) / KB 管理 / 审核 / 指标 / 熔断 / 故障演练
│   ├── data/                       # 数据集：poi.json / knowledge_base.json
│   ├── tests/                      # pytest 测试套件（33 项）
│   ├── pytest.ini
│   └── run.py
├── frontend/                       # Vue 3 + Vite + TS（仿 Trae 单列可折叠导航，头像在右上角含设置）
├── docs/                           # 需求分析 / 架构技术栈 / 技术要点 / 冲突消解 / 功能扩展
├── deploy/                         # docker-compose / nginx / prometheus / k8s
├── reference/                      # 已拉取的 GitHub 参考项目
├── requirements.txt
├── .env.example
└── Dockerfile
```

---

## 六、核心技术点速查

| 技术点 | 位置 |
|---|---|
| 双层限流（滑动窗口 + 并发信号量） | `common/kvstore.py`、`common/ratelimit.py` |
| 熔断状态机（Closed/Open/HalfOpen） | `common/circuit_breaker.py` |
| 有限重试（指数退避 + 抖动） | `common/resilience.py` |
| 幂等（request_id + SETNX） | `common/idempotency.py` |
| 分布式锁（看门狗续期 + Lua 释放） | `common/distlock.py` |
| SSE 生命周期（心跳 + 断开取消） | `services/agent_service/sse/manager.py`、`service.py` |
| Prompt 防护 | `services/agent_service/guard/prompt_guard.py` |
| Token 配额与台账 | `common/quota.py`、`db/models.py::LLMCallLog` |
| 状态图（节点/条件边/checkpointer） | `services/agent_service/core/` |
| RAG（切片/向量/检索，DB 驱动可重建） | `services/agent_service/rag/` |
| 旅行吧动态（帖子/评论/点赞/收藏） | `services/feed_service/router.py` |
| 图片入库与提供（BLOB + 外链同步） | `services/media_service/router.py` |
| 角色权限（user/admin） | `gateway/deps.py::require_admin` |
| 真实工具（Open-Meteo 天气 / OSRM 路线 / 城市坐标） | `services/tool_service/{providers,geo}.py` |
| 当前时间工具 / 行程提醒工具（落库+后台触发） | `services/tool_service/tools.py`、`services/agent_service/reminders.py` |
| 密钥加密落库（Fernet，兼容历史明文） | `common/crypto.py`、`common/user_model.py` |
| 知识库同步脚本（幂等 upsert + 重建索引） | `scripts/sync_kb.py` |
| 消息中心（聚合社交互动/提醒/用量告警） | `services/message_service/router.py`、`common/notify.py` |
| 关注/好友（关注即好友） | `services/user_service/router.py`、`db/models.py::Follow` |
| Token 用量阈值提醒 | `common/quota.py::_maybe_warn` |
| 端到端验证脚本（真实链路 / 新行为 / 前端路径） | `scripts/verify_real_chain.py`、`scripts/smoke_new_behaviors.py`、`scripts/smoke_frontend_path.py` |
| 模型目录与「模型不存在」自动兜底 | `common/runtime_config.py::resolve_model_chain` |
| 上游错误可读化 + 连通性自检 | `services/agent_service/llm/adapter.py` |
| 运行时配置（模型列表/向量/KB 参数） | `common/runtime_config.py` |
| RAG 查询改写 + 词法重排 + 两级结构切片 | `services/agent_service/rag/{retriever,chunker}.py` |
| 工具参数 Pydantic 二次校验 + 结果压缩 | `services/tool_service/tools.py::validate_tool_args` |
| ReAct 对照实现与 FC 对比脚本 | `services/agent_service/core/react.py`、`scripts/compare_fc_react.py` |
| RAG 评测集（50 条 recall@5） | `scripts/eval_rag.py` |
| cache-aside（穿透/击穿/雪崩） | `common/cache.py` |
| 可观测性 / 故障演练 | `services/admin_service/router.py` |

---

## 七、配置（可选）

复制 `.env.example` 为 `.env` 后按需修改：

- `LLM_PROVIDER=openai` + `LLM_API_KEY=...` → 接入真实大模型（DeepSeek / 通义千问）
- `DATABASE_URL=mysql+aiomysql://...` → 切 MySQL 8
- `KV_BACKEND=redis` + `REDIS_URL=...` → 切真实 Redis（滑动窗口走 Lua）
- `VECTOR_BACKEND=pgvector` + `VECTOR_DB_URL=postgresql://...` → 切真实 pgvector 向量库（HNSW）
- `EMBEDDING_PROVIDER=openai` → 切真实 Embedding（模型名/维度均可配）
- `SECRET_ENCRYPTION_KEY=...` → API Key 加密落库的密钥（不设则由 `JWT_SECRET` 派生，生产建议显式设置）

一键起真实基础设施（MySQL:3307 / Redis:6380 / pgvector:5432）：

```powershell
docker compose -f deploy/docker-compose.dev.yml up -d
```

管理员也可在「管理 → 系统设置」里在线切换向量后端、配置向量模型与切片/topk/阈值参数（保存即重建索引）。

---

## 八、参考项目

开发前检索并拉取了 GitHub 上同类开源项目用于结构与思路参考（`reference/`）：
`bcefghj/multi-agent-travel-planner`、`entbappy/TripMate-…-LangGraph`、`chetandekate/ai-travel-itinerary-planner` 等。
本项目为独立实现，未直接复用其代码。

---

## 九、文档索引

- [需求分析与可行性分析](docs/01-需求分析与可行性分析.md)
- [总体架构与技术栈](docs/02-总体架构与技术栈.md)
- [技术要点与设计说明](docs/03-技术要点与设计说明.md)
- [文档冲突消解说明](docs/04-文档冲突消解说明.md)
- [功能扩展说明（旅行吧·管理后台·真实工具·模型选择）](docs/05-功能扩展说明（旅行吧·管理后台·真实工具·模型选择）.md)
- [技术达标检查（对照面试技术手册 Q1–Q51）](docs/06-技术达标检查.md)
