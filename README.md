# Report Agent

一个报告生成智能体系统：上传报告模板和数据，通过对话完成规划、修改与生成。

系统的设计前提是**对话是唯一的写入通道**。用户能做的一切——创建报告、修改计划、确认开工、补充缺失数据——都只有一个动作：发一条消息。前端不做业务判断，只按消息类型渲染服务端推来的结果。

```
上传模板 + 数据 + 一句指令
        ↓
   生成报告计划（章节树 + 每章指标）
        ↓
   ←─ 对话修改计划（去掉某章、改报告期间、加指标…）
        ↓
   说"确认，开始生成"
        ↓
   逐章取数 → 写作 → 前端立刻显示这一章
        │
        └─ 数据不够 → 停下来问缺什么 → 补充后写完本章 → 继续下一章
        ↓
   组装报告 + 生成 Markdown 产物
```

## 快速开始

后端（Python 3.11+，仓库使用 conda 环境 `promptenv`）：

```bash
cd backend
pip install -r requirements-dev.txt
cp .env.example .env   # 填入 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL_NAME
uvicorn app.main:app --reload --port 8000
```

前端（Node 18+）：

```bash
cd frontend
npm install
npm run dev            # http://localhost:5173，/api/v1 代理到 8000
```

示例文件在 `backend/example/`：`report_template.docx`（含表格）、`nested_report_template.md`（含三级标题）、`report_data.xlsx`。

> 同时运行两个后端进程会互相破坏会话状态——它们共享同一个持久化文件，启动时的状态对账会把对方正在跑的会话判死。确保只起一个。

## 仓库结构

```
backend/     FastAPI 服务：对话编排、报告生成、数据源与工具
frontend/    Vue 3 + Pinia 单页应用：对话工作台
ROADMAP.md   下一步计划与已知缺口
```

- 后端分层、模块职责、扩展方式：[backend/ARCHITECTURE.md](./backend/ARCHITECTURE.md)
- 后端接口与运行说明：[backend/README.md](./backend/README.md)
- 下一步计划：[ROADMAP.md](./ROADMAP.md)

## 前端

```
features/conversations/
  ChatPanel.vue            消息流 + 输入区（唯一输入口）
  messages/PlanCard.vue    报告计划（只读，带建议 chip）
  messages/ProgressCard.vue 章节进度四态，已完成章节可展开看正文
  messages/QuestionCard.vue 待补充的数据项（当前只展示）
  messages/ReportCard.vue  完成后的查看/下载入口
features/reports/          模板管理、报告只读全文页
stores/conversation.ts     服务端为唯一真相源，2s 轮询
```

页面路由：

| 路由 | 用途 |
|---|---|
| `/conversations/new`、`/conversations/:conversationId` | 对话工作台，报告的全部操作都在这里 |
| `/reports/:sessionId` | 报告只读全文页（分享/打印用） |
| `/reports/templates` | 模板管理 |
| `/datasets`、`/datasets/:datasetId` | 数据源管理 |
| `/analysis` | 确定性分析 |
| `/login`、`/capabilities` | 登录与能力目录 |

**前端没有任何编辑表单。**计划卡上的建议 chip 只是把一句话填进输入框，提交仍然走 `POST /conversations/{id}/messages`。

## 当前状态

已经跑通的：模板解析（含多级标题和表格）、计划生成与对话式修订、逐章取数与写作、缺数据时停下来提问、章节内容实时回显、Markdown 产物下载、会话持久化（重启不丢）。

尚未闭环的、已知的限制，见 [ROADMAP.md](./ROADMAP.md)。
