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
    "trigger_dot",       # 强制结算目标全部 DoT（卡芙卡族；不消耗 duration，on_dot_retrigger 照发）
    "adjust_duration",   # modifier 时长 ±N（≠ refresh 重置满值；调到 0 按到期移除——刃族）
    "add_toughness_bar", # 追加韧性条（03_actor §3.10 虚韧性族机制赋予；运行期追加按加入序承接）
    "trigger_action",    # 代放/复制行动（可选 scaling_atk 动态倍率覆写）
    "gain_resource",     # 自定义资源 +=（发 on_resource_gain）
    "set_resource",      # 自定义资源直接设值
    "refund_bank",       # bank 返还（16 §16.12 糖展开原语：<rid>_bank → <rid> clamp 回填不回流）
    "gain_skill_point",  # 战技点 +=（可携 overflow_to——溢出恢复转记资源池，花火 1130603 族）
    "set_sp_max",        # 战技点上限覆写（state.sp_max_override——花火天赋「上限额外增加」族首实例）
    "refill_skill_point",  # 溢出回补（from_resource 记录池补足至上限——花火 1130603 族）
    "gain_energy",       # 回能（可走 err_exempt 豁免 ERR）
    "heal_self",         # 自疗（hp_scaling=ratio，走统一治疗管线）
    "heal",              # 治疗（target 选择器 + ratio=施放者 HP 比例，走统一治疗管线——忆灵/丰饶族）
    "set_hp_to_percent", # HP 设为上限×比例（可致死，走死亡检查）
    "drain_hp",          # 生命流失/汲取（floor 保底 + drain_ratio 治疗转化 + into_resource 记账；
                         # 发 on_hp_decrease reason='drain'，不触发伤害类 hook——遐蝶耗血族）
    "summon",            # 召唤物入场（summon_id → 布场+上行动条+actor_enter；12_summon）
    "dismiss_summon",    # 召唤物离场（summon_id → actor_exit reason=dismiss）
    "grant_extra_turn",  # 授予额外回合
    "immediate_action",  # 立即行动（剩余距离置 0 到顶，无视推条；普通回合口径）
    "delay_action",      # 行动延后（amount 百分数）
    "advance_action",    # 行动提前（amount 百分数；remaining ≤ 0 时无效——小伊卡消失拉忆师族）
    "cancel_event",      # waterfall 事件取消（免死族）
    "modify_amount",     # waterfall 事件 amount 改写（抵扣/减免族——遐蝶 E2 炽意抵扣焰息耗血首实例）
    "aha_instant",       # 额外阿哈时刻（21_elation §21.4——固定 20 笑点结算不耗池，爻光终结技族）
    "activate_ultimate", # 激活终结技（目标 ult 立即插入发动、不耗充能——昔涟 141503 族，v1 口径）
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
    "toughness_dmg", "punchline_source", "pool_override",
})
