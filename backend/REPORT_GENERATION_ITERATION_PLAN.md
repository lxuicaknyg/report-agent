# 报告生成方案迭代计划

## 1. 目标与设计原则

本轮迭代的目标是将报告生成流程从“按模板章节直接执行”调整为：

```text
模板 + 数据源 + 用户指令
          ↓
轻量报告计划
          ↓
用户确认计划
          ↓
章节 ReAct 动态取数
          ↓
章节正文生成
          ↓
关键数字关联 Evidence
          ↓
报告组装
```

核心原则：

> 报告计划负责确认“生成什么”，章节 ReAct 负责解决“去哪里、怎么取”，Evidence 负责记录“数字来自哪里”。

本轮不要求 Planner 在计划阶段确定具体 Sheet、表、字段或 SQL。底层数据定位属于章节执行阶段的 ReAct 运行时职责。

## 2. 计划与执行的职责边界

### 2.1 报告计划负责的内容

计划只保留用户需要确认、且会影响报告结果的业务信息：

- 报告标题；
- 报告期间；
- 全局维度，例如机构、区域、季度；
- 章节结构；
- 每个章节涉及的指标。

示例：

```text
报告：2025年第四季度经营分析报告

全局信息：
- 机构：北京分行
- 期间：第四季度

章节一：贷款业务情况
- 指标：授信贷款余额、对公贷款余额

章节二：风险情况
- 指标：不良贷款率、逾期贷款余额
```

### 2.2 报告计划不负责的内容

以下内容不进入用户确认的报告计划：

- 具体 Sheet；
- 具体表名；
- 具体字段名；
- SQL；
- 工具调用顺序；
- 工具调用次数和数据读取上限；
- 只读、不编造、关键数字关联 Evidence 等系统规则。

这些内容由章节 Agent 的运行时逻辑和系统级提示词负责。

### 2.3 章节 ReAct 负责的内容

章节执行阶段通过 ReAct 完成：

1. 理解章节指标和全局维度；
2. 查看数据源、Sheet、表和字段；
3. 将业务指标映射到实际字段；
4. 按维度和期间读取数据；
5. 形成结构化事实和 Evidence；
6. 根据模板原文生成章节正文。

## 3. 目标数据模型

### 3.1 报告全局上下文

```python
class ReportGlobalContext(BaseModel):
    report_period: str | None = None
    dimensions: dict[str, str] = Field(default_factory=dict)
```

示例：

```json
{
  "report_period": "第四季度",
  "dimensions": {
    "机构": "北京分行"
  }
}
```

### 3.2 章节计划

```python
class ChapterPlan(BaseModel):
    section_id: str
    title: str
    metrics: list[str] = Field(default_factory=list)
```

章节计划只描述该章节需要生成的指标，不描述底层数据访问路径。

### 3.3 报告计划

```python
class ReportPlan(BaseModel):
    plan_id: str
    version: int = 1
    status: Literal[
        "generated",
        "awaiting_confirmation",
        "approved",
        "executing",
        "completed",
    ] = "generated"
    template_id: str
    title: str
    instruction: str
    global_context: ReportGlobalContext
    chapters: list[ChapterPlan]
    assembly_order: list[str]
```

其中 `status` 和 `version` 属于计划生命周期字段，用于支持用户确认和后续修改，不属于计划业务内容展示的一部分。

## 4. 分阶段迭代方案

## 4.1 迭代一：调整报告计划模型

涉及文件：

- `backend/app/core/reports.py`
- `backend/app/reporting/planner.py`

主要工作：

1. 新增 `ReportGlobalContext`；
2. 新增 `ChapterPlan`；
3. 将 `ReportPlan.sections` 从模板章节对象调整为章节计划对象；
4. 保留模板章节原文，并通过 `section_id` 关联模板章节；
5. 增加计划版本和状态字段。

目标结果：

```text
报告计划 = 报告标题 + 全局维度 + 章节结构 + 每章指标
```

## 4.2 迭代二：完善数据源元数据并接入 Planner

涉及文件：

- `backend/app/reporting/report_generation.py`
- `backend/app/reporting/planner.py`
- `backend/app/data/sources/excel.py`
- `backend/app/data/sources/sql.py`

流程调整为先构建数据源元数据，再生成报告计划：

```python
data_sources = await self._build_data_source_metadata(session.dataset_ids)

session.plan = await self.planner.create_plan(
    template=session.template_snapshot,
    data_sources=data_sources,
    instruction=session.instruction,
    title=session.title,
)
```

Planner 的输入包括：

- 模板章节和章节正文；
- 用户指令；
- Excel 每个 Sheet 的列信息；
- SQL 表的 Schema；
- 数据源名称和描述；
- 必要时的数据样例。

Planner 的输出只提取：

- 报告期间；
- 全局维度；
- 章节结构；
- 每章涉及的指标。

