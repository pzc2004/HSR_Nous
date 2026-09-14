"""build.yaml 编译器：配装配置 → 队伍 Actor + CompiledPolicy.

v0.3 支持两种角色定义：
- `inline:` 内联（测试/独立场景用）：直接给基础面板与技能
- `character_template: "<id>"`：引用 data/sim_templates 模板（adapters 后置，暂抛 NotImplementedError）

遗器词条计算：主词条满级 + 副词条按 roll 数 × 高档值（数值表 = rulebook relic_affixes，
pipeline 词条数据的镜像，06_relics §6 口径）。
"""
from __future__ import annotations

import re
import types
import warnings
from pathlib import Path
from typing import Any, Container, Dict, List, Optional, Sequence, Union

import yaml

from hsr_nous.sim.compile.compiled import CompiledPolicy, CompiledPolicyRule
from hsr_nous.sim.compile.expr_compiler import ExprCompiler
from hsr_nous.sim_schema.action import ELEMENTS, Action
from hsr_nous.sim_schema.actor import Actor, StatBlock
from hsr_nous.sim_schema.effect_types import (
    EFFECT_EXPR_SLOTS,
    ENGINE_EFFECT_TYPES,
    HOOK_TARGET_SELECTORS,
    POLICY_SELECTOR_DICT_TYPES,
    POLICY_TARGET_SELECTORS,
)
# 模板根唯一事实源在 sim_schema/templates.py（此处 re-export：adapters 侧受边界闸
# 限制只能 import sim_schema，本模块与 stage_compiler 历史引用路径保持不变）
from hsr_nous.sim_schema.templates import DEFAULT_TEMPLATE_ROOTS

# DSL 词条 id → StatBlock 字段（纯词表映射，零数值；与 06_relics §6 词表一致）。
# 数值唯一来源 = rulebook.yaml relic_affixes 段（pipeline StarRailRes 词条数据的镜像，
# 逐值一致由 tests/test_doc_lint.py 遗器词条镜像闸重算保证）；词表外词条编译期炸
# （与 _check_keys 同哲学：静默吞=幻觉温床，报错带词条名）。
# 注意无 effect_res 主词条（5★ 数据不存在——旧硬编码表的 effect_res 主词条系编造值已清除）。
_AFFIX_FIELD: Dict[str, str] = {
    "hp": "hp", "atk": "atk", "def_": "def_",
    "hp_pct": "hp_pct", "atk_pct": "atk_pct", "def_pct": "def_pct",
    "spd": "spd", "crit_rate": "crit_rate", "crit_dmg": "crit_dmg",
    "effect_hit": "effect_hit", "effect_res": "effect_res",
    "break_effect": "break_effect", "energy_regen": "energy_regen",
    "heal_bonus": "heal_bonus",
    "physical_dmg": "dmg_physical", "fire_dmg": "dmg_fire",
    "ice_dmg": "dmg_ice", "thunder_dmg": "dmg_thunder",
    "wind_dmg": "dmg_wind", "quantum_dmg": "dmg_quantum",
    "imaginary_dmg": "dmg_imaginary",
}

# ---------------------------------------------------------------------------
# 编译期校验闸（错拼/未知键/非法枚举一律编译期炸——"LLM 写模板靠报错自愈"，静默吞=幻觉温床）
# ---------------------------------------------------------------------------

#: 糖键（04_modifier §4.12-4.14 设计预览，desugar 未接线——见 sugar.py 顶部注释）：
#: 写在 DSL 里必须炸得"认得"——报错指路"未落地"，而不是按普通未知键处理
_SUGAR_KEYS_UNWIRED = frozenset({
    "every_n", "accumulate", "tally",                         # §4.12 计数器宏族（trigger_limit 已接线）
    "one_shot", "window",                                     # §4.13 攻击窗宏族
    "active_when", "scale_by", "scale_stat",                  # §4.14 门控/缩放
})

#: build.yaml team member 合法键（模板引用与 inline 共用；模板自带键不进本表——member 是作者面）
_MEMBER_KEYS = frozenset({
    "character_template", "actor_id", "name", "actor_type", "level", "eidolon",
    "skill_levels", "light_cone_template", "light_cone", "relics", "base_stats", "actions",
    "custom_resources",  # inline 资源声明（与模板 custom_resources 同一闸——16 §16.2）
    "inline",  # 内联标记（inline: True，与 character_template: "inline" 同义——测试/独立场景）
    "path",  # 命途覆盖/声明（count_team 编成计数口径——inline member 与模板引用均可显式给）
    "groups",  # 分组标签覆盖/声明（faction:xxx——in_group/count_team(group=) 口径；模板同名键可被 member 覆盖）
    "element",  # 元素声明/覆盖（动态元素族 element_of 取数源——模板/inline member 双通道，词表闸）
    "version",  # 加强双轨选边（enhanced〔默认〕/legacy——3.4 加强角色前后两版机制互不兼容，
                # 编译期选模板文件 <ref>_*_legacy.yaml；只对 character_template 引用有意义）
})

#: member.version 词表（_load_character_template 消费——词表闸文本即指路，勿改单边）
_TEMPLATE_VERSIONS = frozenset({"enhanced", "legacy"})

#: base_stats 合法键（StatBlock 字段 + 三个 dict 槽；拼错如 atkk 在此炸）
_BASE_STATS_KEYS = frozenset({
    "hp", "atk", "def", "spd", "crit_rate", "crit_dmg", "break_effect",
    "effect_hit", "effect_res", "max_energy", "energy_regen", "taunt",
    "dmg_bonus", "weakness", "resistance", "toughness_bars",
})

#: action 合法键（= Action 字段的 YAML 映射；消费点见 _compile_inline_character）
_ACTION_KEYS = frozenset({
    "action_id", "name", "action_type", "target_type", "damage_type",
    "scaling", "energy_cost", "energy_gain", "energy_grant",
    "skill_point_cost", "skill_point_gain", "toughness_dmg", "toughness_scope",
    "scaling_blast", "toughness_dmg_blast", "instances", "segment_confirm",
    "instance_variants", "segment_choice",
    "resource_gain", "ult_cost_resource", "ult_cost_amount", "ult_quick_cast",
    "ult_consume_amount",
    "split", "act_now_targets", "apply_modifiers", "assist_cost_resource",
    "instances_from_resource", "instances_per_point", "instances_cap",
    "consume_all_resource", "cleanse_self", "level_key", "prefer_target",
    "available_if", "manual_trigger",
})

#: 段级变体合法键（B35②；消费点：_compile_action_list 变体校验 + 引擎 _execute_action 覆写）
_VARIANT_KEYS = frozenset({"target_type", "scaling", "damage_type", "toughness_dmg"})

#: 元素词表（内部小写；toughness_scope 列表元素/damage_type 同词表）
#: ——唯一事实源已上提 sim_schema/action.py ELEMENTS（hook 动态元素求值校验同读），本地别名沿用
_ELEMENTS = ELEMENTS

#: `$self.<attr>` 字段存在性白名单（13_validator §13.3：错拼如 `$self.atkk` 编译期炸而非运行期炸）——
#: _HookSelfNS 槽/property + StatBlock 字段 + 有效面板派生键；`dmg_<element>` 前缀与
#: owner 绑定参数（variable_bindings 产物，编译期已知）另行放行
_SELF_NS_FIELDS = frozenset({
    "hp", "energy", "max_energy", "state", "actor_id", "max_hp",
    "atk", "def_", "spd", "crit_rate", "crit_dmg", "break_effect", "effect_hit",
    "effect_res", "max_toughness", "toughness_bars", "energy_regen", "taunt",
    "def_pen", "res_pen", "vulnerability", "heal_bonus", "shield_bonus",
    "break_efficiency_boost", "weakness_break_efficiency_boost",
    "dmg_bonus", "weakness", "resistance", "summoner_id", "summon_flags",
    "taunt_eff",
})
_SELF_NS_RE = re.compile(r"\$self\.(\w+)")

#: modifier dict 声明合法键（消费点：modifiers._modifier_from_spec / _attach_shield /
#: _execute_action 的 target 读取；词表按引擎实现冻结）
_MODIFIER_SPEC_KEYS = frozenset({
    "modifier_id", "name", "modifier_type", "duration", "stacks", "max_stack",
    "stack_mode", "stacks_value", "singleton_group", "dispellable", "stat_effects",
    "scaling_effects", "override_effects", "hit_condition",
    "enable_if", "stat_exprs",  # 条件光环（04_modifier §4.16 已落地原语）
    "weakness_add", "grants_immune",
    "tick_anchor", "effect_scope", "hp_lock", "revive_percent", "moon_cocoon",
    "forced_taunt", "shield", "target", "target_resource", "max_override",
})

#: hook 合法键（模板 hooks 块 / 秘技 hooks 共用）
_HOOK_KEYS = frozenset({"event", "condition", "effects",
                        "accumulated", "flush_triggers", "target_filter",
                        "trigger_limit"})

#: policy 合法键
_POLICY_KEYS = frozenset({"name", "action_rules", "target_rules", "parameters", "ult_timing",
                          "mode", "script"})  # mode/script=B4 回放变体（14_policy；state_* 仍炸）
#: policy mode 合法值（14_policy：rule_based 默认 / scripted 严格脚本 / hybrid 脚本+规则回退）
_POLICY_MODES = frozenset({"rule_based", "scripted", "hybrid"})
#: script 条目合法键（mode: scripted/hybrid 的逐回合脚本）
_POLICY_SCRIPT_KEYS = frozenset({"turn", "actor", "action", "target"})
_POLICY_RULE_KEYS = frozenset({"condition", "action", "priority", "selector", "description"})

#: build 段顶层合法键（消费点：compile() 逐键读取）
_BUILD_KEYS = frozenset({"team", "policy", "pre_battle"})

#: pre_battle 引用条目合法键
_PRE_BATTLE_USE_KEYS = frozenset({"actor_id", "technique"})

#: 角色模板顶层合法键（消费点：_compile_inline_character 合并段 + compile() 的 tpl 各分支；
#: 生成器产出的 trace_notes/scaling_notes 为注释槽，照放行）
_CHAR_TEMPLATE_KEYS = frozenset({
    "actor_id", "name", "level", "actor_type", "base_stats", "actions",
    "trace_stat_effects", "trace_notes", "scaling_notes", "custom_resources",
    "state_config", "techniques", "team_modifiers", "hooks", "eidolons",
    "energy_name", "summons", "path", "groups", "element",
    "skill_params",  # hook/modifier 侧系数的等级表（param() 编译期引用，05_effects §5.1）
})

#: summons 块（12_summon）每个召唤物定义的合法键（消费点：compile() 模板分支 _compile_summons）
_SUMMON_KEYS = frozenset({
    "name", "inheritance", "base_stats", "capabilities", "actions", "hooks",
    "max_hp_ratio", "custom_resources", "control",
})
#: 召唤物能力闸合法键（12_summon §12.4 通用约定：默认全开，逐实例显式 false）
_SUMMON_CAPABILITY_KEYS = frozenset({"av", "enemy_targetable", "ally_targetable", "taunt"})

#: 光锥模板顶层合法键（消费点：_merge_light_cone——白值/叠影绑定/hooks 通道）
_LIGHT_CONE_TEMPLATE_KEYS = frozenset({
    "light_cone_id", "name", "rarity", "path", "base_stats",
    "lookup_tables", "variable_bindings", "notes", "hooks",
})
#: 遗器套装模板顶层合法键（消费点：_merge_relic_sets）
_RELIC_TEMPLATE_KEYS = frozenset({"relic_set_id", "name", "set_2pc", "set_4pc", "notes"})
#: 套装件（set_2pc/set_4pc）合法键（stat_effects 纯数值通道；hooks 机制通道——条件效果族）
_RELIC_SET_PIECE_KEYS = frozenset({"desc", "stat_effects", "hooks"})

#: custom_resources 值块合法键（16_custom_resources §16.2；消费点：compile() 模板 cr 分支）
_RESOURCE_BLOCK_KEYS = frozenset({
    "name",  # 资源显示名（元数据登记，与 owner 同类——无行为消费点；白厄毁伤族现役）
    "max", "current", "owner", "scope", "ult_threshold", "activation_grant",
    "overflow_mode", "bank_max", "bank_refund", "host", "provenance",
    "persist_across_battles",
})
#: bank_refund 时机别名 → 总线契约事件（16 §16.12 表面写法 → §23.4 事件名）
_BANK_REFUND_ALIASES = {"after_ultimate": "on_ultimate"}

#: state_config 合法键（消费点：compile() → StateConfig 构造，字段一一对应）
_STATE_CONFIG_KEYS = frozenset({
    "state", "name", "replaces_actions", "locked_actions", "exit_conditions",
    "stat_effects", "final_action_id", "entry_action_id", "countdown_spd_ratio",
    "countdown_initial_ratio", "banish_allies_on_enter", "exit_remove_modifiers",
    "grants_immune", "entry_end_turn",
})
_STATE_CONFIG_EXIT_CONDITION_KEYS = frozenset({"trigger", "value"})

#: techniques 条目合法键（消费点：compile() 战前秘技段——point_cost 错拼=点池闸被绕，必炸）
_TECHNIQUE_KEYS = frozenset({"technique_id", "name", "point_cost", "effects", "hooks"})

#: team_modifiers 合法键（消费点：compile() 的 technique_point_initial_bonus 读取）
_TEAM_MODIFIER_KEYS = frozenset({"technique_point_initial_bonus", "technique_point_max_bonus"})

#: eidolons 条目合法键（消费点：compile() 星魂激活段逐键读取）
_EIDOLON_KEYS = frozenset(
    {"name", "stat_effects", "skill_level_overrides", "overrides", "hooks", "notes"})

#: action apply_modifiers.target 词表（引擎 _apply_action_side_effects 现状二值；
#: all_allies 族待引擎支持后放开——写进来编译期炸，不许静默落入 else 分支当 all_enemies）
_APPLY_MODIFIER_TARGETS = frozenset({"self", "all_enemies"})

#: 各 effect_type 引擎消费的参数键（公共键 effect_type/target/name 之外；
#: 词表 = HookRuntime._run_hook_effect（sim/hooks.py）逐分支实际读取的键，按代码现状冻结）
_EFFECT_PARAM_KEYS: Dict[str, frozenset] = {
    "cancel_event": frozenset(),
    "gain_resource": frozenset({"resource_id", "amount", "source"}),
    "set_resource": frozenset({"resource_id", "amount"}),
    "refund_bank": frozenset({"resource_id"}),
    "gain_skill_point": frozenset({"amount", "overflow_to"}),
    "set_sp_max": frozenset({"amount"}),
    "refill_skill_point": frozenset({"from_resource"}),
    "gain_energy": frozenset({"amount", "err_exempt"}),
    "heal_self": frozenset({"ratio"}),
    "heal": frozenset({"ratio", "amount"}),
    "set_hp_to_percent": frozenset({"percent", "amount"}),
    "drain_hp": frozenset({"amount", "drain_ratio", "heal_target", "floor", "into_resource"}),
    "summon": frozenset({"summon_id"}),
    "dismiss_summon": frozenset({"summon_id"}),
    "apply_modifier": frozenset({"modifier"}),
    "deal_damage": frozenset({"scaling_atk", "scaling_hp", "amount", "category", "damage_type",
                              "toughness_dmg", "action_type"}),
    "trigger_action": frozenset({"action_id", "scaling_atk"}),
    "remove_modifier": frozenset({"modifier_id", "reason", "filter", "max_count"}),
    "break_damage": frozenset({"element", "ratio"}),
    "trigger_dot": frozenset(),
    "adjust_duration": frozenset({"modifier_id", "delta"}),
    "add_toughness_bar": frozenset({"amount"}),
    "grant_extra_turn": frozenset(),
    "immediate_action": frozenset(),
    "delay_action": frozenset({"amount"}),
    "advance_action": frozenset({"amount"}),
    "adjust_stacks": frozenset({"modifier_id", "delta"}),
    "modify_amount": frozenset({"amount"}),
    "activate_ultimate": frozenset(),
}
_EFFECT_COMMON_KEYS = frozenset({"effect_type", "target", "name"})


