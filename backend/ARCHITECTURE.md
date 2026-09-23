# Report Agent Backend 架构文档

本文档描述 `backend` 的实际代码架构、运行时装配关系、报告生成流程，以及新增能力时的扩展方式。文档以当前代码为准；未实现的能力明确标注为规划项，规划项集中在 [../ROADMAP.md](../ROADMAP.md)。

## 1. 项目定位

面向「报告生成」业务的后端，不是通用 Agent 平台。核心链路：

```text
数据源 + 报告模板 + 用户指令
              ↓
        对话（唯一写入通道）
              ↓
       模板解析 → 章节树 → 报告计划
              ↓
        逐章取数和写作
              ↓
       报告组装与文件渲染
```

两条能力链路并存：

1. **数据集管理与确定性分析**：注册 Excel/SQL 数据源、查看 Schema、Profile、执行只读查询。
2. **报告生成**：全部通过对话驱动。

### 一条不可协商的约束

**对话是唯一的写入通道。**`POST /conversations/{id}/messages` 是系统唯一的写接口。所有状态迁移——创建报告、修改计划、确认开工、补充数据——都由 `ConversationOrchestrator` 根据会话当前状态判定意图后触发。

这条约束的直接后果：

- `/reports` 下**没有任何写接口**，只有读和下载。
- 前端不做业务分支，只按 `message.kind` 选渲染组件。
- 计划、进度、追问都是消息，因此天然有历史、可回看、可持久化。

早期版本曾提供表单式的 `POST /reports`、`/plan/confirm`、`/answers`、`/resume`，已全部移除。

## 2. 分层架构

```text
┌──────────────────────────────────────────────────────────────┐
│ API 层：FastAPI routes                                        │
│ 请求校验、HTTP 状态码、文件上传下载；不含业务逻辑              │
└───────────────────────────┬──────────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────────┐
│ 对话层：app/conversations          ★ 唯一写入路径              │
│ ConversationOrchestrator：意图路由 → 调用报告服务 → 产出消息   │
└───────────────────────────┬──────────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────────┐
│ 报告业务层：app/reporting                                     │
│ ReportGenerationService（整份报告生命周期）                    │
│ TemplateParser / Planner / ChapterWriterAgent / Assembler     │
└──────────────┬───────────────────────────┬───────────────────┘
               │                           │
┌──────────────▼──────────────┐ ┌──────────▼───────────────────┐
│ 领域模型与端口 app/core      │ │ 数据访问与工具                │
│ Conversation/Message         │ │ DataCatalog / ToolRegistry   │
│ Session/Plan/Draft/Ports     │ │ Excel / SQL 数据源           │
└──────────────┬──────────────┘ └──────────┬───────────────────┘
               │                           │
┌──────────────▼───────────────────────────▼───────────────────┐
│ app/infrastructure：LLM 适配、日志、仓储、产物存储             │
└──────────────────────────────────────────────────────────────┘
```

设计约束：

- API 层不实现取数、Prompt 或报告组装。
- 对话层决定「这条消息意味着什么」；报告层决定「怎么做」。两者不互相越界：orchestrator 不碰模板解析，报告服务不认识消息。
- `ReportGenerationService` 负责整份报告的生命周期；章节 Agent 只负责一个章节。
- 数据源通过 `DataCatalog` 暴露，Agent 不直接依赖 `openpyxl`、SQLAlchemy。
- LLM、ArtifactStore、仓储通过 `core/ports.py` 与 `*/repository.py` 定义接口。
- `dependencies.py` 是唯一的运行时装配点。

## 3. 目录结构

