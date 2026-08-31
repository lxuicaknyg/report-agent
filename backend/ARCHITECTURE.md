# Report Agent Backend 架构文档

本文档描述当前 `backend` 的实际代码架构、运行时组装关系、报告生成流程，以及新增 Agent 时应如何扩展。文档以当前代码为准；尚未实现的能力会明确标注为规划项。

## 1. 项目定位

本项目是一个面向“报告生成”业务的后端原型，不是通用 Agent 平台。核心业务链路是：

```text
数据源 + 报告模板 + 用户指令
              ↓
      报告生成会话
              ↓
       模板解析与计划
              ↓
        逐章研究和写作
              ↓
       报告组装与文件渲染
```

当前系统同时提供两条能力链路：

1. 数据集管理和确定性分析：注册 Excel/SQL 数据源、查看 Schema、Profile、执行只读查询。
2. 报告生成：上传模板、创建会话、逐章读取数据和写作、处理用户追问、生成 Markdown 产物。

当前默认的报告章节 Writer 是 `ChapterWriterAgent`。它使用 OpenAI-compatible LLM，在每个章节中先进行有界的只读取数循环，再进行一次无工具写作调用。`StubChapterWriter` 仅用于外围流程测试。

## 2. 分层架构

```text
┌────────────────────────────────────────────────────────────┐
│ API 层：FastAPI routes                                     │
│ 请求校验、HTTP 状态码、文件上传和下载                       │
└────────────────────────────┬───────────────────────────────┘
                             │
┌────────────────────────────▼───────────────────────────────┐
│ 应用/业务编排层                                             │
│ ReportGenerationService / AnalysisAgent                    │
└───────────────┬───────────────────────┬────────────────────┘
                │                       │
┌───────────────▼──────────────┐ ┌──────▼────────────────────┐
│ 报告领域模型与端口 core       │ │ 数据访问与工具             │
│ Session/Plan/Draft/Ports      │ │ DataCatalog/Tools         │
└───────────────┬──────────────┘ └──────┬────────────────────┘
                │                       │
┌───────────────▼───────────────────────▼────────────────────┐
│ reporting / data / infrastructure                           │
│ 模板解析、章节 Agent、Renderer、数据源、LLM、仓储和存储       │
└────────────────────────────────────────────────────────────┘
```

设计约束：

- API 层不直接实现取数、Prompt 或报告组装逻辑。
- `ReportGenerationService` 负责整份报告的生命周期；章节 Agent 只负责一个章节。
- 数据源通过 `DataCatalog` 暴露，Agent 不应直接依赖 `openpyxl`、SQLAlchemy 等具体库。
- LLM、ArtifactStore、仓储等可替换组件通过 `core/ports.py` 定义接口。
- `dependencies.py` 是默认运行时装配点；增加实现后必须在这里显式接入。

## 3. 目录结构

```text
backend/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── dependencies.py
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   └── routes/
│   │       ├── __init__.py
│   │       ├── health.py
│   │       ├── datasets.py
│   │       ├── analysis.py
│   │       └── reports.py
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   ├── models.py
│   │   ├── reports.py
│   │   ├── ports.py
│   │   ├── tooling.py
│   │   └── agent.py
│   │
│   ├── data/
│   │   ├── __init__.py
│   │   ├── catalog.py
│   │   └── sources/
│   │       ├── __init__.py
│   │       ├── base.py
│   │       ├── excel.py
│   │       └── sql.py
│   │
│   ├── analysis/
│   │   ├── __init__.py
│   │   └── agent.py
│   │
│   ├── reporting/
│   │   ├── __init__.py
│   │   ├── reports.py
│   │   ├── report_generation.py
│   │   ├── session.py
│   │   ├── template_parser.py
│   │   ├── planner.py
│   │   ├── chapter_writer.py
│   │   ├── chapter_writer_agent.py
│   │   ├── assembler.py
│   │   └── renderer.py
│   │
│   ├── tools/
│   │   ├── __init__.py
│   │   └── dataset_tools.py
│   │
│   └── infrastructure/
│       ├── __init__.py
│       ├── llm.py
│       ├── users.py
│       ├── report_repositories.py
│       └── artifact_store.py
│
├── example/
├── tests/
├── requirements.txt
├── requirements-dev.txt
└── README.md
```

## 4. 文件职责

### 4.1 应用入口与装配

#### `app/__init__.py`

Python 包标记文件，没有业务逻辑。

#### `app/main.py`

创建 FastAPI 应用并注册路由：

- `/health`
- `/api/v1/datasets/*`
- `/api/v1/analysis/*`
- `/api/v1/reports/*`

