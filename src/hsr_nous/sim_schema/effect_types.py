"""hook effect_type 单一事实源：引擎已实现集合 + 编译期校验共用.

引擎 `sim/hooks.py` `HookRuntime._run_hook_effect` 的 if-elif 链是本集合的唯一实现位
（engine 留同名薄委托）；
编译器（`sim/compile/build_compiler.py`）与引擎同读本文件——模板写未登记的
effect_type 编译期即炸（不允许静默吞）。文档侧登记见 `docs/05_effects.md` §5.2
（每个 effect_type 标注 已实现 / 待收编）。
"""

#: 引擎已实现的 hook effect_type（与 _run_hook_effect 分支一一对应）
ENGINE_EFFECT_TYPES = frozenset({
    "apply_modifier",    # 挂 modifier（dict 声明→物化）
    "remove_modifier",   # 摘除 modifier
    "adjust_stacks",     # 层数增减（clamp [0, max_stack]）
    "deal_damage",       # 直伤（scaling_atk/scaling_hp 单行倍率）
    "break_damage",      # 击破伤害（pipeline.break_damage × ratio）
    "trigger_action",    # 代放/复制行动（可选 scaling_atk 动态倍率覆写）
    "gain_resource",     # 自定义资源 +=（发 on_resource_gain）
    "set_resource",      # 自定义资源直接设值
    "gain_skill_point",  # 战技点 +=
    "gain_energy",       # 回能（可走 err_exempt 豁免 ERR）
    "heal_self",         # 自疗（hp_scaling=ratio，走统一治疗管线）
    "set_hp_to_percent", # HP 设为上限×比例（可致死，走死亡检查）
    "grant_extra_turn",  # 授予额外回合
    "delay_action",      # 行动延后（amount 百分数）
    "cancel_event",      # waterfall 事件取消（免死族）
})

#: hook effect `target` 选择器合法值（HookRuntime._hook_target_states 实现）；
#: 另支持动态前缀 `$event.<字段>`（payload actor_id 寻址，见 HookRuntime._event_actor）
HOOK_TARGET_SELECTORS = frozenset({
    "self",
    "all_allies",
    "other_allies",
    "all_enemies",
    "enemy_first",
    "highest_hp",
    "highest_hp_hit",
})

#: policy target_rules 字符串选择器合法值（CompiledPolicyRuntime._apply_selector 实现集）；
#: 编译期（build_compiler._compile_policy）与运行期同读本表——未知选择器编译期炸，
#: 运行期绕过编译层手写 CompiledPolicy 同口径炸（与 hook 选择器同纪律，不许静默兜底）
POLICY_TARGET_SELECTORS = frozenset({
    "primary_target", "enemy_single", "all_enemies", "all_allies",
    "self",
    "lowest_hp", "lowest_hp_ally", "highest_hp",
    "lowest_hp_pct", "highest_hp_pct",
    "highest_atk", "lowest_atk",
    "highest_spd", "lowest_spd",
    "broken", "highest_break",
    "random",
})

#: policy target_rules 参数化 dict 选择器的合法 type（_apply_selector dict 分支实现集）
POLICY_SELECTOR_DICT_TYPES = frozenset({"min", "max", "random", "has_modifier", "filter", "first"})

#: hook effects 的已知表达式槽位：字符串值按白名单表达式编译期预编译（B8：
#: 非法表达式编译期炸——condition 早有闸，effects 数值槽同口径）
EFFECT_EXPR_SLOTS = frozenset({
    "amount", "ratio", "scaling_atk", "scaling_hp", "delta", "percent",
})
