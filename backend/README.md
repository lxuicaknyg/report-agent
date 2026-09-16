# Report Agent Backend

“报告生成应用”的后端。目标不是通用 Agent 平台，而是把模板解析、章节规划、章节写作和文档组装嵌进一条报告生成业务流程。

分层架构、模块职责和扩展规范见 [ARCHITECTURE.md](./ARCHITECTURE.md)。

## 核心设计：对话是唯一的写入通道

`POST /conversations/{id}/messages` 是系统唯一的写接口。创建报告、修改计划、确认开工、补充数据，全部是这一个动作。`ConversationOrchestrator` 根据**会话当前状态**判定这条消息的意图，再调用报告服务：

| 会话状态 | 允许的意图 | 落到的调用 |
|---|---|---|
| 无报告会话 | `create`（附件齐全）/ `chat` | `create_session` |
| `awaiting_confirmation` | `revise_plan` / `approve_plan` / `chat` | `revise_plan` / `approve_plan` |
| `running` | `chat` | — |
| `waiting_user` | `answer` / `chat` | `answer_question` |
| `completed` | `chat` | — |

意图识别优先用一次轻量模型调用，失败或未配置模型时退回关键词规则。

`/reports` 全部是只读接口：报告由对话驱动，没有表单式的写接口。

## 报告生成流程

```text
上传模板 + Excel + 一句指令
        ↓  submit_message：同步解析 docx、注册 Excel（坏文件当场 400）
        ↓  process_message：后台任务，以下都在其中
   解析模板 → 归组成章节树 → 构建数据源元数据 → 生成 ReportPlan
        ↓  status = awaiting_confirmation
   ←── 对话修订计划（version+1，历史版本留在消息流里）
        ↓  用户说“确认，开始生成”
   逐章：有界只读取数 ReAct → 无工具写作调用 → 落盘 → 前端立刻可见
        │
        └─ 数据不足 → 抛出缺失指标 → 整轮停在这一章
                      status = waiting_user
                      补充后重跑本章，再继续下一章
        ↓
   ReportAssembler → MarkdownReportRenderer → ArtifactStore
```

**章节 = 模板的一个顶级标题及其下所有子标题。**一次 agent 运行写完整章（含 H3 子节），不是一个标题一次。子节的标题层级由模板决定，模型只能取舍和改标题，改不了层级。

**计划只表达业务意图，不表达取数方式。**规划阶段禁止确定 Sheet、表名、字段名和 SQL——那是章节 agent 运行时自己带工具探的。所以不懂表结构也能改计划。

## 接口

```text
GET  /health

POST   /api/v1/conversations                    建会话
GET    /api/v1/conversations                    列表
GET    /api/v1/conversations/{id}               会话 + 全部消息 + 报告快照
DELETE /api/v1/conversations/{id}
POST   /api/v1/conversations/{id}/messages      ★ 唯一写入口（multipart 或 JSON）

POST /api/v1/reports/templates                  上传模板
GET  /api/v1/reports/templates
GET  /api/v1/reports/templates/{template_id}
GET  /api/v1/reports                            报告列表（只读）
GET  /api/v1/reports/{session_id}               报告详情（只读）
GET  /api/v1/reports/{session_id}/artifacts/{artifact_id}

GET  /api/v1/datasets
POST /api/v1/datasets/excel
POST /api/v1/datasets/sql
GET  /api/v1/datasets/{dataset_id}/sheets
GET  /api/v1/datasets/{dataset_id}/schema
POST /api/v1/datasets/{dataset_id}/preview

POST /api/v1/analysis/profile
POST /api/v1/analysis/query
```

### 消息类型

一条助手消息的 `kind` 决定前端用哪个组件渲染，`payload` 提供结构化数据。前端不做业务判断。

| kind | payload | 前端渲染 |
|---|---|---|
| `text` | — | 普通气泡 |
| `plan` | `plan`（完整 ReportPlan） | 只读计划卡 + 建议 chip |
| `progress` | `chapters[]`（含状态） | 章节进度，已完成可展开看正文 |
| `question` | `chapters[].questions[]` | 待补充数据卡（指标名 + 期望形式） |
| `report` | `artifacts[]` | 查看全文 / 下载 |
| `error` | — | 错误卡 |

## 目录结构