```text
backend/app/
├── main.py                            创建 FastAPI 应用，注册路由
├── config.py                          .env → Settings
├── dependencies.py                    lru_cache 单例装配
│
├── api/routes/
│   ├── health.py
│   ├── auth.py                        登录、/me、current_user 依赖
│   ├── conversations.py               唯一写入口所在
│   ├── reports.py                     只读
│   ├── connections.py                 数据源连接 CRUD / 测试 / 取数
│   └── datasets.py
│
├── auth/                              ★ 登录
│   ├── service.py                     校验口令、签发与解析 token
│   └── repository.py                  读 AI_DA_DB.users
│
├── conversations/                     ★ 对话层
│   ├── orchestrator.py                意图路由与消息产出
│   └── repository.py                  ConversationRepository 抽象
│
├── connections/                       ★ 已保存的数据库连接
│   ├── service.py                     连通性测试与只读取数
│   └── repository.py                  ConnectionRepository 抽象 + 文件持久化
│
├── core/                              领域模型与端口，无 IO
│   ├── conversations.py               Conversation / Message / MessageIntent
│   ├── reports.py                     报告全部模型 + group_template_chapters
│   ├── connections.py                 DataConnection / 取数请求与指标抽取
│   ├── auth.py                        AuthUser / LoginRequest / 鉴权异常
│   ├── models.py                      通用模型、Evidence、RequestContext
│   ├── ports.py                       LlmService / ArtifactStore
│   ├── tooling.py                     Tool / ToolContext / ToolResult / ToolRegistry
│   └── agent.py                       通用工具调用循环（底层可复用能力）
│
├── reporting/
│   ├── report_generation.py           ReportGenerationService
│   ├── template_parser.py             文档 → ReportTemplate（含表格）
│   ├── planner.py                     ReportPlan 生成与自然语言修订
│   ├── chapter_writer.py              ChapterWriter 接口 + StubChapterWriter
│   ├── chapter_writer_agent.py        两阶段章节 Agent
│   ├── assembler.py                   ChapterDraft → AssembledReport
│   ├── renderer.py                    AssembledReport → Markdown
│   └── session.py                     报告与模板仓储接口
│
├── data/
│   ├── catalog.py                     dataset_id → RegisteredDataSource
│   └── sources/{base,excel,sql}.py
│
├── tools/
│   ├── dataset_tools.py               只读数据工具
│   └── sql2sql_tool.py                自然语言 → 分析 SQL
│
└── infrastructure/
    ├── llm.py                         OpenAI-compatible 适配 + 调用日志
    ├── logging.py                     文件 + 控制台日志，preview() 截断
    ├── conversation_repositories.py   会话/消息：内存 + 文件持久化
    ├── report_repositories.py         报告会话：内存 + 文件持久化；模板：仅内存
    └── artifact_store.py              产物：内存 + 文件系统（默认文件系统）
```

> 模板仓储是唯一没有持久化实现的：进程重启后 `GET /reports/templates/{id}` 返回 404，
> 而解析后的结构已随会话存入 `sessions.json`，所以报告生成本身不受影响。

## 4. 对话层

### 4.1 消息模型

```python
class Message:
    message_id, conversation_id
    role: "user" | "assistant"
    kind: "text" | "plan" | "progress" | "question" | "report" | "error"
    content: str                 # 给人看的自然语言
    payload: dict                # 给 UI 渲染的结构化数据
    attachments: list[MessageAttachment]

class Conversation:
    conversation_id, user_id, title
    report_session_id: str | None    # 一个会话最多一份报告
```

`kind` 是前后端的渲染契约：`plan` 的 payload 装完整 `ReportPlan`，`progress` 装章节完成度，`question` 装按章节分组的待补充项，`report` 装产物列表。

### 4.2 意图路由

`ConversationOrchestrator._classify` 按会话当前状态收敛候选意图，再交给模型判定；模型不可用时退回关键词规则：

| 会话状态 | 候选意图 |
|---|---|
| 消息带模板 + 数据附件 | `create`（无条件） |
| 无报告会话 | `chat` |
| `plan.status == awaiting_confirmation` | `approve_plan` / `revise_plan` / `chat` |
| `waiting_user` 且有待答问题 | `answer` / `chat` |
| 其他 | `chat` |

### 4.3 消息处理的两段式

```python
submit_message()    # 同步：解析 docx 存模板、注册 Excel、落 user message
                    # 坏文件当场 400，请求即返回
process_message()   # 后台 asyncio 任务：意图判定 → 调用报告服务 → 产出助手消息
```

上传解析放在同步段，是为了让文件错误立刻反馈；模型工作放在后台段，是为了让输入框不被几分钟的生成阻塞。

## 5. 报告领域模型

### 5.1 章节树

模板解析产出的是**扁平的标题列表**（忠实于文档），`group_template_chapters` 把它归组成章节树：

```python
class TemplateChapter:
    root: ReportTemplateSection          # 顶级标题
    subsections: list[ReportTemplateSection]   # 其下所有更深的标题
```

归组规则：最浅的标题层级起一章，更深的挂到上一章。正文前言（`metadata.preamble`）自成一章且不参与层级基准计算。