该文件只负责应用入口和路由挂载，不应放置业务流程。

#### `app/config.py`

读取应用配置和 LLM 配置：

- `APP_NAME`
- `ENVIRONMENT`
- `API_PREFIX`
- `DATA_DIR`
- `ARTIFACT_DIR`
- `DATABASE_URL`
- `LLM_BASE_URL`
- `LLM_API_KEY`
- `LLM_MODEL_NAME`

模块会尝试加载 `backend/.env`。仓库只提交 `.env.example`，真实密钥不应提交到 Git。

#### `app/dependencies.py`

默认依赖注入和单例装配中心，当前装配：

```text
DataCatalog
  └── ToolRegistry
        ├── ListDatasetsTool
        ├── ProfileDatasetTool
        ├── QueryDatasetTool
        ├── ListSheetsTool
        └── ReadDatasetTool

ReportGenerationService
  ├── InMemoryReportSessionRepository
  ├── InMemoryReportTemplateRepository
  ├── ReportTemplateParser
  ├── ReportPlanner
  ├── ChapterWriterAgent
  ├── ReportAssembler
  ├── MarkdownReportRenderer
  ├── InMemoryArtifactStore
  └── DataCatalog
```

使用 `lru_cache` 提供进程级单例。替换真实 LLM、数据库仓储、对象存储或 Writer 时，优先修改此文件。

### 4.2 API 层：`app/api`

#### `app/api/routes/health.py`

提供 `GET /health`，用于服务存活检查。

#### `app/api/routes/datasets.py`

数据源接口：

```text
GET  /api/v1/datasets
POST /api/v1/datasets/excel
POST /api/v1/datasets/sql
GET  /api/v1/datasets/{dataset_id}/sheets
GET  /api/v1/datasets/{dataset_id}/schema
POST /api/v1/datasets/{dataset_id}/preview
```

负责文件上传、SQL 数据源注册、Schema 和预览请求的 HTTP 适配。实际访问由 `DataCatalog` 完成。

#### `app/api/routes/analysis.py`

提供：

```text
POST /api/v1/analysis/profile
POST /api/v1/analysis/query
```

当前分析接口是确定性的：调用方提供 `dataset_id`，查询接口提供只读 SQL；这里还没有自然语言转 SQL。

#### `app/api/routes/reports.py`

新报告流程接口：

```text
POST /api/v1/reports/templates
GET  /api/v1/reports/templates/{template_id}
POST /api/v1/reports
GET  /api/v1/reports/{session_id}
POST /api/v1/reports/{session_id}/answers
POST /api/v1/reports/{session_id}/resume
GET  /api/v1/reports/{session_id}/artifacts/{artifact_id}
```

此外保留：

```text
POST /api/v1/reports/draft
```

该旧接口只生成基于 Profile 的兼容性报告，不走新的模板和章节 Agent 流程。

### 4.3 领域层：`app/core`

#### `app/core/models.py`

通用领域模型，包括：

- `User`、`RequestContext`
- `ColumnSchema`、`SheetInfo`
- `DataReadRequest`、`DataReadResult`
- `DatasetInfo`、`DatasetProfile`、`QueryResult`
- `Evidence`
- `AnalysisRequest`、`AnalysisResult`
- 旧版 `ReportDraft`

这些模型不应依赖 FastAPI 或具体数据库实现。

#### `app/core/reports.py`

报告生成领域契约，包括：

- `ReportGenerationStatus`：`created`、`running`、`waiting_user`、`completed`、`failed`、`cancelled`
- `ReportTemplate`、`ReportTemplateSection`
- `ReportPlan`
- `DataSourceMetadata`
- `ChapterWriterInput`、`ChapterWriterResult`
- `ChapterDraft`
- `AssembledReport`
- `ReportArtifact`
- `UserQuestion`
- `ReportGenerationSession`
- 创建会话和回答问题的请求模型

这是报告模块的稳定边界。新增 Agent 应优先复用这些契约，而不是自行创建相似的字典结构。

当前 `ReportTemplateSection` 有 `level` 字段，但没有 `parent_section_id` 或 `children`；因此多级标题目前只能被识别层级，计划和组装仍是扁平章节列表。

#### `app/core/ports.py`

定义可替换接口：

- `DataSource`
- `LlmService`
- `ArtifactStore`
- `UserResolver`

业务层依赖这些抽象，不应直接依赖 OpenAI SDK、S3 SDK 或具体数据库客户端。

#### `app/core/tooling.py`

定义工具系统：

