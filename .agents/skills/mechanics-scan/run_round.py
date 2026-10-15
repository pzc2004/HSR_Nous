#!/usr/bin/env python3
"""机制扫描轮次工具：check / status / todo / diff.

用法:
  python3 run_round.py check [raw_dir]   # 校验 raw 标注文件（默认自动探测最近轮次）
  python3 run_round.py status [raw_dir]  # 花名册对账 + 状态分布
  python3 run_round.py todo [raw_dir]    # 列出未扫角色（ swarm items 格式）
  python3 run_round.py diff <dirA> <dirB>  # 两轮标注状态迁移

raw 文件格式：每角色一个 <id>.json，内容为标注记录列表，
每条含 character_id / skill_id / primitive / status / rationale
（status ∈ green|yellow|red）。

另：本文件的 `synonyms` 同义词字典 + `normalize_primitive_name` 是原语
归一化的权威来源（METHODOLOGY.md §3 引用），diff 默认启用归一化，
merge_to_matrix.py / merge_round2.py（历史脚本，随产物归档）也从这里导入。
"""

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import yaml

def _find_root() -> Path:
    """向上找 pyproject.toml 定位仓库根（脚本可能挪动位置）。"""
    for p in Path(__file__).resolve().parents:
        if (p / 'pyproject.toml').exists():
            return p
    raise RuntimeError('找不到仓库根（pyproject.toml）')


def _default_raw() -> Path:
    """最近一次扫描轮次的 raw 目录（reports/mechanics_scan/*/raw 中按内容 mtime 取最新）。"""
    base = _ROOT / 'reports/mechanics_scan'
    best, best_t = None, -1.0
    if base.is_dir():
        for d in base.iterdir():
            raw = d / 'raw'
            files = list(raw.glob('*.json')) if raw.is_dir() else []
            if not files:
                continue
            t = max(f.stat().st_mtime for f in files)
            if t > best_t:
                best, best_t = raw, t
    return best if best else base / 'roundN' / 'raw'  # 无轮次时返回占位，main 报目录不存在


_ROOT = _find_root()
DEFAULT_RAW = _default_raw()
ROSTER = Path(__file__).parent / 'roster.yaml'
CHARS_JSON = _ROOT / 'data/starrailres/index_new/cn/characters.json'

STATUSES = ('green', 'yellow', 'red')
SEVERITY = {'green': 0, 'yellow': 1, 'red': 2}
REQUIRED_FIELDS = ('character_id', 'skill_id', 'primitive', 'status', 'rationale')


