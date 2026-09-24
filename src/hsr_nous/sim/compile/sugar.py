"""糖 desugar 展开器：表面糖 → 核心原语（VM 只见展开产物）.

v1 首糖 `trigger_limit`（04_modifier §4.12①，B24 宏链路的第一个宏/dogfood）：
挂接点 = **hook 顶层键**（修饰该 hook 的触发频率）；展开 = 计数器四联件——

1. 计数资源注册（`res_<rid>` 命名空间恒有定义的前提，编译期登记进 owner 资源表）
2. 充满 hook ×N（`on_battle_start` + 窗口重置事件；`set_resource` 置满——初始即满额度）
3. 门控并入该 hook 的 condition（`res_<rid> > 0` AND 原条件）
4. 消耗效果追加到该 hook effects 末尾（`gain_resource` amount=-1——负值消耗复用现有
   原语，**不立** `consume_resource` 新 effect_type）

纪律（22_syntax_reference.md §22.13）：宏体纯数据变换（禁计算）；展开深度上限 + 禁循环
引用；先展开后过同一编译期校验；VM 只见原语。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

MAX_EXPANSION_DEPTH = 8

#: trigger_limit v1 窗口档 → 重置事件（须为总线契约事件——on_after_action 属 modifier
#: 生命周期触发器命名空间（04_modifier §4.8），不在 §23.4 契约，v1 不收）
_WINDOW_RESET_EVENT = {
    "per_turn": "on_turn_start",      # 每回合最多 N 次（默认档）
    "per_wave": "on_wave_start",      # 每波次 N 次
    "per_action": "on_action",        # 每次行动重置（v1 口径：行动=on_action 事件）
    "once_per_battle": None,          # 全场 N 次（不重置）
    "per_battle": None,               # 全场 N 次（参数化同上）
}
#: v1 明确不收的窗口档（写了大声炸指路——实例到了再上，不许静默近似）
_UNSUPPORTED_WINDOWS = ("per_attack", "per_instance", "per_target", "cooldown_turns")


class SugarError(ValueError):
    """糖展开错误（未知档/循环引用/深度超限/契约外事件）."""


def desugar_trigger_limit(spec: Dict[str, Any], *, owner_hook_desc: str,
                          contract: frozenset, depth: int = 0) -> Dict[str, Any]:
    """trigger_limit 糖 → 计数器四联件（资源注册 + 充满 hooks + 门控 + 消耗效果）.

    spec 形状：{<窗口档>: N?, count?: N, reset_on?: "<契约事件>"}——窗口档见
    `_WINDOW_RESET_EVENT`（once_per_battle/per_battle 无重置事件）；count 缺省 1
    （cooldown_turns 档 count=档值）；reset_on 覆盖窗口默认重置点（须为契约事件，
    `cast:*` 等 modifier 生命周期触发器形态 v1 不收）。
    """
    if depth > MAX_EXPANSION_DEPTH:
        raise SugarError(f"trigger_limit 展开深度超限（{depth} > {MAX_EXPANSION_DEPTH}）")
    if not isinstance(spec, dict) or not spec:
        raise SugarError(f"{owner_hook_desc}：trigger_limit 须为非空 dict，实得 {spec!r}")

    count = 1
    window = "per_turn"
    reset_on: Optional[str] = None
    for key, val in spec.items():
        if key == "count":
            count = int(val)
        elif key == "reset_on":
            reset_on = str(val)
        elif key in _UNSUPPORTED_WINDOWS:
            raise SugarError(
                f"{owner_hook_desc}：trigger_limit 窗口档 {key!r} v1 未收"
                f"（已收：{sorted(_WINDOW_RESET_EVENT)}；per_attack 与 per_action 的语义差未钉，"
                f"实例到了再上——04_modifier §4.12）")
        elif key in _WINDOW_RESET_EVENT:
            window = key
            # 窗口档数值=次数（per_turn: 3 每回合 3 次；once_per_battle: true → 1——bool 即 int 1）
            count = 1 if val is None else int(val)
        else:
            raise SugarError(
                f"{owner_hook_desc}：trigger_limit 未知窗口档/键 {key!r}"
                f"（合法：{sorted(_WINDOW_RESET_EVENT) + ['count', 'reset_on']}）")
    if count < 1:
        raise SugarError(f"{owner_hook_desc}：trigger_limit count 须 ≥1，实得 {count}")

    reset_event = reset_on or _WINDOW_RESET_EVENT[window]
    if reset_on is not None and reset_on not in contract:
        raise SugarError(
            f"{owner_hook_desc}：trigger_limit reset_on {reset_on!r} 不是总线契约事件"
            f"（v1 仅收 §23.4 契约事件；cast:* 生命周期触发器形态未收）")

    import hashlib
    rid = f"_tl_{hashlib.md5(owner_hook_desc.encode()).hexdigest()[:10]}"
    return {
        "resource_id": rid,
        "count": count,
        # 充满 hooks：开局充满 + 窗口重置点充满（initial=满额度，开局即可触发）
        "charge_hooks": ([{"event": "on_battle_start",
                           "effects": [{"effect_type": "set_resource",
                                        "resource_id": rid, "amount": count}]}]
                         + ([] if reset_event is None else [{
                             "event": reset_event,
                             "effects": [{"effect_type": "set_resource",
                                          "resource_id": rid, "amount": count}]}])),
        "gate": f"res_{rid} > 0",
        "consume_effect": {"effect_type": "gain_resource", "resource_id": rid, "amount": -1},
        "window": window,
    }


# 糖注册表：新增糖在此登记（闭合关键字集，未登记 = validator error；B24 远期方向=
# 宏定义进数据（世界规则文件/角色 YAML），糖攒到 5-6 个有实证再泛化）
_SUGARS = {
    "trigger_limit": desugar_trigger_limit,
}


def desugar(name: str, spec: Dict[str, Any], *, depth: int = 0, **kwargs) -> Dict[str, Any]:
    """按名展开糖；未登记的糖名 = SugarError."""
    fn = _SUGARS.get(name)
    if fn is None:
        raise SugarError(f"未登记的糖：{name}（闭合关键字集，新增须决策卡）")
    return fn(spec, depth=depth, **kwargs)


def list_sugars() -> List[str]:
    return sorted(_SUGARS)
