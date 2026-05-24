# Services Layout

`services` 按 NL2SQL 管线职责分组：

```text
services/
├── routing/      # 问题路由、难度判断、上下文编排
├── retrieval/    # schema、字段、JOIN、规则、SQL pattern 检索
├── knowledge/    # 知识文件、few-shot、失败案例、验证模板
├── llm/          # LLM、Embedding、Reranker、Supervisor 调用
├── planning/     # 复杂问题的查询计划
├── execution/    # SQL 安全校验、语义校验、执行
├── quality/      # 结果体检、空结果诊断、反思重试、洞察生成
└── tracing/      # trace 汇总
```

放置规则：

- 新增“如何选上下文”的逻辑，优先放到 `routing/` 或 `retrieval/`。
- 新增“知识源、样例、模板、记忆”的逻辑，放到 `knowledge/`。
- 新增模型调用封装，放到 `llm/`。
- 新增 SQL 执行前后的硬校验，放到 `execution/`。
- 新增结果质量、修复判断、洞察输出，放到 `quality/`。
- 新增 trace 展示或摘要逻辑，放到 `tracing/`。