def normalize_primitive_name(name):
    """Normalize primitive names to a canonical form."""
    if not name:
        return 'unknown'

    # Lowercase
    n = name.lower().strip()

    # Synonym map - merge similar primitives
    synonyms = {
        # Damage types - keep as-is
        'deal_dmg_by_max_hp': 'deal_damage',
        'deal_aoe_damage': 'deal_damage',
        'deal_blast_damage': 'deal_damage',
        'splash_damage': 'deal_damage',
        'aoe_damage': 'deal_damage',
        'multi_hit_damage': 'deal_damage',
        'bounce_damage': 'deal_damage',
        'deal_damage_split_evenly': 'deal_damage',
        'deal_damage_blast': 'deal_damage',
        'deal_damage_aoe': 'deal_damage',
        'deal_damage_by_tally': 'deal_damage',
        'deal_damage_on_wave_start': 'deal_damage',
        'deal_damage_with_split_scaling': 'deal_damage',
        'deal_damage_on_combat_start': 'deal_damage',
        'deal_elation_damage': 'deal_damage',
        'deal_elation_damage_aoe': 'deal_damage',
        'deal_max_hp_scaled_damage': 'deal_damage',
        'deal_max_hp_scaled_damage_split': 'deal_damage',
        'extra_damage_with_hp_loss_tally_scaling': 'deal_damage',
        'deal_additional_dmg': 'deal_damage',
        'deal_true_damage': 'deal_damage',
        'deal_true_dmg': 'deal_damage',
        'true_damage': 'deal_damage',

        # Add_stat
        'add_stat': 'add_stat',
        'add_dmg_bonus': 'add_stat',
        'add_crit_rate': 'add_stat',
        'add_res_pen': 'add_stat',
        'add_all_res': 'add_stat',
        'add_res_reduction': 'add_stat',
        'add_bounce_count': 'add_stat',
        'add_effect_res': 'add_stat',
        'add_def_reduction': 'add_stat',
        'add_damage_taken': 'add_stat',
        'add_dmg_bonus_to_all_allies': 'add_stat',
        'add_stat_with_stacks': 'add_stat',
        'add_stat_with_duration': 'add_stat',
        'add_stat_from_ally_hp': 'add_stat',
        'add_stat_from_ally_crit': 'add_stat',
        'conditional_add_stat': 'add_stat',
        'excess_spd_to_crit_dmg': 'add_stat',
        'excess_spd_to_healing': 'add_stat',
        'excess_spd_to_res_pen': 'add_stat',
        'excess_atk_to_elation': 'add_stat',
        'buff_dmg_in_state': 'add_stat',
        'buff_max_hp_on_low_hp': 'add_stat',
        'state_stack_gain': 'add_stat',
        'stack_based_damage': 'add_stat',
        'convert_heal_to_resource': 'add_stat',
        'track_hp_loss': 'add_stat',
        'buff_dmg_bonus': 'add_stat',
        'conditional_crit_rate_buff_in_state': 'add_stat',
        'chance_per_stack': 'add_stat',
        'chance_extra_action': 'add_stat',
        'stack_dmg_bonus_per_unique_target': 'add_stat',
        'battle_long_stacking': 'add_stat',
        'stack_per_resource': 'add_stat',
        'scaling_per_resource': 'add_stat',
        'add_vulnerability': 'add_stat',
        'apply_vulnerability_per_summon_hit': 'add_stat',
        'global_dot_dmg_buff (while_on_field)': 'add_stat',

        # Apply modifier
        'apply_modifier': 'apply_modifier',
        'apply_modifier_extra_stacks': 'apply_modifier',
        'apply_modifier_to_ally_targets': 'apply_modifier',
        'apply_persistent_mark': 'apply_modifier',
        'dmg_vulnerability': 'apply_modifier',
        'apply_dmg_reduction_modifier': 'apply_modifier',
        'apply_freeze': 'apply_modifier',
        'apply_debuff_block': 'apply_modifier',
        'debuff_enemy': 'apply_modifier',
        'dispel_debuff_self': 'apply_modifier',
        'apply_weakness': 'apply_modifier',
        'add_weakness': 'apply_modifier',
        'implant_weakness': 'apply_modifier',
        'mass_dispel_on_skill': 'apply_modifier',
        'mass_dispel_on_summon': 'apply_modifier',
        'vulnerability_apply': 'apply_modifier',
        'increase_vulnerability': 'apply_modifier',
        'dmg_taken_increase': 'apply_modifier',
        'apply_vulnerability': 'apply_modifier',
        'apply_zone': 'apply_modifier',
        'apply_zone_buff': 'apply_modifier',

        # Remove modifier
        'remove_modifier': 'remove_modifier',
        'dispel_debuff': 'remove_modifier',
        'remove_debuff': 'remove_modifier',
        'remove_state': 'remove_modifier',
        'remove_modifier_self': 'remove_modifier',
        'dismiss_zone_on_actor_downed': 'remove_modifier',
        'dispel_zone': 'remove_modifier',
        'remove_resource_cap': 'remove_modifier',
        'force_end_current_turn': 'remove_modifier',

        # Gain energy
        'gain_energy': 'gain_energy',
        'gain_energy_for_ally': 'gain_energy',
        'regenerate_energy_to_owner': 'gain_energy',
        'regenerate_energy_for_allies': 'gain_energy',
        'gain_energy_per_summon_hit': 'gain_energy',
        'gain_energy_after_attack': 'gain_energy',
        'gain_energy_on_aha_end': 'gain_energy',
        'gain_energy_on_kill': 'gain_energy',

        # Gain skill point
        'gain_skill_point': 'gain_skill_point',
        'sp_recover': 'gain_skill_point',
        'gain_skill_point_on_combat_start': 'gain_skill_point',
        'gain_skill_point_no_cost': 'gain_skill_point',
        'no_skill_point_gain': 'gain_skill_point',
        'recover_skill_point_block': 'gain_skill_point',
        'skill_point_block_consume': 'gain_skill_point',

        # Consume skill point
        'consume_skill_point': 'consume_skill_point',
        'override_skill_cost': 'consume_skill_point',  # dynamic modify
        'sp_max_increase': 'consume_skill_point',  # wrong category but rare
        'modify_max_skill_points': 'consume_skill_point',
        'sp_consume_track': 'consume_skill_point',

        # Heal
        'heal': 'heal',
        'heal_on_attack': 'heal',
        'heal_on_battle_start': 'heal',
        'heal_after_attack': 'heal',
        'consume_hp_to_heal': 'heal',
        'heal_on_ally_attack': 'heal',

        # Advance action
        'advance_action': 'advance_action',
        'advance_all_action': 'advance_action',
        'advance_action_on_summon_disappear': 'advance_action',
        'repeat_advance_action': 'advance_action',
        'self_action_advance': 'advance_action',

        # Trigger extra turn
        'grant_extra_turn': 'grant_extra_turn',
        'grant_extra_turn_on_kill': 'grant_extra_turn',
        'grant_extra_turn_to_summon': 'grant_extra_turn',
        'grant_extra_conditional_turn': 'grant_extra_turn',
        'grant_extra_turn_on_aha_end': 'grant_extra_turn',
        'grant_extra_turn_on_kill_all': 'grant_extra_turn',
        'grant_extra_turn_on_ally_action': 'grant_extra_turn',
        'grant_extra_turn_to_ally': 'grant_extra_turn',

        # Summon
        'summon': 'summon',
        'summon_unit_on_battle_start': 'summon',
        'dismiss_summon': 'summon',
        'summon_inherits_owner_atk': 'summon',
        'summon_inherit_hp_pct': 'summon',
        'summon_multi_hit_random_target': 'summon',
        'inherit_stats_from_owner': 'summon',
        'summon_aoe_adjacent_dmg_bonus': 'summon',
        'joint_attack': 'summon',
        'summon_in_zone': 'summon',
        'dispatch_summon_to_attack': 'summon',
        'dispatch_follow_up_attack': 'summon',
        'dispatch_extra_elation_skill': 'summon',

        # Mitigate
        'mitigate_damage': 'mitigate_damage',
        'distribute_damage_to_self': 'mitigate_damage',
        'resist_debuff': 'mitigate_damage',

        # Transform state
        'transform_state': 'transform_state',
        'transform_actor': 'transform_state',  # 主体变形态
        'transform_action': 'transform_state',
        'transform_skill': 'transform_state',
        'transform_action_to_enhanced': 'transform_state',
        'enter_state_with_duration': 'transform_state',
        'enter_state': 'transform_state',
        'enter_hellscape_state': 'transform_state',
        'set_action_state': 'transform_state',
        'exit_state': 'transform_state',
        'exit_state_on_action_count': 'transform_state',
        'change_damage_type': 'transform_state',
        'transform_damage_type': 'transform_state',

        # State
        'set_spd_to_zero': 'transform_state',
        'banish_ally': 'transform_state',
        'lock_turn_entry': 'transform_state',
        'actor_state': 'transform_state',
        'transform_to_godmode': 'transform_state',
        'replace_action_in_state': 'transform_state',

        # Immune
        'immune_death': 'immune_death',
        'immune_to_cc': 'immune_death',
        'immune_crowd_control': 'immune_death',
        'death_save': 'immune_death',
        'death_immunity': 'immune_death',
        'ignore_debuff': 'immune_death',

        # Custom resources
        'gain_resource': 'gain_resource',
        'consume_resource': 'consume_resource',
        'gain_charge_stack': 'gain_resource',
        'gain_charge_stack_on_hp_loss': 'gain_resource',
        'consume_charge_stacks': 'consume_resource',
        'consume_resource_for_damage': 'consume_resource',
        'consume_resource_for_atk': 'consume_resource',
        'consume_ultimate_energy': 'consume_resource',
        'consume_state_for_dmg': 'consume_resource',
        'consume_modifier': 'consume_resource',
        'consume_overflow_resource': 'consume_resource',
        'consume_tally': 'consume_resource',
        'consume_mark_for_resource': 'consume_resource',
        'consume_energy': 'consume_resource',
        'consume_hp_per_turn': 'consume_resource',
        'reset_resource': 'consume_resource',
        'convert_resource': 'consume_resource',
        'convert_energy_to_certified_banger': 'consume_resource',
        'convert_punchline_to_hidden_mmr': 'consume_resource',
        'convert_ally_resource': 'consume_resource',
        'reset_counter': 'consume_resource',
        'consume_mark': 'consume_resource',
        'remove_stack': 'consume_resource',

        # Set HP
        'set_hp_to_percent': 'set_hp_to_percent',
        'set_hp_to_value': 'set_hp_to_percent',
        'set_hp_to_1': 'set_hp_to_percent',
        'self_damage_on_insufficient_hp': 'set_hp_to_percent',
        'consume_hp_for_atk': 'set_hp_to_percent',
        'set_max_hp': 'set_hp_to_percent',
        'modify_max_hp': 'set_hp_to_percent',
        'modify_max_hp_for_allies': 'set_hp_to_percent',

        # Drain HP（X2 裁决原语：耗血/自伤类，见 05_effects.md）
        'drain_hp': 'drain_hp',
        'lose_hp_self': 'drain_hp',
        'consume_hp_percent': 'drain_hp',
        'boost_max_hp': 'set_hp_to_percent',

        # DoT
        'deal_dot_damage': 'deal_dot_damage',
        'dot_chance_apply': 'deal_dot_damage',
        'dot_add': 'deal_dot_damage',
        'dot_stack_dmg': 'deal_dot_damage',
        'splash_dot': 'deal_dot_damage',
        'trigger_dot_immediately': 'deal_dot_damage',
        'trigger_existing_dot': 'deal_dot_damage',
        'reset_stack_on_tick': 'deal_dot_damage',
        'reset_dot_on_tick': 'deal_dot_damage',
        'dot_spread_debuff': 'deal_dot_damage',

        # Trigger
        'trigger_follow_up': 'trigger_follow_up',
        'trigger_follow_up_atk': 'trigger_follow_up',
        'trigger_followup_repeatedly': 'trigger_follow_up',
        'triggered_extra_action': 'trigger_follow_up',
        'triggered_follow_up': 'trigger_follow_up',
        'trigger_count_consume': 'trigger_follow_up',
        'follow_up_attack': 'trigger_follow_up',
        'trigger_on_heal_received': 'trigger_follow_up',
        'trigger_on_heal_provided': 'trigger_follow_up',
        'trigger_on_being_targeted_by_ally': 'trigger_follow_up',
        'trigger_on_ally_hp_decreased': 'trigger_follow_up',
        'trigger_on_energy_received': 'trigger_follow_up',
        'trigger_on_ally_basic_atk': 'trigger_follow_up',
        'triggered_mode': 'trigger_follow_up',
        'auto_use_skill': 'trigger_follow_up',
        'auto_cast_after_owner_action': 'trigger_follow_up',

        # Override action param
        'override_action_param': 'override_action_param',
        'override_skill_max_level': 'override_action_param',
        'modify_action_param': 'override_action_param',
        'skill_level_up': 'override_action_param',
        'append_action_param': 'override_action_param',
        'modify_action_value': 'override_action_param',

        # Spread
        'spread_modifier': 'spread_modifier',
        'splash_debuff': 'spread_modifier',
        'dot_spread': 'spread_modifier',

        # Force advance
        'force_advance_enemy': 'force_advance_enemy',
        'force_enemy_action': 'force_advance_enemy',

        # Deploy zone
        'deploy_zone': 'deploy_zone',
        'deploy_territory': 'deploy_zone',
        'deploy_zone_indefinite': 'deploy_zone',
        'zone_create': 'deploy_zone',
        'zone_expire': 'deploy_zone',
        'force_immobilize_enemies': 'deploy_zone',
        'maze_zone': 'deploy_zone',

        # Def pen / res pen
        'ignore_def': 'ignore_def',
        'ignore_weakness': 'ignore_weakness',
        'ignore_weakness_for_toughness': 'ignore_weakness',
        'res_pen': 'res_pen',
        'reduce_effect_res': 'reduce_effect_res',
        'effect_res_reduce': 'reduce_effect_res',
        'extra_dmg_with_hp_loss_tally_scaling': 'ignore_def',
        'modify_spd_inheritance': 'ignore_def',  # wrong

        # Crit
        'guaranteed_crit': 'guaranteed_crit',
        'guaranteed_crit_rate': 'guaranteed_crit',

        # Def
        'def_to_zero': 'def_to_zero',

        # Taunt
        'forced_taunt': 'forced_taunt',
        'ally_target_pull': 'forced_taunt',

        # Misc special
        'refresh_extra_turns': 'refresh_extra_turns',
        'set_modifier_conditional': 'set_modifier_conditional',
        'sync_hp_pct': 'sync_hp_pct',
        'decrease_continuous_effects_duration': 'decrease_continuous_effects_duration',
        'apply_terrified': 'apply_terrified',
        'activate_ally_ultimate': 'activate_ally_ultimate',
        'no_technique_point_cost': 'no_technique_point_cost',
        'instant_defeat_normal_enemy': 'instant_defeat_normal_enemy',
        'stack_action_restriction': 'stack_action_restriction',
        'convert_debuff_type': 'convert_debuff_type',
        'replace_action': 'replace_action',
        'ext_action_param': 'ext_action_param',
        'extend_buff_duration': 'extend_buff_duration',
        'transfer_stacks': 'transfer_stacks',
        'on_resource_threshold': 'on_resource_threshold',
        'ultimate_unlock_threshold': 'on_resource_threshold',
        'is_not_actual_skill': 'is_not_actual_skill',
        'on_battle_enter': 'on_battle_start',
        'set_weakness_to_all': 'set_weakness_to_all',
        'override_resistance_to_zero': 'override_resistance_to_zero',
        'on_enemy_enter_combat': 'actor_enter',
        'unlock_elation_skill': 'unlock_elation_skill',
        'gain_punchline': 'gain_punchline',
        'gain_certified_banger': 'gain_certified_banger',
        'gain_hidden_mmr': 'gain_hidden_mmr',
        'gain_thrill': 'gain_thrill',
        'gain_merrymake': 'gain_merrymake',
        'gain_elation': 'gain_elation',
        'transform_state_to_godmode': 'transform_state',
        'on_ally_certified_banger_gain': 'after_gain',
        'on_ally_certified_banger_expire': 'after_remove_modifier',
        'on_ally_use_elation_skill': 'on_elation_skill',
        'on_elation_skill': 'on_elation_skill',
        'on_state_enter': 'on_state_change',
        'on_state_exit': 'on_state_change',
        'on_target_dead_redirect': 'on_target_dead_redirect',  # 机制专属复合触发（改投新登场敌人）；总线可用 actor_enter+condition 表达（23.4 示例），矩阵扫描保留独立名
        'on_kill_all': 'on_kill',
        'on_energy_threshold_reach': 'on_resource_threshold',
        'on_resource_increment_threshold': 'on_resource_threshold',
        'on_follow_up_attack_dispatch': 'on_follow_up_attack_dispatch',  # 总线无对应事件，保留独立名
        'aha_instant': 'aha_instant',  # 阿哈时刻（机制原语，非 start/end 边界事件）
        'elation_damage': 'deal_damage',
        'elation_multi': 'add_stat',
        'punchline_multi': 'add_stat',
        'merrymake_multi': 'add_stat',
        'count_unique_resource_sources': 'count_unique_resource_sources',
        'queue_buff_to_next_ultimate': 'queue_buff_to_next_ultimate',
        'stack_next_action_modifier': 'stack_next_action_modifier',
        'gain_certified_banger_on_next_skill': 'gain_certified_banger_on_next_skill',
        'decaying_probability': 'decaying_probability',
        'reset_trigger_chance': 'reset_trigger_chance',
        'random_effect_from_weighted_list': 'random_effect_from_weighted_list',
        'dispatch_top_loot_box': 'dispatch_top_loot_box',
        'dispatch_top_loot_box_on_wave_start': 'dispatch_top_loot_box_on_wave_start',
        'dispatch_top_loot_box_periodic': 'dispatch_top_loot_box_periodic',
        'add_stat_per_resource': 'add_stat',
        'use_max_ally_resource_for_damage': 'use_max_ally_resource_for_damage',
        'random_gift_selection': 'random_gift_selection',
        'extra_instance_per_engagement': 'extra_instance_per_engagement',
        'increase_dmg_multiplier': 'increase_dmg_multiplier',
        'gain_elation_from_crit_dmg': 'gain_elation',
        'punchline_to_res_pen': 'add_stat',
        'punchline_to_crit_dmg': 'add_stat',
        'thrill_to_crit_dmg': 'add_stat',
        'on_ally_ult': 'on_ultimate',
        'per_turn_trigger_cap': 'per_turn_trigger_cap',
        'per_event_charge_cap': 'per_event_charge_cap',
        'prevent_repeat_extra_turn': 'prevent_repeat_extra_turn',
        'prevent_recursive_extra_turn': 'prevent_repeat_extra_turn',
        'select_random_debuff_from_pool': 'select_random_debuff_from_pool',
        'gain_energy_per_debuff_on_target': 'gain_energy_per_debuff_on_target',
        'stacking_dmg_bonus_per_debuff': 'stacking_dmg_bonus_per_debuff',
        'multi_instance_damage': 'multi_instance_damage',
        'modify_summon_hits_per_action': 'modify_summon_hits_per_action',
        'post_summon_dmg_buff': 'post_summon_dmg_buff',
        'reduce_charge_threshold_with_extra_dmg': 'reduce_charge_threshold_with_extra_dmg',
        'ext_resource_based_dmg': 'ext_resource_based_dmg',
        'per_event_cap': 'per_event_cap',

        # === 补盘批次新增（1501 火花 / 1502 爻光） ===

        # add_stat_* all map to add_stat
        'add_stat_atk': 'add_stat',
        'add_stat_def': 'add_stat',
        'add_stat_hp': 'add_stat',
        'add_stat_hp_pct': 'add_stat',
        'add_stat_crit_dmg': 'add_stat',
        'add_stat_crit_rate': 'add_stat',
        'add_stat_speed': 'add_stat',
        'add_stat_elation': 'add_stat',
        'add_stat_elation_damage_bonus': 'add_stat',
        'add_stat_res_pen_all': 'add_stat',
        'add_stat_effect_hit': 'add_stat',
        'add_stat_speed_pct_zone': 'add_stat',
        'add_all_res_pen_per_punchline': 'add_stat',
        'add_all_res_pen_team': 'add_stat',
        'add_crit_dmg_per_punchline': 'add_stat',
        'add_elation_per_atk_excess': 'add_stat',
        'add_elation_per_spd_excess': 'add_stat',
        'extra_elation_in_zone': 'add_stat',
        'extra_great_luck_on_skill_point_spend': 'add_stat',
        'ignore_defense_pct_elation': 'add_stat',
        'override_elation_skill_dmg_multiplier': 'add_stat',
        'damage_multiplier_buff_blast': 'add_stat',
        'on_gain_certified_banger_extend_duration': 'add_stat',
        'on_consume_climax_add_crit_dmg': 'add_stat',

        # Damage variants -> deal_damage
        'deal_damage_aoe_on_battle_enter': 'deal_damage',
        'deal_elation_damage_aoe_extra': 'deal_damage',
        'deal_elation_damage_random': 'deal_damage',
        'bounce_damage_elation': 'deal_damage',
        'bounce_extra_elation_damage': 'deal_damage',
        'deal_damage_maze': 'deal_damage',

        # Resource variants
        'gain_resource_climax': 'gain_resource',
        'consume_resource_climax_as_skill_point': 'consume_resource',
        'convert_state_to_resource': 'gain_resource',
        'gain_punchline_and_skill_point': 'gain_punchline',
        'gain_red_envelope_on_destroyable': 'gain_resource',
        'override_energy_gain_to_30': 'gain_energy',

        # Deploy zone variants
        'zone_team_elation_buff': 'deploy_zone',
        'use_self_elation_if_higher': 'deploy_zone',
        'no_attack_count_for_great_luck': 'deploy_zone',

        # Trigger variants — keep on_* but normalize（目标名以 04_modifier.md §4.8 / 23_event_hook_system.md §23.4 为准）
        'on_aha_instant_end_extra_turn': 'aha_instant_end',
        'on_aha_instant_end_gain_climax': 'aha_instant_end',
        'on_aha_instant_end_gain_punchline': 'aha_instant_end',
        'on_ally_attack_dispatch_great_luck': 'on_ally_damage',
        'on_self_basic_skill_gain_punchline': 'on_self_basic_skill',
        'on_ultimate_gain_punchline': 'on_ultimate',
        'on_elation_skill_gain_skill_point': 'on_elation_skill',
        'on_holding_certified_banger': 'on_holding_certified_banger',  # 门控条件（非总线事件），按 condition 表达

        # New / keep-separate primitives
        'aha_instant_execution': 'aha_instant_execution',  # 阿哈时刻执行（动作原语，非 start/end 边界事件）
        'apply_blacklist': 'apply_blacklist',
        'auto_trigger_skill_on_battle_enter': 'auto_trigger_skill_on_battle_enter',
        'conditional_extra_punchline_and_climax': 'conditional_extra_punchline_and_climax',
        'dispatch_interactive_trap': 'dispatch_interactive_trap',
        'elation_skill_dmg_multi_in_aha_turn': 'elation_skill_dmg_multi_in_aha_turn',
        'grant_aha_extra_turn_with_punchline': 'grant_aha_extra_turn',  # 阿哈专属额外回合变体；schema 无同名原语（05 仅有通用 grant_extra_turn），保留家族名
        'no_skill_point_cost': 'consume_skill_point',  # 直达终点（override_skill_cost 已映射 consume_skill_point；synonyms.get 不做传递归一，需直达）
        'override_aha_extra_turn_punchline_to_40': 'override_aha_extra_turn_punchline',
        'resource_capped_per_week': 'resource_capped_per_week',
        'scale_bounce_with_punchline': 'scale_bounce_with_punchline',
        'scaling_with_elation': 'scaling_with_elation',
        'transform_normal_to_enhanced': 'transform_state',
    }

    return synonyms.get(n, n)


