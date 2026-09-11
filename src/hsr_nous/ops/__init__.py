"""生产运行时与批量流水线层（ops）——DAG 执行器 + 生产 DAG（打标 annotator 首租）.

与产品层（sim/api/agents）分家：产品层管"用户怎么用"，本层管"生产资料怎么造"。
边界：允许 `llm, adapters, sim, pipeline, sim_schema`；禁 `raw_schema, agents, api`。
`ops/dag/` 通用运行时零项目依赖（节点走注册注入），生产 DAG 节点才 import 各层。
"""
