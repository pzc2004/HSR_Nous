"""LLM 节点运行器协议与 tribios 接线（ops/annotator/llm）.

`LLMRunner`：system+prompt → text。`make_tribios_runner` 走 `llm/`（tribios）：
`HSR_NOUS_LLM_ANNOTATOR_*`（或回落 OPENAI_*）读 key/模型/端点 + live_config.json 热更
（api_base/model/effort/concurrency 运行中可改，**key 只从 env 读**）——换 API = 改
`.env`（或热更文件），零代码改动。`bash scripts/annotator.sh ping` 即验证。
`FakeRunner`：罐头回复——测试/dogfood 管线打通用。
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[4]
#: 热更配置（与 mechanism_annotator 同路径——一处控制两线）
DEFAULT_LIVE_CONFIG_PATH = Path.home() / ".config" / "hsr_nous" / "annotator_live_config.json"


class LLMRunner:  # noqa: D401 —— 协议
    """LLM 调用协议：__call__(system, prompt, max_tokens) -> str。"""

    def __call__(self, *, system: str, prompt: str, max_tokens: int = 8000) -> str:
        raise NotImplementedError("LLMRunner 未接线")


class FakeRunner(LLMRunner):
    """罐头 LLM：[(关键字, 回复), ...] 按序命中；每次调用留痕（attempt 可审计）。"""

    def __init__(self, canned: List[Tuple[str, str]]) -> None:
        self._canned = canned
        self.calls: List[Dict[str, str]] = []

    def __call__(self, *, system: str, prompt: str, max_tokens: int = 8000) -> str:
        self.calls.append({"system": system, "prompt": prompt})
        for key, reply in self._canned:
            if key in prompt:
                return reply
        raise AssertionError(f"FakeRunner 无罐头命中（prompt 前 80 字：{prompt[:80]!r}）")


class _TribiosRunner(LLMRunner):
    """tribios 实现：LLMClient.chat + LiveConfig 热更轮询（每次派发前 poll）。"""

    def __init__(self, client: "object", live: "object") -> None:
        self._client = client
        self._live = live

    def __call__(self, *, system: str, prompt: str, max_tokens: int = 8000) -> str:
        ov = self._live.poll()
        if ov is not None:  # 热更生效于之后的派发（在飞在原端点跑完）
            self._client.apply_endpoint(api_base=ov.api_base, model=ov.model, effort=ov.effort)
        return self._client.chat(
            [{"role": "system", "content": system},
             {"role": "user", "content": prompt}],
            max_tokens=max_tokens)


def make_tribios_runner(
    *,
    use: str = "ANNOTATOR",
    live_path: Optional[Path] = None,
    transport: Optional[Callable] = None,
    env: Optional[dict] = None,
) -> LLMRunner:
    """装配 tribios 运行器：.env（repo 根）→ `HSR_NOUS_LLM_<USE>_*` → LLMClient + LiveConfig。

    transport/env：测试注入点（mock httpx 层/显式配置映射，不接真 API、不读真 .env）。
    配置错误（缺 key/model）抛 `llm.LLMConfigError`——`annotator.sh ping` 直接可见。
    """
    from hsr_nous.llm import LLMClient, LiveConfig
    from hsr_nous.llm.config import load_dotenv, load_use_config

    if env is None:
        load_dotenv(ROOT / ".env")
    use_cfg = load_use_config(use, env=env)
    live = LiveConfig.materialize(live_path or DEFAULT_LIVE_CONFIG_PATH, use_cfg)
    return _TribiosRunner(LLMClient(use_cfg, transport=transport), live)


def ping(*, use: str = "ANNOTATOR", live_path: Optional[Path] = None,
         transport: Optional[Callable] = None, env: Optional[dict] = None) -> str:
    """API 连通性自检（换 API 后第一件事）：一次最小 chat，回显端点/模型（永不回显 key）。"""
    from hsr_nous.llm import LLMClient, LiveConfig
    from hsr_nous.llm.config import load_dotenv, load_use_config

    if env is None:
        load_dotenv(ROOT / ".env")
    use_cfg = load_use_config(use, env=env)
    live = LiveConfig.materialize(live_path or DEFAULT_LIVE_CONFIG_PATH, use_cfg)
    ov = live.current
    client = LLMClient(use_cfg, transport=transport)
    out = client.chat(
        [{"role": "system", "content": "你是连通性自检。"},
         {"role": "user", "content": "只回两个字：正常"}],
        max_tokens=512)   # reasoning 模型先吃推理预算——16 会被 length 截成空 content（实测）
    return (f"ping OK：api_base={ov.api_base} model={ov.model} "
            f"keys={use_cfg.key_count} concurrency={ov.concurrency} → 回文 {out.strip()[:20]!r}")
