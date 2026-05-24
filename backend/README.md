# Backend README

## 项目定位

本后端是一个面向制造业数据集的轻量化 NL2SQL Agent 服务，用于将用户的自然语言问题转换为可校验、可执行、可追踪的 SQL 查询。系统并不是直接把问题丢给 LLM 生成 SQL，而是围绕难度路由、schema 检索、字段链接、JOIN 检索、业务规则、few-shot、失败案例、模板复用、SQL 校验、执行反馈和 trace 观测构建完整管线，以提升生成结果的可控性和可诊断性。

## 核心能力

- 按问题复杂度进行难度路由，为不同查询选择差异化的上下文构建和生成策略。
- 基于 schema 检索、字段语义检索和字段链接，将自然语言实体映射到表、字段和候选条件。
- 结合 JOIN 检索与关系映射，为跨表查询提供可复用的连接路径提示。
- 引入业务规则、SQL pattern、few-shot 示例和失败案例，约束生成行为并减少重复错误。
- 支持已验证模板复用，在高置信场景下优先使用稳定 SQL 模板。
- 通过 SQLGuard、语义校验、执行反馈和修复流程，对生成 SQL 进行安全性与可执行性检查。
- 记录 trace summary/debug 信息，支持链路观测、问题定位和后续质量分析。

后端是 NL2SQL Agent 的核心服务，负责把自然语言问题转换成 SQL，执行查询，并返回结果、解释、洞察和 trace 信息。

## 目录结构

```text
backend/
├── app/
│   ├── core/
│   │   ├── config.py            # 环境变量和运行配置
│   │   ├── database.py          # SQLAlchemy 连接和 schema inspection
│   │   ├── init_db.py           # 从 DDL + CSV 初始化 SQLite
│   │   └── tracing.py           # 请求链路追踪
│   ├── prompts/
│   │   └── nl2sql_prompt.py     # SQL 生成、计划、修复 prompt
│   ├── schemas/
│   │   └── chat.py              # Pydantic 请求/响应模型
│   └── services/
│       ├── routing/             # 问题路由、难度判断、上下文编排
│       ├── retrieval/           # schema、字段、JOIN、规则、模式检索
│       ├── knowledge/           # 知识库、few-shot、失败案例、模板
│       ├── llm/                 # LLM、Embedding、Reranker、Supervisor
│       ├── planning/            # 查询计划
│       ├── execution/           # SQL 校验和执行
│       ├── quality/             # 结果体检、诊断、反思、洞察
│       └── tracing/             # trace 汇总
├── data/
│   ├── knowledge/               # 业务规则、SQL 模式、few-shot、失败案例
│   ├── nl2sqlpublic/public/     # 数据集、DDL、CSV、表字典
│   └── nl2sql.db                # 本地 SQLite 数据库
├── tests/
├── requirements.txt
└── run.py
```

## 启动配置

在 `backend/.env` 中配置：

```text
SILICONFLOW_API_KEY=你的 API Key
SILICONFLOW_BASE_URL=https://api.siliconflow.cn/v1
LLM_MODEL_NAME=Qwen/Qwen3-Coder-30B-A3B-Instruct
EMBEDDING_MODEL_NAME=BAAI/bge-m3
RERANKER_MODEL_NAME=BAAI/bge-reranker-v2-m3
APP_HOST=0.0.0.0
APP_PORT=8001
DEBUG=false
```

启动：

```powershell
backend\.venv\Scripts\python.exe backend\run.py
```

健康检查：

```text
http://localhost:8001/health
```

## 数据初始化

启动时会调用 `app/core/init_db.py`：

1. 检查 SQLite 中是否已有完整数据表。
2. 如果未初始化，则读取 `data/nl2sqlpublic/public/schema_annotated.sql` 创建表。
3. 遍历 `data/nl2sqlpublic/public/csv/`，把每个 CSV 导入同名表。
4. 生成或更新 `data/nl2sql.db`。

当前 CSV 初始化只支持 SQLite。

## `/api/chat` 主流程

### 请求接入与 trace 初始化

输入为 `ChatRequest.question` 以及请求侧的基础参数。服务创建 `TraceRecorder`，为本次调用分配 trace 标识，并记录原始问题、入口时间和后续阶段需要共享的上下文容器。

输出是带有 trace 上下文的内部请求状态。该阶段的作用是把一次普通 API 调用转换为可观测、可回放的处理链路。

### Schema 读取与问题路由

系统调用 `get_table_schema()` 读取数据库表结构、字段信息和必要的样例行，并将用户问题交给 `DifficultyRouter.classify()` 判断难度等级。输入是用户问题和当前数据库 schema，输出是结构化 schema 快照、难度等级以及对应的 pipeline 配置。

该阶段决定后续使用轻量生成、增强检索还是高难度规划流程。路由结果会影响上下文规模、是否生成 Query Plan、是否启用更强的校验与修复策略。

### 上下文构建

`ContextBuilder.build_context_for_profile()` 根据路由配置构建紧凑上下文，整合 schema、字段候选、字段链接、JOIN hint、业务规则和 SQL pattern。系统还会从 `ExampleStore` 和 `FailureCaseStore` 中检索相关 few-shot 示例与失败案例，作为正向参考和反向约束。

输出是面向 SQL 生成的上下文包，包括候选表字段、连接路径、规则约束、写法模式和示例片段。该阶段的作用是减少 LLM 的自由猜测空间，把生成过程限制在当前数据集和业务规则内。

### 高难度问题的 Query Plan 生成

对于 L3/L4 等高难度问题，系统会根据配置调用规划能力生成 Query Plan。输入是用户问题、路由结果和已构建的上下文，输出是包含查询目标、关键字段、过滤条件、聚合逻辑和 JOIN 思路的计划。