def _check_self_ns_fields(expr_src: Any, *, where: str, extra: Sequence[str] = ()) -> None:
    """`$self.<attr>` 字段存在性校验（13_validator §13.3）：错拼（如 `$self.atkk`）编译期炸.

    放行集：`_SELF_NS_FIELDS` 白名单 ∪ `dmg_<元素>` 前缀 ∪ extra（owner 绑定参数名——
    variable_bindings 产物，调用方按编译期已知注入）；其余 `$self.xxx` 一律报错指路。
    """
    if not isinstance(expr_src, str):
        return
    extras = set(extra)
    for attr in _SELF_NS_RE.findall(expr_src):
        if attr in _SELF_NS_FIELDS or attr in extras:
            continue
        if any(attr == f"dmg_{e}" for e in _ELEMENTS):
            continue
        raise ValueError(
            f"{where} 引用了不存在的 `$self.{attr}`"
            f"（白名单：{sorted(_SELF_NS_FIELDS)} + dmg_<元素> + 绑定参数 {sorted(extras) or '[]'}）")


#: hook 语境资源平铺键引用（`res_<rid>`——引擎 _hook_ctx 按 "res_"+资源 id 逐字注入：
#: id 无前导下划线=单下划线形如 res_charge；有前导下划线=双下划线形如 res__vendetta）
_RES_REF_RE = re.compile(r"\bres_([A-Za-z0-9_]+)")

#: `$event.<字段>` 引用（模板侧对账闸用——注册表 sim/bus.py DEFAULT_PAYLOAD_FIELDS）
_EVENT_NS_RE = re.compile(r"\$event\.([A-Za-z_]\w*)")

#: `$event` 注册载荷外的合法键：insert/cancel（_hook_ctx 默认注入全事件）、
#: targets（累积模式聚合清单——23 章 §23.9 登记，运行期 flush 富化）
_EVENT_CTX_DEFAULT_KEYS = frozenset({"insert", "cancel", "targets"})


def _check_event_ns_fields(expr_src: Any, event: str, *, where: str) -> None:
    """`$event.<字段>` 对账闸（13_validator §13.3 同族）：引用字段须在该事件注册载荷内
    （sim/bus.py DEFAULT_PAYLOAD_FIELDS）∪ ctx 默认键；错拼=运行期 B8 按不触发+⚠=静默
    死钩（丹恒 100202 打标稿 `$event.crit` 实证——正解 is_critical）。

    覆盖范围：hook condition / effects 表达式槽 / target_filter / 字符串 target 选择器
    （目标代数 dict 内 where/order_by 表达式的 $event 引用待代数闸接 event 语境后补，在案）。
    """
    if not isinstance(expr_src, str):
        return
    from hsr_nous.sim.bus import DEFAULT_PAYLOAD_FIELDS
    allowed = set(DEFAULT_PAYLOAD_FIELDS.get(event, ())) | _EVENT_CTX_DEFAULT_KEYS
    for attr in _EVENT_NS_RE.findall(expr_src):
        if attr not in allowed:
            hint = ""
            if attr == "target" and "actor" in allowed:
                hint = ("；该事件主体键是 `actor`——'回合开始/结束谁行动'写 $event.actor"
                        "（on_turn_start/on_turn_end 族没有 target，$event.target 多系笔误）")
            raise ValueError(
                f"{where} 引用了事件 {event!r} 注册载荷外的 `$event.{attr}`"
                f"（合法：{sorted(allowed)}；注册表 sim/bus.py DEFAULT_PAYLOAD_FIELDS——"
                f"与 23 章事件表实发集同义）{hint}")


def _check_res_refs(expr_src: Any, decls: Dict[str, Any], *, where: str,
                    written: Container[str] = ()) -> None:
    """`res_<rid>` 平铺键对账闸（13_validator §13.3 同族）：引用的资源须可静态证真——
    ① 同 actor custom_resources 已声明（trigger_limit 糖计数器注册产物同列）；或
    ② 同 hooks 块内有 set/gain/adjust_stacks 写账（`_` 前缀内部闩免声明惯例——白厄
    `_immune_used` 形态入场置零族）；或 ③ 引擎/糖内部件（`_state_actions_*`/`_tl_*`）。
    三者皆无=错拼推定，编译期炸.

    病灶实证：万敌打标初稿 `res__charge`（正解 `res_charge`——declared 却按双下划线写，
    未声明+无写账+非内部）——编译放行、冒烟绿，运行期 B8 按不触发+⚠=整条入血仇链静默
    全哑（e2e 钓出）。覆盖范围：hook condition 与 effects 表达式槽（action available_if
    的 res_ 平铺闸待声明管线前移后补，在案）。
    """
    if not isinstance(expr_src, str):
        return
    for rid in _RES_REF_RE.findall(expr_src):
        if rid in decls or rid in written:
            continue
        if rid.startswith("_state_actions_") or rid.startswith("_tl_"):
            continue   # 引擎形态计数 / trigger_limit 糖计数器（外部模板不手写，防御放行）
        raise ValueError(
            f"{where} 引用了无法证真的资源平铺键 `res_{rid}`"
            f"（本 actor 已声明：{sorted(decls) or '[]'}；本块有写账：{sorted(written) or '[]'}；"
            f"平铺键=res_+资源 id 逐字——id 无前导下划线时单下划线形如 res_charge，"
            f"有则双下划线 res__xxx；内部闩须在同块有 set/gain 写账或显式声明）")


#: 资源写账 effect 族（res_ 对账闸的"本块有写账"判定集——与收尾存在性闸同口径）
_RESOURCE_WRITE_TYPES = frozenset({"gain_resource", "set_resource", "adjust_stacks",
                                   "refund_bank"})


# --- 枚举词表（拼错编译期炸；历史案例：ult_timing "after_actoin" 终结技永远不开零提示） ---

#: action_type 合法值（03_actor.md §3.8 枚举表）
ACTION_TYPES = frozenset({"basic", "skill", "ultimate", "follow_up", "memosprite_skill", "assist"})

#: target_type 合法值（引擎 _resolve_targets 实现集——其余写法落入默认单体=静默错，冻结拒绝；
#: 文档示例里的 enemy_single/enemy_aoe 引擎未实现，不在词表）
TARGET_TYPES = frozenset({"single", "blast", "aoe", "bounce", "self", "ally_single", "ally_aoe"})

#: ult_timing 合法值（policy_api ULT_BEFORE_ACTION/ULT_AFTER_ACTION/ULT_NEVER）
ULT_TIMINGS = frozenset({"before_action", "after_action", "never"})

#: modifier 枚举字段（引擎 stack_mode/tick_anchor/effect_scope 实现集，state.py 注释同口径）
STACK_MODES = frozenset({"refresh", "independent", "replace", "set"})
TICK_ANCHORS = frozenset({"owner_turn_end", "owner_turn_start", "on_action", "source_turn_end",
                          "source_turn_start"})
EFFECT_SCOPES = frozenset({"self", "team"})

#: action prefer_target 词表（机制级优先目标，03_actor §3.8.1——
#: owner_last_target = 召唤物"优先召唤者最后攻击的敌人"族，长夜月 Evey 1141301 首实例）
PREFER_TARGETS = frozenset({"owner_last_target"})

#: duration dict 糖（04_modifier §4.14）：合法键 + tick_on 词表
#: （词表镜像：modifiers._DURATION_TICK_ON——按引擎实现冻结，改一边同步另一边；
#: until 已登记未落地——写了编译期炸指路，不静默吞）
_DURATION_DICT_KEYS = frozenset({"value", "tick_on", "until"})
DURATION_TICK_ON = frozenset({"$modifier.source"})

#: shield 数值块合法键（04_modifier §4.15——accumulate/cap 具名累积池族）
_SHIELD_BLOCK_KEYS = frozenset({"scaling", "flat", "accumulate", "cap"})
#: shield cap 子块合法键（multiplier × scaling/flat 按 shield 公式求值）
_SHIELD_CAP_KEYS = frozenset({"scaling", "flat", "multiplier"})


def _check_keys(spec: Dict[str, Any], known: frozenset, *, where: str) -> None:
    """已知键集合 diff 校验：未知键（错拼）编译期炸，报错列出非法键+合法集合."""
    for k in spec:
        if k in _SUGAR_KEYS_UNWIRED and k not in known:
            raise ValueError(
                f"{where} 使用了糖键 {k!r}——04_modifier §4.12-4.14 设计预览，"
                f"desugar 未接线（sugar.py），落地前不可在模板中使用"
            )
        if k not in known:
            raise ValueError(f"{where} 含未知键 {k!r}（合法集合：{sorted(known)}）")


def _check_enum(value: Any, legal: frozenset, *, where: str, field: str) -> None:
    if value is not None and str(value) not in legal:
        raise ValueError(
            f"{where} 的 {field} 非法值 {value!r}（合法集合：{sorted(legal)}）"
        )


def _check_mapping(value: Any, *, where: str, field: str) -> None:
    """dict 槽容器闸（编译期抓形状错——漏到运行期就是 TypeError/AttributeError 谜语：
    1408 resource_gain:list、1207 grants_immune:true、1504 stat_effects:list 病例）."""
    if value is not None and not isinstance(value, dict):
        raise ValueError(f"{where} 的 {field} 须为 mapping，实得 {type(value).__name__}")


def _check_mapping_list(value: Any, *, where: str, field: str) -> None:
    """mapping 列表槽容器闸（scaling 族：list[dict]，元素非 dict 同罪）."""
    if value is not None and not (
            isinstance(value, list) and all(isinstance(s, dict) for s in value)):
        raise ValueError(f"{where} 的 {field} 须为 mapping 列表，实得 {type(value).__name__}")


#: params 引用宏（05_effects §5.1）：param(<skill_id>, <N>)——编译期按有效技能等级取
#: 模板 skill_params 表替换为字面量；替换发生在表达式预编译闸之前，运行期零新概念
_PARAM_REF_RE = re.compile(r"\bparam\(\s*(\d+)\s*,\s*(\d+)\s*\)")
_PARAM_REF_ANY_RE = re.compile(r"\bparam\s*\(")

#: skill_params 条目合法键
_SKILL_PARAMS_ENTRY_KEYS = frozenset({"level_key", "rows"})


class _SkillParams:
    """模板 `skill_params` 块的编译期视图：param() 引用按有效等级取档替换（05_effects §5.1）.

    levels 视图 = 模板主角色编译期最终 skill_levels（默认档 + member 覆写 + 星魂
    skill_level_overrides 加算**之后**——slo 已前移到 _compile_inline_character）+
    忆灵槽种子（memosprite_skill/memosprite_talent 默认 10：角色 skill_levels 无此键，
    官方数据 10 档上限；星魂若声明该槽覆写则自然进入视图并被钳位警告接住）。
    """

    def __init__(self, spec: Any, levels: Dict[str, int], *, where: str) -> None:
        self.tables: Dict[str, Dict[str, Any]] = {}
        self.levels = {"memosprite_skill": 10, "memosprite_talent": 10,
                       **{str(k): int(v) for k, v in levels.items()}}
        if spec is None:
            return
        _check_mapping(spec, where=where, field="skill_params")
        for sid, entry in (spec or {}).items():
            e_desc = f"{where} skill_params[{sid!r}]"
            _check_mapping(entry, where=e_desc, field=f"skill_params[{sid!r}]")
            _check_keys(entry, _SKILL_PARAMS_ENTRY_KEYS, where=e_desc)
            lk = entry.get("level_key")
            if not isinstance(lk, str) or not lk:
                raise ValueError(
                    f"{e_desc} 的 level_key 须为非空字符串"
                    f"（basic/skill/ultimate/talent/memosprite_skill/memosprite_talent 族——"
                    f"读 actor.skill_levels 的哪一键）")
            rows = entry.get("rows")
            if not isinstance(rows, list) or not rows:
                raise ValueError(
                    f"{e_desc} 的 rows 须为非空列表（lv1..lvN 全表照抄原始数据 params）")
            for ri, row in enumerate(rows):
                if not isinstance(row, list) or not row or any(
                        isinstance(x, bool) or not isinstance(x, (int, float)) for x in row):
                    raise ValueError(
                        f"{e_desc} 的 rows[{ri}]（lv{ri + 1} 行）须为非空数值列表")
            self.tables[str(sid)] = {"level_key": lk, "rows": rows}

    def substitute(self, text: str, *, where: str) -> str:
        """param(<sid>, <N>) → 字面量文本（无引用原样返回；无表/序号越界编译期炸；越档钳表尾 ⚠）."""
        if not _PARAM_REF_ANY_RE.search(text):
            return text

        def _repl(m: "re.Match[str]") -> str:
            sid, n = m.group(1), int(m.group(2))
            entry = self.tables.get(sid)
            if entry is None:
                raise ValueError(
                    f"{where}：param({sid}, {n}) 无表——本模板 skill_params 未声明 {sid!r}"
                    f"（光锥/遗器/秘技 hooks 语境无角色等级轨道，等同无表；05_effects §5.1）")
            rows = entry["rows"]
            lv = int(self.levels.get(entry["level_key"], self.levels.get("ultimate", 10)))
            if lv > len(rows):
                warnings.warn(
                    f"{where}：param({sid}, {n}) 取档 lv{lv} 越出表尾（{len(rows)} 档）——"
                    f"钳到表尾（忆灵技/忆灵天赋 10 档上限、E3/E5 忆灵+1 无第 11 档数据口径，"
                    f"05_effects §5.1）", stacklevel=2)
                lv = len(rows)
            row = rows[max(lv - 1, 0)]
            if not (1 <= n <= len(row)):
                raise ValueError(
                    f"{where}：param({sid}, {n}) 序号越界——lv{lv} 行仅 {len(row)} 项"
                    f"（N 从 1 起，对应官方描述 #N[i]）")
            v = float(row[n - 1])
            return str(int(v)) if v == int(v) else repr(v)  # 整值渲成 16 而非 16.0

        out = _PARAM_REF_RE.sub(_repl, text)
        if _PARAM_REF_ANY_RE.search(out):
            raise ValueError(
                f"{where}：param 引用语法非法——合法形 param(<skill_id>, <N>)，"
                f"skill_id 不加引号、N 为 ≥1 整数（05_effects §5.1）")
        return out


#: 无 skill_params 语境（inline 角色/光锥/遗器 hooks）——任何 param() 引用走"无表"报错
_NO_PARAMS = _SkillParams(None, {}, where="（无 skill_params 语境）")


#: stat_effects 已知词表（= pipeline.effective_stats 产出键 + pct 族 + 引擎读取的扩展槽；
#: dmg_* / res_* 前缀族与前缀匹配放行）。stat_effects 是开放命名空间（自定义 stat 合法），
#: 不能硬闸——词表外只 warnings.warn 提示（crit_dmgg 类错拼被点亮，自定义 stat 不拦）
_KNOWN_STAT_KEYS = frozenset({
    # effective_stats 基础产出键
    "hp", "atk", "def_", "def", "spd", "crit_rate", "crit_dmg", "def_pen", "res_pen",
    "vulnerability", "energy_regen", "break_effect", "break_efficiency_boost",
    "weakness_break_efficiency_boost", "effect_hit", "effect_res", "taunt", "taunt_eff",
    "heal_bonus", "shield_bonus",
    # pct 族（_PCT_BASE）+ 增伤通槽
    "hp_pct", "atk_pct", "def_pct", "spd_pct", "all_dmg",
    # 引擎/pipeline 读取的扩展槽（命中穿透/受疗/嘲讽加成）
    "effect_res_pen", "incoming_heal", "aggro_boost",
    # 超击破体系（B38——pipeline.super_break_damage 直读）：转换倍率池 / 超击破增伤池
    "super_break_modifier", "super_break_dmg_boost",
})