def load_game_characters():
    """游戏数据里的角色全集（唯一事实来源，别手写 id）。"""
    return json.loads(CHARS_JSON.read_text(encoding='utf-8'))


def load_roster():
    if not ROSTER.exists():
        return []
    return yaml.safe_load(ROSTER.read_text(encoding='utf-8')).get('characters', [])


def load_raw(raw_dir):
    """返回 {character_id: [records]}；跳过 _ 开头文件。"""
    out = {}
    for fp in sorted(Path(raw_dir).glob('*.json')):
        if fp.name.startswith('_'):
            continue
        out[fp.stem] = json.loads(fp.read_text(encoding='utf-8'))
    return out


def cmd_check(raw_dir):
    chars = load_game_characters()
    # 合法 id 全集：技能（含子技能/星魂条目）+ 星魂 + 行迹
    known_skill_ids = set()
    for fn in ('character_skills.json', 'character_ranks.json', 'character_skill_trees.json'):
        known_skill_ids.update(json.loads((CHARS_JSON.parent / fn).read_text(encoding='utf-8')).keys())

    errors, warnings = [], []
    total_records = 0
    for fp in sorted(Path(raw_dir).glob('*.json')):
        if fp.name.startswith('_'):
            continue
        try:
            records = json.loads(fp.read_text(encoding='utf-8'))
        except json.JSONDecodeError as e:
            errors.append(f'{fp.name}: JSON 解析失败 {e}')
            continue
        if not isinstance(records, list):
            errors.append(f'{fp.name}: 顶层必须是列表')
            continue
        for i, r in enumerate(records):
            loc = f'{fp.name}[{i}]'
            total_records += 1
            for f in REQUIRED_FIELDS:
                if f not in r:
                    errors.append(f'{loc}: 缺字段 {f}')
            cid = r.get('character_id', '')
            if cid != fp.stem:
                errors.append(f'{loc}: character_id={cid} 与文件名 {fp.stem} 不一致')
            if r.get('status') not in STATUSES:
                errors.append(f'{loc}: 非法 status {r.get("status")!r}')
            sid = r.get('skill_id', '')
            if sid and sid not in known_skill_ids:
                warnings.append(f'{loc}: skill_id {sid} 不在游戏数据技能/星魂清单（子技能或笔误）')
            if cid and cid not in chars:
                warnings.append(f'{loc}: character_id {cid} 不在角色清单')

    print(f'records: {total_records}  errors: {len(errors)}  warnings: {len(warnings)}')
    for e in errors:
        print(f'  ERROR {e}')
    for w in warnings[:50]:
        print(f'  WARN  {w}')
    if len(warnings) > 50:
        print(f'  ... 其余 {len(warnings) - 50} 条 warning 略')
    return 1 if errors else 0