需要同步修复的数据源元数据问题：

- SQL 数据源的 `DatasetInfo` 补充 columns；
- Excel 为每个 Sheet 保存独立字段信息；
- 报告会话保存数据源元数据快照，保证当前报告使用的元数据稳定。

## 4.3 迭代三：增加计划确认流程

涉及文件：

- `backend/app/reporting/report_generation.py`
- `backend/app/api/routes/reports.py`
- `frontend/src/types/report.ts`
- `frontend/src/features/reports/ReportDetailPage.vue`

目标流程：

```text
创建报告会话
      ↓
生成报告计划
      ↓
状态：awaiting_confirmation
      ↓
用户确认或修改
      ↓
开始章节生成
```

新增接口：

```text
POST /api/v1/reports/{session_id}/plan/confirm
```

第一版支持用户确认或修改：

- 报告期间；
- 全局维度；
- 章节标题；
- 章节指标。

建议将报告创建请求中的 `auto_start` 默认值调整为 `false`，由计划确认接口触发执行。

计划确认后，应保存最终版本，并将计划状态更新为 `approved`。

## 4.4 迭代四：让章节 Agent 执行已确认计划

涉及文件：

- `backend/app/reporting/chapter_writer.py`
- `backend/app/reporting/chapter_writer_agent.py`
- `backend/app/reporting/report_generation.py`

章节 Agent 输入调整为：

```text
章节模板原文
+ 当前 ChapterPlan
+ 全局期间和维度
+ 数据源元数据
+ 用户补充回答
```

章节 Agent 不再从完整报告需求中重新规划章节，而是围绕已确认的指标执行动态取数。

ReAct 运行步骤：

```text
读取章节计划
    ↓
发现 Sheet / 表 / 字段
    ↓
将业务指标映射到实际字段
    ↓
调用 read_dataset / query_dataset
    ↓
形成事实和 Evidence
    ↓
生成章节正文
```

如有需要，可将以下工具纳入章节研究阶段：

- `list_sheets`；
- `profile_dataset`；
- `read_dataset`；
- `query_dataset`。

## 4.5 迭代五：实现关键数字与 Evidence 关联

涉及文件：

- `backend/app/core/reports.py`
- `backend/app/reporting/chapter_writer_agent.py`
- `backend/app/reporting/renderer.py`
- `frontend/src/types/report.ts`

新增结构化事实模型：

```python
class ReportFact(BaseModel):
    fact_id: str
    label: str
    value: Any
    unit: str | None = None
    dimensions: dict[str, str] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)
```

`ChapterDraft` 增加：

```python
facts: list[ReportFact] = Field(default_factory=list)
```

示例：

```json
{
  "fact_id": "fact_001",
  "label": "授信贷款余额",
  "value": 123,
  "unit": "元",
  "dimensions": {
    "机构": "北京分行",
    "期间": "第四季度"
  },
  "evidence_ids": ["evidence_001"]
}
```

第一版可以在 Markdown 正文中使用简单引用标记：

```text
北京分行第四季度授信贷款余额为123元[证据:evidence_001]。
```

后续可以将引用标记改造成前端可点击的证据链接。

## 5. 当前阶段明确不实现的内容

本轮暂不实现：

- 分组聚合；
- 同比、环比、占比等复杂计算；
- 自动生成复杂 SQL；
- 报告正文质量评分；
- 数字合理性校验；
- 图表生成；
- DOCX/PDF 导出；
- 在计划阶段强制确定字段、Sheet、表和 SQL。

## 6. 推荐实施顺序

```text
1. 调整 ReportPlan / ChapterPlan 数据模型
2. 完善 Excel / SQL 数据源元数据
3. Planner 接入 LLM，生成轻量报告计划
4. 增加计划确认接口和前端展示
5. Chapter Agent 接收并执行已确认计划
6. 实现 ReportFact 与 Evidence 关联
7. 补充测试并清理 analysis/reporting 重复代码
```

## 7. 验收标准

### 计划阶段

- Planner 能接收模板、用户指令和数据源元数据；
- 生成的计划包含报告期间、全局维度、章节结构和章节指标；
- 计划不要求包含具体 Sheet、表、字段或 SQL；
- 用户可以查看并确认计划；
- 用户可以修改章节指标和全局维度。

### 章节执行阶段

- Chapter Agent 能收到已确认的章节计划；
- Agent 能通过 ReAct 动态发现实际数据位置；
- Agent 能按照计划中的指标和维度读取数据；
- 章节正文中的关键数字能关联至少一个 Evidence；
- 数据缺失或无法定位时可以暂停并向用户提问。

### 报告生成阶段

- 所有章节完成后能够正常组装报告；
- 原有 Markdown 产物流程保持可用；
- 计划确认前不会直接执行章节生成；
- 计划和章节生成状态能够持久化并支持恢复。

