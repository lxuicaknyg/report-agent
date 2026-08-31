# Report Agent Backend

这是一个“报告生成应用”的后端原型。系统的核心目标不是搭建通用 Agent 平台，而是在报告生成业务流程中嵌入模板解析、章节规划、章节写作和文档组装能力。

详细的分层架构、文件职责、运行时依赖关系和新增 Agent 的开发规范，请参阅 [ARCHITECTURE.md](./ARCHITECTURE.md)。

当前后端同时保留两条能力链路：

1. 数据集管理与确定性分析：上传 Excel、注册 SQL 数据源、查看 Schema、执行只读查询。
2. 报告生成外围流程：上传报告模板、创建报告生成会话、解析模板、生成章节计划、执行章节 Writer、组装报告并生成 Markdown 产物。

当前默认装配的是 `ChapterWriterAgent`，它通过 OpenAI-compatible LLM 完成章节研究和写作；`StubChapterWriter` 仅用于外围流程测试。指标计算、图表生成和更复杂的跨数据源分析仍在后续规划中。

## 当前实时进度

截至当前版本，后端已经完成“报告生成外围流程”和“Excel 文件取数基础能力”的搭建：

- Excel 常规取数已经切换为 `openpyxl` 只读模式，支持 Sheet、Schema、分页预览、字段选择和精确筛选。
- 报告模板可以上传并解析为章节结构，当前支持 DOCX、Markdown 和 TXT。
- 已建立 `ReportGenerationSession`，支持报告会话创建、章节结果保存、用户问题保存和恢复接口。
- 已建立 `ReportPlan`、`ChapterWriterInput`、`ChapterWriterResult` 等章节智能体外围契约。
- 当前章节生成默认使用 `ChapterWriterAgent`：先进行有界的只读取数循环，再执行无工具写作调用；`StubChapterWriter` 仅用于测试。
- `openai` 适配器已经进入运行时链路；`langgraph`、`markitdown` 虽已列入依赖，但目前没有进入报告生成主流程。
- 报告当前只能生成 Markdown 产物，DOCX、PDF 和 HTML 仍属于后续工作。
- 会话、模板和产物当前使用内存存储，服务重启后会丢失。
- 当前测试结果为 `9 passed`（在 `promptenv` 环境中执行）。

## 一、总体架构

```text
客户端 / 前端
      │
      ▼
FastAPI API
      │
      ├── 数据集 API
      │       └── DataCatalog
      │               ├── ExcelDataSource
      │               └── SqlDataSource
      │
      ├── 分析 API
      │       └── AnalysisAgent
      │               └── ToolRegistry
      │                       ├── ListDatasetsTool
      │                       ├── ProfileDatasetTool
      │                       └── QueryDatasetTool
      │
      └── 报告 API
              └── ReportGenerationService
                      ├── ReportGenerationSession
                      ├── ReportTemplateParser
                      ├── ReportPlanner
                      ├── ChapterWriter
                      ├── ReportAssembler
                      ├── ReportRenderer
                      └── ArtifactStore
```

报告生成主流程：

```text
上传报告模板 + 选择多个数据源 + 用户指令
                    │
                    ▼
        创建 ReportGenerationSession
                    │
                    ▼
             解析 ReportTemplate
                    │
                    ▼
               生成 ReportPlan
                    │
                    ▼
             按章节执行 ChapterWriter
                    │
          ┌─────────┴─────────┐
          │                   │
      章节完成            需要用户补充信息
          │                   │
          │             WAITING_USER
          │                   │
          └─────── 用户回答后恢复 ───────┘
                    │
                    ▼
              ReportAssembler
                    │
                    ▼
           Markdown（当前）
           HTML / DOCX / PDF（规划）
```

## 二、目录结构