def _warn_unknown_stat_keys(stat_effects: Any, where: str) -> None:
    """stat_effects 键错拼告警：词表外且与某已知键高度相似的键（疑 crit_dmgg 类错拼）
    编译期 warn 不拒绝；与词表无近似的自定义 stat 属开放命名空间，静默放行."""
    import difflib
    for k in stat_effects or ():
        if k in _KNOWN_STAT_KEYS or str(k).startswith(("dmg_", "res_")):
            continue
        near = difflib.get_close_matches(str(k), sorted(_KNOWN_STAT_KEYS), n=1, cutoff=0.8)
        if not near:
            continue  # 自定义 stat（与词表无近似）：合法，不拦不扰
        warnings.warn(
            f"{where} 的 stat_effects 键 {k!r} 不在已知词表，疑似 {near[0]!r} 错拼"
            f"（自定义 stat 合法，仅提示不拒绝）",
            stacklevel=3,
        )


# ----------------------------------------------------------------------------
# 病族闸（2026-09-14 病族灭源批——验收型批 40 只勘正聚类的编译期固化）
# 每条带实证指路；哲学同 _check_keys：静默吞=幻觉温床，报错带正解。
# ----------------------------------------------------------------------------

#: 死键→正解映射：命中即炸。`_warn_unknown_stat_keys` 的「无近似静默放行」是这类键
#: 反复漏网的结构根因（dmg_taken/max_hp 等与词表无近似，全被当自定义 stat 放行）。
_DEAD_STAT_KEYS: Dict[str, str] = {
    "dmg_taken": "vulnerability（承伤区易伤——1108 桑博/1507 先例）",
    "dmg_taken_reduction": "dmg_dmg_reduction（减伤乘区——1107 克拉拉/1206 素裳先例）",
    "dmg_reduction": "dmg_dmg_reduction（裸键无消费端——1107/1206/1211 先例）",
    "outgoing_heal": "heal_bonus（1211 白露 E2 先例）",
    "hp_max": "hp（flat——Layer 1 并入即生命上限提高；1208 符玄慧明先例）",
    "max_hp": "hp（flat——同上）",
    "max_hp_pct": "hp_pct（pct 族——1211 白露 A2 先例）",
    "damage_dealt_mult": "all_dmg（增伤区加算——1203 罗刹 E4 先例）",
    "skill_dmg": "dmg_skill_dmg_boost（类型桶——1008 先例）",
    "basic_dmg": "dmg_basic_dmg_boost（类型桶——1013 先例）",
    "dot_dmg_bonus": "（无消费端——DoT 增伤待收，事件跳伤承载，勿写）",
    "all_type_res": "（无消费端——全抗件待收，1006/1015/1106/1203 同案，勿写）",
    "def_shred": "def_pct 负值（1015 先例）",
    "cc_res": "（控制特化抵抗无通道——type_res 无实例源不新造；1213 饮月/1217 藿藿同案）",
}


def _check_dead_stat_keys(keys: Any, where: str) -> None:
    """死键硬闸：命中映射表即炸带正解（stat_effects/stat_exprs 共用）."""
    for k in keys or ():
        if k in _DEAD_STAT_KEYS:
            raise ValueError(
                f"{where} 的 stat 键 {k!r} 是已知死键（无消费端——写了静默无效）"
                f"——正解：{_DEAD_STAT_KEYS[k]}")


#: grants_immune 合法 kind 词表（与 modifiers._apply_modifier 的 new_kind 取值空间同源：
#: modifier_type∈{debuff,dot,control} + debuff_kind∈{dot,control}——开放 kind 到达时同步
#: 本表（同模块边界闸哲学：词表与所指物同文件就近维护）
_GRANTS_IMMUNE_KINDS = frozenset({"debuff", "dot", "control"})


def _check_grants_immune_literal(v: Any, where: str) -> None:
    """grants_immune 字面 kind 闸：列表项必须在 kind 词表（成员判定，**不是表达式**——
    1207 驭空 `\"$mod.kind == 'debuff'\"` 幻视实证：表达式字符串字面匹配永不命中=免疫
    死挂）；词表外标识符同炸（1221 云璃 \"crowd_control\" 错拼实证——形似 kind 但引擎
    不认，同样死挂；错拼提示 control）。
    """
    for item in v or ():
        if not isinstance(item, str) or item not in _GRANTS_IMMUNE_KINDS:
            hint = "（crowd_control 的正确拼写是 control）" if item == "crowd_control" else ""
            raise ValueError(
                f"{where} 的 grants_immune 项 {item!r} 非法——字面 kind 词表 "
                f"{sorted(_GRANTS_IMMUNE_KINDS)}（成员判定非表达式；1221 云璃 crowd_control "
                f"错拼同案{hint}）")


def _check_no_hook_chance(expr_src: Any, where: str) -> None:
    """hook/effect 域 chance() 幻视闸：chance(N) 白名单层有但 **hook 宿主不注入 rng**
    （22_syntax_reference §22.4 钉死）——写了运行期静默不触发+⚠（1009 艾丝妲/1206 素裳/
    1209 彦卿实证）；正解 mechanic_chance(p)（宿主函数：expected ≥0.5 钉 / roll 真掷）.
    """
    import ast as _ast
    if not isinstance(expr_src, str):
        return
    try:
        tree = self_expr_parse(expr_src).tree
    except Exception:
        return   # 语法错由既有预编译闸报（不重复审判）
    for node in _ast.walk(tree):
        if isinstance(node, _ast.Call) and isinstance(node.func, _ast.Name) \
                and node.func.id == "chance":
            raise ValueError(
                f"{where} 使用了 chance()——hook 宿主不注入 rng，运行期静默不触发"
                f"（1009/1206/1209 实证）；正解 mechanic_chance(p)")


def self_expr_parse(src: str) -> Any:
    """expression.parse 的层固定包装（病族闸内部通道——effect 层白名单）."""
    from hsr_nous.sim_schema.expression import parse
    return parse(src, layer="effect")


def _check_no_eidolon_in_mainline(items: Any, where: str) -> None:
    """星魂件主干泄漏闸：主干 hooks 的 apply_modifier modifier_id 命中星魂前缀
    （^(E[1-6]|S[1-6])_）→ 炸。主干=星魂未激活也生效——1209 彦卿 E2_ERR/E4_SEARING_STING
    主干泄漏 E0 生效实证；星魂机制必须进 eidolons.EX 块（纯命名避让：主干件别用星魂前缀）。
    """
    import re as _re
    pat = _re.compile(r"^(E[1-6]|S[1-6])_")
    for h in items or ():
        for e in (h.get("effects") or []):
            if not isinstance(e, dict) or e.get("effect_type") != "apply_modifier":
                continue
            mid = str((e.get("modifier") or {}).get("modifier_id", ""))
            if pat.match(mid):
                raise ValueError(
                    f"{where} 的主干 hook 挂了星魂件 {mid!r}（^(E[1-6]|S[1-6])_ 前缀）"
                    f"——星魂机制必须进 eidolons.EX 块，主干=星魂未激活也生效"
                    f"（1209 彦卿四件泄漏 E0 生效实证；非星魂件请改名避让前缀）")


def _yaml_load_strict(stream: Any, fname: str) -> Any:
    """YAML 加载（重复键即炸，报文件名+键名）.

    PyYAML 默认重复键静默后值盖前值（1408 模板 stack_mode/stat_effects 重复块事故）——
    模板是机制唯一来源，重复键=歧义定义，必须炸。
    """
    import yaml

    class _Loader(yaml.SafeLoader):
        pass

    def _construct_mapping(loader: Any, node: Any, deep: bool = False) -> Dict[Any, Any]:
        mapping: Dict[Any, Any] = {}
        for key_node, value_node in node.value:
            key = loader.construct_object(key_node, deep=True)
            if key in mapping:
                raise ValueError(f"模板 {fname} 存在重复键 {key!r}（YAML 重复键不许静默覆盖）")
            mapping[key] = loader.construct_object(value_node, deep=deep)
        return mapping

    _Loader.add_constructor(
        yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping)
    return yaml.load(stream, Loader=_Loader)


#: 模板根缺省值：见顶部 re-export（唯一定义在 sim_schema/templates.py 的
#: DEFAULT_TEMPLATE_ROOTS，相对 CWD——与不注入时的历史行为一致）