**章节是取数、写作和渲染的统一单位**：一次 agent 运行写完整章（含 H3 子节），渲染时章节固定输出 `##`，子节按相对深度输出 `###` / `####`。

### 5.2 报告计划

```python
class ChapterPlan:
    section_id, title
    level: int                       # 来自模板，模型不可修改
    metrics: list[str]               # 覆盖本章及其全部子节
    subsections: list[SubchapterPlan]

class ReportPlan:
    plan_id, version, status
    title, instruction
    global_context: ReportGlobalContext    # report_period + dimensions
    chapters: list[ChapterPlan]
    assembly_order: list[str]
```

计划**只表达业务意图**：规划阶段禁止确定 Sheet、表名、字段名、SQL 或工具调用顺序。这条约束让计划成为一个不懂表结构也能修改的对象。

模型返回的计划一律经 `_parse_plan_payload` 校验：`section_id` 必须存在于模板、子节必须属于本章、指标必须是字符串数组、层级一律从模板取。首次规划要求覆盖整棵树，修订允许两级子集与重排——所以「去掉某一章」会连带去掉它的子节，不会留下孤儿。

### 5.3 会话状态

```text
created → awaiting_confirmation ⇄ (revise_plan)
              ↓ approve_plan
           running ⇄ waiting_user
              ↓
          completed / failed / cancelled
```

`waiting_user` 的语义是「停着等人补数据」，不是「进行中」——所以进程重启时**不对账**它。

## 6. 章节 Agent

`ChapterWriterAgent` 两阶段，参数 `max_iterations=8`、`max_retries_per_error=2`、`max_rows_per_read=100`：

**阶段一 · 取数（有界 ReAct）**

只暴露 `read_dataset` / `query_dataset` 两个只读工具。`_execute_read_tool` 做三层校验：数据集必须在本次会话白名单内；按数据源类型强制工具匹配（Excel 用 `read_dataset`，SQL 用 `query_dataset`）；行数上限。工具报错回喂给模型让它改参数，同类错误超过上限才放弃。

**阶段二 · 写作（无工具）**

输入是章节模板原文（含 Markdown 化的表格）、子节列表及其应输出的 heading 行、计划指标、全局上下文、全部成功读取的数据。

几条来自实测的硬约束：

- **questions 非空即视为需要补充数据**，不依赖模型把 `status` 设对——实测中模型经常一边在正文写"待补充后再计算"、一边把状态标成 `completed`，导致请求被静默丢弃。
- `waiting_user` 但没给出任何问题时，用章节计划的指标兜底生成一条，**绝不让会话静默挂起**。
- `chapter_plan.metrics` 为空的叙述性章节（前言、数据来源说明）不允许因缺数据提问。
- 表格必须写在 `content` 里。`ChapterDraft.tables` 字段渲染器不消费，模型把表放进去就等于丢弃。

### 6.1 追问：先判定要什么，再问怎么补

一条 `UserQuestion` 带 `expected`，它在**提问时**就已经定下，用户不需要自己声明答案的形态：

| `expected` | 含义 | 用户可用的补充方式 |
| --- | --- | --- |
| `value` | 正文里引用的一个数 | 直接填数值 / 写 SQL |
| `table` | 要填进模板表格、或本身就是逐行清单的一份明细 | 粘贴明细 / 写 SQL |
| `text` | 一段文字说明 | 直接填写 |

判定顺序：取数 agent 在 unresolved 里给的 `needs` 优先（它刚为这个指标取过数，最清楚）；没给就看本章模板表头是否出现过该指标名、以及指标名本身像不像一份清单（`_expectation`）。

`expected` 决定后端怎么读用户的 SQL：`value` 走「最后一列是取值、前面列是维度，且必须收敛到一行」，`table` 走「所有列都是内容，最多 100 行」。这条守卫是有意保留的——一个本该是单值的指标返回了 50 行，必须报错而不是静默取第一行。判定错了由用户一键纠正（`QuestionResolutionInput.as_table`），而不是让所有人每次都先选一次。

粘贴的明细由 `core/tabular.py` 解析，支持 Excel 复制（制表符）、`指标：数值` 多指标行、Markdown 表格、逗号分隔与空格对齐。解析只有服务端一份实现：`POST /supplements/preview` 给用户看的预览，和提交后真正入库的那次解析，走的是同一个函数。

## 7. 实际运行流程