```text
backend/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── dependencies.py
│   │
│   ├── api/
│   │   └── routes/
│   │       ├── health.py
│   │       ├── datasets.py
│   │       ├── analysis.py
│   │       └── reports.py
│   │
│   ├── core/
│   │   ├── models.py
│   │   ├── reports.py
│   │   ├── ports.py
│   │   ├── tooling.py
│   │   └── agent.py
│   │
│   ├── data/
│   │   ├── catalog.py
│   │   └── sources/
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
│   │   └── dataset_tools.py
│   │
│   └── infrastructure/
│       ├── llm.py
│       ├── users.py
│       ├── report_repositories.py
│       └── artifact_store.py
│
├── tests/
├── requirements.txt
├── requirements-dev.txt
└── README.md
```

## 三、各目录和模块职责

### `app/main.py`

应用组装入口：创建 FastAPI 应用，注册健康检查、数据集、分析和报告路由，并配置默认 `/api/v1` 前缀。

### `app/config.py`

集中管理应用名称、运行环境、数据目录、产物目录、数据库连接和 LLM 配置。

### `app/dependencies.py`

负责依赖注入和组件装配。目前通过 `lru_cache` 提供进程级单例，包括 `DataCatalog`、`ToolRegistry`、`AnalysisAgent`、`ReportGenerationService`、内存仓储和 ArtifactStore。后续替换真实 Writer、数据库仓储或对象存储时，主要修改这里的装配关系。

## 四、API 层：`app/api`

API 层只负责 HTTP 请求、参数校验、状态码和响应，不直接实现数据分析或报告业务逻辑。

### `routes/health.py`

```text
GET /health
```

### `routes/datasets.py`

```text
GET  /api/v1/datasets
POST /api/v1/datasets/excel
POST /api/v1/datasets/sql
GET  /api/v1/datasets/{dataset_id}/sheets
GET  /api/v1/datasets/{dataset_id}/schema
POST /api/v1/datasets/{dataset_id}/preview
```

负责数据集注册和 Schema 查询。

### `routes/analysis.py`

```text
POST /api/v1/analysis/profile
POST /api/v1/analysis/query
```

当前 `/analysis/query` 要求调用方提供 `dataset_id` 和只读 SQL，不负责自然语言转 SQL。

### `routes/reports.py`

报告生成接口：

```text
POST /api/v1/reports/templates
GET  /api/v1/reports/templates/{template_id}

POST /api/v1/reports
GET  /api/v1/reports/{session_id}
POST /api/v1/reports/{session_id}/answers
POST /api/v1/reports/{session_id}/resume
GET  /api/v1/reports/{session_id}/artifacts/{artifact_id}
```

同时保留旧版兼容接口：

```text
POST /api/v1/reports/draft
```

## 五、领域层：`app/core`

### `core/models.py`

定义用户上下文、数据集、Schema、Profile、查询结果、Evidence、分析请求和旧版 `ReportDraft` 等通用领域模型。

### `core/reports.py`

定义报告生成流程模型：

- `ReportGenerationSession`：一次报告生成过程的状态和中间结果。
- `ReportGenerationStatus`：创建、运行、等待用户、完成、失败等最小状态。
- `ReportTemplate`、`ReportTemplateSection`：解析后的模板和章节结构。
- `ReportPlan`：报告章节顺序和组装计划。
- `DataSourceMetadata`：传递给章节 Writer 的数据源元数据。
- `ChapterWriterInput`、`ChapterWriterResult`：章节智能体的输入和输出契约。
- `ChapterDraft`：单个章节的生成结果。
- `AssembledReport`：组装后的结构化报告。
- `ReportArtifact`：最终产物的元数据。
- `UserQuestion`：记录章节 Writer 在数据不足或需要确认时提出的问题。

这一层定义“报告是什么”和“生成过程处于什么状态”，不负责文件解析、LLM 调用或文档渲染。

### `core/ports.py`

定义可替换的基础接口：`DataSource`、`LlmService`、`ArtifactStore` 和 `UserResolver`。

### `core/tooling.py`

定义 `Tool`、`ToolContext`、`ToolResult` 和 `ToolRegistry`，负责工具注册、Schema 暴露、权限检查和调用。

### `core/agent.py`

提供通用工具调用循环 `ToolCallingAgent`。它是底层可复用能力，不是报告系统的总控入口。

## 六、数据层：`app/data`

### `data/catalog.py`