- `ToolContext`：请求用户、会话和权限上下文
- `ToolResult`：成功标志、给模型的摘要、结构化数据、错误和证据
- `Tool`：工具名称、描述、参数 Schema 和执行方法
- `ToolRegistry`：注册、列举 Schema、权限检查和调用

#### `app/core/agent.py`

提供通用的 `ToolCallingAgent` 工具调用循环。它是基础能力，不负责报告会话、模板或 Artifact 生命周期。新的通用工具调用型 Agent 可以复用它，但章节报告流程仍应实现 `ChapterWriter` 接口。

### 4.4 数据层：`app/data`

#### `app/data/catalog.py`

`DataCatalog` 维护：

```text
dataset_id → RegisteredDataSource
```

统一提供数据集列表、Schema、Sheet、行读取、Profile 和查询能力，是上层访问数据源的唯一入口。

#### `app/data/sources/base.py`

定义 `RegisteredDataSource` 抽象接口。新增数据源类型时，应实现该接口，而不是修改报告 Agent 让它直接读取新格式。

#### `app/data/sources/excel.py`

`ExcelDataSource`：

- 使用 `openpyxl` 只读模式读取 `.xlsx`
- 支持多 Sheet
- 支持 Schema、分页行读取、列选择和精确筛选
- 支持 Profile
- 保留显式 SQL 查询兼容路径，懒加载 DuckDB/SQLite

#### `app/data/sources/sql.py`

`SqlDataSource` 使用 SQLAlchemy 连接外部数据库，提供表 Schema、Profile 和只读 `SELECT`/`WITH` 查询。

当前 Excel 和 SQL 数据源分别执行查询，不支持跨数据源 JOIN。

### 4.5 分析层：`app/analysis`

#### `app/analysis/agent.py`

`AnalysisAgent` 是面向数据分析 API 的轻量应用服务：

- `profile()` 调用 Profile 工具
- `query()` 调用只读查询工具

它与报告生成流程相互独立。后续可以被报告 Writer 复用，但不应让它接管报告会话生命周期。

### 4.6 报告层：`app/reporting`

#### `app/reporting/template_parser.py`

`ReportTemplateParser` 将 DOCX/Markdown/TXT 转为 `ReportTemplate`。

- DOCX：读取 `word/document.xml`，识别 Title、Heading1-6 和普通段落
- Markdown：识别 `#` 到 `######`
- TXT：识别普通文本和简单编号标题

当前重点是语义结构，不是样式克隆。复杂表格、图片、字体、颜色和版式尚未保真保存。

#### `app/reporting/planner.py`

`ReportPlanner` 当前是确定性计划器：按 `order` 排序并生成 `assembly_order`。它不会自动拆解指标、生成数据查询任务，也不会建立多级章节父子关系。

#### `app/reporting/chapter_writer.py`

定义稳定的章节 Writer 接口：

```python
class ChapterWriter(ABC):
    async def write(
        self,
        input: ChapterWriterInput,
        session: ReportGenerationSession,
    ) -> ChapterWriterResult:
        ...
```

同时提供 `StubChapterWriter`，用于不依赖 LLM 的外围流程测试。

#### `app/reporting/chapter_writer_agent.py`

当前默认章节 Agent，分为两阶段：

1. 研究阶段：只开放 `read_dataset` 和 `query_dataset`，限制数据集范围、循环次数和读取行数；工具错误会反馈给模型修正。
2. 写作阶段：关闭工具，将章节模板、用户指令、历史回答和已收集数据交给 LLM，生成 `ChapterDraft`。

读取结果中的 `Evidence` 会附加到章节和最终报告中。数据不足或模型明确请求补充信息时，返回 `waiting_user`。

#### `app/reporting/report_generation.py`

`ReportGenerationService` 是整份报告的应用服务，负责：

1. 上传和保存模板
2. 校验模板与数据集
3. 创建/恢复会话
4. 解析模板并生成计划
5. 构建数据源元信息
6. 按计划逐章调用 Writer
7. 保存章节草稿和中间状态
8. 处理等待用户、回答和恢复
9. 组装报告
10. 渲染并保存 Artifact

已完成的章节会根据 `session.chapter_drafts` 跳过，因此恢复时不会重复生成已完成章节。

#### `app/reporting/assembler.py`

按 `ReportPlan.assembly_order` 排列章节，合并章节证据，生成 `AssembledReport`。不重新取数，也不调用 LLM。

#### `app/reporting/renderer.py`

定义当前 Markdown 渲染实现 `MarkdownReportRenderer`。当前只生成 Markdown；未来可增加 DOCX、HTML、PDF Renderer。

