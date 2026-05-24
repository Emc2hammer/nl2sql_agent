# NL2SQL Agent for Manufacturing Dataset

这是一个面向制造业数据集的自然语言转 SQL 项目。用户在前端输入业务问题，后端会根据问题自动选择相关表、字段、JOIN 路径、业务规则和 few-shot 示例，生成可执行 SQL，并返回查询结果、生成说明和轻量洞察。

## 技术栈

后端：
- Python
- FastAPI
- SQLite
- SQLAlchemy
- LangChain `ChatOpenAI`
- SiliconFlow OpenAI-compatible API

前端：
- React 18
- TypeScript
- Vite

默认模型：
- LLM: `Qwen/Qwen3-Coder-30B-A3B-Instruct`
- Embedding: `BAAI/bge-m3`
- Reranker: `BAAI/bge-reranker-v2-m3`

## 项目结构

```text
.
├── backend/
│   ├── app/
│   │   ├── core/                # 配置、数据库连接、数据初始化
│   │   ├── prompts/             # NL2SQL Prompt 模板
│   │   ├── schemas/             # API 请求/响应模型
│   │   └── services/            # NL2SQL 核心服务，按职责分组
│   ├── data/
│   │   ├── knowledge/           # 业务规则、SQL 模式、few-shot、失败案例
│   │   ├── nl2sqlpublic/public/ # 制造业公开数据集、DDL、CSV、字典
│   │   └── nl2sql.db            # 启动后生成的 SQLite 数据库
│   └── run.py
├── frontend/
│   ├── src/App.tsx              # AskData 主界面
│   └── src/api.ts               # 前端 API Client
├── docker-compose.yml
└── README.md
```

## 数据来源

数据集位于：

```text
backend/data/nl2sqlpublic/public/
```

关键文件：
- `schema_annotated.sql`: 数据库 DDL
- `csv/`: 各业务表 CSV 数据
- `table_dictionary.csv`: 表和字段说明
- `relationship_map.csv`: 表关系和 JOIN 线索
- `question_bank.json`: 问题样例、难度和 SQL 特征
- `schema_overview.md`: 数据集概览

后端启动时会检查本地 SQLite。如果目标表不存在，会根据 `schema_annotated.sql` 创建表，并把 `csv/` 下的数据导入到：

```text
backend/data/nl2sql.db
```

## 核心流程

```text
用户输入问题
  ↓
前端 POST /api/chat
  ↓
后端读取 SQLite Schema
  ↓
DifficultyRouter 判断 L1/L2/L3/L4 难度
  ↓
ContextBuilder 构建紧凑上下文
  ↓
检索表、字段、JOIN、业务规则、SQL Pattern、few-shot、历史失败案例
  ↓
复杂问题生成 Query Plan
  ↓
优先尝试复用 validated template
  ↓
未命中模板时调用 LLM 生成 SQL
  ↓
SQLGuard 做安全校验
  ↓
SQLSemanticVerifier 做业务语义校验
  ↓
必要时调用 SQL Repair
  ↓
QueryService 执行 SQL
  ↓
ResultSanityChecker 检查结果合理性
  ↓
ReflectionService 对错误或异常结果进行反思和重试
  ↓
InsightService 生成结果洞察
  ↓
返回 SQL、结果、解释、insights、trace_id
```

## 难度分层

后端会把问题分为四档，并为每档选择不同的执行策略：

```text
L1 SIMPLE
  简单查表或过滤，少量 schema 和 few-shot，不启用 planner/repair。

L2 MEDIUM
  涉及 JOIN、聚合、业务规则，启用基础 repair。

L3 HARD
  涉及复杂聚合、排名、派生指标、时间比较，启用 query planner 和 repair。

L4 EXPERT
  涉及多事实表、多跳 JOIN、复杂业务规则、TopN by group 等，使用更完整的上下文和修复链路。
```

## 服务分组

```text
backend/app/services/
├── routing/      # 问题路由、难度判断、上下文编排
├── retrieval/    # schema、字段、JOIN、规则、SQL pattern 检索
├── knowledge/    # 知识文件、few-shot、失败案例、验证模板
├── llm/          # LLM、Embedding、Reranker、Supervisor 调用
├── planning/     # 复杂问题的查询计划
├── execution/    # SQL 安全校验、语义校验、执行
├── quality/      # 结果体检、空结果诊断、反思重试、洞察生成
└── tracing/      # trace 汇总
```

重要服务：

- `routing/difficulty_router.py`: 问题难度分类，并决定 pipeline 参数。
- `routing/context_builder.py`: 汇总路由、字段检索、表检索、JOIN、规则、模式和字段链接。
- `routing/query_router.py`: 判断问题所属业务域，例如 sales、inventory、quality、production。
- `retrieval/schema_retriever.py`: 根据问题挑选相关表和字段。
- `retrieval/field_semantic_retriever.py`: 从字段语义角度补充候选字段。
- `retrieval/column_linker.py`: 把业务表达映射到具体字段。
- `retrieval/join_retriever.py`: 根据表关系找 JOIN 路径。
- `retrieval/rule_retriever.py`: 检索业务规则。
- `retrieval/pattern_retriever.py`: 检索 SQL 写法模式。
- `knowledge/example_store.py`: 检索 few-shot 示例。
- `knowledge/validated_template_service.py`: 复用已验证 SQL 模板。
- `llm/nl2sql_service.py`: 调用 LLM 生成 plan、SQL 或修复 SQL。
- `execution/sql_guard.py`: 阻止危险 SQL。
- `execution/sql_semantic_verifier.py`: 检查 SQL 是否满足业务语义。
- `execution/query_service.py`: 执行 SQL 并返回结果。
- `quality/result_sanity.py`: 检查结果异常。
- `quality/reflection_service.py`: 对失败结果进行反思和重试。
- `quality/insight_service.py`: 生成轻量数据洞察。
- `tracing/trace_summary_service.py`: 汇总 trace 信息。

## API

默认后端地址：

```text
http://localhost:8001
```

接口：

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

## 启动方式

后端配置文件：

```text
backend/.env
```

示例配置：

```text
SILICONFLOW_API_KEY=你的 API Key
SILICONFLOW_BASE_URL=https://api.siliconflow.cn/v1
LLM_MODEL_NAME=Qwen/Qwen3-Coder-30B-A3B-Instruct
EMBEDDING_MODEL_NAME=BAAI/bge-m3
RERANKER_MODEL_NAME=BAAI/bge-reranker-v2-m3
APP_PORT=8001
DEBUG=false
```

启动后端：

```powershell
backend\.venv\Scripts\python.exe backend\run.py
```

或：

```powershell
python backend\run.py
```

启动前端：

```powershell
cd frontend
npm install
npm run dev
```

前端默认地址：

```text
http://localhost:5173
```

## 调试建议

查看后端健康状态：

```powershell
curl http://localhost:8001/health
```

查看某个问题会检索到哪些上下文：

```powershell
curl "http://localhost:8001/api/context?question=查询最近10个订单"
```

查看知识源和 few-shot 命中情况：

```powershell
curl "http://localhost:8001/api/knowledge?question=查询最近10个订单"
```

查看 trace summary：

```powershell
curl "http://localhost:8001/api/traces/{trace_id}/summary"
```

## 测试

后端测试：

```powershell
cd backend
python -m pytest
```

前端构建：

```powershell
cd frontend
npm run build
```