class BuildCompiler:
    """build.yaml → (team actors, actions_by_actor, CompiledPolicy)."""

    def __init__(self, expr: Optional[ExprCompiler] = None) -> None:
        self.expr = expr or ExprCompiler()
        #: params 引用语境（actor_id → _SkillParams，05_effects §5.1）——
        #: _compile_inline_character 构建，compile() 主循环 hooks/召唤物/星魂/秘技段消费
        self._param_ctx_by_actor: Dict[str, _SkillParams] = {}

    @staticmethod
    def _load_template(kind: str, ref: str, *, roots: Sequence[Union[str, Path]],
                       legacy: bool = False) -> Dict[str, Any]:
        """按序在 roots 各根下加载 <kind>/<id>_*.yaml 模板（kind=characters/light_cones/relics/enemies）.

        roots 为调用方注入的有序模板根（str/Path 均可；生产 = DEFAULT_TEMPLATE_ROOTS，
        测试可注入人工 fixtures 根优先）：按序查 {root}/{kind}/{ref}_*.yaml，
        **第一个有命中的根生效**——跨根同 ID 不炸（人工全机制版如 `1408_phainon.yaml`
        压生成器副本如 `1408_白厄.yaml` 靠根序，两版同存不报错）；**根内**同 id 多文件
        = 撞名即炸（报全部文件名——同根内按排序取第一个是静默歧义，不许；删到只剩
        一个再编译，冲突时以人工版为准删生成器文件）；所有根零命中 →
        FileNotFoundError（报查过的全部根路径）。

        legacy=True（3.4 加强角色"加强前"模板分流——member.version 词表闸消费）：
        改查 {ref}_*_legacy.yaml；False（默认）时从命中里排除 *_legacy.yaml
        （加强后 enhanced 是默认真身，两文件同根共存不撞名）。
        """
        import glob

        for root in roots:
            if legacy:
                hits = sorted(glob.glob(f"{root}/{kind}/{ref}_*_legacy.yaml")) or glob.glob(
                    f"{root}/{kind}/{ref}_legacy.yaml")
            else:
                hits = sorted(h for h in glob.glob(f"{root}/{kind}/{ref}_*.yaml")
                              if not h.endswith("_legacy.yaml")) or glob.glob(
                    f"{root}/{kind}/{ref}.yaml")
            if not hits:
                continue
            if len(hits) > 1:
                raise ValueError(
                    f"模板 {kind}/{ref} 撞名（根 {root}）：同 ID {len(hits)} 个文件 {hits}——"
                    f"删到只剩一个再编译（人工全机制版与生成器副本冲突时以人工版为准）"
                )
            with open(hits[0], encoding="utf-8") as f:
                return _yaml_load_strict(f, hits[0])
        track = "加强前（legacy）" if legacy else ""
        raise FileNotFoundError(
            f"模板 {kind}/{ref} {track}不存在（已查根 {[str(r) for r in roots]}）："
            f"先跑 adapters/template_generator 生成"
        )

    @classmethod
    def _load_character_template(cls, ref: str, *, roots: Sequence[Union[str, Path]],
                                 version: str = "enhanced") -> Dict[str, Any]:
        # version 词表闸（错拼如 legancy 编译期炸而非静默落到默认轨）——
        # enhanced=加强后〔默认真身 <id>_<名>.yaml〕/ legacy=加强前〔<id>_<名>_legacy.yaml〕
        if version not in _TEMPLATE_VERSIONS:
            raise ValueError(
                f"角色模板 {ref} version 非法值 {version!r}（词表 {sorted(_TEMPLATE_VERSIONS)}——"
                "加强双轨选边：enhanced=加强后〔默认〕/ legacy=加强前）")
        tpl = cls._load_template("characters", ref, roots=roots, legacy=(version == "legacy"))
        # 模板顶层键闸（teamm 类错拼曾静默吞整块 team_modifiers）
        _check_keys(tpl, _CHAR_TEMPLATE_KEYS, where=f"角色模板 {ref}")
        return tpl

    # ------------------------------------------------------------------
    # 角色（inline）
    # ------------------------------------------------------------------

    def _compile_inline_character(self, spec: Dict[str, Any], *, roots: Sequence[Union[str, Path]]) -> tuple[Actor, List[Action]]:
        """内联角色定义 / 模板引用 → Actor + 技能列表."""
        aid_desc = f"team member {spec.get('actor_id') or spec.get('character_template')!r}"
        # inline 角色的 hooks: 块不接线——机制自包含 DSL 只走模板文件通道
        # （data/sim_templates/characters/<id>_*.yaml 的 hooks: 块，经 character_template 引用），
        # 不许静默吞：写了就炸并指路
        if "hooks" in spec:
            raise ValueError(
                f"{aid_desc}：inline 角色不支持 hooks: 块——机制 hook 请写进角色模板文件"
                f"（data/sim_templates/characters/，经 character_template 引用编译）"
            )
        _check_keys(spec, _MEMBER_KEYS, where=aid_desc)
        ref = spec.get("character_template")
        if ref is not None and not str(ref).startswith("inline"):
            version = str(spec.get("version") or "enhanced").lower()
            tpl = self._load_character_template(str(ref), roots=roots, version=version)
            # 模板提供 actor_id/name/base_stats/actions；member 提供 level/eidolon/relics 覆盖
            spec = {**tpl, **{k: v for k, v in spec.items() if k in ("level", "eidolon", "relics", "skill_levels", "path", "groups", "element")}}
        elif "version" in spec:
            raise ValueError(
                f"{aid_desc} version 只对 character_template 引用有意义（加强双轨选文件）——"
                "inline 角色无版本轨，写了就炸不静默吞")

        base = spec.get("base_stats", {})
        _check_keys(base, _BASE_STATS_KEYS, where=f"{aid_desc} base_stats")
        groups = spec.get("groups") or []
        if not isinstance(groups, (list, tuple)) or any(not isinstance(g, str) for g in groups):
            raise ValueError(f"{aid_desc} groups 须为字符串列表（faction:xxx 开放命名空间，03_actor §3.1）")
        element = str(spec.get("element", "") or "").lower()
        if element and element not in _ELEMENTS:
            raise ValueError(
                f"{aid_desc} element 非法值 {element!r}（元素词表 {sorted(_ELEMENTS)}，"
                "英文小写 canonical key——动态元素族 element_of 取数源）")
        level = int(spec.get("level", 80))
        if not (1 <= level <= 80):
            raise ValueError(f"{aid_desc} level {level} 越界（合法 1-80，13_validator §13.3）")
        if float(base.get("spd", 100.0)) <= 0:
            raise ValueError(f"{aid_desc} spd 必须 > 0，实得 {base.get('spd')!r}（13_validator §13.3）")
        cr = float(base.get("crit_rate", 0.05))
        if not (0.0 <= cr <= 1.0):
            # 建议档 warning（不炸——warning 通道（13_validator §13.3：暴击率建议 0-1））
            warnings.warn(f"{aid_desc} crit_rate {cr} 超出建议区间 [0, 1]", stacklevel=2)
        stats = StatBlock(
            hp=float(base.get("hp", 0.0)),
            atk=float(base.get("atk", 0.0)),
            def_=float(base.get("def", 0.0)),
            spd=float(base.get("spd", 100.0)),
            crit_rate=cr,
            crit_dmg=float(base.get("crit_dmg", 0.5)),
            break_effect=float(base.get("break_effect", 0.0)),
            effect_hit=float(base.get("effect_hit", 0.0)),
            effect_res=float(base.get("effect_res", 0.0)),
            max_energy=float(base.get("max_energy", 100.0)),
            energy_regen=float(base.get("energy_regen", 1.0)),
            taunt=float(base.get("taunt", 100.0)),
            toughness_bars=[float(x) for x in (base.get("toughness_bars") or [])],
        )
        for k, v in (base.get("dmg_bonus") or {}).items():
            stats.dmg_bonus[k] = float(v)
        stats.weakness = list(base.get("weakness") or [])
        stats.resistance = {k: float(v) for k, v in (base.get("resistance") or {}).items()}

        actor = Actor(
            actor_id=spec["actor_id"],
            name=spec.get("name", spec["actor_id"]),
            actor_type=spec.get("actor_type", "character"),
            level=level,
            stats=stats,
            path=str(spec.get("path", "") or ""),  # 命途（count_team 编成计数口径；缺省 ""）
            groups=[str(g) for g in groups],  # 分组标签（in_group/count_team(group=) 口径）
            element=element,  # 元素（element_of 取数源；"" = 未声明）
            skill_levels=self._effective_skill_levels(spec),
        )

        # params 引用语境（05_effects §5.1）：本模板 skill_params 表 + 最终 skill_levels
        # ——action apply_modifiers / 后续 hooks 的 param() 替换共用；inline 角色为空表
        # （写了 param() 走"无表"报错）
        param_ctx = _SkillParams(spec.get("skill_params"), actor.skill_levels, where=aid_desc)
        self._param_ctx_by_actor[actor.actor_id] = param_ctx
        actions = self._compile_action_list(spec.get("actions", []), aid_desc,
                                            param_ctx=param_ctx)
        return actor, actions

    @staticmethod
    def _effective_skill_levels(spec: Dict[str, Any]) -> Dict[str, int]:
        """编译期最终 skill_levels：默认档 + member `skill_levels` 覆写 + 星魂
        `skill_level_overrides` 逐档加算（含 cap）.

        星魂加算**前移**到此（原在 compile() 主循环 hooks 编译之后才应用——param()
        取档要求 hook 编译时等级已定稿；等级战斗中不变，编译期一次算清零运行期成本）。
        星魂块其余消费（stat_effects/overrides/hooks）与 rank 键白名单闸维持主循环原位。
        """
        levels = {**{"basic": 6, "skill": 10, "ultimate": 10, "talent": 10},
                  **{k: int(v) for k, v in (spec.get("skill_levels") or {}).items()}}
        eidolon_n = int(spec.get("eidolon", 0) or 0)
        eidolons = spec.get("eidolons") or {}
        for rank in range(1, min(max(eidolon_n, 0), 6) + 1):
            slo = (eidolons.get(f"E{rank}") or {}).get("skill_level_overrides")
            for k, v in (slo or {}).items():
                cap = 10 if k == "basic" else 15
                levels[k] = min(cap, levels.get(k, 10) + int(v))
        return levels

    def _compile_action_list(self, actions_spec: List[Dict[str, Any]], aid_desc: str,
                             param_ctx: Optional[_SkillParams] = None) -> List[Action]:
        """行动列表编译（角色模板与召唤物 actions 块共用同一闸与构造——12_summon）."""
        sub = (param_ctx or _NO_PARAMS).substitute
        actions: List[Action] = []
        for a in actions_spec:
            a_desc = f"{aid_desc} action {a.get('action_id')!r}"
            _check_keys(a, _ACTION_KEYS, where=a_desc)
            _check_enum(a.get("action_type"), ACTION_TYPES, where=a_desc, field="action_type")
            _check_enum(a.get("target_type"), TARGET_TYPES, where=a_desc, field="target_type")
            # 病族闸（warn）：target_type 'single'（敌方池）但无伤害段——我方增益/治疗/净化
            # 技应为 ally_single（1101/1105/1110/1202/1203/1215/1217 八次实证）；
            # 敌方 debuff 植入技合法，故仅 warn
            if str(a.get("target_type")) == "single" and not a.get("damage_type") \
                    and not a.get("scaling"):
                warnings.warn(
                    f"{a_desc} 的 target_type 是 'single'（敌方池）但无 damage_type/scaling"
                    f"（无伤害段）——我方指向技应为 ally_single（八次打标实证）；"
                    f"确为敌方 debuff 植入技可忽略",
                    stacklevel=3,
                )
            if a.get("prefer_target"):
                _check_enum(a.get("prefer_target"), PREFER_TARGETS,
                            where=a_desc, field="prefer_target")
            _check_mapping(a.get("resource_gain"), where=a_desc, field="resource_gain")
            _check_mapping_list(a.get("scaling"), where=a_desc, field="scaling")
            _check_mapping_list(a.get("scaling_blast"), where=a_desc, field="scaling_blast")
            for m in a.get("apply_modifiers") or []:
                self._validate_modifier_spec(m, f"{a_desc} apply_modifiers",
                                             param_ctx=param_ctx)
                # target 词表 = 引擎 _apply_action_side_effects 现状二值（self / all_enemies）；
                # 其余值（all_allies 族）编译期炸——引擎未支持前不许静默落入 else 当 all_enemies
                _check_enum(m.get("target"), _APPLY_MODIFIER_TARGETS,
                            where=f"{a_desc} apply_modifiers", field="target")
            if a.get("instance_variants") is not None:
                # 段级变体（B35②）：逐段覆写——键闸 + target_type 枚举 + scaling 形状
                if not isinstance(a["instance_variants"], list):
                    raise ValueError(f"{a_desc} instance_variants 须为列表（None=该段用基础行动）")
                for iv in a["instance_variants"]:
                    if iv is None:
                        continue
                    _check_keys(iv, _VARIANT_KEYS, where=f"{a_desc} instance_variants")
                    if iv.get("target_type") is not None:
                        _check_enum(iv["target_type"], TARGET_TYPES,
                                    where=f"{a_desc} instance_variants", field="target_type")
                    _check_mapping_list(iv.get("scaling"), where=f"{a_desc} instance_variants",
                                        field="scaling")
            ts = a.get("toughness_scope")
            if ts:
                # 削韧作用域（决策卡 #5）："all" 或元素列表——其余写法编译期炸
                bad_ts = (isinstance(ts, list) and any(str(e).lower() not in _ELEMENTS for e in ts)) \
                    or (not isinstance(ts, list) and str(ts).lower() not in ("all",) and str(ts).lower() not in _ELEMENTS)
                if bad_ts:
                    raise ValueError(
                        f"{a_desc} toughness_scope 非法值 {ts!r}"
                        f'（合法："all" / 元素列表 {sorted(_ELEMENTS)}）')
            # available_if（03_actor §3.8.1 行动级可用条件）：声明期预编译 + $self 字段闸
            #（hit_condition 同口径；产物随 Action 携带，引擎合法集求值不重复 parse）；
            # param() 替换同 EFFECT_EXPR_SLOTS 口径（05_effects §5.1——一切表达式槽同通道）
            available_if = str(a.get("available_if", "") or "")
            available_if_expr = None
            if available_if:
                available_if = sub(available_if, where=f"{a_desc} available_if")
                try:
                    available_if_expr = self.expr.compile(available_if, layer="effect")
                except Exception as e:
                    raise ValueError(f"{a_desc} 的 available_if 表达式非法：{e}") from e
                _check_self_ns_fields(available_if, where=f"{a_desc} available_if")
            scaling = a.get("scaling") or []
            actions.append(Action(
                action_id=a["action_id"],
                name=a.get("name", a["action_id"]),
                action_type=a["action_type"],
                target_type=a.get("target_type", "single"),
                damage_type=a.get("damage_type"),
                scaling=[{k: float(v) for k, v in s.items()} for s in scaling],
                energy_cost=int(a.get("energy_cost", 0)),
                energy_gain=(int(v) if (v := a.get("energy_gain")) is not None else None),
                energy_grant=float(a.get("energy_grant", 0.0)),
                skill_point_cost=int(a.get("skill_point_cost", 0)),
                skill_point_gain=int(a.get("skill_point_gain", 0)),
                toughness_dmg=int(a.get("toughness_dmg", 0)),
                toughness_scope=([str(e).lower() for e in a["toughness_scope"]]
                                 if isinstance(a.get("toughness_scope"), list)
                                 else str(a.get("toughness_scope", "")).lower()),
                scaling_blast=([{k: float(v) for k, v in s.items()} for s in sb]
                               if (sb := a.get("scaling_blast")) else None),
                toughness_dmg_blast=(int(v) if (v := a.get("toughness_dmg_blast")) is not None else None),
                instances=int(a.get("instances", 1)),
                segment_confirm=bool(a.get("segment_confirm", False)),  # 逐段确认（B35①）
                # 段级变体 + 逐击选招（B35②）：变体键闸 + target_type 枚举闸（词表外拼错编译期炸）
                instance_variants=([None if iv is None else dict(iv)
                                    for iv in a["instance_variants"]]
                                   if a.get("instance_variants") is not None else None),
                segment_choice=bool(a.get("segment_choice", False)),
                resource_gain={k: float(v) for k, v in (a.get("resource_gain") or {}).items()},
                ult_cost_resource=str(a.get("ult_cost_resource", "")),
                ult_cost_amount=float(a.get("ult_cost_amount", 0.0)),
                ult_consume_amount=float(a.get("ult_consume_amount", 0.0)),
                ult_quick_cast=bool(a.get("ult_quick_cast", False)),
                manual_trigger=bool(a.get("manual_trigger", False)),
                split=str(a.get("split", "")),
                act_now_targets=str(a.get("act_now_targets", "")),
                assist_cost_resource=str(a.get("assist_cost_resource", "")),  # 助战技额度资源
                apply_modifiers=[dict(m) for m in a.get("apply_modifiers") or []],
                instances_from_resource=str(a.get("instances_from_resource", "")),
                instances_per_point=float(a.get("instances_per_point", 1.0)),
                instances_cap=int(a.get("instances_cap", 0)),
                consume_all_resource=str(a.get("consume_all_resource", "")),
                cleanse_self=bool(a.get("cleanse_self", False)),
                level_key=str(a.get("level_key", "")),  # 倍率取档键（曾静默丢失——白厄模板族）
                prefer_target=str(a.get("prefer_target", "")),  # 机制级优先目标（忆灵优先忆师末目标族）
                available_if=available_if,
                available_if_expr=available_if_expr,
            ))
        return actions

    def _compile_summons(
        self,
        summons_spec: Dict[str, Any],
        owner: Actor,
        ref: str,
        hooks_out: List[Any],
        actions_out: Dict[str, List[Action]],
        param_ctx: Optional[_SkillParams] = None,
    ) -> Dict[str, Any]:
        """模板 summons 块 → SummonDef 注册件（12_summon；actions/hooks 与角色模板同闸）.

        param_ctx：召唤物侧 hooks/actions 的 param() 引用取**角色模板**的 skill_params
        与模板主角色等级（星魂等级覆写落在角色上，召唤物无星魂——05_effects §5.1 边界）。

        inheritance："full"（默认，召唤时继承召唤者 Layer-1 面板）/ "none"（用自带 base_stats）/
        stat 字段名列表（部分继承：列出字段继承，其余用 base_stats 兜底）。
        capabilities：能力闸（默认全开，逐实例显式 false——小伊卡 {"av": false} 族）。
        max_hp_ratio：hp 覆写比例（正浮点；召唤物 hp = 召唤时刻召唤者有效生命上限 × 比例，
        覆盖 inheritance 的 hp 分量，其余字段照常——12_summon §12.1 末）。
        """
        from hsr_nous.sim.compile.compiled import SummonDef

        defs: Dict[str, Any] = {}
        for sid, s in (summons_spec or {}).items():
            s_desc = f"模板 {ref} 召唤物 {sid!r}"
            _check_mapping(s, where=s_desc, field="summons")
            _check_keys(s, _SUMMON_KEYS, where=s_desc)
            caps = s.get("capabilities") or {}
            _check_keys(caps, _SUMMON_CAPABILITY_KEYS, where=f"{s_desc} capabilities")
            for ck, cv in caps.items():
                if not isinstance(cv, bool):
                    raise ValueError(f"{s_desc} capabilities[{ck!r}] 须为 bool，实得 {cv!r}")
            max_hp_ratio = s.get("max_hp_ratio", 0.0)
            # 缺省（未写）= 0.0 不覆写；写了就须为正浮点（0/负/非数值/bool 编译期炸）
            if ("max_hp_ratio" in s
                    and (isinstance(max_hp_ratio, bool)
                         or not isinstance(max_hp_ratio, (int, float))
                         or max_hp_ratio <= 0)):
                raise ValueError(
                    f"{s_desc} max_hp_ratio 须为正数，实得 {max_hp_ratio!r}")
            inheritance = s.get("inheritance", "full")
            if not (inheritance in ("full", "none")
                    or (isinstance(inheritance, list)
                        and all(isinstance(f, str) for f in inheritance))):
                raise ValueError(
                    f"{s_desc} inheritance 非法值 {inheritance!r}"
                    f'（合法："full" / "none" / stat 字段名列表）')
            base = s.get("base_stats") or {}
            _check_keys(base, _BASE_STATS_KEYS, where=f"{s_desc} base_stats")
            if inheritance == "none" and not base.get("hp"):
                raise ValueError(f'{s_desc} inheritance: "none" 但 base_stats 未给 hp')
            if isinstance(inheritance, list):
                unknown = [f for f in inheritance if f not in _BASE_STATS_KEYS]
                if unknown:
                    raise ValueError(f"{s_desc} inheritance 含未知 stat 字段 {unknown}")
            stats = StatBlock(
                hp=float(base.get("hp", 0.0)),
                atk=float(base.get("atk", 0.0)),
                def_=float(base.get("def", 0.0)),
                spd=float(base.get("spd", 100.0)),
                crit_rate=float(base.get("crit_rate", 0.05)),
                crit_dmg=float(base.get("crit_dmg", 0.5)),
                break_effect=float(base.get("break_effect", 0.0)),
                effect_hit=float(base.get("effect_hit", 0.0)),
                effect_res=float(base.get("effect_res", 0.0)),
                max_energy=float(base.get("max_energy", 100.0)),
                energy_regen=float(base.get("energy_regen", 1.0)),
                taunt=float(base.get("taunt", 100.0)),
            )
            for k, v in (base.get("dmg_bonus") or {}).items():
                stats.dmg_bonus[k] = float(v)
            stats.weakness = list(base.get("weakness") or [])
            stats.resistance = {k: float(v) for k, v in (base.get("resistance") or {}).items()}
            summon_actor = Actor(
                actor_id=str(sid),
                name=str(s.get("name", sid)),
                actor_type="summon",
                level=owner.level,
                stats=stats,
                summoner_id=owner.actor_id,
                summon_flags={str(k): bool(v) for k, v in caps.items()},
            )
            summon_actions = self._compile_action_list(s.get("actions") or [], s_desc,
                                                       param_ctx=param_ctx)
            actions_out[str(sid)] = summon_actions
            self._compile_hooks(s.get("hooks") or [], s_desc, str(sid), hooks_out,
                                param_ctx=param_ctx)
            # 召唤物 custom_resources 值块（12_summon v1.2：与角色模板同一闸/同一消费——
            # 声明挂 SummonDef，compile() 收尾并入全队 decl 并集，引擎召唤布场时初始化）
            s_decls = self._parse_resource_decls(
                s.get("custom_resources") or {}, s_desc, str(sid), hooks_out)
            control = str(s.get("control", "auto"))
            if control not in ("auto", "manual"):
                raise ValueError(
                    f"{s_desc}: control 词表仅 auto|manual（得到 {control!r}）——"
                    f"auto=回合全自动（默认，多数忆灵），manual=回合玩家操控（死龙族）")
            defs[str(sid)] = SummonDef(
                owner_id=owner.actor_id,
                actor=summon_actor,
                inheritance=("full" if inheritance == "full"
                             else "none" if inheritance == "none"
                             else tuple(str(f) for f in inheritance)),
                max_hp_ratio=float(max_hp_ratio),
                resource_decls=s_decls,
                control=control,
            )
        return defs

    # ------------------------------------------------------------------
    # modifier / hook 校验（编译期闸：未知键 + 枚举 + effect_type 白名单 + 表达式预编译）
    # ------------------------------------------------------------------

    def _validate_modifier_spec(self, spec: Dict[str, Any], where: str,
                                extra_self_fields: Sequence[str] = (),
                                param_ctx: Optional[_SkillParams] = None) -> None:
        """modifier dict 声明：未知键 diff + 枚举字段校验（stack_mode/tick_anchor/effect_scope）
        + duration dict 糖形态校验（§4.14）+ stat_effects 键错拼告警（开放命名空间不硬闸，词表外 warn）
        + scaling_effects 形状校验 + hit_condition 预编译（B8 同口径：非法表达式编译期炸）.

        param() 替换（05_effects §5.1）就地写回 spec——调用方须让产物流入下游构造
        （action apply_modifiers 的 YAML dict 即下游拷贝源；hook apply_modifier 由
        _validate_effects 回写 eff["modifier"]）。
        """
        _check_keys(spec, _MODIFIER_SPEC_KEYS, where=where)
        # 容器类型闸（编译期抓形状错，反馈须能被标注自愈环消费——漏到运行期就是
        # TypeError/AttributeError 谜语：1207 grants_immune:true、1504 stat_effects:list 病例）
        for k in ("stat_effects", "scaling_effects", "override_effects", "shield"):
            v = spec.get(k)
            if v is not None and not isinstance(v, dict):
                raise ValueError(f"{where} 的 {k} 须为 mapping，实得 {type(v).__name__}")
        for k in ("weakness_add", "grants_immune"):
            v = spec.get(k)
            if v is not None and not isinstance(v, (list, tuple)):
                raise ValueError(f"{where} 的 {k} 须为 list，实得 {type(v).__name__}")
        _check_grants_immune_literal(spec.get("grants_immune"), where)
        # shield 数值块（04_modifier §4.15）：键 diff + accumulate/cap 配对与形状闸
        sh = spec.get("shield")
        if sh is not None:
            _check_keys(sh, _SHIELD_BLOCK_KEYS, where=f"{where} shield")
            acc = sh.get("accumulate")
            if acc is not None and not (isinstance(acc, str) and acc.strip()):
                raise ValueError(f"{where} shield 的 accumulate 须为非空字符串池名")
            cap = sh.get("cap")
            if cap is not None:
                if not acc:
                    raise ValueError(
                        f"{where} shield 的 cap 须配 accumulate（独立实例无池可封——语义死键，"
                        "04_modifier §4.15）")
                if not isinstance(cap, dict):
                    raise ValueError(f"{where} shield 的 cap 须为 mapping，实得 {type(cap).__name__}")
                _check_keys(cap, _SHIELD_CAP_KEYS, where=f"{where} shield cap")
                mult = cap.get("multiplier", 1.0)
                if isinstance(mult, str):
                    # cap.multiplier 同接 param()（三月七 1304 封顶倍率随档实证——
                    # 与 scaling/flat 同槽口径；替换后须为字面量）
                    mult2 = (param_ctx or _NO_PARAMS).substitute(
                        mult, where=f"{where} shield cap multiplier")
                    try:
                        cap["multiplier"] = mult = float(mult2)
                    except (ValueError, TypeError):
                        raise ValueError(
                            f"{where} shield cap 的 multiplier 是数值/param 字面量槽——"
                            f"替换后仍非字面量（实得 {mult2!r}）") from None
                if isinstance(mult, bool) or not isinstance(mult, (int, float)) or mult <= 0:
                    raise ValueError(f"{where} shield cap 的 multiplier 须为正数，实得 {mult!r}")
        # params 引用取档（05_effects §5.1）：一切表达式字符串槽先替换再过预编译闸；
        # stat_effects 纯字面量回 float 主通道（表达式字符串槽留给真表达式——蒙福者快照族）
        sub = (param_ctx or _NO_PARAMS).substitute
        for k in ("enable_if", "hit_condition"):
            v = spec.get(k)
            if isinstance(v, str):
                spec[k] = sub(v, where=f"{where} {k}")
                _check_no_hook_chance(spec[k], f"{where} {k}")
        # 病族闸：死键硬闸（stat_effects/stat_exprs 共用——命中即炸带正解）
        _check_dead_stat_keys((spec.get("stat_effects") or {}).keys(), f"{where} stat_effects")
        _check_dead_stat_keys((spec.get("stat_exprs") or {}).keys(), f"{where} stat_exprs")
        for stat, v in list((spec.get("stat_effects") or {}).items()):
            if isinstance(v, str):
                v2 = sub(v, where=f"{where} stat_effects[{stat!r}]")
                try:
                    spec["stat_effects"][stat] = float(v2)
                except ValueError:
                    spec["stat_effects"][stat] = v2
                    _check_no_hook_chance(v2, f"{where} stat_effects[{stat!r}]")
        for stat, v in list((spec.get("stat_exprs") or {}).items()):
            if isinstance(v, str):
                spec["stat_exprs"][stat] = sub(v, where=f"{where} stat_exprs[{stat!r}]")
                _check_no_hook_chance(spec["stat_exprs"][stat],
                                      f"{where} stat_exprs[{stat!r}]")
        # 病族闸（warn）：表达式烘焙件缺 stack_mode——refresh 重挂只刷层数/时长、烘焙留旧值
        #（1207 驭空号令重烘链全挂 0 实证）；重烘语义须 stack_mode: "replace"。
        # 判定点在 float 化之后——残留的 str 才是真表达式（纯数值串不扰）
        if spec.get("stack_mode") is None and any(
                isinstance(v, str) for v in (spec.get("stat_effects") or {}).values()):
            warnings.warn(
                f"{where} 的 stat_effects 含表达式烘焙值但未声明 stack_mode——refresh 重挂"
                f"只刷层数/时长、烘焙留旧值（1207 驭空案）；重烘语义写 stack_mode: \"replace\"",
                stacklevel=3,
            )
        # shield 结构槽 param() 取档（B27 #6 收编——三月七 1304 护盾随档实证）：scaling/flat
        # （与 cap 的 scaling/flat）字符串值先替换；**只收数值/param 字面量**——替换后仍非
        # 字面量=表达式槽未接线，编译期炸指路（护盾公式形状走 scaling+flat 声明，不写表达式）
        if sh is not None:
            for blk in ([sh] + ([sh["cap"]] if isinstance(sh.get("cap"), dict) else [])):
                b_where = f"{where} shield" + (" cap" if blk is not sh else "")
                for key in ("flat",):
                    v = blk.get(key)
                    if isinstance(v, str):
                        v2 = sub(v, where=f"{b_where} {key}")
                        try:
                            blk[key] = float(v2)
                        except ValueError:
                            raise ValueError(
                                f"{b_where} 的 {key} 是数值/param 字面量槽——替换后仍非字面量"
                                f"（实得 {v2!r}；表达式槽未接线，护盾公式走 scaling+flat 声明）") from None
                for stat, v in list((blk.get("scaling") or {}).items()):
                    if isinstance(v, str):
                        v2 = sub(v, where=f"{b_where} scaling[{stat!r}]")
                        try:
                            blk["scaling"][stat] = float(v2)
                        except ValueError:
                            raise ValueError(
                                f"{b_where} 的 scaling[{stat!r}] 是数值/param 字面量槽——"
                                f"替换后仍非字面量（实得 {v2!r}）") from None
        _check_enum(spec.get("stack_mode"), STACK_MODES, where=where, field="stack_mode")
        _check_enum(spec.get("tick_anchor"), TICK_ANCHORS, where=where, field="tick_anchor")
        _check_enum(spec.get("effect_scope"), EFFECT_SCOPES, where=where, field="effect_scope")
        # 资源上限覆写成对闸（16 §16.12）：target_resource 与 max_override 必须同写
        # （单写语义残缺=静默写废），max_override 须为正数
        tr = spec.get("target_resource")
        mo = spec.get("max_override")
        if (tr is None) != (mo is None):
            raise ValueError(
                f"{where} 资源上限覆写两键须成对：target_resource 与 max_override 同写"
                f"（16_custom_resources §16.12——单写语义残缺）")
        if mo is not None and (isinstance(mo, bool) or not isinstance(mo, (int, float)) or mo <= 0):
            raise ValueError(f"{where} 的 max_override 须为正数（覆写后的资源上限值）")
        # override 互斥（13_validator §13.3）：同一 modifier 同一 stat 不得同时携带
        # override 与 flat/scaling（语义互相覆盖=静默写废一边）
        ovl = set(spec.get("override_effects") or {})
        if ovl:
            clash = ovl & (set(spec.get("stat_effects") or {})
                           | set(spec.get("scaling_effects") or {}))
            if clash:
                raise ValueError(
                    f"{where} override 互斥：stat {sorted(clash)} 同时出现在 override_effects"
                    f" 与 flat/scaling（同 modifier 只许一种写法，见 04_modifier §4.2）")
        dur = spec.get("duration")
        if isinstance(dur, dict):
            d_where = f"{where} duration"
            _check_keys(dur, _DURATION_DICT_KEYS, where=d_where)
            _check_enum(dur.get("tick_on"), DURATION_TICK_ON, where=d_where, field="tick_on")
            if "until" in dur:
                raise ValueError(
                    f"{d_where} 的 until 事件到期形态未落地（04_modifier §4.14 设计预览）——"
                    "已落地形态：int 直给 / {value, tick_on}")
        _warn_unknown_stat_keys(spec.get("stat_effects"), where)
        # stat_effects 字符串值（蒙福者快照族"暴伤=施加者暴伤×比例"现场求值槽）：
        # 表达式预编译 + `$self` 字段存在性（运行时才烘焙的值在此先过闸——LLM 错拼高发地）
        for stat, v in (spec.get("stat_effects") or {}).items():
            if isinstance(v, str):
                try:
                    self.expr.compile(v, layer="effect")
                except Exception as e:
                    raise ValueError(f"{where} stat_effects[{stat!r}] 表达式非法：{e}") from e
                _check_self_ns_fields(v, where=f"{where} stat_effects[{stat!r}]",
                                      extra=extra_self_fields)
        for stat, v in (spec.get("scaling_effects") or {}).items():
            if not (isinstance(v, (list, tuple)) and len(v) == 2):
                raise ValueError(
                    f"{where} 的 scaling_effects[{stat!r}] 形状须为 [source_stat, ratio]"
                    f"（Layer 2 转化：stat += source_L1 × ratio）")
        hit_condition = spec.get("hit_condition")
        if hit_condition is not None:
            try:
                self.expr.compile(str(hit_condition), layer="effect")
            except Exception as e:
                raise ValueError(f"{where} 的 hit_condition 表达式非法：{e}") from e
        # 条件光环（04_modifier §4.16）：enable_if / stat_exprs 同 hit_condition 口径——
        # 声明期预编译 + `$self` 字段闸（运行期求值失败按不生效，语法错在此拦截）
        enable_if = spec.get("enable_if")
        if enable_if is not None:
            try:
                self.expr.compile(str(enable_if), layer="effect")
            except Exception as e:
                raise ValueError(f"{where} 的 enable_if 表达式非法：{e}") from e
            _check_self_ns_fields(str(enable_if), where=f"{where} enable_if",
                                  extra=extra_self_fields)
        stat_exprs = spec.get("stat_exprs")
        if stat_exprs is not None and not isinstance(stat_exprs, dict):
            raise ValueError(f"{where} 的 stat_exprs 须为 mapping，实得 {type(stat_exprs).__name__}")
        _warn_unknown_stat_keys(stat_exprs, where)
        for stat, v in (stat_exprs or {}).items():
            try:
                self.expr.compile(str(v), layer="effect")
            except Exception as e:
                raise ValueError(f"{where} stat_exprs[{stat!r}] 表达式非法：{e}") from e
            _check_self_ns_fields(str(v), where=f"{where} stat_exprs[{stat!r}]",
                                  extra=extra_self_fields)

    def _validate_effects(self, effects: List[Dict[str, Any]], source_desc: str,
                          extra_self_fields: Sequence[str] = (),
                          param_ctx: Optional[_SkillParams] = None,
                          resources_ctx: Optional[Dict[str, Any]] = None,
                          resource_writes: Container[str] = (),
                          event_ns: Optional[str] = None) -> None:
        """hook effects 编译期闸（与引擎侧 _run_hook_effect（sim/hooks.py HookRuntime）同读 effect_types 单一事实源）.

        三道：effect_type 白名单（未实现=编译期炸）→ 参数键 diff（错拼静默丢的防线）
        → 表达式槽预编译（B8 同口径：condition 早有闸，effects 数值槽补齐）。
        param() 替换（05_effects §5.1）先于一切闸——产物是字面量/常规表达式。
        """
        sub = (param_ctx or _NO_PARAMS).substitute
        for i, eff in enumerate(effects):
            e_desc = f"{source_desc} effects[{i}]"
            for slot in EFFECT_EXPR_SLOTS:
                v = eff.get(slot)
                if isinstance(v, str):
                    v2 = sub(v, where=f"{e_desc} 的 {slot}")
                    # 纯字面量回数值通道（与手写 amount: 10.0 同形；混写表达式留字符串槽）
                    try:
                        eff[slot] = float(v2)
                    except ValueError:
                        eff[slot] = v2
            if isinstance(eff.get("filter"), str):
                eff["filter"] = sub(eff["filter"], where=f"{e_desc} 的 filter")
            t = eff.get("effect_type")
            if t not in ENGINE_EFFECT_TYPES:
                raise ValueError(
                    f"{e_desc} 未知 effect_type {t!r}（已实现集合："
                    f"{sorted(ENGINE_EFFECT_TYPES)}，见 sim_schema/effect_types.py）"
                )
            _eff_allowed = _EFFECT_COMMON_KEYS | _EFFECT_PARAM_KEYS[t]
            _misplaced = (set(eff) - _eff_allowed) & _MODIFIER_SPEC_KEYS
            if _misplaced:
                raise ValueError(
                    f"{e_desc} 的 {sorted(_misplaced)} 是 modifier 块字段——apply_modifier 的"
                    f"子块键（enable_if/stat_exprs/stat_effects/duration/grants_immune 等）一律"
                    f"写进 modifier: {{...}} 内，写在 effect 层必被键闸打回（1001 打标实证）")
            _check_keys(eff, _eff_allowed, where=e_desc)
            if t == "deal_damage" and eff.get("amount") is not None and (
                    eff.get("scaling_atk") is not None or eff.get("scaling_hp") is not None):
                # 基数区二态互斥（05_effects §造成伤害）：amount = ability_multiplier 直写
                # （ tally×比例族——资源值即基数）；scaling_atk/scaling_hp = 倍率×面板。
                # 同写语义互相覆盖=静默写废一边（override 互斥同口径，13_validator §13.3）
                raise ValueError(
                    f"{e_desc} deal_damage 的 amount 与 scaling_atk/scaling_hp 互斥"
                    f"（基数区二态：amount 直写 / 倍率×面板，只写一路）")
            if t == "deal_damage" and eff.get("action_type") is not None:
                # 伪行动类别声明槽（2026-09-14——飞霄 1220 终结技子击标 ultimate 首实例）：
                # hook 伤害缺省归 follow_up/additional——"终结技伤害"身份族（E6 穿透
                # scoped/Formshift「终结技视为追加攻击」反向族）须经本槽声明，
                # 枚举同 action 层 ACTION_TYPES
                _check_enum(eff["action_type"], ACTION_TYPES, where=e_desc,
                            field="action_type")
            if t == "deal_damage" and str(eff.get("category", "")) == "true" \
                    and eff.get("toughness_dmg") is not None:
                # 真伤不削韧（mechanics 02 §2.8：真实伤害=无属性固定伤害——无属性可匹配
                # 弱点，永不进韧性管线）。同写=语义自相矛盾，静默写废一边不可接受
                #（override 互斥同口径，13_validator §13.3）
                raise ValueError(
                    f"{e_desc} deal_damage 的 category 'true' 与 toughness_dmg 互斥"
                    f"（真伤无属性不削韧——要削韧请去掉 category）")
            if t == "deal_damage":
                # damage_type 二态（05_effects §造成伤害——动态元素族，丹恒•腾荒 1414 同袍
                # "相应属性"附加伤害首实例）：元素字面量直用；词表外按白名单表达式预编译
                #（element_of/who_has 宿主——求值结果运行期校验须为合法元素）；
                # category "true" 的真伤可写伪属性字面量 "true"（运行期真伤分支不读 damage_type）
                dt = eff.get("damage_type")
                if str(eff.get("category", "")) == "true" and dt == "true":
                    dt = None
                if isinstance(dt, str) and dt and dt.lower() not in _ELEMENTS:
                    try:
                        self.expr.compile(dt, layer="effect")
                    except Exception as ex:
                        raise ValueError(
                            f"{e_desc} deal_damage 的 damage_type 非法：{dt!r} 不是元素字面量"
                            f"（{sorted(_ELEMENTS)}），按表达式预编译亦失败：{ex}") from ex
                    if re.fullmatch(r"[A-Za-z_]\w*", dt.strip()):
                        # 裸标识符不可能是动态元素表达式（宿主函数调用才有意义）——按字面量错拼拦
                        raise ValueError(
                            f"{e_desc} deal_damage 的 damage_type 非法值 {dt!r}"
                            f"（元素词表 {sorted(_ELEMENTS)}；动态元素请用 element_of(...) 表达式）")
                    _check_self_ns_fields(dt, where=f"{e_desc} 的 damage_type",
                                          extra=extra_self_fields)
            sel = eff.get("target")
            if t == "remove_modifier":
                # modifier_id 与 filter 至少其一（05_effects §移除 modifier；filter=$mod 绑定
                # 按类摘除——长夜月天赋净化控制族）；filter 白名单预编译同 EFFECT_EXPR_SLOTS 口径
                if not eff.get("modifier_id") and not eff.get("filter"):
                    raise ValueError(
                        f"{e_desc} remove_modifier 的 modifier_id 与 filter 至少写其一"
                        f"（都写=交集；见 05_effects §移除 modifier 字段语境对账）")
                if eff.get("filter") is not None:
                    try:
                        self.expr.compile(str(eff["filter"]), layer="effect")
                    except Exception as ex:
                        raise ValueError(f"{e_desc} 的 filter 表达式非法：{ex}") from ex
                mc = eff.get("max_count")
                if mc is not None and (isinstance(mc, bool) or not isinstance(mc, int) or mc < 1):
                    raise ValueError(
                        f"{e_desc} remove_modifier 的 max_count 须为 ≥1 整数"
                        f"（逐目标 LIFO 截断——05_effects §移除 modifier 字段语境对账）")
            if t == "gain_energy" and sel is not None and not isinstance(sel, dict) \
                    and str(sel) not in ("self", "all_allies") \
                    and not str(sel).startswith("$event."):
                # gain_energy target 按 05_effects §回复能量收窄为二值 + '$event.<字段>'
                # 事件寻址通道（与运行时同词表；全词表放行曾让 highest_hp 等静默落入全体充能）
                # ——停云/星期日单充族实例已到达（131303 恢复目标能量上限 20%），通道开启；
                # dict 豁免：目标代数通用通道（藿藿 1217 终结技"excluding this unit"排自身实证）
                raise ValueError(
                    f"{e_desc} gain_energy 的 target 非法值 {sel!r}"
                    f"（合法集合：['all_allies', 'self'] + '$event.<字段>' + 代数 dict，"
                    f"见 05_effects §回复能量）"
                )
            if t in ("gain_resource", "set_resource") \
                    and str(eff.get("resource_id", "")) == "energy":
                # 病族闸：energy 是内建资源——custom_resources/gain_resource 只装自定义资源
                #（1210 桂乃芬 E4 实证）；能量机制走 gain_energy 钩 / action energy_gain
                raise ValueError(
                    f"{e_desc} 的 resource_id 'energy' 是内建资源——能量走 gain_energy 钩"
                    f" / action 层 energy_gain（1210 桂乃芬实证——1004/1103 同口径）")
            if sel is not None and isinstance(sel, dict):
                # 目标代数 dict（B31）：键 diff + pool/take/mode 词表 + where/order_by 预编译
                # （where/order_by 先过 param() 取档就地写回——藿藿 1217 加强版阈值实证：
                # 未替换会被白名单当未知函数拒，槽同 EFFECT_EXPR_SLOTS 口径 B27 #6 同族）
                from hsr_nous.sim.target_algebra import validate_algebra
                for _ak in ("where", "order_by"):
                    if isinstance(sel.get(_ak), str):
                        sel[_ak] = sub(sel[_ak], where=f"{e_desc} target {_ak}")
                validate_algebra(sel, where=f"{e_desc} target", expr=self.expr, allow_pool=True)
            elif sel is not None and str(sel).startswith("$event."):
                if event_ns is not None:
                    _check_event_ns_fields(str(sel), event_ns, where=f"{e_desc} 的 target")
            elif sel is not None and str(sel) not in HOOK_TARGET_SELECTORS:
                raise ValueError(
                    f"{e_desc} 未知 target 选择器 {sel!r}（合法集合："
                    f"{sorted(HOOK_TARGET_SELECTORS)} + '$event.<字段>' + 代数 dict）"
                )
            if t == "apply_modifier":
                mod_spec = dict(eff.get("modifier") or {})
                self._validate_modifier_spec(
                    mod_spec, f"{e_desc} modifier",
                    extra_self_fields=extra_self_fields, param_ctx=param_ctx)
                # param() 替换就地写回——产物随 eff 进 CompiledHook（05_effects §5.1）
                eff["modifier"] = mod_spec
            for slot in EFFECT_EXPR_SLOTS:
                v = eff.get(slot)
                if isinstance(v, str):
                    try:
                        self.expr.compile(v, layer="effect")
                    except Exception as e:
                        raise ValueError(f"{e_desc} 的 {slot} 表达式非法：{e}") from e
                    _check_no_hook_chance(v, f"{e_desc} 的 {slot}")
                    _check_self_ns_fields(v, where=f"{e_desc} 的 {slot}",
                                          extra=extra_self_fields)
                    if resources_ctx is not None:
                        _check_res_refs(v, resources_ctx, where=f"{e_desc} 的 {slot}",
                                        written=resource_writes)
                    if event_ns is not None:
                        _check_event_ns_fields(v, event_ns, where=f"{e_desc} 的 {slot}")

    def _compile_hooks(self, items: List[Dict[str, Any]], source_desc: str,
                       owner_id: str, out: List[Any],
                       resources_out: Optional[Dict[str, List[str]]] = None,
                       extra_self_fields: Sequence[str] = (),
                       param_ctx: Optional[_SkillParams] = None) -> None:
        """模板/秘技 hooks 块 → CompiledHook 追加进 out.

        编译期闸：hook 键 diff → event 对总线契约表（bus.py DEFAULT_CONTRACT）
        → condition 白名单预编译 → effects 三道（_validate_effects）。
        param() 替换（05_effects §5.1）先于一切表达式闸。
        """
        from hsr_nous.sim.bus import DEFAULT_CONTRACT
        from hsr_nous.sim.compile.compiled import CompiledHook
        from hsr_nous.sim.compile.sugar import desugar

        sub = (param_ctx or _NO_PARAMS).substitute
        # 本块资源写账集（res_ 对账闸的"内部闩可证真"判定——白厄 _immune_used 形态入场置零族）
        written_rids = frozenset(
            str(e.get("resource_id"))
            for hh in items for e in (hh.get("effects") or [])
            if isinstance(e, dict) and e.get("effect_type") in _RESOURCE_WRITE_TYPES
            and e.get("resource_id"))
        for _h_idx, h in enumerate(items):
            _check_keys(h, _HOOK_KEYS, where=f"{source_desc} 的 hook")
            event = str(h.get("event", ""))
            if event not in DEFAULT_CONTRACT:
                raise ValueError(
                    f"{source_desc} 的 hook 引用了未登记事件 {event!r}"
                    f"（契约表见 sim/bus.py DEFAULT_CONTRACT）"
                )
            effects = [dict(x) for x in h.get("effects") or []]
            cond_src = h.get("condition")
            if cond_src:
                cond_src = sub(str(cond_src),
                               where=f"{source_desc} hook({event}) condition")
                _check_no_hook_chance(cond_src, f"{source_desc} hook({event}) condition")
                _check_self_ns_fields(cond_src, where=f"{source_desc} hook({event}) condition",
                                      extra=extra_self_fields)
            # trigger_limit 糖（04_modifier §4.12①，B24 首糖）：展开为计数器四联件
            # （资源注册 + 充满 hooks + 门控并入 condition + 消耗追加 effects）——VM 只见展开产物
            if h.get("trigger_limit") is not None:
                if event == "on_battle_start":
                    raise ValueError(
                        f"{source_desc} 的 hook(on_battle_start) 挂 trigger_limit"
                        f"——v1 不收（初始充满与同事件快照的时序边未钉，实例到了再上）")
                if resources_out is None:
                    raise ValueError(
                        f"{source_desc} 的 hook({event}) 挂 trigger_limit"
                        f"——v1 仅角色模板/星魂 hooks 块（资源注册通道未接）")
                exp = desugar("trigger_limit", h["trigger_limit"],
                              owner_hook_desc=f"{source_desc} hook({event})#{_h_idx}",
                              contract=DEFAULT_CONTRACT)
                resources_out.setdefault(owner_id, {})
                if exp["resource_id"] not in resources_out[owner_id]:
                    # 计数资源 decl（max=额度——充满/消耗过统一入口时白拿 clamp 语义）
                    resources_out[owner_id][exp["resource_id"]] = {
                        "max": float(exp["count"]), "current": 0.0, "overflow_mode": "none"}
                cond_src = f"({cond_src}) and ({exp['gate']})" if cond_src else exp["gate"]
                effects.append(dict(exp["consume_effect"]))
                # 充满 hooks 排在本 hook 之前（开局充满 + 重置点充满——先注满后门控才有意义）
                self._compile_hooks(exp["charge_hooks"], f"{source_desc} trigger_limit",
                                    owner_id, out, param_ctx=param_ctx)
            if cond_src and resources_out is not None:
                # res_ 平铺键对账（trigger_limit 计数器注册之后——糖门控自带 res__tl_ 引用）
                _check_res_refs(cond_src, resources_out.get(owner_id, {}),
                                where=f"{source_desc} hook({event}) condition",
                                written=written_rids)
            if cond_src:
                # $event 字段对账（载荷注册表——错拼=运行期 B8 静默死钩）
                _check_event_ns_fields(cond_src, event,
                                       where=f"{source_desc} hook({event}) condition")
            self._validate_effects(effects, f"{source_desc} hook({event})",
                                   extra_self_fields=extra_self_fields, param_ctx=param_ctx,
                                   resources_ctx=(resources_out.get(owner_id, {})
                                                  if resources_out is not None else None),
                                   resource_writes=written_rids, event_ns=event)
            # 累积模式（§23.9）：flush_triggers 必填且逐事件过契约闸；target_filter 白名单预编译
            accumulated = bool(h.get("accumulated", False))
            flush = [str(e) for e in (h.get("flush_triggers") or [])]
            if accumulated and not flush:
                raise ValueError(
                    f"{source_desc} 的 hook({event}) 声明 accumulated: true 但无 flush_triggers"
                    f"——队列永不消费=静默吞（编译期炸，见 23_event_hook_system §23.9）")
            for fe in flush:
                if fe not in DEFAULT_CONTRACT:
                    raise ValueError(
                        f"{source_desc} 的 hook({event}) flush_triggers 引用未登记事件 {fe!r}")
            tf_src = h.get("target_filter")
            if tf_src and not accumulated:
                raise ValueError(
                    f"{source_desc} 的 hook({event}) 写了 target_filter 但未声明 accumulated: true"
                    f"——过滤只在累积模式有消费点（静默忽略=幻觉温床，编译期炸指路）")
            if tf_src and accumulated:
                tf_src = sub(str(tf_src),
                             where=f"{source_desc} hook({event}) target_filter")
                _check_event_ns_fields(tf_src, event,
                                       where=f"{source_desc} hook({event}) target_filter")
            out.append(CompiledHook(
                owner_id=owner_id,
                event=event,
                condition_expr=self.expr.compile(cond_src, layer="effect") if cond_src else None,
                effects=tuple(effects),
                accumulated=accumulated,
                flush_triggers=tuple(flush),
                target_filter_expr=(self.expr.compile(tf_src, layer="effect")
                                    if tf_src and accumulated else None),
            ))

    # ------------------------------------------------------------------
    # 遗器词条计算
    # ------------------------------------------------------------------

    def apply_relics(self, stats: StatBlock, relics: Dict[str, Dict[str, Any]]) -> None:
        """把遗器主/副词条累进面板（满级主词条 + roll 数 × 副词条高档值）.

        词条数值查 rulebook relic_affixes 表（pipeline 数据镜像，见 _AFFIX_FIELD 注释）；
        不在表的词条编译期炸（旧版静默吞——编造词条/错拼零提示，与 _check_keys 同哲学改报错）。
        百分比词条按**基础值**（白值）乘算——合成公式唯一来源 = rulebook zones.stat_with_pct
        （01_formula §1.12 镜像），此处为编译期同口径喂入，不复述公式。
        """
        from hsr_nous.sim_schema.rulebook import get_rulebook

        tables = get_rulebook().relic_affixes
        main_table, sub_table = tables.get("main") or {}, tables.get("sub") or {}
        base_hp, base_atk, base_def = stats.hp, stats.atk, stats.def_
        for slot, relic in (relics or {}).items():
            main = relic.get("main")
            if main is not None:
                field, val = self._affix_lookup(str(main), main_table, where=f"遗器 {slot} 主词条")
                self._add_stat(stats, field, val, base_hp, base_atk, base_def)
            for sub_id, rolls in (relic.get("subs") or {}).items():
                field, per = self._affix_lookup(str(sub_id), sub_table, where=f"遗器 {slot} 副词条")
                self._add_stat(stats, field, per * float(rolls), base_hp, base_atk, base_def)

    @staticmethod
    def _affix_lookup(affix_id: str, table: Dict[str, float], *, where: str) -> tuple[str, float]:
        """词条 id → (StatBlock 字段, 数值)：词表外/表外一律报错（带词条名）."""
        field = _AFFIX_FIELD.get(affix_id)
        if field is None:
            raise ValueError(
                f"{where} 未知词条 {affix_id!r}（合法集合：{sorted(_AFFIX_FIELD)}）"
            )
        if affix_id not in table:
            raise ValueError(
                f"{where} 词条 {affix_id!r} 不存在于该表（合法集合：{sorted(table)}）——"
                f"词表与数值表的一致性由遗器词条镜像闸保证，此报错=词条用错了位置"
            )
        return field, float(table[affix_id])

    @staticmethod
    def _add_stat(stats: StatBlock, field: str, val: float, base_hp: float, base_atk: float, base_def: float) -> None:
        if field.startswith("dmg_"):
            element = field.removeprefix("dmg_")
            stats.dmg_bonus[element] = stats.dmg_bonus.get(element, 0.0) + val
        elif field == "hp_pct":
            stats.hp += base_hp * val
        elif field == "atk_pct":
            stats.atk += base_atk * val
        elif field == "def_pct":
            stats.def_ += base_def * val
        elif field == "def_":
            stats.def_ += val
        else:
            setattr(stats, field, getattr(stats, field) + val)

    # ------------------------------------------------------------------
    # 策略
    # ------------------------------------------------------------------

    def _compile_policy(self, spec: Dict[str, Any]) -> CompiledPolicy:
        _check_keys(spec, _POLICY_KEYS, where="policy")
        _check_enum(spec.get("ult_timing"), ULT_TIMINGS, where="policy", field="ult_timing")
        # B4 回放变体（14_policy）：mode/script 编译期闸——mode 枚举；scripted/hybrid 必有
        # script 且逐条键闸/turn≥1；rule_based 写 script 指路炸（静默吞=回放轴跑飞）
        mode = str(spec.get("mode", "rule_based") or "rule_based")
        _check_enum(mode, _POLICY_MODES, where="policy", field="mode")
        script_spec = spec.get("script") or []
        if mode == "rule_based" and script_spec:
            raise ValueError("policy 是 rule_based 但写了 script——脚本只在 scripted/hybrid 有消费点")
        if mode in ("scripted", "hybrid") and not script_spec:
            raise ValueError(f"policy mode: {mode!r} 必须配非空 script")
        script: List[Dict[str, Any]] = []
        for i, e in enumerate(script_spec):
            _check_keys(e, _POLICY_SCRIPT_KEYS, where=f"policy script[{i}]")
            turn = e.get("turn")
            if not isinstance(turn, int) or turn < 1:
                raise ValueError(f"policy script[{i}] 的 turn 须为 ≥1 的整数，实得 {turn!r}")
            if not e.get("actor") or not e.get("action"):
                raise ValueError(f"policy script[{i}] 缺 actor/action：{e!r}")
            script.append({"turn": turn, "actor": str(e["actor"]),
                           "action": str(e["action"]),
                           **({"target": str(e["target"])} if e.get("target") else {})})

        def rules_of(items: List[Dict[str, Any]], with_selector: bool, kind: str) -> tuple[CompiledPolicyRule, ...]:
            out = []
            for r in items or []:
                _check_keys(r, _POLICY_RULE_KEYS, where=f"policy {kind}")
                sel = r.get("selector")
                if with_selector and sel is not None:
                    # 选择器编译期闸（与 hook 同纪律；词表 = 引擎 _apply_selector 实现集）
                    if isinstance(sel, str):
                        _check_enum(sel, POLICY_TARGET_SELECTORS, where=f"policy {kind}", field="selector")
                    elif isinstance(sel, dict):
                        from hsr_nous.sim.target_algebra import (
                            TARGET_ALGEBRA_KEYS, validate_algebra,
                        )
                        if set(sel) & TARGET_ALGEBRA_KEYS:
                            # 目标代数 dict（B31；policy 池=候选集，不允许 pool 键）
                            validate_algebra(sel, where=f"policy {kind} selector",
                                             expr=self.expr, allow_pool=False)
                        else:
                            _check_enum(sel.get("type"), POLICY_SELECTOR_DICT_TYPES,
                                        where=f"policy {kind}", field="selector.type")
                    else:
                        raise ValueError(
                            f"policy {kind} 的 selector 须为字符串或参数化 dict，"
                            f"收到 {type(sel).__name__}：{sel!r}")
                out.append(CompiledPolicyRule(
                    action=r.get("action", ""),
                    priority=int(r.get("priority", 0)),
                    condition_expr=self.expr.try_compile(r.get("condition", "true")),
                    selector=(r.get("selector") if with_selector else None),
                    description=r.get("description", ""),
                ))
            return tuple(sorted(out, key=lambda r: -r.priority))

        return CompiledPolicy(
            name=spec.get("name", "default"),
            action_rules=rules_of(spec.get("action_rules"), with_selector=False, kind="action_rules"),
            target_rules=rules_of(spec.get("target_rules"), with_selector=True, kind="target_rules"),
            parameters=dict(spec.get("parameters") or {}),
            ult_timing=spec.get("ult_timing", "after_action"),
            mode=mode,
            script=tuple(script),
        )

    # ------------------------------------------------------------------
    # 光锥/遗器套装归并（编译期并进所属 actor 三桶，00_overview 数据流）
    # ------------------------------------------------------------------

    def _merge_light_cone(self, stats: StatBlock, spec: Dict[str, Any], *,
                          roots: Sequence[Union[str, Path]], actor_id: str) -> tuple[List[Any], Dict[str, float]]:
        """light_cone_template 引用 → 白值三围归并进面板 + 叠影绑定求值 + 机制 hooks 通道.

        白值并入后 pct 族基数口径自动正确（游戏公式：白值 = 角色 + 光锥，mechanics 01 §1.2）。
        variable_bindings（15_data_separation 绑定层 v1，光锥通道）按 build 叠影求值 →
        绑定参数（经 CompiledEncounter 进引擎 `$self.<param>` 命名空间——hooks 表达式消费）；
        模板 hooks 块与角色模板同一编译闸（owner=装备者，绑定参数作 `$self` 字段放行集）。
        notes 态自由文本不结算。
        返回 (lc_hooks, binding_params)；无光锥引用 → ([], {})。
        """
        ref = spec.get("light_cone_template")
        if not ref:
            return [], {}
        tpl = self._load_template("light_cones", str(ref), roots=roots)
        _check_keys(tpl, _LIGHT_CONE_TEMPLATE_KEYS, where=f"光锥模板 {ref}")
        base = tpl.get("base_stats", {})
        stats.hp += float(base.get("hp", 0.0))
        stats.atk += float(base.get("atk", 0.0))
        stats.def_ += float(base.get("def", 0.0))
        lc_spec = spec.get("light_cone") or {}
        params = self._eval_variable_bindings(
            tpl.get("variable_bindings") or [], tpl.get("lookup_tables") or {},
            superimposition=int(lc_spec.get("superimposition", 1)),
            where=f"光锥模板 {ref}")
        lc_hooks: List[Any] = []
        self._compile_hooks(tpl.get("hooks") or [], f"光锥模板 {ref}", actor_id, lc_hooks,
                            extra_self_fields=tuple(params.keys()))
        return lc_hooks, params

    def _eval_variable_bindings(self, bindings: List[Any], tables: Dict[str, Any], *,
                                superimposition: int, where: str) -> Dict[str, float]:
        """variable_bindings 求值（绑定层 v1）：`self.<name> = <表达式>` → {name: 数值}.

        表达式上下文：`$build.light_cone.superimposition`；宿主函数
        `lookup_table("<表名>", index=<下标表达式>)`——未知表名/越界大声炸（不静默吞）。
        """
        params: Dict[str, float] = {}

        def _lookup(name: Any, index: Any) -> float:
            col = tables.get(str(name))
            if col is None:
                raise ValueError(
                    f"{where}：lookup_table 引用未知表 {name!r}（已有：{sorted(tables)}）")
            i = int(index)
            if not (0 <= i < len(col)):
                raise ValueError(
                    f"{where}：lookup_table({name!r}, index={i}) 越界（表长 {len(col)}）")
            return float(col[i])

        ctx = {"build": types.SimpleNamespace(
            light_cone=types.SimpleNamespace(superimposition=superimposition))}
        for stmt in bindings:
            m = re.match(r"^\s*self\.(\w+)\s*=\s*(.+?)\s*$", str(stmt))
            if not m:
                raise ValueError(
                    f"{where}：variable_bindings 语句形态非法 {stmt!r}"
                    f"（须为 `self.<名> = <表达式>`，见 15_data_separation）")
            name, rhs = m.group(1), m.group(2)
            params[name] = float(self.expr.evaluate(
                self.expr.compile(rhs, layer="formula"), ctx,  # formula 层才带 lookup_table 白名单
                functions={"lookup_table": _lookup}))
        return params

    def _merge_relic_sets(self, spec: Dict[str, Any], *, roots: Sequence[Union[str, Path]],
                          actor_id: str, hooks_out: List[Any]) -> List[Any]:
        """relics 部件的 set_id 聚合计数（15 章形状）→ 满 2/4 件触发套装效果：
        stat_effects 转初始 Modifier（纯数值通道）；hooks 块进编译闸（机制通道，owner=装备者）."""
        from collections import Counter

        from hsr_nous.sim.state import Modifier

        counts: Counter = Counter(
            str(r.get("set_id")) for r in (spec.get("relics") or {}).values()
            if isinstance(r, dict) and r.get("set_id")
        )
        mods: List[Any] = []
        for set_id, n in counts.items():
            tpl = self._load_template("relics", set_id, roots=roots)
            _check_keys(tpl, _RELIC_TEMPLATE_KEYS, where=f"遗器套装模板 {set_id}")
            for need, key in ((2, "set_2pc"), (4, "set_4pc")):
                if n < need or key not in tpl:
                    continue
                piece = tpl[key] or {}
                _check_keys(piece, _RELIC_SET_PIECE_KEYS, where=f"遗器套装模板 {set_id} {key}")
                eff = piece.get("stat_effects")
                if eff:
                    mods.append(Modifier(
                        modifier_id=f"RELIC_{tpl['relic_set_id']}_{need}PC",
                        name=f"{tpl['name']} {need}pc",
                        modifier_type="buff", duration=0, dispellable=False,
                        stat_effects={k: float(v) for k, v in eff.items()},
                        # F2 来源记账：遗器套装件（ref=套装名）
                        source_kind="relic", source_ref=str(tpl.get("name") or set_id),
                    ))
                # 套装机制 hooks（条件效果族——风套拉条/冰套暴伤族；与角色模板同一编译闸）
                self._compile_hooks(piece.get("hooks") or [],
                                    f"遗器套装模板 {set_id} {key}", actor_id, hooks_out)
        return mods

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------

    def _parse_resource_decls(
        self,
        cr: Dict[str, Any],
        where: str,
        owner_id: str,
        hooks_out: List[Any],
    ) -> Dict[str, Dict[str, Any]]:
        """custom_resources 值块 → 资源声明 dict（16_custom_resources §16.2/§16.12 v1）.

        max 截断 / current 初始化 / bank 溢出形态（自动注册 `<rid>_bank` + 返还 hook desugar）
        / provenance 来源记账；未消费键指路炸不静默吞。模板路径与 inline member 共用同一闸。
        """
        from hsr_nous.sim.bus import DEFAULT_CONTRACT
        from hsr_nous.sim.compile.compiled import CompiledHook

        _check_mapping(cr, where=where, field="custom_resources")
        decls: Dict[str, Dict[str, Any]] = {}
        for rid, rspec in cr.items():
            _check_mapping(rspec, where=f"{where} custom_resources", field=rid)
            if str(rid) == "energy":
                raise ValueError(
                    f"{where} custom_resources 声明内建资源 'energy'"
                    f"——energy 三段式（银枝双档族）v1 未接，现役 action 级"
                    f" energy_cost 已表达（16_custom_resources §16.12 注）")
            _check_keys(rspec, _RESOURCE_BLOCK_KEYS,
                        where=f"{where} custom_resources[{rid!r}]")
            for uk, ureason, ubad in (
                    ("scope", "scope: team（队级资源池）v1 未消费——B4 策略状态机同窗口",
                     rspec.get("scope") not in (None, "actor")),
                    ("host", "host != self（资源长在他人身上物化）v1 未消费——昔涟标注批同上",
                     rspec.get("host") not in (None, "self")),
                    ("persist_across_battles",
                     "persist_across_battles（跨战斗保留）挂起——低优先级（§16.14）",
                     bool(rspec.get("persist_across_battles"))),
                    ("activation_grant",
                     "activation_grant（激活提供值）v1 未消费——与 activate_ultimate effect 同批",
                     rspec.get("activation_grant") is not None)):
                if ubad:
                    raise ValueError(
                        f"{where} custom_resources[{rid!r}] 的 {uk}={rspec.get(uk)!r}"
                        f"——{ureason}（已登记未消费，写了指路炸不静默吞）")
            mx = rspec.get("max", "inf")
            if not (isinstance(mx, (int, float)) or mx == "inf"):
                raise ValueError(
                    f"{where} custom_resources[{rid!r}] 的 max 须为数值或 'inf'，实得 {mx!r}")
            decl: Dict[str, Any] = {"max": mx,
                                    "current": float(rspec.get("current", 0.0) or 0.0)}
            if rspec.get("provenance"):
                decl["provenance"] = True
            if rspec.get("ult_threshold") is not None:
                ut = rspec["ult_threshold"]
                if isinstance(ut, list):
                    raise ValueError(
                        f"{where} custom_resources[{rid!r}] ult_threshold 多档列表"
                        f" v1 未消费（银枝双档现役 action 级 energy_cost 已表达；单值阈值可写）")
                decl["ult_threshold"] = float(ut)
            om = str(rspec.get("overflow_mode", "none") or "none")
            if om not in ("none", "bank"):
                raise ValueError(
                    f"{where} custom_resources[{rid!r}] overflow_mode 非法值 {om!r}")
            decl["overflow_mode"] = om
            if om == "bank":
                bm = rspec.get("bank_max")
                if not isinstance(bm, (int, float)):
                    raise ValueError(
                        f"{where} custom_resources[{rid!r}] overflow_mode: 'bank'"
                        f" 必须配数值 bank_max，实得 {bm!r}")
                br = str(rspec.get("bank_refund", "") or "")
                br_event = _BANK_REFUND_ALIASES.get(br, br)
                if br_event not in DEFAULT_CONTRACT:
                    raise ValueError(
                        f"{where} custom_resources[{rid!r}] bank_refund {br!r}"
                        f" 不是总线契约事件（别名映射：{_BANK_REFUND_ALIASES}）")
                decls[f"{rid}_bank"] = {"max": float(bm), "current": 0.0,
                                        "overflow_mode": "none"}
                # 返还 hook desugar（糖展开：两普通资源 + 返还 hook——引擎只见原语）
                hooks_out.append(CompiledHook(
                    owner_id=owner_id, event=br_event, condition_expr=None,
                    effects=({"effect_type": "refund_bank", "resource_id": str(rid)},),
                ))
            decls[str(rid)] = decl
        return decls

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------

    def compile(self, build: Dict[str, Any], *,
                template_roots: Optional[Sequence[Union[str, Path]]] = None) -> tuple[tuple[Actor, ...], Dict[str, List[Action]], CompiledPolicy, Dict[str, List[Any]], Dict[str, tuple[Any, str]], List[Any]]:
        """build.yaml 的 build 段 → (team, actions, policy, modifiers, state_configs, hooks).

        state_configs: {actor_id: (StateConfig, entry_action_id)}——模板 state_config 块；
        hooks: 模板 hooks 块的 CompiledHook 列表（机制自包含 DSL 的编译产物）；
        template_roots: 模板根注入（有序，先命中根生效）；None → DEFAULT_TEMPLATE_ROOTS（生产缺省）.
        """
        from hsr_nous.sim.state import Modifier, StateConfig

        _check_keys(build, _BUILD_KEYS, where="build")
        roots = (tuple(str(r) for r in template_roots)
                 if template_roots is not None else DEFAULT_TEMPLATE_ROOTS)
        self._param_ctx_by_actor = {}  # 复编译不串味（_compile_inline_character 重建）
        team: List[Actor] = []
        actions_by_actor: Dict[str, List[Action]] = {}
        modifiers_by_actor: Dict[str, List[Any]] = {}
        state_configs: Dict[str, tuple[Any, str]] = {}
        resource_decls_by_actor: Dict[str, Dict[str, Dict[str, Any]]] = {}
        hooks: List[Any] = []
        summon_defs: Dict[str, Any] = {}
        binding_params: Dict[str, Dict[str, float]] = {}
        techniques_by_actor: Dict[str, List[Dict[str, Any]]] = {}
        tp_bonus = 0
        for member in build.get("team", []):
            actor, actions = self._compile_inline_character(member, roots=roots)
            if len(team) >= 4:
                raise ValueError(
                    f"队伍人数超过上限 4（13_validator §13.3：角色数量上限 4 个）")
            lc_hooks, lc_params = self._merge_light_cone(
                actor.stats, member, roots=roots, actor_id=actor.actor_id)
            hooks.extend(lc_hooks)
            if lc_params:
                binding_params[actor.actor_id] = lc_params
            if member.get("relics"):
                self.apply_relics(actor.stats, member["relics"])
            team.append(actor)
            actions_by_actor[actor.actor_id] = actions
            # inline member 的 custom_resources 声明（与模板同一闸——16 §16.2 值块消费）
            if member.get("custom_resources"):
                idecls = self._parse_resource_decls(
                    member["custom_resources"], f"team member {actor.actor_id!r}",
                    actor.actor_id, hooks)
                resource_decls_by_actor.setdefault(actor.actor_id, {}).update(idecls)
            mods = self._merge_relic_sets(member, roots=roots,
                                          actor_id=actor.actor_id, hooks_out=hooks)
            if mods:
                modifiers_by_actor[actor.actor_id] = mods
            # 模板 state_config 块 → 引擎形态注册件
            ref = member.get("character_template")
            if ref is not None and not str(ref).startswith("inline"):
                tpl = self._load_character_template(
                    str(ref), roots=roots,
                    version=str(member.get("version") or "enhanced").lower())
                # 行迹 pct（trace_stat_effects）→ 初始 modifier（与遗器套装同通道；pct 白值口径由引擎结算）
                tse = tpl.get("trace_stat_effects")
                if tse:
                    _warn_unknown_stat_keys(tse, f"模板 {ref} trace_stat_effects")
                    modifiers_by_actor.setdefault(actor.actor_id, []).append(Modifier(
                        modifier_id=f"TRACE_{actor.actor_id}", name="行迹", modifier_type="buff",
                        duration=0, dispellable=False,
                        stat_effects={k: float(v) for k, v in tse.items()},
                        # F2 来源记账：行迹聚合作（多节点合一，ref 无单一节点可指 → 空）
                        source_kind="trace",
                    ))
                sc = tpl.get("state_config")
                # 模板 custom_resources 值块消费（16_custom_resources §16.2/§16.12 v1：
                # max 截断 / current 初始化 / bank 溢出形态（自动注册 <rid>_bank + 返还 hook
                # desugar）/ provenance 来源记账；未消费键指路炸，不静默吞）
                cr = tpl.get("custom_resources")
                if cr:
                    decls = self._parse_resource_decls(cr, f"模板 {ref}", actor.actor_id, hooks)
                    resource_decls_by_actor.setdefault(actor.actor_id, {}).update(decls)
                if sc:
                    _check_keys(sc, _STATE_CONFIG_KEYS, where=f"模板 {ref} state_config")
                    _warn_unknown_stat_keys(sc.get("stat_effects"), f"模板 {ref} state_config")
                    for cond in sc.get("exit_conditions") or []:
                        _check_keys(cond, _STATE_CONFIG_EXIT_CONDITION_KEYS,
                                    where=f"模板 {ref} state_config exit_conditions")
                    # stat_effects 字符串值过 param() 取档（05_effects §5.1 同口径——
                    # 昔涟 141503 #3 双方暴率并进形态标记族；纯字面量回 float 通道）
                    _sc_sub = (self._param_ctx_by_actor.get(actor.actor_id) or _NO_PARAMS).substitute

                    def _sc_stat_float(k: str, v: Any) -> float:
                        if not isinstance(v, str):
                            return float(v)
                        v2 = _sc_sub(v, where=f"模板 {ref} state_config stat_effects[{k!r}]")
                        try:
                            return float(v2)
                        except ValueError:
                            raise ValueError(
                                f"模板 {ref} state_config stat_effects[{k!r}] 是纯数值槽——"
                                f"param() 取档后须为字面量，不承接混写表达式（实得 {v2!r}）") from None

                    state_configs[actor.actor_id] = (StateConfig(
                        state=sc["state"],
                        replaces_actions={k: ([str(x) for x in v] if isinstance(v, list) else str(v))
                                          for k, v in (sc.get("replaces_actions") or {}).items()},
                        locked_actions=[str(x) for x in sc.get("locked_actions") or []],
                        exit_conditions=[dict(c) for c in sc.get("exit_conditions") or []],
                        stat_effects={k: _sc_stat_float(k, v)
                                      for k, v in (sc.get("stat_effects") or {}).items()},
                        final_action_id=str(sc.get("final_action_id", "")),
                        exit_remove_modifiers=[str(x) for x in sc.get("exit_remove_modifiers") or []],
                        banish_allies_on_enter=bool(sc.get("banish_allies_on_enter", False)),
                        countdown_spd_ratio=float(sc.get("countdown_spd_ratio", 1.0)),
                        # 数值=固定比例 | "uniform"=均匀随机（不 float——字符串要原样透传）
                        countdown_initial_ratio=sc.get("countdown_initial_ratio", 1.0),
                        name=str(sc.get("name", "")),
                        grants_immune=[str(x) for x in sc.get("grants_immune") or []],
                        entry_end_turn=bool(sc.get("entry_end_turn", True)),
                    ), str(sc.get("entry_action_id", "")))
                # 模板 techniques / team_modifiers 登记（战前秘技池与秘技表）
                if tpl.get("techniques"):
                    for t in tpl["techniques"]:
                        # 键闸不可绕：point_cost 错拼（point_costt）曾使点池校验读到默认 0
                        _check_keys(t, _TECHNIQUE_KEYS, where=f"模板 {ref} techniques")
                    techniques_by_actor[actor.actor_id] = [dict(t) for t in tpl["techniques"]]
                tm = tpl.get("team_modifiers")
                if tm:
                    _check_keys(tm, _TEAM_MODIFIER_KEYS, where=f"模板 {ref} team_modifiers")
                    tp_bonus += int(tm.get("technique_point_initial_bonus", 0) or 0)
                # 模板 hooks 块 → CompiledHook（编译期闸全家：键 diff/事件契约/condition+effects 预编译）
                _check_no_eidolon_in_mainline(tpl.get("hooks") or [], f"模板 {ref}")
                self._compile_hooks(tpl.get("hooks") or [], f"模板 {ref}", actor.actor_id, hooks,
                                    resources_out=resource_decls_by_actor,
                                    extra_self_fields=tuple(
                                        binding_params.get(actor.actor_id, {}).keys()),
                                    param_ctx=self._param_ctx_by_actor.get(actor.actor_id))
                # 模板 summons 块（12_summon）→ SummonDef 注册件（actions/hooks 与角色同闸；
                # 召唤物 hooks 此时 owner 未入场——HookRuntime 按 owner_id 查 state.actors，
                # 查无即跳过，入场后自然生效，无需运行时订阅）
                if tpl.get("summons"):
                    new_defs = self._compile_summons(tpl["summons"], actor, ref, hooks,
                                                     actions_by_actor,
                                                     param_ctx=self._param_ctx_by_actor.get(
                                                         actor.actor_id))
                    dup = set(new_defs) & set(summon_defs)
                    if dup:
                        raise ValueError(
                            f"召唤物 actor_id {sorted(dup)} 重复登记（跨模板撞 id——"
                            f"会在 state.actors 键控下静默互踩，编译期炸）")
                    summon_defs.update(new_defs)
                    # 召唤物 custom_resources 并入全队 decl 并集（12_summon v1.2——
                    # 收尾交叉校验的资源存在性口径与引擎 _resource_decls 同源；
                    # current 初始化在引擎召唤布场时，不在 setup）
                    for sid, d in new_defs.items():
                        if d.resource_decls:
                            resource_decls_by_actor.setdefault(sid, {}).update(d.resource_decls)

                # 星魂激活：member.eidolon: N → 模板 eidolons E1..EN 生效
                from dataclasses import replace as _dc_replace
                eidolon_n = int(member.get("eidolon", 0) or 0)
                eidolons = tpl.get("eidolons") or {}
                for rank_key, e in eidolons.items():
                    if rank_key not in {f"E{i}" for i in range(1, 7)}:
                        raise ValueError(
                            f"模板 {ref} eidolons 含未知键 {rank_key!r}"
                            f"（合法集合：{[f'E{i}' for i in range(1, 7)]}）"
                        )
                    _check_keys(e, _EIDOLON_KEYS, where=f"模板 {ref} 星魂 {rank_key}")
                for rank in range(1, min(max(eidolon_n, 0), 6) + 1):
                    e = eidolons.get(f"E{rank}")
                    if not e:
                        continue
                    se = e.get("stat_effects")
                    if se:
                        _warn_unknown_stat_keys(se, f"模板 {ref} 星魂 E{rank}")
                        _check_dead_stat_keys(se.keys(), f"模板 {ref} 星魂 E{rank} stat_effects")
                        modifiers_by_actor.setdefault(actor.actor_id, []).append(Modifier(
                            modifier_id=f"EIDO_{actor.actor_id}_E{rank}",
                            name=str(e.get("name", f"E{rank}")), modifier_type="buff",
                            duration=0, dispellable=False,
                            stat_effects={k: float(v) for k, v in se.items()},
                        ))
                    # skill_level_overrides 的消费已前移到 _compile_inline_character
                    # （_effective_skill_levels——param() 取档要求 hook 编译时等级已定稿）
                    ov = e.get("overrides")
                    if ov and actor.actor_id in state_configs:
                        cfg, entry = state_configs[actor.actor_id]
                        state_configs[actor.actor_id] = (
                            _dc_replace(cfg, **{k: v for k, v in ov.items()}), entry)
                    self._compile_hooks(e.get("hooks") or [], f"模板 {ref} 星魂 E{rank}",
                                        actor.actor_id, hooks,
                                        resources_out=resource_decls_by_actor,
                                        extra_self_fields=tuple(
                                            binding_params.get(actor.actor_id, {}).keys()),
                                        param_ctx=self._param_ctx_by_actor.get(actor.actor_id))
        policy = self._compile_policy(build.get("policy") or {})

        # 战前秘技：池校验（默认 5 + Σ bonus）→ 选中秘技 effects 注入 hooks 开头（装填预置先于一切 hook）
        pre_battle = build.get("pre_battle") or []
        if pre_battle:
            from hsr_nous.sim.compile.compiled import CompiledHook
            tp_pool = 5 + tp_bonus
            spent = 0
            pre_hooks: List[Any] = []
            for use in pre_battle:
                _check_keys(use, _PRE_BATTLE_USE_KEYS, where="pre_battle")
                aid = str(use.get("actor_id", ""))
                tid = str(use.get("technique", ""))
                tdef = next((t for t in techniques_by_actor.get(aid, [])
                             if str(t.get("technique_id")) == tid), None)
                if tdef is None:
                    raise ValueError(f"pre_battle 引用不存在的秘技：{aid}/{tid}")
                spent += int(tdef.get("point_cost", 0))
                if spent > tp_pool:
                    raise ValueError(
                        f"秘技点超支：累计 {spent} > 池 {tp_pool}（默认 5 + 队伍加成 {tp_bonus}）"
                    )
                # 进战一次性 effects → on_battle_start hook（装填预置；effects 过同一编译期闸）
                one_shot = [dict(e) for e in tdef.get("effects") or []]
                self._validate_effects(one_shot, f"秘技 {aid}/{tid}",
                                       param_ctx=self._param_ctx_by_actor.get(aid),
                                       event_ns="on_battle_start",
                                       resources_ctx=resource_decls_by_actor.get(aid, {}),
                                       resource_writes=frozenset(
                                           str(e.get("resource_id"))
                                           for e in one_shot
                                           if isinstance(e, dict)
                                           and e.get("effect_type") in _RESOURCE_WRITE_TYPES
                                           and e.get("resource_id")))
                pre_hooks.append(CompiledHook(
                    owner_id=aid, event="on_battle_start", condition_expr=None,
                    effects=tuple(one_shot),
                ))
                # 常驻 hooks（如每波次伤害）→ 同模板 hooks 编译通道
                self._compile_hooks(tdef.get("hooks") or [], f"秘技 {aid}/{tid}", aid, pre_hooks,
                                    resources_out=resource_decls_by_actor,
                                    param_ctx=self._param_ctx_by_actor.get(aid))
            hooks = pre_hooks + hooks  # 装填预置先于模板 hooks

        self._final_cross_checks(team, actions_by_actor, modifiers_by_actor, hooks,
                                 resource_decls_by_actor, summon_defs)
        # 跨 actor hook 执行序（23 §23.11 v1）：global/trigger_order.yaml（可选——
        # 缺省=编译产物列表序，零迁移）；{事件名: [actor_id 优先序]}，未列单位兜底
        trigger_order = self._load_trigger_order(roots)
        return (tuple(team), actions_by_actor, policy, modifiers_by_actor, state_configs, hooks,
                resource_decls_by_actor, summon_defs, binding_params, trigger_order)

    @staticmethod
    def _load_trigger_order(roots: Sequence[Union[str, Path]]) -> Dict[str, tuple]:
        """按 roots 序查 global/trigger_order.yaml（第一个命中根生效；不存在=空表）."""
        import glob as _glob

        for root in roots:
            hits = _glob.glob(f"{root}/global/trigger_order.yaml")
            if not hits:
                continue
            with open(hits[0], encoding="utf-8") as f:
                doc = yaml.safe_load(f) or {}
            order = doc.get("order") or {}
            _check_mapping(order, where="global/trigger_order.yaml", field="order")
            out: Dict[str, tuple] = {}
            for ev, ids in order.items():
                if not isinstance(ids, (list, tuple)):
                    raise ValueError(
                        f"global/trigger_order.yaml order[{ev!r}] 须为 actor_id 列表，"
                        f"实得 {type(ids).__name__}")
                out[str(ev)] = tuple(str(i) for i in ids)
            return out
        return {}

    def _final_cross_checks(
        self,
        team: List[Actor],
        actions_by_actor: Dict[str, List[Action]],
        modifiers_by_actor: Dict[str, List[Any]],
        hooks: List[Any],
        resource_decls_by_actor: Dict[str, Dict[str, Dict[str, Any]]],
        summon_defs: Dict[str, Any],
    ) -> None:
        """编译期收尾交叉校验（13_validator §13.3）：重复 actor_id / override 冲突 /
        resource_id 存在性（全队 decl 并集 + 内部 `_` 前缀放行）。"""
        # 重复 actor_id（队伍成员 + 召唤物——撞 id 会在 state.actors 键控下静默互踩）
        seen: Dict[str, str] = {}
        for a in team:
            if a.actor_id in seen:
                raise ValueError(
                    f"重复 actor_id {a.actor_id!r}（{seen[a.actor_id]} 与 {a.name}——"
                    f"同 id 单位在 state.actors 键控下互相覆盖，编译期炸）")
            seen[a.actor_id] = a.name
        for sid, sdef in summon_defs.items():
            if sid in seen:
                raise ValueError(f"召唤物 actor_id {sid!r} 与 {seen[sid]} 撞 id（同上）")
            seen[sid] = sdef.actor.name
        # override 冲突（13_validator §13.3）：同一单位初始 modifier 集里同一 stat 被多个
        # override 来源覆写（静态可判的叠加场景——结果取决于挂载序=静默不定，必须报错）
        for aid, mods in modifiers_by_actor.items():
            ovl_stats: Dict[str, str] = {}
            for m in mods:
                for stat in getattr(m, "override_effects", {}) or {}:
                    if stat in ovl_stats:
                        raise ValueError(
                            f"override 冲突：单位 {aid} 的初始 modifier {ovl_stats[stat]!r} 与 "
                            f"{m.modifier_id!r} 都覆写 stat {stat!r}——同 stat 只许一个 "
                            f"override 来源（13_validator §13.3）")
                    ovl_stats[stat] = m.modifier_id
        # resource_id 存在性：actions/hooks 引用的资源必须在全队 decl 并集内
        # （bank 派生 <rid>_bank 已注册在 decl；内部 `_` 前缀放行（_state_actions_/_tl_ 等））
        known = {rid for decls in resource_decls_by_actor.values() for rid in decls}

        def _rid_ok(rid: Any) -> bool:
            s = str(rid)
            return s in known or s.startswith("_")

        for aid, acts in actions_by_actor.items():
            for a in acts:
                for rid in (*a.resource_gain.keys(), a.consume_all_resource,
                            a.instances_from_resource, a.ult_cost_resource,
                            a.assist_cost_resource):
                    if rid and not _rid_ok(rid):
                        raise ValueError(
                            f"action {a.action_id}（{aid}）引用未声明资源 {rid!r}"
                            f"（已声明：{sorted(known)}——custom_resources 登记处）")
        for h in hooks:
            for eff in h.effects:
                t = eff.get("effect_type")
                if t in ("gain_resource", "set_resource", "refund_bank"):
                    sel = eff.get("target")
                    if sel is not None and sel != "self":
                        # 跨 actor 写通道（05_effects §5.3 target）：资源长在目标面板——可能
                        # 由他模板声明，本队未编该模板时 hook 蛰伏而非错字，存在性闸不拦
                        continue
                    rid = str(eff.get("resource_id", ""))
                    if rid and not _rid_ok(rid):
                        raise ValueError(
                            f"{h.owner_id} hook({h.event}) 的 {t} 引用未声明资源 {rid!r}"
                            f"（已声明：{sorted(known)}）")