#### `app/reporting/session.py`

定义：

- `ReportSessionRepository`
- `ReportTemplateRepository`
- `StoredReportTemplate`

这里是仓储抽象，具体内存实现位于 infrastructure。

#### `app/reporting/reports.py`

旧版 `ReportService`，生成基于 Profile 的 `ReportDraft`，仅为 `/reports/draft` 兼容接口保留。

### 4.7 工具层：`app/tools`

#### `app/tools/dataset_tools.py`

当前工具：

- `ListDatasetsTool`
- `ListSheetsTool`
- `ProfileDatasetTool`
- `QueryDatasetTool`
- `ReadDatasetTool`

工具统一通过 `DataCatalog` 访问数据，返回 `ToolResult`，并在成功读取时附带 `Evidence`。

### 4.8 基础设施层：`app/infrastructure`

#### `app/infrastructure/llm.py`

`OpenAICompatibleLlmService` 将内部消息和工具 Schema 转换为 OpenAI Chat Completions 请求，兼容 DashScope 等 OpenAI-compatible 服务。

#### `app/infrastructure/users.py`

`LocalUserResolver`，当前返回本地用户上下文。真实认证、JWT、OAuth 和用户隔离应在此层扩展。

#### `app/infrastructure/report_repositories.py`

提供内存版模板仓储和会话仓储。服务重启后数据丢失。

#### `app/infrastructure/artifact_store.py`

提供 `InMemoryArtifactStore`。产物 URI 为 `memory://...`，服务重启后文件不可恢复。

## 5. 当前实际报告生成流程

### 5.1 API 顺序

```text
1. POST /reports/templates
2. POST /reports
3. GET  /reports/{session_id}
4. （可选）POST /reports/{session_id}/answers
5. （可选）POST /reports/{session_id}/resume
6. GET  /reports/{session_id}/artifacts/{artifact_id}
```

### 5.2 会话状态

```text
created → running → completed
              │
              └→ waiting_user → running

运行异常 → failed
```

### 5.3 当前计划结构

`ReportPlan` 当前包含：

- `plan_id`
- `template_id`
- `title`
- `instruction`
- `sections`
- `assembly_order`

`sections` 是扁平数组。虽然 `ReportTemplateSection.level` 会保留 Heading 层级，但目前没有树形父子关系；多级章节会被逐个当成独立 Writer 任务，Markdown Renderer 也会统一输出二级标题。这是当前架构的已知限制。

## 6. 新增 Agent 的开发方式

先判断新 Agent 属于哪一类：

| 类型 | 推荐位置 | 是否接入报告主流程 |
| --- | --- | --- |
| 新的章节写作 Agent | `app/reporting/` | 实现 `ChapterWriter`，替换 Writer 装配 |
| 数据分析/指标 Agent | `app/analysis/` 或独立业务包 | 通过 `DataCatalog` 和工具访问数据 |
| 通用工具调用 Agent | `app/core/agent.py` 附近复用基础能力 | 由具体应用服务调用 |
| 新的数据读取能力 | `app/tools/` + `app/data/sources/` | 先扩展数据源/工具，再被 Agent 调用 |

### 6.1 新增章节 Writer Agent

适用于：财务章节 Writer、风险章节 Writer、图表章节 Writer、不同模型供应商 Writer 等。

步骤：

1. 在 `app/reporting/` 新建文件，例如 `risk_chapter_writer.py`。
2. 继承 `ChapterWriter`。
3. 实现 `write(input, session) -> ChapterWriterResult`。
4. 只通过 `ChapterWriterInput` 获取模板、数据源元信息、用户指令和历史回答。
5. 成功时返回 `ChapterWriterResult(status="completed", draft=ChapterDraft(...))`。
6. 需要用户补充时返回 `status="waiting_user"` 和 `UserQuestion`。
7. 失败时返回 `status="failed"` 和可诊断的错误信息。
8. 在 `app/dependencies.py` 中替换 `writer=` 的实现。
9. 在 `backend/tests/` 增加单元测试和至少一个报告流程测试。

示例骨架：

```python
from app.reporting.chapter_writer import ChapterWriter
from app.core.reports import (
    ChapterDraft,
    ChapterWriterInput,
    ChapterWriterResult,
    ReportGenerationSession,
)


class RiskChapterWriter(ChapterWriter):
    async def write(
        self,
        input: ChapterWriterInput,
        session: ReportGenerationSession,
    ) -> ChapterWriterResult:
        # 通过 DataCatalog/ToolRegistry 读取数据，或调用 LlmService。
        # 不要在这里直接改写 session 状态。
        draft = ChapterDraft(
            chapter_id=input.section.section_id,
            section_id=input.section.section_id,
            title=input.section.title,
            content="...",
        )
        return ChapterWriterResult(status="completed", draft=draft)
```