`DataCatalog` 维护：

```text
dataset_id → RegisteredDataSource
```

上层通过 Catalog 获取数据源，不直接依赖 Excel 或 SQL 的具体实现。

### `data/sources/base.py`

定义 `RegisteredDataSource` 接口，统一要求数据源提供数据集列表、Schema、Profile 和查询能力。

### `data/sources/excel.py`

当前 Excel 实现：

- 常规读取使用 `openpyxl.load_workbook(..., read_only=True, data_only=True)`。
- 支持多 Sheet 列表、按 Sheet 获取 Schema、分页读取行数据。
- 支持指定列和简单精确筛选。
- 提供 Profile 能力。
- 旧的 SQL 查询接口仍保留为兼容能力，仅在显式调用时懒加载 DuckDB/SQLite。

Excel 的主取数路径已经是 `openpyxl → 结构化行数据`，不需要先把 Excel 转换为 DuckDB。后续报告 Writer 通过 DataCatalog 读取数据，不应直接依赖 openpyxl。

### `data/sources/sql.py`

使用 SQLAlchemy 访问外部 SQL 数据库，提供表结构、样例数据和只读 `SELECT` / `WITH` 查询。当前 Excel 和外部 SQL 数据源分别执行查询，不支持跨数据源 JOIN。

## 七、报告生成层：`app/reporting`

这是报告业务层，不是通用 Agent 平台。

### `reporting/report_generation.py`

`ReportGenerationService` 是报告生成流程的应用服务，负责：

1. 保存和解析模板。
2. 创建 `ReportGenerationSession`。
3. 调用 `ReportPlanner` 生成章节计划。
4. 按计划调用章节 Writer。
5. 处理等待用户、恢复、失败和完成状态。
6. 调用 `ReportAssembler` 组装报告。
7. 调用 Renderer 生成文件并保存 Artifact 元数据。

它是报告业务流程的总编排器，但不负责实现章节内部的取数和写作细节。

### `reporting/session.py`

定义 `ReportSessionRepository`、`ReportTemplateRepository` 等仓储接口。当前具体实现位于 `infrastructure/report_repositories.py`。

### `reporting/template_parser.py`

将用户上传的模板转换为 `ReportTemplate`。当前支持 `.docx`、`.md`、`.markdown` 和 `.txt`，主要解析标题、Heading 层级、章节顺序和示例正文。

### `reporting/planner.py`

将 `ReportTemplate` 转换为 `ReportPlan`，保留章节原文和章节顺序。章节 Writer 根据章节原文和数据源元数据自行决定取数动作，不在 Planner 层预先拆分复杂执行任务。

### `reporting/chapter_writer.py`

定义章节 Writer 接口：

```python
class ChapterWriter:
    async def write(input, session) -> ChapterWriterResult:
        ...
```

`input` 包含当前章节模板原文、模板结构、报告大纲、数据源元数据、用户指令和历史回答。当前 `ChapterWriterAgent` 已实现两阶段流程：先通过 `read_dataset`/`query_dataset` 执行有界的多轮只读取数 ReAct，工具报错时反馈给模型修正参数；取数完成后，再将章节模板和所有成功读取的数据交给无工具的写作调用，生成 `ChapterDraft`。`StubChapterWriter` 仍保留用于外围流程测试。

### `reporting/assembler.py`

`ReportAssembler` 按计划顺序将多个 `ChapterDraft` 组装成 `AssembledReport`。它只负责结构组装，不重新取数、不调用 LLM。

### `reporting/renderer.py`

负责将结构化报告转换成具体格式。当前实现 `MarkdownReportRenderer`，后续可增加 HTML、DOCX 和 PDF Renderer。

### `reporting/reports.py`

保留旧版 `ReportService`，用于兼容 `/reports/draft`。新报告生成流程使用 `ReportGenerationService`。

### `analysis/agent.py`

`AnalysisAgent` 当前负责调用数据工具完成 Profile 和确定性 SQL 查询。后续可以作为 WriterAgent 的数据分析辅助能力，但不负责整份报告的生命周期。

