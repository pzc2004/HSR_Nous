"""tribios / 缇里西庇俄丝——项目级 LLM 统一接入层.

代号名册：**tribios / 缇里西庇俄丝**——「碎作千片」、分赴各地传递神谕：
多 key 管理（每 key 独立并发额度）+ 流式任务调度（完成一个补一个）+ 限次重试与人工队列。
owner 特批：半神名跨层级用于本非引擎内模块（引擎内部组件仍走泰坦级名册，见 sim/README.md）。

模块边界：`llm/` 零项目依赖（只标准库 + httpx）——不 import 任何项目模块；
`adapters`/`agents`/`api` 允许 import `llm`（AGENTS.md 模块边界表登记）。

导出：`LLMClient`（多 key 轮转 chat 客户端）、`Scheduler`（流式任务调度）、
`LLMUseConfig` / `load_use_config`（按用途读 HSR_NOUS_LLM_<USE>_* 配置）、
`LiveConfig` / `LiveOverrides`（live_config.json 热更新：端点/模型/effort/并发）、
`load_dotenv`（手写 .env 解析）、`LLMError` / `LLMConfigError`。
"""
from __future__ import annotations

from hsr_nous.llm.client import LLMClient, LLMError
from hsr_nous.llm.config import (
    LLMConfigError, LLMEndpointProfile, LLMUseConfig, LiveConfig, LiveOverrides,
    load_dotenv, load_use_config,
)
from hsr_nous.llm.scheduler import DeadTask, Scheduler

__all__ = [
    "LLMClient", "LLMError", "Scheduler", "DeadTask",
    "LLMUseConfig", "LLMConfigError", "load_use_config", "load_dotenv",
    "LLMEndpointProfile", "LiveConfig", "LiveOverrides",
]