Query Plan 用于在生成 SQL 前显式拆解问题结构。它为后续模板匹配、LLM 生成和语义校验提供中间表达，降低复杂查询一次性生成失败的概率。

### 模板复用决策

`ValidatedTemplateService` 会基于问题相似度、上下文匹配度和模板验证状态判断是否可复用已有 SQL 模板。输入是当前问题、Query Plan 或上下文特征，输出是可复用模板、模板参数或放弃复用的决策。

该阶段优先利用已验证的稳定查询形式。只有在模板匹配不足或参数化条件不满足时，流程才继续进入完整的 LLM SQL 生成。

### LLM SQL 生成

当没有合适模板可复用时，`NL2SQLService` 会将问题、上下文、few-shot、失败案例和可选 Query Plan 组装为 prompt，并调用 LLM 生成 SQL。输入是完整生成上下文，输出是候选 SQL 以及必要的生成说明。

该阶段负责把前面检索和规划得到的结构化信息落到具体 SQL。LLM 的角色是受约束的 SQL 生成器，而不是独立决定表、字段和业务规则的唯一来源。

### SQL 安全校验和语义校验

候选 SQL 会先经过 `SQLGuard` 做安全性和合规性检查，再由 `SQLSemanticVerifier` 校验字段、表、业务规则和查询语义。输入是候选 SQL、schema、业务规则和 trace 上下文，输出是校验通过结果或需要修复的错误信息。

该阶段用于阻断危险 SQL、无效字段、错误 JOIN 和违反业务约束的查询。如果校验失败且具备修复条件，系统会调用 `NL2SQLService.repair_sql()` 生成修复后的 SQL 并再次校验。

### 执行 SQL

校验通过后，`QueryService` 在目标数据库上执行 SQL，并限制返回行数与执行边界。输入是最终 SQL，输出是查询结果、列信息、执行耗时和可能的数据库错误。

该阶段将生成结果转化为真实数据响应。执行结果会写入 trace，并作为后续结果体检、空结果诊断和洞察生成的输入。

### 结果体检、空结果诊断、反思修复

`ResultSanityChecker` 会检查结果是否存在明显异常，例如结果为空、数量异常或字段与问题不匹配。对于空结果或执行异常，`EmptyResultDiagnoser` 和 `ReflectionService` 会结合 trace 判断原因，并决定是否触发修复或重试。

输入是 SQL、执行结果、错误信息和完整 trace，输出是诊断结论、重试决策或修复后的结果。该阶段用于把执行反馈纳入闭环，避免仅返回不可解释的空结果或底层错误。

### 洞察生成与 trace 保存

`InsightService` 根据最终结果生成简短业务洞察，并与 SQL、结果、错误、诊断信息一起组装为 `ChatResponse`。输入是最终查询结果和处理链路信息，输出是面向调用方的响应体。

流程结束前会保存 trace summary/debug，记录关键阶段的输入输出、决策和异常信息。该阶段为接口响应、问题排查和后续质量评估提供统一依据。

## 关键服务说明

- `routing/DifficultyRouter`: 根据问题特征输出 `L1/L2/L3/L4` 和对应 pipeline 配置。
- `routing/ContextBuilder`: 组织 schema、字段、JOIN、规则、SQL pattern、字段链接等上下文。
- `routing/QueryRouter`: 将问题路由到业务域。
- `retrieval/SchemaRetriever`: 挑选和裁剪相关表结构。
- `retrieval/FieldSemanticRetriever`: 根据字段语义选择候选字段。
- `retrieval/ColumnLinker`: 把用户问题中的业务词映射到具体字段。
- `retrieval/JoinRetriever`: 基于 `relationship_map.csv` 返回 JOIN hint。
- `retrieval/RuleRetriever`: 从 `business_rules.json` 检索业务规则。
- `retrieval/PatternRetriever`: 从 `sql_patterns.json` 检索 SQL 写法模式。
- `knowledge/ExampleStore`: 从 `few_shots.json` 检索正向示例。
- `knowledge/FailureCaseStore`: 保存和检索历史失败案例，作为 negative examples。
- `knowledge/ValidatedTemplateService`: 对高相似、已验证模板进行复用决策。
- `llm/NL2SQLService`: 调用 LLM 生成 SQL、生成 plan、修复 SQL。
- `execution/SQLGuard`: 拦截危险或不合规 SQL。
- `execution/SQLSemanticVerifier`: 校验业务语义规则。
- `execution/QueryService`: 执行 SQL，最多返回 200 行。
- `quality/ResultSanityChecker`: 检查结果是否出现明显异常。
- `quality/ReflectionService`: 根据 trace 判断是否需要重试。
- `quality/InsightService`: 根据结果生成简短业务洞察。

## API

```text
GET  /health
GET  /api/schema
GET  /api/context?question=...
GET  /api/knowledge?question=...
GET  /api/traces/{trace_id}/summary
GET  /api/traces/{trace_id}/debug
POST /api/chat
POST /api/validate-sql
```

`POST /api/chat` 请求：

```json
{
  "question": "查询最近 10 个订单"
}
```

响应：

```json
{
  "trace_id": "trace id",
  "question": "查询最近 10 个订单",
  "sql": "SELECT ...",
  "generated_sql": "SELECT ...",
  "result": [],
  "columns": [],
  "execution_time": 0.0,
  "error": null,
  "explanation": "生成过程说明",
  "insights": []
}
```

## 测试

```powershell
cd backend
python -m pytest
```

也可以单独做语法检查：

```powershell
python -m compileall app
```
