"""tribios LLM 客户端：OpenAI 兼容 chat/completions + 多 key 轮转 + 传输重试.

每 key 一个端点槽位：直调 `chat()` 按轮转选 key；Scheduler 调度时经 contextvar
`_KEY_SLOT` 把任务钉在获得额度的 key 上（semaphore 与真实用 key 不漂移）。
"""
from __future__ import annotations

import contextvars
import dataclasses
import itertools
import json
import re
import time
from typing import Any, Callable, Dict, List, Optional

import httpx

from hsr_nous.llm.config import LLMUseConfig

#: quota/余额不足类报文嗅探（号池 failover 判据——401/402/403 之外的文本类确定性死：
#: insufficient_balance / quota exceeded / insufficient_quota 族）
_QUOTA_HINT = re.compile(r"quota|balance|insufficient|额度|余额", re.IGNORECASE)

__all__ = ["LLMError", "LLMClient", "current_key_slot"]

#: LLM 请求超时（reasoning 模型慢，放宽）
LLM_TIMEOUT_S = 600.0
#: 传输层错误自动重试次数（ReadTimeout 等偶发慢响应——首次实例：机制标注并发双调用双端超时）
#: 批量场景指数退避（15s/45s/120s/120s ≈ 5 分钟窗口——休眠唤醒/上游限流的瞬断族，
#: 5s 平躺重试在分钟级 suspend 面前等于没有，1004/1005 并行试点实证）
TRANSPORT_RETRIES = 4

#: 当前任务被调度器分配的 key 槽位（None = 未被调度，chat 走轮转）
_KEY_SLOT: contextvars.ContextVar[Optional[int]] = contextvars.ContextVar(
    "tribios_key_slot", default=None)


def current_key_slot() -> Optional[int]:
    """读当前 context 的 key 槽位（测试/诊断用）."""
    return _KEY_SLOT.get()


class LLMError(RuntimeError):
    """LLM 调用错误（传输层重试后仍失败 / HTTP 非 200 / 空 content）."""


#: 传输层可注入点（测试 mock）：(url, payload, headers) -> httpx.Response 兼容对象
Transport = Callable[[str, Dict[str, Any], Dict[str, str]], httpx.Response]


def _default_transport(url: str, payload: Dict[str, Any], headers: Dict[str, str]) -> httpx.Response:
    return httpx.post(url, json=payload, headers=headers, timeout=LLM_TIMEOUT_S)