## 八、工具层：`app/tools`

`tools/dataset_tools.py` 当前提供：

- `ListDatasetsTool`
- `ListSheetsTool`
- `ProfileDatasetTool`
- `QueryDatasetTool`
- `ReadDatasetTool`

工具通过 `DataCatalog` 访问数据，并统一返回 `ToolResult` 和 `Evidence`。当前已经包含 Sheet 列表和行数据读取工具，后续可增加指标计算、同比环比和图表规格等工具。

## 九、基础设施层：`app/infrastructure`

### `llm.py`

OpenAI-compatible LLM 适配器，支持 DashScope 等兼容 OpenAI Chat Completions 的服务。配置从 `backend/.env` 的 `LLM_BASE_URL`、`LLM_API_KEY` 和 `LLM_MODEL_NAME` 读取，并负责把内部工具 schema 转换为供应商 API 所需的 function tools 格式。

### `users.py`

当前提供 `LocalUserResolver`。真实认证、JWT、OAuth 或用户系统接入后放在这一层。

### `report_repositories.py`

当前提供内存版会话仓储和模板仓储。服务重启后数据会丢失，后续可替换为数据库仓储。

### `artifact_store.py`

当前提供内存版 `InMemoryArtifactStore`，后续可替换为本地文件、S3 或其他对象存储。

## 十、当前状态和边界

### 已实现

- FastAPI 应用、健康检查和 OpenAPI 文档。
- Excel 和外部 SQL 数据源注册。
- 数据集 Schema、Profile 和只读查询。
- Excel Sheet 列表、Schema、分页预览和条件取数。
- 工具注册、调用和基础权限检查。
- 报告模板上传和基础结构解析。
- 报告生成会话和状态流转。
- 报告计划、章节 Writer 输入/输出模型。
- `ChapterWriterAgent` 的有界只读取数和章节写作流程。
- Stub 章节 Writer（仅用于外围流程测试）。
- 报告组装和 Markdown 产物生成。
- 报告产物下载接口。
- 旧版 Profile 报告接口兼容。

### 当前未实现或仍是占位

- 真实模型的高级路由、流式输出和供应商专属参数。
- 自然语言到数据查询/指标计算的完整链路。
- 指标计算、聚合和图表生成。
- DOCX 模板样式的完整克隆和 PDF 渲染。
- DOCX/PDF/HTML 完整渲染。
- 报告模板样式、表格、图表的保真复制。
- 会话、模板和产物的持久化。
- 登录认证、用户级数据隔离和审计。
- 完整的跨数据源分析。

## 十一、运行方式

在 `backend` 目录执行：

```powershell
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 8000
```

健康检查：

```text
GET http://127.0.0.1:8000/health
```

接口文档：

```text
http://127.0.0.1:8000/docs
```

运行测试：

```powershell
python -m pytest -q
```

依赖说明：运行时依赖现在以 `requirements.txt` 为主，开发环境使用 `requirements-dev.txt`。依赖版本已与 `report/backend/requirements.txt` 的公共运行环境对齐，并保留了本项目当前使用的 pandas、openpyxl、DuckDB、SQLAlchemy 等依赖。开发时直接使用共享的 `promptenv` Conda 环境即可。项目不再使用 `pyproject.toml` 或额外的 pytest 配置文件。

Docker 或离线内网部署时，可以先准备本地 wheel 目录，再执行：

```powershell
pip install --no-index --find-links=./wheels -r requirements.txt
```

## 十二、后续推荐迭代顺序

1. 完成真实 LLM 配置、供应商兼容性和端到端链路验证，并保持 `ChapterWriter` 外围接口不变。
2. 增加指标计算、聚合和图表数据生成能力。
3. 增强缺失数据追问、会话暂停和恢复策略。
4. 增加 DOCX 模板样式克隆和 PDF Renderer。
5. 增加 DOCX 模板保真组装和 DOCX/PDF Renderer。
6. 将内存仓储替换为数据库，将 ArtifactStore 替换为文件或对象存储。
7. 最后补齐认证、权限、日志、监控和异步任务能力。
