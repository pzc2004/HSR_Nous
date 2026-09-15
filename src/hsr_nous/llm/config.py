"""tribios 配置层：.env 手写解析 + 按用途读取 LLM 端点配置（零项目依赖，只标准库）.

变量规范（`HSR_NOUS_LLM_<用途>_*`，<用途> 如 ANNOTATOR/AGENTS/EVALUATOR）：

| 变量 | 说明 | 回落 |
|------|------|------|
| `HSR_NOUS_LLM_<USE>_API_KEY` | API key，**逗号分隔多 key**（每 key 独立并发额度） | `OPENAI_API_KEY`（单 key） |
| `HSR_NOUS_LLM_<USE>_MODEL` | 模型名 | `OPENAI_MODEL` |
| `HSR_NOUS_LLM_<USE>_API_BASE` | OpenAI 兼容端点 | `OPENAI_API_BASE` → `https://api.openai.com/v1` |
| `HSR_NOUS_LLM_<USE>_EFFORT` | reasoning_effort 透传（有值才带） | 无 |
| `HSR_NOUS_LLM_<USE>_CONCURRENCY` | 每 key 并发上限 | 无，默认 4 |
| `HSR_NOUS_LLM_<USE>_MAX_TOKENS` | max_tokens 缺省（reasoning 吃预算，≥16k） | 无，默认 32768 |

另含热更新层 `LiveConfig`（见类 docstring）：运行中经 `live_config.json` 改
api_base/model/effort/concurrency，不重启生效于之后的派发；api_key 只从 env 读。
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple

__all__ = [
    "LLMConfigError", "LLMUseConfig", "LiveConfig", "LiveOverrides",
    "load_dotenv", "load_use_config", "ENV_PREFIX",
]

ENV_PREFIX = "HSR_NOUS_LLM_"
#: 每 key 并发上限缺省
DEFAULT_CONCURRENCY = 4
#: max_tokens 缺省（reasoning 吃预算，≥16k 给足）
DEFAULT_MAX_TOKENS = 32768

#: 热更配置文件（LiveConfig 物化落点——仓库树外，防整体拷贝外泄；
#: api_key 永不进文件）。单一事实源在 llm 层（ops/annotator 与 api/cli 同引——
#: 边界表 api/ops 均放行 llm，互引会越界）
DEFAULT_LIVE_CONFIG_PATH = Path.home() / ".config" / "hsr_nous" / "annotator_live_config.json"
#: API_BASE 缺省
DEFAULT_API_BASE = "https://api.openai.com/v1"


class LLMConfigError(RuntimeError):
    """LLM 配置错误（缺 key/model、非法并发值等）."""


def load_dotenv(path: Path) -> Optional[Path]:
    """手写 .env 解析（不依赖 python-dotenv 包）：`KEY=VALUE`，# 注释，值可带引号.

    不覆盖已存在的环境变量（外部环境优先）；行内 ` #` 注释会剥掉（引号内不剥）。
    文件不存在返回 None。
    """
    path = Path(path)
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        key, _, value = s.partition("=")
        key, value = key.strip(), value.strip()
        if not key:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        os.environ.setdefault(key, value)
    return path


@dataclass(frozen=True)
class LLMEndpointProfile:
    """号池槽位（端点画像）：`HSR_NOUS_LLM_<USE>_POOL` JSON 数组元素."""

    api_base: str
    model: str
    api_keys: Tuple[str, ...]
    extra_headers: Tuple[Tuple[str, str], ...] = ()


@dataclass(frozen=True)
class LLMUseConfig:
    """单个用途的 LLM 端点配置（多 key = 多端点槽位，每槽位独立并发额度）."""

    use: str
    api_keys: Tuple[str, ...]
    model: str
    api_base: str
    effort: str = ""
    concurrency: int = DEFAULT_CONCURRENCY   # 每 key 并发上限
    max_tokens: int = DEFAULT_MAX_TOKENS
    # 额外请求头（OpenAI 兼容端点的厂商扩展头族）：
    # env `HSR_NOUS_LLM_<USE>_EXTRA_HEADERS`（JSON 对象字符串），client.chat 逐请求并入
    extra_headers: Tuple[Tuple[str, str], ...] = ()
    # 号池（优先级链，env `HSR_NOUS_LLM_<USE>_POOL` JSON 数组，按序 failover——
    # 空 = 单端点旧径）：auth/quota 类确定性死（401/403/余额不足）才换下一槽；
    # 429/5xx 传输族仍在槽内退避重试，不换槽
    pool: Tuple[LLMEndpointProfile, ...] = ()

    @property
    def key_count(self) -> int:
        return len(self.api_keys)


def load_use_config(use: str, env: Optional[Mapping[str, str]] = None) -> LLMUseConfig:
    """读 `HSR_NOUS_LLM_<USE>_*`（use 大小写不敏感，内部统一大写）；缺省回落 OPENAI_*.

    API_KEY 支持逗号分隔多 key（空白裁剪、空段丢弃）。EFFORT/CONCURRENCY/MAX_TOKENS 无回落。
    """
    env = os.environ if env is None else env
    prefix = f"{ENV_PREFIX}{use.upper()}_"

    def _get(name: str, default: str = "") -> str:
        return (env.get(prefix + name) or env.get(f"OPENAI_{name}") or default).strip()

    keys_raw = env.get(prefix + "API_KEY") or env.get("OPENAI_API_KEY") or ""
    keys = tuple(k.strip() for k in keys_raw.split(",") if k.strip())
    if not keys:
        raise LLMConfigError(f"缺 {prefix}API_KEY（或回落 OPENAI_API_KEY）——配在 repo 根 .env")
    model = _get("MODEL")
    if not model:
        raise LLMConfigError(f"缺 {prefix}MODEL（或回落 OPENAI_MODEL）")
    try:
        concurrency = int(env.get(prefix + "CONCURRENCY") or DEFAULT_CONCURRENCY)
    except ValueError as e:
        raise LLMConfigError(f"{prefix}CONCURRENCY 须为整数：{env.get(prefix + 'CONCURRENCY')!r}") from e
    if concurrency < 1:
        raise LLMConfigError(f"{prefix}CONCURRENCY 须 ≥1：{concurrency}")
    try:
        max_tokens = int(env.get(prefix + "MAX_TOKENS") or DEFAULT_MAX_TOKENS)
    except ValueError as e:
        raise LLMConfigError(f"{prefix}MAX_TOKENS 须为整数：{env.get(prefix + 'MAX_TOKENS')!r}") from e
    extra_headers: Tuple[Tuple[str, str], ...] = ()
    raw_extra = (env.get(prefix + "EXTRA_HEADERS") or "").strip()
    if raw_extra:
        try:
            parsed = json.loads(raw_extra)
        except json.JSONDecodeError as e:
            raise LLMConfigError(f"{prefix}EXTRA_HEADERS 须为 JSON 对象字符串：{e}") from e
        if not isinstance(parsed, dict) or not all(
                isinstance(k, str) and isinstance(v, str) for k, v in parsed.items()):
            raise LLMConfigError(f"{prefix}EXTRA_HEADERS 须为 {{\"头名\": \"值\"}} 对象")
        extra_headers = tuple(sorted(parsed.items()))
    pool: Tuple[LLMEndpointProfile, ...] = ()
    raw_pool = (env.get(prefix + "POOL") or "").strip()
    if raw_pool:
        try:
            plist = json.loads(raw_pool)
        except json.JSONDecodeError as e:
            raise LLMConfigError(f"{prefix}POOL 须为 JSON 数组：{e}") from e
        if not isinstance(plist, list) or not plist:
            raise LLMConfigError(f"{prefix}POOL 须为非空 JSON 数组（元素含 api_base/api_key/model）")
        profs = []
        for j, ent in enumerate(plist):
            if not isinstance(ent, dict):
                raise LLMConfigError(f"{prefix}POOL[{j}] 须为对象")
            p_base = str(ent.get("api_base") or "").strip()
            p_model = str(ent.get("model") or "").strip()
            p_keys = tuple(k.strip() for k in str(ent.get("api_key") or "").split(",") if k.strip())
            if not p_base or not p_model or not p_keys:
                raise LLMConfigError(
                    f"{prefix}POOL[{j}] 缺 api_base/model/api_key（三者必填）")
            p_headers: Tuple[Tuple[str, str], ...] = ()
            raw_ph = ent.get("extra_headers")
            if raw_ph is not None:
                if not isinstance(raw_ph, dict) or not all(
                        isinstance(k, str) and isinstance(v, str) for k, v in raw_ph.items()):
                    raise LLMConfigError(f"{prefix}POOL[{j}].extra_headers 须为 {{\"头名\": \"值\"}} 对象")
                p_headers = tuple(sorted(raw_ph.items()))
            profs.append(LLMEndpointProfile(api_base=p_base, model=p_model,
                                            api_keys=p_keys, extra_headers=p_headers))
        pool = tuple(profs)
    return LLMUseConfig(
        use=use.upper(),
        api_keys=keys,
        model=model,
        api_base=_get("API_BASE", DEFAULT_API_BASE),
        effort=(env.get(prefix + "EFFORT") or "").strip(),
        concurrency=concurrency,
        max_tokens=max_tokens,
        extra_headers=extra_headers,
        pool=pool,
    )


# ---------------------------------------------------------------------------
# 热更新配置（live config）：运行中改端点/模型/effort/并发，不重启生效于之后的派发
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LiveOverrides:
    """live_config.json 的一个快照（校验后的生效值）."""

    api_base: str
    model: str
    effort: str
    concurrency: int      # 每 key 并发上限


class LiveConfig:
    """热更新配置文件监视器：mtime 变化才 reload；非法内容沿用旧值（`last_error` 可见）.

    文件格式（如 `data/annotator/live_config.json`）::

        {"api_base": "https://...", "model": "...", "effort": "max", "concurrency": 8}

    - 首次不存在则以 env 配置**物化**（`materialize`），供用户照着改；
    - `api_key` 只从 env 读、永不进此文件——文件里出现该键与其他未知键一律忽略
      （parse 只读四个已知键）；
    - 缺键 = 保持当前值（允许只改一个字段）；
    - `concurrency` 调大 = 之后的派发立即加槽，调小 = 在飞自然回落（不杀在飞）；
    - `api_base`/`model`/`effort` 只影响**之后派发**的任务（在飞在原端点跑完）。
    """

    def __init__(self, path: Path, current: LiveOverrides) -> None:
        self.path = Path(path)
        self._current = current
        self._mtime_ns: Optional[int] = None
        self.last_error = ""

    @classmethod
    def materialize(cls, path: Path, use_cfg: LLMUseConfig) -> "LiveConfig":
        """打开（必要时创建）热更文件：不存在则以 env 配置物化；已存在则立即装载."""
        lc = cls(Path(path), LiveOverrides(
            api_base=use_cfg.api_base, model=use_cfg.model,
            effort=use_cfg.effort, concurrency=use_cfg.concurrency))
        if not lc.path.exists():
            lc.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = lc.path.with_name(lc.path.name + ".tmp")
            tmp.write_text(json.dumps({
                "api_base": use_cfg.api_base,
                "model": use_cfg.model,
                "effort": use_cfg.effort,
                "concurrency": use_cfg.concurrency,
            }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
            os.replace(tmp, lc.path)  # 原子写（与 run_state 同手法）
            lc._sync_mtime()
        else:
            lc.poll()  # 已存在 → 立即装载（非法内容沿用 env 值，last_error 可见）
        return lc

    @property
    def current(self) -> LiveOverrides:
        return self._current

    def poll(self) -> Optional[LiveOverrides]:
        """mtime 变了才 reload。返回新快照（有变化）；无变化 / 文件缺席 / 非法 → None."""
        try:
            mtime = self.path.stat().st_mtime_ns
        except OSError:
            return None  # 文件被删：沿用旧值，不动 mtime 书签（重现即按新 mtime 再载）
        if mtime == self._mtime_ns:
            return None
        self._mtime_ns = mtime
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            ov = self._parse(data)
        except (json.JSONDecodeError, OSError, LLMConfigError) as e:
            self.last_error = f"{type(e).__name__}: {e}"
            return None
        self.last_error = ""
        if ov == self._current:
            return None
        self._current = ov
        return ov

    def _sync_mtime(self) -> None:
        try:
            self._mtime_ns = self.path.stat().st_mtime_ns
        except OSError:
            self._mtime_ns = None

    def _parse(self, data: Any) -> LiveOverrides:
        if not isinstance(data, dict):
            raise LLMConfigError(
                f"{self.path} 须为 JSON mapping（api_base/model/effort/concurrency），"
                f"实得 {type(data).__name__}")
        cur = self._current
        api_base = str(data.get("api_base", cur.api_base)).strip() or cur.api_base
        model = str(data.get("model", cur.model)).strip() or cur.model
        effort = str(data.get("effort", cur.effort)).strip()
        raw_conc: Any = data.get("concurrency", cur.concurrency)
        try:
            concurrency = int(raw_conc)
        except (TypeError, ValueError) as e:
            raise LLMConfigError(f"{self.path} concurrency 须为整数：{raw_conc!r}") from e
        if concurrency < 1:
            raise LLMConfigError(f"{self.path} concurrency 须 ≥1：{concurrency}")
        return LiveOverrides(api_base=api_base, model=model,
                             effort=effort, concurrency=concurrency)