```text
backend/
├── app/
│   ├── main.py                        注册路由
│   ├── config.py                      .env 读取
│   ├── dependencies.py                运行时装配（lru_cache 单例）
│   │
│   ├── api/routes/                    health / conversations / reports / datasets / analysis
│   │
│   ├── conversations/                 ★ 对话层：系统唯一写入路径
│   │   ├── orchestrator.py            意图路由 + 调用报告服务 + 产出消息
│   │   └── repository.py              会话与消息仓储接口
│   │
│   ├── core/                          领域模型与端口
│   │   ├── conversations.py           Conversation / Message / MessageIntent
│   │   ├── reports.py                 Session / Plan / Draft / TemplateChapter / 分组函数
│   │   ├── models.py  ports.py  tooling.py  agent.py
│   │
│   ├── reporting/                     报告业务
│   │   ├── report_generation.py       整份报告的生命周期编排
│   │   ├── template_parser.py         DOCX/MD/TXT → 章节 + 表格结构
│   │   ├── planner.py                 计划生成与自然语言修订
│   │   ├── chapter_writer_agent.py    单章两阶段：取数 ReAct → 写作
│   │   ├── chapter_writer.py          Writer 接口 + Stub
│   │   ├── assembler.py  renderer.py  session.py
│   │
│   ├── data/                          DataCatalog + Excel/SQL 数据源
│   ├── tools/                         只读数据工具
│   └── infrastructure/                LLM / 日志 / 仓储 / 产物存储
│
├── example/                           示例模板与数据
└── tests/
```

## 关键实现说明

### 模板解析

- DOCX 按文档顺序遍历 `w:body` 的子元素，`w:p` 和 `w:tbl` 混排处理。**只遍历 `w:p` 会把表格连同单元格文字一起丢掉**——`example/report_template.docx` 里那张四列表就踩过这个坑。
- Markdown 认 `#` 标题、中文/数字编号标题（`一、` `1.1.`）和 `|---|` 管道表。
- 表格保留为结构化块 `{"type":"table","header":[...],"rows":[...]}`，同时渲染成 Markdown 进 `template_text`，章节 agent 照着填真实数据。
- 正文前的段落合成一个 `metadata.preamble` 的章节，归组时不参与层级基准计算——否则 H2 起步的模板会被整篇吞成一章。

### 章节 Agent

两阶段，`max_iterations=8`、`max_rows_per_read=100`：

1. **取数**：只给 `read_dataset` / `query_dataset` 两个只读工具。校验数据集白名单，按数据源类型强制工具匹配（Excel 用 `read_dataset`，SQL 用 `query_dataset`），用错直接回错误让模型改参数。
2. **写作**：无工具调用，输入是章节模板 + 全部成功读取的数据。

**questions 非空即视为需要补充数据**，不依赖模型把 `status` 设对——模型经常一边在正文里写"待补充后再计算"一边把状态标成 completed。`chapter_plan.metrics` 为空的叙述性章节（前言、数据来源说明）不允许因缺数据提问。

### 持久化

会话、报告和消息落到系统临时目录的 JSON 文件，进程重启不丢。启动时会把 `CREATED` / `RUNNING` 的报告对账成 `CANCELLED`（进程没了，内存里的 worker 回不来），但 **`WAITING_USER` 保留**——它停着等人，重启后答案照样能到。

模板和产物目前仍是内存存储。

### 日志

`configure_logging` 同时输出到轮转文件和控制台。可观测的内容：用户原话与附件、意图判定、每次模型调用的 prompt/响应/耗时/token、计划完整结构、章节 agent 的每次工具调用（工具名 + 参数 + 成功与否 + 返回）、章节正文预览。长内容统一经 `preview()` 压成单行截断。

## 运行

```bash
pip install -r requirements-dev.txt
cp .env.example .env        # LLM_BASE_URL / LLM_API_KEY / LLM_MODEL_NAME
uvicorn app.main:app --reload --port 8000
```

```bash
python -m pytest -q         # 当前 44 passed
```

接口文档 `http://127.0.0.1:8000/docs`，健康检查 `GET /health`。

开发直接用共享的 `promptenv` Conda 环境。离线部署可先准备 wheel 目录：

```bash
pip install --no-index --find-links=./wheels -r requirements.txt
```

> 不要同时起两个后端进程：它们共享同一个持久化文件，启动对账会把对方正在跑的会话判死。

## 当前边界

已实现：模板解析（多级标题 + 表格）、对话式计划生成与修订、逐章取数与写作、缺数据阻塞与提问、章节内容实时可见、报告组装与 Markdown 产物、会话持久化、结构化日志。

未实现：见 [../ROADMAP.md](../ROADMAP.md)。