如果新 Agent 只针对某些章节生效，不建议在 `ReportGenerationService` 中写大量标题判断。更推荐引入显式的 Writer 路由器，例如根据模板元数据、章节类型或配置选择 Writer，并让路由器本身实现 `ChapterWriter` 接口。

### 6.2 新增数据分析 Agent

适用于：指标计算、同比环比、异常检测、经营诊断等。

推荐步骤：

1. 在 `app/analysis/` 新建业务 Agent。
2. 通过 `DataCatalog` 或 `ToolRegistry` 获取数据。
3. 输入输出定义在 `app/core/models.py` 或新建领域模型文件中。
4. 如果需要 LLM，依赖 `LlmService` 抽象，不直接实例化 OpenAI 客户端。
5. 如果需要新动作，先在 `app/tools/` 增加工具。
6. 由报告 Writer 或 API 应用服务显式调用。

### 6.3 新增 Agent 工具

例如增加 `calculate_metric`：

1. 在 `app/tools/` 新建工具类，继承 `Tool`。
2. 定义稳定的 `name`、`description` 和 `parameters_schema`。
3. 在 `execute()` 中调用 `DataCatalog` 或领域服务。
4. 对用户可控参数做校验和权限限制。
5. 返回结构化 `ToolResult`，重要结论附带 `Evidence`。
6. 在 `get_registry()` 注册。
7. 如果只允许某个 Agent 使用，在 `ToolContext` 中增加权限判断，而不是在工具内部依赖调用方名称。

章节 Writer 目前会过滤工具，只把 `read_dataset` 和 `query_dataset` 暴露给研究阶段。新增工具后，需要明确它是否应加入 `ChapterWriterAgent._read_tool_names` 或由新的 Agent 单独控制，不能默认让所有 Agent 使用。

### 6.4 新增 LLM 实现

如果要接入新的模型供应商：

1. 实现 `core/ports.py` 中的 `LlmService`。
2. 在 `infrastructure/` 新建适配器。
3. 将供应商差异封装在适配器内，包括消息格式、工具调用格式、超时和错误转换。
4. 在 `config.py` 增加配置项（如确有必要）。
5. 在 `dependencies.py` 选择并装配实现。
6. 使用假的 `LlmService` 编写确定性测试，避免单元测试依赖真实网络和 API Key。

### 6.5 新增 Renderer 或持久化实现

Renderer 应实现与 Markdown Renderer 相同的输出约定，并由 `ReportGenerationService` 统一调用。模板仓储、会话仓储和 ArtifactStore 则分别实现 `reporting/session.py` 和 `core/ports.py` 的接口，再在 `dependencies.py` 替换内存实现。

## 7. 测试与本地运行

在 `promptenv` 环境中：

```bash
conda activate promptenv
cd backend
python -m pytest -q
uvicorn app.main:app --reload --port 8000
```

当前测试覆盖：

- 通用工具调用 Agent
- 核心领域模型
- Excel 读取、分页、筛选和 Profile
- 报告模板解析
- 报告外围流程和 Artifact
- 章节 Writer Agent 的工具错误重试和章节写作

新增 Agent 至少应覆盖：

- 正常完成
- 工具失败或参数错误
- `waiting_user` 分支（如果 Agent 需要追问）
- 结构化输出和证据传递
- 与 `ReportGenerationService` 的集成

## 8. 当前架构限制与后续演进

当前已知限制：

- `ReportPlan` 是扁平章节列表，尚未支持真正的多级章节树。
- Planner 尚未生成具体数据任务、指标任务或章节依赖。
- 报告只渲染 Markdown，尚未保真生成 DOCX/PDF/HTML。
- 会话、模板、Artifact 都是内存存储。
- 尚无真实认证、用户隔离、审计和异步任务调度。
- 不支持跨数据源 JOIN。
- `langgraph` 已列入依赖，但尚未进入当前业务执行链路。

建议演进顺序：

1. 完善模板层级模型和树形 `ReportPlan`。
2. 抽取指标计算、聚合和图表规格工具。
3. 增加 Writer 路由和章节级数据依赖。
4. 增加真实的 DOCX/PDF/HTML Renderer。
5. 将内存仓储替换为数据库和对象存储。
6. 增加认证、权限、日志、监控和异步执行。
7. 在稳定后再评估是否使用 LangGraph 管理复杂 Agent 状态图。