def cmd_status(raw_dir):
    chars = load_game_characters()
    raw = load_raw(raw_dir)
    roster_ids = {str(e['id']) for e in load_roster()}

    print(f'{"id":<6} {"name":<14} {"records":>7} {"green":>6} {"yellow":>6} {"red":>4}')
    totals = Counter()
    for cid in sorted(chars):
        name = chars[cid]['name']
        records = raw.get(cid)
        if records is None:
            print(f'{cid:<6} {name:<14} {"-- 未扫 --":>7}')
            continue
        c = Counter(r['status'] for r in records)
        totals.update(c)
        print(f'{cid:<6} {name:<14} {len(records):>7} {c["green"]:>6} {c["yellow"]:>6} {c["red"]:>4}')
    n = sum(totals.values())
    print(f'\n合计 {n} 条：green {totals["green"]} ({totals["green"]/max(n,1)*100:.0f}%) '
          f'yellow {totals["yellow"]} red {totals["red"]}')
    extra = set(raw) - set(chars)
    if extra:
        print(f'raw 里多出非角色 id: {sorted(extra)}')
    if roster_ids and roster_ids != set(chars):
        print(f'roster.yaml 与游戏数据不一致：roster 少 {sorted(set(chars)-roster_ids)} 多 {sorted(roster_ids-set(chars))}')
    return 0