class LLMClient:
    """OpenAI 兼容 chat 客户端：多 key 端点槽位 + 轮转 + 传输重试."""

    def __init__(self, config: LLMUseConfig, *, transport: Optional[Transport] = None) -> None:
        self.config = config
        self._transport = transport or _default_transport
        self._rr = itertools.count()

    @property
    def key_count(self) -> int:
        return self.config.key_count

    def apply_endpoint(
        self,
        *,
        api_base: Optional[str] = None,
        model: Optional[str] = None,
        effort: Optional[str] = None,
    ) -> None:
        """endpoint 级热替换：重建 config 实例（frozen dataclass → replace），保留 key 列表.

        只影响**之后**的 chat 调用——在飞请求进入 chat 时已取走旧 config 快照
        （frozen 对象），在原端点跑完。属性赋值单次原子，多线程任务下安全。
        """
        self.config = dataclasses.replace(
            self.config,
            api_base=(api_base or self.config.api_base),
            model=(model or self.config.model),
            effort=(self.config.effort if effort is None else effort),
        )

    def _pick_key(self, key_index: Optional[int]) -> int:
        if key_index is not None:
            return key_index
        slot = _KEY_SLOT.get()
        if slot is not None:
            return slot
        return next(self._rr) % self.key_count

    def chat(
        self,
        messages: List[Dict[str, str]],
        *,
        effort: Optional[str] = None,
        max_tokens: Optional[int] = None,
        key_index: Optional[int] = None,
    ) -> str:
        """一次 chat/completions 调用。reasoning_effort 有值才带（参数 > 配置缺省）。

        传输层错误（超时/连接）自动重试 TRANSPORT_RETRIES 次——仍失败抛 LLMError；
        HTTP 非 200 与空 content 不重试（确定性错误，重试无用）。
        号池（config.pool 非空）：按优先级链逐槽试——auth/quota 类确定性死
        （401/402/403 或报文含 quota/balance/insufficient）换下一槽重发；
        429/5xx 传输族与 400/空 content 仍在槽内按旧径处理，不换槽。
        """
        cfg = self.config
        if key_index is not None and not 0 <= key_index < self.key_count:
            raise LLMError(f"key_index 越界：{key_index}（共 {self.key_count} 个 key）")
        chain: List[Tuple[str, str, Tuple[str, ...], Tuple[Tuple[str, str], ...]]] = (
            [(p.api_base, p.model, p.api_keys, p.extra_headers) for p in cfg.pool]
            if cfg.pool else
            [(cfg.api_base, cfg.model, cfg.api_keys, cfg.extra_headers)])
        last_err: Optional[Exception] = None
        for slot_i, (api_base, model, keys, extra_headers) in enumerate(chain):
            ki = self._pick_key(key_index) % len(keys)
            url = api_base.rstrip("/") + "/chat/completions"
            payload: Dict[str, Any] = {
                "model": model,
                "messages": messages,
                "max_tokens": max_tokens or cfg.max_tokens,
            }
            eff = cfg.effort if effort is None else effort
            if eff:
                payload["reasoning_effort"] = eff
            headers = {"Authorization": f"Bearer {keys[ki]}", **dict(extra_headers)}
            resp: Optional[httpx.Response] = None
            for attempt in range(TRANSPORT_RETRIES + 1):
                try:
                    resp = self._transport(url, payload, headers)
                except httpx.HTTPError as e:
                    if attempt == TRANSPORT_RETRIES:
                        raise LLMError(
                            f"LLM 传输层错误（重试 {TRANSPORT_RETRIES} 次后仍失败，"
                            f"槽 {slot_i + 1}/{len(chain)} key#{ki + 1}）："
                            f"{type(e).__name__}: {e}") from e
                    time.sleep(min(15 * (3 ** attempt), 120))   # 指数退避（分钟级 suspend 窗口）
                    continue
                if (resp.status_code >= 500 or resp.status_code == 429) \
                        and attempt < TRANSPORT_RETRIES:
                    # 5xx（502/503/529 上游瞬断族）+ 429（限流——20 宽批量压上游属常态）按传输层
                    # 同策略退避重试——一次瞬断不该 fail-fast 整 run（首个真跑 draft 撞 502）
                    time.sleep(min(15 * (3 ** attempt), 120))
                    continue
                break
            assert resp is not None
            if resp.status_code != 200:
                body = resp.text[:500]
                if resp.status_code in (401, 402, 403) or _QUOTA_HINT.search(body):
                    # auth/quota 类确定性死：本槽判死，按优先级链换下一槽（号池语义——
                    # 「先把首槽榨干再换备胎」）；末槽也死才抛
                    last_err = LLMError(
                        f"LLM HTTP {resp.status_code}（槽 {slot_i + 1}/{len(chain)} "
                        f"key#{ki + 1}，auth/quota 类——换槽）：{body}")
                    continue
                raise LLMError(f"LLM HTTP {resp.status_code}（key#{ki + 1}）：{body}")
            data = resp.json()
            choices = data.get("choices") or []
            content: Any = (choices[0].get("message") or {}).get("content") if choices else None
            if isinstance(content, list):  # 部分端点 content 为 parts 列表
                content = "".join(str(p.get("text", "")) for p in content if isinstance(p, dict))
            if not content:
                raise LLMError(
                    f"LLM 返回空 content（key#{ki + 1}）：{json.dumps(data, ensure_ascii=False)[:500]}")
            return str(content)
        raise LLMError(f"LLM 号池全槽判死（{len(chain)} 槽）：{last_err}")