```text
POST /conversations/{id}/messages  (multipart: text + template_file + data_file)
  │
  ├─ submit_message         upload_template / register_excel_dataset / 落 user message
  │                         ← 立即返回
  └─ process_message（后台）
       ├─ _classify → create
       └─ create_session
            └─ _prepare_plan
                 解析模板快照 → 数据源元数据（含前 5 行样例）→ planner.create_plan
                 status = awaiting_confirmation，产出 kind="plan" 消息

（用户说"去掉风险章节"）→ revise_plan → version+1 → 新的 kind="plan" 消息
（用户说"确认，开始生成"）→ approve_plan → start → _continue

_continue：
  for chapter in plan.chapters:
      已有 draft → 跳过
      落盘 current_chapter_id（否则外部观察不到"哪一章在跑"）
      ChapterWriterAgent.write(章节 + 子节 + 指标 + 数据源)
        ├─ waiting_user → 记录问题（带 metric/expected/chapter_title）
        │                 status = waiting_user，**就地返回**，后续章节不启动
        └─ completed  → 存 draft、落盘 → 前端 2s 内可见该章正文
  全部完成 → assemble → render → ArtifactStore → kind="report" 消息
```

补充数据后 `answer_question` 消费问题，全部答齐则自动 `start` 恢复：重跑当前章，再继续下一章。重试前会清掉该章的历史问题，避免重复堆积。

## 8. 扩展方式

### 8.1 新增章节 Writer

实现 `ChapterWriter` 接口，在 `dependencies.get_report_generation_service` 里替换 `writer=`：

```python
class ChapterWriter(ABC):
    async def write(self, input: ChapterWriterInput, session) -> ChapterWriterResult: ...
```

`ChapterWriterInput` 提供章节模板、子节列表、计划指标、全局上下文、数据源元数据、用户指令和历史回答。返回 `completed`（带 `ChapterDraft`）、`waiting_user`（带 `questions`）或 `failed`。外围流程不关心内部是 ReAct、单次调用还是纯规则。

### 8.2 新增数据工具

实现 `core/tooling.Tool`，在 `dependencies.get_registry` 注册。若要让章节 Agent 用到，还需加入 `ChapterWriterAgent._read_tool_names`——该集合是取数阶段的白名单。

### 8.3 新增 Renderer / 仓储 / LLM

分别实现 `MarkdownReportRenderer` 的同型接口、`*Repository` 抽象、`core/ports.LlmService`，然后在 `dependencies.py` 装配。所有替换点都收敛在这一个文件。

### 8.4 新增消息类型

在 `core/conversations.MessageKind` 增加字面量，在 orchestrator 产出该 kind 的消息，在前端 `ChatPanel` 增加对应渲染组件。**不要**为新交互增加写接口——所有写入都应该经由消息。

## 9. 测试与运行

```bash
pip install -r requirements-dev.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
python -m pytest -q          # 当前 44 passed
```

测试分布：

| 文件 | 覆盖 |
|---|---|
| `test_conversation_orchestrator.py` | 意图路由、计划修订、确认生成、一会话一报告、缺数据提问 |
| `test_conversation_api.py` | HTTP 层：multipart 上传、后台处理、旧写接口确已移除 |
| `test_template_chapter_tree.py` | 章节归组、整章一次生成、缺数据阻塞与恢复、运行中可观测 |
| `test_template_tables.py` | DOCX/Markdown 表格解析、提示词防回归 |
| `test_report_generation.py` | 报告外围流程、重启对账 |
| `test_chapter_writer_agent.py` | 取数重试、questions 优先于 status、无问题兜底 |
| `test_excel_reading.py` / `test_core.py` / `test_agent.py` | 数据层与通用能力 |

> 不要同时起两个后端进程：它们共享同一个持久化文件，启动对账会把对方正在跑的会话判死。

## 10. 当前限制

- **追问不支持上传文件**：明细可以粘贴或写 SQL 取，但不能直接传一个 Excel 上来。
- **无聚合工具**：Excel 数据源只有整行读取，指标计算依赖模型对原始行心算，行数一多必然出错。
- **无 SSE**：前端 2s 轮询。
- **后台任务是进程内 asyncio**：生成中途重启，该次运行不会自动恢复。
- **模板与产物仍是内存存储**；DOCX/PDF/HTML 渲染未实现；DOCX 样式保真未实现。
- **无认证与用户隔离**：`RequestContext` 固定为 `local-user`。

演进顺序见 [../ROADMAP.md](../ROADMAP.md)。