def cmd_todo(raw_dir):
    chars = load_game_characters()
    raw = load_raw(raw_dir)
    missing = [(cid, chars[cid]['name']) for cid in sorted(chars) if cid not in raw]
    if not missing:
        print('全部角色已有 raw 标注。')
        return 0
    print(f'未扫 {len(missing)} 个角色（swarm items 格式）：')
    for cid, name in missing:
        print(f'{cid} {name}')
    return 0


def cmd_diff(dir_a, dir_b):
    a, b = load_raw(dir_a), load_raw(dir_b)
    # 原语名经 synonyms 归一化：同一机制两轮换叫法不会误报为两条迁移
    key = lambda r: (r['character_id'], r.get('skill_id', ''), normalize_primitive_name(r['primitive']))

    map_a = defaultdict(list)
    for records in a.values():
        for r in records:
            map_a[key(r)].append(r)
    map_b = defaultdict(list)
    for records in b.values():
        for r in records:
            map_b[key(r)].append(r)

    def worst(records):
        return max((r['status'] for r in records), key=lambda s: SEVERITY[s])

    trans = Counter()
    changes = []
    for k in sorted(set(map_a) | set(map_b)):
        sa = worst(map_a[k]) if k in map_a else None
        sb = worst(map_b[k]) if k in map_b else None
        trans[f'{sa or "∅"}->{sb or "∅"}'] += 1
        if sa != sb:
            changes.append((k, sa, sb))

    chars = load_game_characters()
    print('| A \\ B | green | yellow | red | ∅ |')
    print('|---|---|---|---|---|')
    for sa in STATUSES + (None,):
        row = [sa or '∅']
        for sb in STATUSES + (None,):
            row.append(str(trans.get(f'{sa or "∅"}->{sb or "∅"}', 0)))
        print('| ' + ' | '.join(row) + ' |')
    print(f'\n变化 {len(changes)} 条：')
    for (cid, sid, prim), sa, sb in changes:
        name = chars.get(cid, {}).get('name', cid)
        print(f'  {name}({cid}) {sid} {prim}: {sa or "∅"} -> {sb or "∅"}')
    return 0


def main():
    args = sys.argv[1:]
    if not args or args[0] not in ('check', 'status', 'todo', 'diff'):
        print(__doc__)
        return 2
    cmd = args[0]
    if cmd == 'diff':
        if len(args) != 3:
            print('用法: run_round.py diff <dirA> <dirB>')
            return 2
        return cmd_diff(args[1], args[2])
    raw_dir = Path(args[1]) if len(args) > 1 else DEFAULT_RAW
    if not raw_dir.is_dir():
        print(f'目录不存在: {raw_dir}')
        return 2
    return {'check': cmd_check, 'status': cmd_status, 'todo': cmd_todo}[cmd](raw_dir)


if __name__ == '__main__':
    sys.exit(main())
