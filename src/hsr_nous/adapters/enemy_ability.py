"""上游 CharacterConfig/Ability → 敌人 sim_schema 的通用编译器.

只按上游节点类型注册转换，不写怪物/技能 ID 分支。TBGD 提供数值与结构；
Fandom 仅由调用方传入名字和受击回能等文本补充。未注册节点、未知动态哈希、
条件分支或目标语义不明都会进入 ``unsupported``，候选不得因此定稿。

执行帧感知翻译（#26 期 2/3，语义锚 23_event_hook_system.md §23.15 +
14_policy.md 概率分支节）：写后读谓词（同技能写入后再 ByCompareDynamicValue/
ByCompareMonsterPhase）与概率分支（ByRandomChance/RandomConfig）编译为
**单 hook + 纯 effect 级 condition**——effect 级 condition 是执行时活读，
读得到帧覆盖层的未提交写入；概率分支前置 ``bind_roll`` 绑定共享掷骰（roll 键
按节点路径生成稳定键）。PostfixExpr 中被写键的动态哈希经键名反查表回落为
``dynamic_of`` 活读。主动与事件 hook 均可使用概率分支；帧外事件由 HookRuntime 自动建帧。
多抽/跨局随机记忆（RandomCount/RandomMaskKey 等）保持显式 unsupported；单独 RandomUnique 的单抽不建记忆。

被动事件族（14_policy.md 被动事件族节）：SkillList Passive/SkillP 条目走
``compile_passive`` 挂载通道——OnAdd→OnStart 编译为 on_battle_start 钩 +
actor_enter（wave_index≥1）补挂；modifier 回调经 ``_PASSIVE_EVENT_MAP``
（单一事实源）映射到引擎事件总线（持有者窄化）或定义期消费，无载体事件逐条
显式 unsupported 进 human_queue。
"""
from __future__ import annotations

import base64
import copy
import json
from dataclasses import dataclass, field, replace
from typing import Any, Dict, Iterable, List, Optional, Tuple

from hsr_nous.sim_schema.action import ELEMENTS
from hsr_nous.sim_schema.actor import PATH_ALIASES, PATHS
from hsr_nous.sim_schema.config_ai import dynamic_value_hash

#: 纯表现/动画节点。含机制 TaskList 的动画节点不在此列，由专门处理器递归。
IGNORED_TASK_TYPES = frozenset({
    "RPG.GameCore.AddChallengeBossInfoPanelState",
    "RPG.GameCore.AnimSetParameter",
    "RPG.GameCore.AudioSetRTPCValue",      # 音频参数（纯表现）
    "RPG.GameCore.AudioSetRTPCValueByRatio",
    "RPG.GameCore.AddGlobalDynamicOffset",  # 镜头全局动态偏移（纯表现）
    "RPG.GameCore.SetEffectAnimatorParameter",  # 特效状态机/预览开关（纯表现）
    "RPG.GameCore.TriggerSoundInAnim",     # 动画音效（纯表现）
    "RPG.GameCore.TriggerEffectList",      # 特效路径列表（纯表现）
    "RPG.GameCore.SetComfortZoneWidthOverride",  # 镜头舒适区（纯表现）
    "RPG.GameCore.OverrideSelectDarkTeamEntityCamera",  # 镜头选目标权重（纯表现）
    "RPG.GameCore.BlockCameraDitherUpdate",   # 相机抖动更新（纯表现）
    "RPG.GameCore.SetEntityForbidCameraDither",  # 实体镜头抖动开关（纯表现）
    "RPG.GameCore.SetMonsterHUDVisibleType",  # 怪物 HUD 显隐（纯表现）
    "RPG.GameCore.SetControlSkillMapping",    # 控制按钮→既有技能映射（UI 元数据，不改行动）
    "DGAOCHGKJKJ",                            # 同上的混淆映射/开关形态（ControlSkill11/21 实样）
    "RPG.GameCore.SwitchBossHeadEffType",     # boss 头部特效切换（纯表现）
    "CLMMOEFOCNP",                            # 自定义 Hint 节点（技能提示，纯表现）
    "RPG.GameCore.DisableHeadLookAtOverride",  # 头部看向动画开关（纯表现）
    "RPG.GameCore.SetMonsterEnergyBarState",   # 怪物能量条 UI 状态（纯表现）
    "RPG.GameCore.SetModifierOverrideNameForStatus",  # modifier 状态显示名覆盖（纯表现）
    "RPG.GameCore.SetBattleUIPauseEnvironmentInfo",   # 战斗 UI 环境信息（纯表现）
    "RPG.GameCore.SetDawnsEyeWeatherUI",       # 黎明之眼天气 UI（纯表现）
    "RPG.GameCore.SetBattleAchievement",       # 战斗成就（纯表现）
    "RPG.GameCore.StackStatusDesc",            # 状态描述文本（纯表现）
    "RPG.GameCore.SetBattleUIPanelState",      # 战斗 UI 面板状态（纯表现）
    "RPG.GameCore.TriggerUITopEffect",         # UI 顶部特效（纯表现）
    "RPG.GameCore.ChangeTargetModifierEffectState",
    "RPG.GameCore.CharacterChangePhase",
    "RPG.GameCore.CharacterReactionAnimConfig",
    "RPG.GameCore.SetResilience",             # 受击反应动画等级（S/A/B/C/D 权重，纯表现）
    "RPG.GameCore.ClearEntityFollowAttachPoint",
    "RPG.GameCore.DamagePerformFinish",
    "RPG.GameCore.DebugLog",
    "RPG.GameCore.GlobalMainIntensityEffect",
    "RPG.GameCore.GetGapSecondsForSyncWithBgm",
    "RPG.GameCore.HideCharacterFilteredEffect",
    "RPG.GameCore.HideEffectByCharacterType",
    "RPG.GameCore.HideEntityForCurrentCamera",
    "RPG.GameCore.HideLevelStage",
    "RPG.GameCore.HideModifierEffect",
    "RPG.GameCore.LevelAudioState",
    "RPG.GameCore.LevelAudioSwitch",
    "RPG.GameCore.LookAt",
    "RPG.GameCore.HeadLookAt",                  # 头部/根部朝向动画（纯表现）
    "RPG.GameCore.MakeCharacterHUDVisible",
    "RPG.GameCore.ModifierAttachEffect",
    "RPG.GameCore.ModifierDetachEffect",
    "RPG.GameCore.MoveToTargetList",
    "RPG.GameCore.MoveToTargetPosition",
    "RPG.GameCore.PlayMonsterHPBarTween",
    "RPG.GameCore.PlayScreenTransfer",
    "RPG.GameCore.PlayTimeline",
    "RPG.GameCore.RadialBlurCurveEffect",
    "RPG.GameCore.RadialBlurEffect",
    "RPG.GameCore.RefreshChangePhaseUI",
    "RPG.GameCore.ReleaseCharacterHUDVisibleControl",
    "RPG.GameCore.RemoveEffect",
    "RPG.GameCore.RemoveChallengeBossInfoPanelState",
    "RPG.GameCore.ResetBattleBGMToStage",
    "RPG.GameCore.ResetHeadLookAt",
    "RPG.GameCore.ScaleCharacterModel",
    "RPG.GameCore.SetAttachmentScale",
    "RPG.GameCore.SetAttachmentVisibility",
    "RPG.GameCore.SetAttachEffectTimeSlow",
    "RPG.GameCore.SetBattleBGMState",
    "RPG.GameCore.SetCharacterEffectMaterialBlock",
    "RPG.GameCore.SetCharacterPartsVisibility",
    "RPG.GameCore.SetCharacterScaleFollow",
    "RPG.GameCore.SetEffectAnimSpeed",
    "RPG.GameCore.SetEffectAnimatorTrigger",
    "RPG.GameCore.SetEntityFollowAttachPoint",
    "RPG.GameCore.SetEntityPosition",
    "RPG.GameCore.SetEntityVisible",
    "RPG.GameCore.SetLocalOffsetAsMoveTarget",
    "RPG.GameCore.SetSimulationSpeedEnable",
    "RPG.GameCore.SetSkillTargetFormationByPos",
    "RPG.GameCore.SetTargetDamageTextVisible",
    "RPG.GameCore.SetTeamFormation",
    "RPG.GameCore.SetTeamRootOffset",
    "RPG.GameCore.SetTriggeredFormationAssetAutoCenter",
    "RPG.GameCore.ShowBattleAlert",
    "RPG.GameCore.ShowBattleConditionUI",     # 战斗条件提示 UI（纯表现）
    "RPG.GameCore.ShowBattleUI",
    "RPG.GameCore.ShowBossInfoBar",
    "RPG.GameCore.ShowEntityFloatMessage",
    "RPG.GameCore.ShowSkillTextDialog",
    "BENHFIGIMGL",                            # 仅 Textmap Hash 的技能提示/语音节点（无战斗状态字段）
    "RPG.GameCore.ShowUI",                  # BattleCommonHintDialog 文本提示（纯表现）
    "RPG.GameCore.ShowUIPage",
    "RPG.GameCore.SkillExecutionStart",
    "RPG.GameCore.SkillPerformFinish",
    "RPG.GameCore.StartAim",
    "RPG.GameCore.StopAim",
    "RPG.GameCore.SyncMonsterLightByCameraDir",
    "RPG.GameCore.TargetTimeSlow",
    "RPG.GameCore.ClearTargetTimeSlow",  # 清除同名 SlowKey 的表现层慢动作
    "RPG.GameCore.RemoveGlobalTimeSlow",  # 全局慢动作表现清除
    "RPG.GameCore.ChangeCharacterConfigParamClientOnly",  # 客户端 HUD/模型配置
    "RPG.GameCore.SetCustomLocationConfig",  # 模型/碰撞宽度（不改变编队站位）
    "RPG.GameCore.SetColliderCenterFollowAttachPoint",  # 碰撞中心附着表现（不改变编队站位）
    "RPG.GameCore.AvatarIntensityEffect",
    "RPG.GameCore.SetCharacterVisibleInViewMode",
    "RPG.GameCore.ShowBattleTalkBGUI",
    "RPG.GameCore.ToggleHitCountUITop",
    "RPG.GameCore.TriggerModelShake",
    "RPG.GameCore.UpdateMonsterFootIKMode",  # 脚部 IK 表现
    "RPG.GameCore.ChangeMonsterHeadIcon",  # 怪物头像 UI
    "RPG.GameCore.SetCharacterVisibilityFollow",  # 可见性跟随表现
    "RPG.GameCore.SetMonsterHitCountEnergyBarState",  # 能量条计数 UI
    "RPG.GameCore.SetBattleItemProgressInfo",  # 战斗道具进度展示
    "RPG.GameCore.WriteCustomValueToStatistic",  # 挑战统计，不反哺战斗机制
    "RPG.GameCore.OverrideMonsterRankScore",     # 挑战评分显示，不改变战斗 Rank/目标结算
    "PBEMMHIOJBO",  # 屏幕显隐（Screen_Visible）
    "LHOKPKHEBIK",  # 屏幕特效附着点与位置偏移（Screen，纯表现）
    "RPG.GameCore.ByIsContainModifier",  # 控制流谓词；仅在整棵表现子树中忽略
    "RPG.GameCore.ToggleUITop",
    "RPG.GameCore.TriggerEffect",
    "RPG.GameCore.TriggerEnergyBarEffect",
    "RPG.GameCore.TriggerAnimState",
    "RPG.GameCore.TriggerSound",
    "RPG.GameCore.MuteEntitySound",           # 实体静音/恢复（纯音频）
    "RPG.GameCore.SetLayerWeight",            # 动画 VisualLayer 权重（纯表现）
    "RPG.GameCore.TriggerUINotify",
    "RPG.GameCore.VCameraConfigChange",
    "RPG.GameCore.WaitAnimEvent",
    "RPG.GameCore.WaitAnimState",
    "RPG.GameCore.WaitAbilityStartTimeStamp",  # 相对技能开始的演出计时
    "RPG.GameCore.WaitSkillPerformAbilityFinish",  # 同步技能演出屏障
    "RPG.GameCore.EnableEmotion",  # 表情表现开关
    "RPG.GameCore.WaitParallelTimeStamp",
    "RPG.GameCore.WaitSecond",
    "RPG.GameCore.WaitMissionTalkFinish",
    "RPG.GameCore.WaitCustomString",      # 客户端自定义串演出屏障；同步战斗不保存等待
    "RPG.GameCore.WaitTimelineFinish",
    "RPG.GameCore.AbortModifierPhasePerform",  # 中止 modifier 阶段演出/提示，不改计时或战斗状态
    # —— 任务节点长尾族（14_policy.md 任务节点长尾节）：数据形态核证为纯表现 ——
    "RPG.GameCore.TriggerCustomString",       # 客户端自定义串（Level_SpecialWin 等 UI/表现触发）
    "RPG.GameCore.ModifyDefaultTeamFormation",  # 站位编排参数（LocalZOffset/CentralXOffset 显示位）
    "RPG.GameCore.RemoveEntityFromTeamFormation",
    "RPG.GameCore.MappingAttachPoint",        # 模型挂点映射
    "RPG.GameCore.SetEntityArtRotation",      # 模型朝向
    "RPG.GameCore.ClearActionBarHighlightEntity",
    "RPG.GameCore.SwitchChallengeBossInfoPanelState",  # UI 面板（Add/Remove 同族已在列）
    "RPG.GameCore.SwitchBattleArea",  # 场景区域切换；无战斗规则读取区域状态
    "RPG.GameCore.PreloadBattleEventByID",    # 战斗事件预载（表现资产）
    "RPG.GameCore.InsertBattlePerform",       # 剧情 BattlePerformance 资产演出
    # —— OnStack 残余复核：原始字段只含动画、模型或 UI 展示 ——
    "RPG.GameCore.ClearEntityFloatMessage",
    "RPG.GameCore.HideMonsterSkillInViewMode",
    "RPG.GameCore.HideSkillDisplayInfo",
    "RPG.GameCore.RefreshWeaknessUI",
    "RPG.GameCore.SaveModelWhenDead",
    "RPG.GameCore.SetIronTombInfinityHPUI",
    "RPG.GameCore.SetMonsterHPTotalSeg",  # 血条分段显示；不写 HP 或阶段阈值
    "RPG.GameCore.NotifyDeadPartSelected",  # 客户端死亡部位选中通知；不写战斗状态
    "RPG.GameCore.SetMonsterPhasePointPrefab",
    "RPG.GameCore.TriggerAnimStateOnModifierCustomEvent",
    # —— UI、音频、镜头、模型与特效节点（原始字段核证） ——
    "RPG.GameCore.AutoMappingAttachPoint",
    "RPG.GameCore.ChangeCharacterModel",
    "RPG.GameCore.ChangeCharacterUIDisplay",
    "RPG.GameCore.DisableCharacterVO",
    "RPG.GameCore.GlobalTimeSlow",
    "RPG.GameCore.ModifierOverrideOnHitEffect",
    "RPG.GameCore.OverrideEntityModifierPhaseCamera",
    "RPG.GameCore.ResetCharacterCustomTeamFormation",
    "RPG.GameCore.SetCameraRootFollow",
    "RPG.GameCore.SetEntityForceVisible",
    "RPG.GameCore.SetFaceDirectionLocked",
    "RPG.GameCore.ShowActionBarEffect",
    "RPG.GameCore.ShowBattleEventButton",
    "RPG.GameCore.CreateBattleEventQTEUI",    # 已注册战斗事件的 QTE 界面，不重复创建机制实体
    "RPG.GameCore.StartEffectAim",
    "RPG.GameCore.StopTimeline",
    "RPG.GameCore.TutorialTaskUnlock",
    "RPG.GameCore.VCameraNoiseChange",
    "RPG.GameCore.TriggerAutoLayoutTransferPerform",
    "RPG.GameCore.SwitchOverrideController",  # 动画 Override1/Override2，非 state_config
    "RPG.GameCore.CharacterChangeModel",
    "RPG.GameCore.DecoupleParentTransform",
    "RPG.GameCore.SetActionBarRightDownMiniIcon",
    "RPG.GameCore.LevelAudioTrigger",
    "RPG.GameCore.SetModifierEffectVisible",
    "RPG.GameCore.ChangeAnimEventConfig",
    "RPG.GameCore.FrameCaptureIfNeed",
    "RPG.GameCore.LockAnimatorSpeed",
    "RPG.GameCore.SetCharacterAtlasFaceEmotion",
    "RPG.GameCore.ForbidBattleConditionOnStart",
    "RPG.GameCore.SetSignedAngleByTarget",
    "RPG.GameCore.AlignTargetToTeamCenter",
    "RPG.GameCore.ResetTeammateAttackPerform",  # 攻击演出复位；控制状态由相邻 RemoveModifier 清除
    "RPG.GameCore.SetCharacterFormation",
    "RPG.GameCore.SetCharacterCustomTeamFormation",
})

#: 注册表即节点覆盖矩阵；值为 AbilityCompiler 方法名。
TASK_HANDLERS = {
    "RPG.GameCore.AddModifier": "_compile_add_modifier",
    "RPG.GameCore.AddWeakness": "_compile_add_weakness",
    "RPG.GameCore.DamageByAttackProperty": "_compile_damage",
    "MEDEPLMJCIC": "_compile_damage",
    "RPG.GameCore.ModifyDamageData": "_compile_modify_damage_data",
    "RPG.GameCore.StackProperty": "_compile_stack_property_task",
    "RPG.GameCore.DamageStance": "_compile_damage_stance",
    "RPG.GameCore.ReduceStanceRatio": "_compile_reduce_stance_ratio",
    "RPG.GameCore.ExitBreakState": "_compile_exit_break",
    "RPG.GameCore.ResetStance": "_compile_reset_stance",
    "RPG.GameCore.DispelStatus": "_compile_dispel_status",
    "RPG.GameCore.TurnInsertAction": "_compile_turn_insert_action",
    "RPG.GameCore.RecordEntityFormationIndex": "_compile_record_formation_index",
    "RPG.GameCore.ClearRecordEntityFormation": "_compile_clear_formation_record",
    "RPG.GameCore.EscapeFromBattle": "_compile_escape_from_battle",
    "RPG.GameCore.CharacterLeaveStage": "_compile_character_leave_stage",
    "RPG.GameCore.RemoveShield": "_compile_remove_shield",
    "RPG.GameCore.LockHP": "_compile_lock_hp",
    "RPG.GameCore.LockTargetHP": "_compile_lock_hp",
    "RPG.GameCore.UnlockTargetHP": "_compile_unlock_hp",
    "RPG.GameCore.CreateBattleEvent": "_compile_create_battle_event",
    "RPG.GameCore.SetModifierDynamicValue": "_compile_set_modifier_dynamic_value",
    "RPG.GameCore.LoopExecuteTaskListWithInterval": "_compile_loop_execute",
    "RPG.GameCore.LoopTargetList": "_compile_loop_target_list",
    "RPG.GameCore.AddEntityToTeamFormation": "_compile_add_to_formation",
    "RPG.GameCore.AttachEntityUnselectable": "_compile_attach_unselectable",
    "RPG.GameCore.SetDynamicEntityParam": "_compile_set_entity_param",
    "RPG.GameCore.SetTargetUniqueName": "_compile_set_unique_name",
    "RPG.GameCore.SetTargetTeamLocation": "_compile_team_location",
    "RPG.GameCore.SetEntityActionState": "_compile_entity_action_state",
    "RPG.GameCore.SetCharacterAlwaysIdleState": "_compile_always_idle",
    "RPG.GameCore.SetDynamicValueByVariateType": "_compile_variate",
    "RPG.GameCore.SetModifierValue": "_compile_set_modifier_value",
    "RPG.GameCore.DefineDynamicValue": "_compile_define_dynamic",
    "RPG.GameCore.ForceKill": "_compile_force_kill",
    "RPG.GameCore.DestroyBattleCharacter": "_compile_destroy_character",
    "RPG.GameCore.FireProjectile": "_compile_projectile",
    "RPG.GameCore.NewFireProjectile": "_compile_projectile",
    "RPG.GameCore.FireWaveProjectile": "_compile_wave_projectile",
    "RPG.GameCore.HealHP": "_compile_heal_hp",
    "RPG.GameCore.InitShield": "_compile_init_shield",
    "RPG.GameCore.IncludeTaskListTemplate": "_compile_include_tasks",
    "RPG.GameCore.TriggerParallelTaskListTemplate": "_compile_parallel_templates",
    "RPG.GameCore.LoseHPByRatio": "_compile_lose_hp",
    "RPG.GameCore.LoseHP": "_compile_lose_hp_absolute",
    "RPG.GameCore.ModifyLoseHPData": "_compile_modify_lose_hp",
    "RPG.GameCore.LoopExecuteTaskList": "_compile_loop",
    "RPG.GameCore.ConditionLoopExecuteTaskList": "_compile_condition_loop",
    "RPG.GameCore.WaitFor": "_compile_wait_for",
    "RPG.GameCore.ApplyOperation": "_compile_apply_operation",
    "RPG.GameCore.ShowTargetHPBar": "_compile_show_target_hp_bar",
    "RPG.GameCore.SequenceConfig": "_compile_sequence_config",
    "RPG.GameCore.LockStance": "_compile_lock_stance",
    "RPG.GameCore.LockActionDelayChange": "_compile_lock_action_delay",
    "RPG.GameCore.LockTargetActionDelay": "_compile_lock_action_delay",
    "RPG.GameCore.ModifyActionDelay": "_compile_modify_action_delay",
    "RPG.GameCore.ModifyCurrentSkillDelayCost": "_compile_current_skill_delay",
    "RPG.GameCore.ModifySPNew": "_compile_modify_energy",
    "RPG.GameCore.ModifySpecialSP": "_compile_modify_special_sp",
    "RPG.GameCore.ModifyTeamBoostPoint": "_compile_modify_skill_point",
    "RPG.GameCore.ModifyTeamBoostPointMax": "_compile_modify_skill_point_max",
    "RPG.GameCore.ModifyShieldMax": "_compile_modify_shield_max",
    "RPG.GameCore.ModifyShield": "_compile_modify_shield",
    "RPG.GameCore.PredicateTaskList": "_compile_predicate_tasks",
    "RPG.GameCore.IncludeGlobalTaskListTemplate": "_compile_include_tasks",
    "RPG.GameCore.RandomConfig": "_compile_random_config",
    "RPG.GameCore.Retarget": "_compile_retarget",
    "RPG.GameCore.RetargetList": "_compile_retarget_list",
    "RPG.GameCore.Remodifier": "_compile_remodifier",
    "RPG.GameCore.RemoveModifier": "_compile_remove_modifier",
    "RPG.GameCore.RemoveModifierByBehaviorFlag": "_compile_remove_modifier_by_behavior_flag",
    "RPG.GameCore.RemoveSelfModifier": "_compile_remove_self_modifier",
    "RPG.GameCore.SetActionDelay": "_compile_action_delay",
    "RPG.GameCore.SetActionDelayNearTarget": "_compile_action_delay_near",
    "RPG.GameCore.ResetActionDelay": "_compile_reset_action_delay",
    "RPG.GameCore.SetHP": "_compile_set_hp",
    "RPG.GameCore.SetDieImmediately": "_compile_set_die",
    "RPG.GameCore.SetDynamicValue": "_compile_define_dynamic",
    "RPG.GameCore.SetDynamicValueByAddValue": "_compile_dynamic_add",
    "RPG.GameCore.SetDynamicValueByCharacterCount": "_compile_character_count",
    "RPG.GameCore.SetDynamicValueByDelayCumulate": "_compile_delay_cumulate",
    "RPG.GameCore.SetDynamicValueByStanceCount": "_compile_stance_count_value",
    "RPG.GameCore.SetDynamicValueByCopying": "_compile_dynamic_copying",
    "RPG.GameCore.SetDynamicValueByChangeValue": "_compile_change_value",
    "RPG.GameCore.SetDynamicValueByBPChange": "_compile_change_value",
    "RPG.GameCore.SetDynamicValueByMaxBP": "_compile_max_bp",
    "RPG.GameCore.SetDynamicValueByDamageDataProperty": "_compile_damage_data_value",
    "RPG.GameCore.SetDynamicValueByHPRatio": "_compile_hp_ratio_dynamic",
    "RPG.GameCore.SetDynamicValueBySkillMaxHitSplitCount": "_compile_skill_max_hit_split_count",
    "RPG.GameCore.SetDynamicValueByFormationIndex": "_compile_formation_index",
    "RPG.GameCore.SetDynamicValueByModifierValue": "_compile_modifier_value",
    "RPG.GameCore.SetBattleTargetProgress": "_compile_battle_target_progress",
    "RPG.GameCore.SetBossHPStanceChangeType": "_compile_boss_hp_stance_change",
    "RPG.GameCore.SetDynamicValueByBattleTargetParam": "_compile_battle_target_param",
    "RPG.GameCore.SetDynamicValueByProperty": "_compile_property_value",
    "BIEFKHPDHPI": "_compile_obfuscated_property_value",
    "JONKKMAJCAH": "_compile_obfuscated_empty_placeholder",
    "PHKBMFDEOOK": "_compile_obfuscated_empty_placeholder",
    "DBLFKIDDKDO": "_compile_obfuscated_empty_placeholder",
    "RPG.GameCore.SetMonsterPhase": "_compile_monster_phase",
    "RPG.GameCore.SetMonsterViewPhase": "_compile_monster_view_phase",
    "RPG.GameCore.ApplyMonsterPhaseOverrideConfig": "_compile_empty_phase_override",
    "RPG.GameCore.SetMonsterStanceVulnerable": "_compile_stance_vulnerable",
    "RPG.GameCore.SetStanceCount": "_compile_set_stance_count",
    "RPG.GameCore.TriggerStanceCountDown": "_compile_trigger_stance_countdown",
    "RPG.GameCore.TriggerBreak": "_compile_trigger_break",
    "RPG.GameCore.SummonMonster": "_compile_summon_monster",
    "RPG.GameCore.SwitchCaseByDynamicValue": "_compile_switch",
    "RPG.GameCore.SwitchCase": "_compile_switch_cases",
    "RPG.GameCore.SwitchCaseByAttackDamageType": "_compile_switch_damage_type",
    "RPG.GameCore.TriggerModifierCustomEvent": "_compile_trigger_modifier_custom_event",
    "RPG.GameCore.TriggerAbility": "_compile_trigger_ability",
    "RPG.GameCore.AutoUseUltraSkill": "_compile_auto_ultra",
    "RPG.GameCore.OwnerEntityAddAbility": "_compile_owner_add_ability",
    "RPG.GameCore.AddStageAbilityByName": "_compile_add_stage_ability",
    "RPG.GameCore.TriggerParallelAbility": "_compile_parallel_ability",
    "RPG.GameCore.TriggerAnimStateWithMove": "_compile_animation_events",
    "RPG.GameCore.TurnInsertAbility": "_compile_trigger_ability",
    "RPG.GameCore.ChangeCharacterConfigParam": "_compile_change_config_param",
    "RPG.GameCore.StackWeakness": "_compile_stack_weakness_task",
    "RPG.GameCore.ClearWeakness": "_compile_clear_weakness",
    "RPG.GameCore.PerformDelayExecute": "_compile_perform_delay_execute",
    "RPG.GameCore.AddBuffPerform": "_compile_add_buff_perform",
    "RPG.GameCore.BattlePlayVideo": "_compile_battle_play_video",
    "MOPOKJECALI": "_compile_obfuscated_control_mapping",
    "DNBOLDHOBML": "_compile_obfuscated_hp_bar_visibility",
    "OHONOHOIOJA": "_compile_obfuscated_empty_disable",
    "AIGHNCCAJPL": "_compile_obfuscated_auto_bp_preferences",
    "AGPCKNGHOAH": "_compile_obfuscated_auto_bp_preferences",
    "JDOLDFECMPL": "_compile_obfuscated_punchline",
}
EVENT_HANDLERS = {
    "OnDeathrattle": "_compile_deathrattle",
    "OnListenCharacterDie": "_compile_deathrattle",
}

#: 被动 modifier 回调事件 → 引擎载体映射（14_policy.md 被动事件族节为文档镜像——改映射
#: 只改这里；`_compile_modifier_lifecycle` 消费）。值 = (kind, engine_event, condition)：
#: - kind="hook"：回调任务编译为 engine_event 上的全局钩，condition 为持有者窄化
#:   （"$self.actor_id" = modifier 持有者 = hook owner；owner 死亡的 alive 闸天然生效）；
#: - kind="definition"：modifier 定义编译期消费（visit_stack/DoT 既有口径，非常消费任务
#:   在定义编译里显式拒）；
#: - kind=None：无载体事件显式 unsupported（condition 位写理由，进 human_queue 不猜测）。
_PASSIVE_EVENT_MAP = {
    "OnBeingBreak": ("hook", "on_break", "$event.target == $self.actor_id"),
    "OnBeforeBeingBreak": ("hook", "on_break", "$event.target == $self.actor_id"),
    "OnListenBreak": ("hook", "on_break", "true"),
    "OnTriggerBreak": ("hook", "on_break", "$event.target == $self.actor_id"),
    "OnEndBreak": ("hook", "toughness_recovered", "$event.target == $self.actor_id"),
    "OnStanceReset": ("hook", "toughness_recovered", "$event.target == $self.actor_id"),
    "OnListenEndBreak": ("hook", "toughness_recovered", "true"),
    "OnListenBattleEventCreate": ("hook", "battle_event_create", "true"),
    "OnMonsterPhaseChanged": ("hook", "monster_phase_changed", "$event.actor == $self.actor_id"),
    "OnDeathrattle": ("hook", "on_kill", "$event.target == $self.actor_id"),
    "OnTriggerDeath": ("hook", "on_kill", "$event.target == $self.actor_id"),
    "OnTriggerDeathrattle": ("hook", "on_kill", "$event.target == $self.actor_id"),
    "OnModifierAdd": ("hook", "after_apply_modifier", "$event.target == $self.actor_id"),
    "OnListenModifierAdd": ("hook", "after_apply_modifier", "$event.target == $self.actor_id"),
    "OnModifierOnStack": ("hook", "after_apply_modifier", "true"),
    "OnListenModifierOnStack": ("hook", "after_apply_modifier", "true"),
    "OnModifierRemove": ("hook", "after_remove_modifier", "$event.target == $self.actor_id"),
    "OnListenModifierRemove": ("hook", "after_remove_modifier",
                               "$event.target == $self.actor_id"),
    "OnListenModifierDispel": ("hook", "after_remove_modifier",
                               "$event.target == $self.actor_id and $event.reason == 'dispel'"),
    "OnDispel": ("hook", "after_remove_modifier",
                 "$event.target == $self.actor_id and $event.reason == 'dispel'"),
    "OnAfterBeingHit": ("hook", "after_being_hit", "$event.target == $self.actor_id"),
    "OnAfterBeingHitAll": ("hook", "after_being_hit", "$event.target == $self.actor_id"),
    "OnListenAfterBeingHitAll": ("hook", "after_being_hit", "true"),
    "OnAfterHit": ("hook", "after_being_hit", "$event.source == $self.actor_id"),
    "OnAfterHitAll": ("hook", "after_being_hit", "$event.target == $self.actor_id"),
    "OnBeforeHit": ("hook", "before_take_damage", "$event.target == $self.actor_id"),
    "OnBeforeHitAll": ("hook", "before_take_damage", "$event.source == $self.actor_id"),
    "OnAfterBeingAttacked": ("hook", "after_being_hit", "$event.target == $self.actor_id"),
    "OnAfterBeingAttackedEnd": ("hook", "after_being_hit", "$event.target == $self.actor_id"),
    "OnAfterBeingAttackedAdv": ("hook", "after_being_hit", "$event.target == $self.actor_id"),
    "OnBeforeBeingHit": ("hook", "before_take_damage", "$event.target == $self.actor_id"),
    "OnBeforeBeingHitAll": ("hook", "before_take_damage", "$event.target == $self.actor_id"),
    "OnBeforeBeingAttacked": ("hook", "before_take_damage", "$event.target == $self.actor_id"),
    "OnEnterBattle": ("hook", "actor_enter", "$event.actor == $self.actor_id"),
    "OnListenCharacterCreate": ("hook", "actor_enter", "true"),
    "OnListenTurnBegin": ("hook", "on_turn_start", "true"),
    "OnListenTurnEnd": ("hook", "on_turn_end", "true"),
    "OnListenTurnPhase1Begin": ("hook", "on_turn_start", "true"),
    "OnListenTurnPhase2Begin": ("hook", "on_turn_end", "true"),
    "OnListenBeforeTurnPhase1End": ("hook", "on_turn_end", "true"),
    "OnListenInsertAbilityStart": ("hook", "on_action", "$event.insert"),
    "OnInsertAbilityStart": ("hook", "on_action", "$event.insert and $event.actor == $self.actor_id"),
    "OnListenInsertAbilityFinish": ("hook", "on_action_end", "$event.insert"),
    "OnInsertAbilityFinish": ("hook", "on_action_end", "$event.insert"),
    "OnListenInsertActionFinish": ("hook", "on_action_end", "$event.insert"),
    "OnListenElationTimeStart": ("hook", "aha_instant_start", "true"),
    "OnListenAfterAction": ("hook", "on_action_end", "true"),
    "OnAfterSkillUse": ("hook", "on_action",
                        "$event.actor == $self.actor_id and $event.action_type == 'skill'"),
    "OnListenAfterSkillUse": ("hook", "on_action", "$event.action_type == 'skill'"),
    "OnLeaveBattle": ("hook", "actor_exit", "$event.actor == $self.actor_id"),
    "OnDepartedStart": ("hook", "before_actor_exit", "$event.actor == $self.actor_id"),
    "OnListenDepartedStart": ("hook", "before_actor_exit", "true"),
    "OnDepartedEnd": ("hook", "actor_exit", "$event.actor == $self.actor_id"),
    "OnListenDepartedEnd": ("hook", "actor_exit", "true"),
    "OnLockHPThresholdReached": ("hook", "on_hp_lock", "$event.target == $self.actor_id"),
    "OnBeingStanceDamage": ("hook", "on_toughness_damage", "$event.target == $self.actor_id"),
    "OnBeforeWaveMonster": ("hook", "on_wave_start", "true"),   # 近似：波开始 vs 怪登场前，待实测
    "OnWaveMonster": ("hook", "on_wave_start", "true"),
    "OnStack": ("definition", "", ""),
    "OnPhase1": ("definition", "", ""),
    "OnPhase2": ("definition", "", ""),
    "OnStage": ("definition", "", ""),
    # —— 无载体事件：显式 unsupported（理由逐条写明） ——
    "OnHPOverflow": ("hook", "on_hp_increase", "$event.excess > 0"),
    "OnBeforeBeingLoseHP": ("hook", "before_drain", "$event.target == $self.actor_id"),
    "OnListenRevive": ("hook", "on_revive", "true"),
    "OnBeingRevived": ("hook", "on_revive", "$event.target == $self.actor_id"),
    "OnSPChange": ("hook", "on_energy_change", "$event.target == $self.actor_id"),
    "OnListenBpChange": ("hook", "on_skill_point_change", "true"),
    "OnUnselectableStart": ("hook", "on_unselectable_start", "$event.target == $self.actor_id"),
    "OnUnselectableEnd": ("hook", "on_unselectable_end", "$event.target == $self.actor_id"),
    "OnAllowAction": ("hook", "on_turn_start", "not action_disabled($event.actor)"),
    "OnListenAllowAction": ("hook", "on_turn_start", "not action_disabled($event.actor)"),
    "OnActionEnd": ("hook", "on_action_end", "$event.actor == $self.actor_id"),
    "OnCharmAction": ("hook", "on_action", "$event.actor == $self.actor_id"),
    "OnAfterAttack": ("hook", "on_action_end", "$event.actor == $self.actor_id"),
    "OnAfterAttackEnd": ("hook", "on_action_end", "$event.actor == $self.actor_id"),
    "OnListenAfterAttack": ("hook", "on_action_end", "true"),
    "OnListenAfterAttackEnd": ("hook", "on_action_end", "true"),
    "OnListenCharmMakeDamage": ("hook", "after_being_hit", "true"),
    "OnBeforeAction": ("hook", "before_action", "$event.actor == $self.actor_id"),
    "OnBeforeAttack": ("hook", "before_action", "$event.actor == $self.actor_id"),
    "OnListenBeforeAttack": ("hook", "before_action", "true"),
    "OnListenBeforeAction": ("hook", "before_action", "true"),
    "OnActionPhaseBegin": ("hook", "before_action", "$event.actor == $self.actor_id"),
    "OnListenActionPhaseBegin": ("hook", "before_action", "true"),
    "OnBeforeSkillUse": ("hook", "before_action",
                         "$event.actor == $self.actor_id and $event.action_type == 'skill'"),
    "OnListenBeforeSkillUse": ("hook", "before_action", "$event.action_type == 'skill'"),
    "OnUltraSkillPrepare": ("hook", "on_ultimate_prepare", "$event.source == $self.actor_id"),
    "OnBeforeUltraSkillPrepare": ("hook", "on_ultimate_prepare", "$event.source == $self.actor_id"),
    "OnListenUltraSkillPrepare": ("hook", "on_ultimate_prepare", "true"),
    "OnBeingLimbo": ("hook", "on_hp_decrease", "__limbo__"),
    "OnLimboWaitHeal": ("hook", "on_hp_decrease", "__limbo__"),
    "OnBeforeMortallyWonded": (None, "", "濒死保护域语义未收编"),
    "OnCustomEvent": (None, "", "非 DoT/怪物阶段自定义事件未注册"),
    "OnListenCharacterDie": ("hook", "on_kill", "true"),
    "OnListenShieldChange": ("hook", "shield_changed", "true"),
    "OnShieldChange": ("hook", "shield_changed", "$event.target == $self.actor_id"),
    "OnListenCharacterEscape": ("hook", "actor_exit", "$event.reason == 'flee'"),
    "OnListenCharacterLimbo": ("hook", "on_hp_decrease", "hp_of($event.target) <= 0"),
    "OnListenActionEnd": ("hook", "on_action_end", "true"),
    "OnInsertActionStart": ("hook", "before_action", "$event.insert and $event.actor == $self.actor_id"),
    "OnBeforeInsertActionPrepare": ("hook", "before_action", "$event.insert and $event.actor == $self.actor_id"),
    "OnListenInsertActionStart": ("hook", "before_action", "$event.insert"),
    "OnBeingStanceCountDown": ("hook", "on_stance_countdown", "$event.target == $self.actor_id"),
    "OnAfterAction": ("hook", "on_action_end", "$event.actor == $self.actor_id"),
    "OnBeforeEscape": ("hook", "before_actor_exit",
                       "$event.actor == $self.actor_id and $event.reason == 'flee'"),
}

_ELEMENT = {"Thunder": "thunder", "Lightning": "thunder"}
_SUMMON_ID_HASH_BASE = 1509106746   # 上游保留的 SummonIDList[0..5] 哈希段
_DEFAULT_LAYER_ADD_HASH = -797864550   # LayerAddWhenStack 的默认单层保留哈希


def _is_passive_row(skill: Dict[str, Any]) -> bool:
    """CharacterConfig.SkillList 行是否被动技能——SkillType=Passive 优先（真实数据
    里行 Name 常是能力名而非 Passive 前缀，如 Kafka `Monster_W2_Kafka_00_Passive01`），
    Passive/SkillP 名前缀为兼容闸。"""
    return (str(skill.get("SkillType") or "").lower().startswith("passive")
            or str(skill.get("Name") or "").startswith(("Passive", "SkillP")))


def _is_camera_ability(name: Any) -> bool:
    text = str(name or "")
    return (text.endswith(("_Camera", "DeathSetCamera", "MuteHitFly")) or "_Camera_" in text
            or ("_Camera" in text and text.rsplit("_Camera", 1)[1].isdigit()))


def _element(raw: Any) -> str:
    value = str((raw or {}).get("DamageType") if isinstance(raw, dict) else raw or "").lower()
    return _ELEMENT.get(str((raw or {}).get("DamageType") if isinstance(raw, dict) else raw), value)


def _trailblazer_target_spec() -> Optional[Dict[str, Any]]:
    from hsr_nous.pipeline.build.loader import load_characters
    ids = sorted(str(cid) for cid, info in load_characters().items()
                 if info.get("name") in {"{NICKNAME}", "Trailblazer"})
    if not ids:
        return None
    return {"pool": "allies", "where": f"character_id($it) in {ids!r}"}


def _fixed(raw: Any) -> Any:
    if isinstance(raw, dict) and not raw.get("IsDynamic"):
        return (raw.get("FixedValue") or {}).get("Value")
    return raw


def _atom(value: Any) -> Any:
    return ("atom", value) if isinstance(value, str) else value


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _binary(op: str, left: Any, right: Any) -> Any:
    if _is_number(left) and _is_number(right):
        if op == "+":
            return left + right
        if op == "*":
            return left * right
        if op == "-":
            return left - right
        if op == "/":
            if right == 0:
                raise ValueError("PostfixExpr 除数为 0")
            return left / right
        if op == "==":
            return 1.0 if left == right else 0.0
    if op == "*":
        parts: List[Any] = []
        for value in (left, right):
            if isinstance(value, tuple) and value and value[0] == "*":
                parts.extend(value[1])
            else:
                parts.append(value)
        coefficient = 1.0
        others = []
        for value in parts:
            if _is_number(value):
                coefficient *= value
            else:
                others.append(value)
        if coefficient == 0:
            return 0.0
        parts = ([] if coefficient == 1 and others else [coefficient]) + others
        if len(parts) == 1:
            return parts[0]
        return ("*", parts)
    return (op, left, right)


def _format(value: Any, parent: str = "") -> str:
    if _is_number(value) or isinstance(value, str):
        return str(value)
    if isinstance(value, tuple) and value[0] == "atom":
        return str(value[1])
    op = value[0]
    parts = value[1] if op == "*" else list(value[1:])
    rendered = []
    for part in parts:
        text = _format(part, op)
        if isinstance(part, tuple) and part[0] not in {"atom", op}:
            text = f"({text})"
        rendered.append(text)
    return f" {op} ".join(rendered)


def compile_dynamic_value(raw: Any, symbols: Optional[Dict[int, Any]] = None) -> Any:
    """编译上游 PostfixExpr；支持固定值、动态槽、四则运算、等值比较及单目取负，其余显式拒绝.

    返回数值或 DSL 表达式字符串。字节码中 0/1 分别为 FixedValues /
    DynamicHashes 下标读取，0x06 为数值等值比较，0x0e 为单目取负，0x11 为结束；
    未知 opcode 不猜测。
    """
    if not isinstance(raw, dict) or not raw.get("IsDynamic"):
        return _fixed(raw)
    expr = raw.get("PostfixExpr") or {}
    symbols = symbols or {}
    try:
        code = base64.b64decode(str(expr.get("OpCodes") or ""))
    except Exception as exc:
        raise ValueError("PostfixExpr.OpCodes 不是合法 base64") from exc
    fixed = expr.get("FixedValues") or []
    dynamic = expr.get("DynamicHashes") or []
    stack: List[Any] = []
    index = 0
    ended = False
    while index < len(code):
        op = code[index]
        index += 1
        if op in (0, 1):
            if index >= len(code):
                raise ValueError("PostfixExpr 槽读取缺下标")
            slot = code[index]
            index += 1
            source = fixed if op == 0 else dynamic
            if slot >= len(source):
                raise ValueError(f"PostfixExpr {'固定' if op == 0 else '动态'}槽越界：{slot}")
            if op == 0:
                stack.append((source[slot] or {}).get("Value"))
            else:
                key = int(source[slot])
                if key not in symbols:
                    raise ValueError(f"未知 DynamicHash：{key}")
                stack.append(_atom(symbols[key]))
            continue
        operators = {2: "+", 3: "-", 4: "*", 5: "/", 6: "=="}
        if op in operators:
            if len(stack) < 2:
                raise ValueError("PostfixExpr 二元运算栈不足")
            right, left = stack.pop(), stack.pop()
            stack.append(_binary(operators[op], left, right))
            continue
        if op == 14:
            if not stack:
                raise ValueError("PostfixExpr 单目取负栈不足")
            stack.append(_binary("-", 0, stack.pop()))
            continue
        if op == 17:
            ended = True
            break
        raise ValueError(f"未知 PostfixExpr opcode：0x{op:02x}")
    if not ended or len(stack) != 1:
        raise ValueError("PostfixExpr 未正常结束或栈不唯一")
    value = stack[0]
    return value if _is_number(value) else _format(value)


_ELATION_BE_TARGET = {
    "concat": [{"pool": "unique:$battle_event:70001"}, {"pool": "unique:$battle_event:70002"}],
}

_INCLUSIVE_TEAM_TARGETS = {
    "TauntOrAggroEnemy": {"pool": "enemy_targets", "take": 1, "mode": "taunt_or_aggro"},
    "AllEnemy.RemoveServant": {"pool": "allies", "where": "not $it.summoner_id"},
    "AllLightAvatar": {"pool": "allies", "where": "actor_type_of($it) == 'character'"},
    "AllLightTeam - ModifierOwnerEntity": {
        "pool": "allies", "where": "$it.actor_id != $self.actor_id"},
    "AllDarkTeam - ModifierOwnerEntity": {
        "pool": "enemies", "where": "$it.actor_id != $self.actor_id"},
    "Monster_W4_Griffin_00_LocalLegend_Partner": {
        "pool": "enemies", "where": "$it.actor_id != $self.actor_id"},
    "AllDarkTeamUnselectable": {
        "pool": "enemies", "include_unselectable": True,
        "where": "not ($it.enemy_targetable and $it.ally_targetable)"},
    "AllEnemy.GetServant": {"pool": "allies", "where": "$it.summoner_id"},
    "ServantEntityList": {
        "pool": "all", "include_unselectable": True,
        "where": "actor_type_of($it) == 'summon'"},
    "AllLightTeamOnlyAddSPOnceForServant": {
        "pool": "allies", "where": "not $it.summoner_id"},
    "AllLightTeam.SortByHP.Reverse": {"pool": "allies", "order_by": "-$it.hp"},
    "AbilityTargetEntity.GetSummoner": {
        "pool": "all", "where": "$it.actor_id == summoner_of($event.target)"},
    "ModifierOwnerEntityAllTeammate": {
        "pool": "enemies", "where": "$it.actor_id != $self.actor_id"},
    "ModifierOwnerEntityAdjoinEntity": {
        "pool": "enemies", "where": "is_adjacent($it, $self.actor_id)"},
    "ProjectileHitEntityAdjoinEntity": {
        "pool": "allies", "where": "is_adjacent($it, $event.target)"},
    "AllTeammate.RemoveUnselectable": {
        "pool": "enemies", "where": "$it.enemy_targetable and $it.ally_targetable"},
    "AllDarkTeam + AllLightTeam": {"pool": "all"},
    "AllTeammateWithUnselectable": {"pool": "enemies", "include_unselectable": True},
    "LeftToRightDarkTeamTarget": {"pool": "enemies", "order_by": "formation"},
    "RightToLeftDarkTeamTarget": {"pool": "enemies", "order_by": "-formation"},
    "Monster_Svarog_00_Unselectable": {
        "pool": "enemies", "include_unselectable": True,
        "where": "in_group($it, 'W1_SvarogPart')"},
    "Monster_Svarog_00_RL_Unselectable": {
        "pool": "enemies", "include_unselectable": True,
        "where": "in_group($it, 'W1_SvarogPart') and in_group($it, 'RL')"},
    "AllLightTeamWithAllLightTeamUnselectable": {
        "pool": "allies", "include_unselectable": True},
    "AllLightTeamWithAllUnselectableLightTeam": {
        "pool": "allies", "include_unselectable": True},
    "AllLightTeamWithAllLightTeamUnselectable.RemoveServant": {
        "pool": "allies", "include_unselectable": True,
        "where": "not $it.summoner_id"},
    "AllLightTeamWithAllUnselectableLightTeam.RemoveServant": {
        "pool": "allies", "include_unselectable": True,
        "where": "not $it.summoner_id"},
    "AbilityTargetEntity.WithServant": {
        "pool": "all",
        "where": "$it.actor_id == $event.target or $it.summoner_id == $event.target"},
    "AllLightTeamWithAllLightTeamUnselectable.RemoveBattleEvent": {
        "pool": "allies", "include_unselectable": True,
        "where": "actor_type_of($it) != 'battle_event'"},
    "AllLightTeamWithAllUnselectableLightTeam.RemoveBattleEvent": {
        "pool": "allies", "include_unselectable": True,
        "where": "actor_type_of($it) != 'battle_event'"},
    "AllDarkTeamWithAllDarkTeamUnselectable": {
        "pool": "enemies", "include_unselectable": True},
    "AllLightTeamWithAllDarkTeam": {"pool": "all"},
    "AllLightTeamIgnoreServant.RemoveCharacterChangeTarget": {
        "pool": "allies", "where": "actor_type_of($it) == 'character'"},
    "AllLightTeamWithAllDarkTeamWithAllUnSelectable": {
        "pool": "all", "include_unselectable": True},
    "BattleAllEntity": {"pool": "all_with_battle_events"},
    "BattleEventEntityList": {"pool": "battle_events"},
    "AllUnselectable": {"pool": "unselectable"},
    "AllEnemyIgnoreServant": {"pool": "allies", "where": "not $it.summoner_id"},
    "AllLightTeam.GetServant": {"pool": "allies", "where": "$it.summoner_id"},
    "AllEnemyWithUnSelectable": {"pool": "allies", "include_unselectable": True},
    "AllUnselectableWithAllTeammate": {"pool": "enemies", "include_unselectable": True},
    "GridFight_AllBackEnd": {"pool": "enemies", "include_unselectable": True},
    "ModifierOwnerSummonedMinions": {
        "pool": "enemies", "where": "$it.summoner_id == $self.actor_id"},
    "ModifierOwnerEntityAndAdjoinEntity": {
        "pool": "enemies",
        "where": "$it.actor_id == $self.actor_id or is_adjacent($it, $self.actor_id)"},
    "CasterWithAllEnemy": {
        "pool": "all",
        "where": "$it.actor_id == $self.actor_id or not (actor_type_of($it) == 'monster' or actor_type_of($it) == 'enemy')"},
    "Caster + CasterSummonedMinions": {
        "pool": "all",
        "where": "$it.actor_id == $self.actor_id or $it.summoner_id == $self.actor_id"},
    "CasterSummoner": {
        "pool": "all", "where": "$it.actor_id == summoner_of($self.actor_id)"},
    "CurrentTurnOwnerEntity": {
        "pool": "all", "where": "$it.actor_id == turn_owner_of()"},
    "AvatarNextTurnOwnerEntity": {
        "pool": "allies", "where": "is_top_action_delay_target($it, 'light', 1)"},
    "ModifierOwnerSummoner": {
        "pool": "all", "where": "$it.actor_id == summoner_of($self.actor_id)"},
    "LeftToRightLightTeamTarget": {"pool": "allies", "order_by": "formation"},
    "LeftToRightLightTeamTarget.RemoveServant": {
        "pool": "allies", "where": "not $it.summoner_id", "order_by": "formation"},
    "RightToLeftLightTeamTarget": {"pool": "allies", "order_by": "-formation"},
}


@dataclass
class _Context:
    mode: str
    skill: Dict[str, Any]
    event: str = "on_action"
    condition: str = "true"
    damages: List[Dict[str, Any]] = field(default_factory=list)
    effects: List[Dict[str, Any]] = field(default_factory=list)
    pre_effects: List[Dict[str, Any]] = field(default_factory=list)
    seen_damage: bool = False
    conditional_damage: bool = False
    hit_effects: List[Dict[str, Any]] = field(default_factory=list)
    loop_depth: int = 0
    retarget: Any = None
    retarget_damage: bool = False
    retarget_damage_records: List[Dict[str, Any]] = field(default_factory=list)
    current_modifier: str = ""
    param_modifier: str = ""
    dynamic_writes: set[str] = field(default_factory=set)
    count_expressions: Dict[int, str] = field(default_factory=dict)
    value_symbols: Dict[int, Any] = field(default_factory=dict)
    lifecycle_hooks: List[Dict[str, Any]] = field(default_factory=list)
    before_dying_stack: Tuple[str, ...] = ()
    modifier_stack: Tuple[str, ...] = ()
    summons: List[Dict[str, Any]] = field(default_factory=list)
    unsupported: List[Dict[str, str]] = field(default_factory=list)
    handled: List[str] = field(default_factory=list)
    live_condition: str = "true"
    in_target_filter: bool = False
    current_ability: str = ""
    passive_owner: bool = False   # 被动挂载通道标记（compile_passive 置位）
    passive_deathrattle_names: frozenset = frozenset()  # 已由专用亡语通道消费的 ability.Modifiers
    in_dynamic_loop: bool = False


class AbilityCompiler:
    """按节点类型递归编译一个敌人的技能与被动."""

    def __init__(
        self,
        enemy_id: str,
        skills: List[Dict[str, Any]],
        sources: Dict[str, Any],
        *,
        semantics: Optional[Dict[str, Dict[str, Any]]] = None,
        level: int = 80,
    ) -> None:
        self.enemy_id = str(enemy_id)
        self.level = int(level)
        self.skills = {str(s.get("trigger_key")): s for s in skills if s.get("trigger_key")}
        self.sources = sources
        self.config = sources.get("character_config") or {}
        self.abilities = sources.get("abilities") or {}
        self.modifiers = sources.get("modifiers") or {}
        added = self._scan_added_abilities(
            "RPG.GameCore.OwnerEntityAddAbility", "AbilityName")
        initial = {str(name) for name in self.config.get("AbilityList") or []}
        self.gated_abilities = added - initial
        self.gated_stage_abilities = self._scan_added_abilities(
            "RPG.GameCore.AddStageAbilityByName", "StageAbilityName")
        self.stage_ability_params: Dict[str, Dict[str, Any]] = {}
        self.semantics = semantics or {}
        self.custom_values = sources.get("custom_values") or {}
        self.custom_value_tags = sources.get("custom_value_tags") or []
        self.skill_param_triggers = self._scan_skill_param_triggers()
        self.config_ai_references = self._scan_config_ai_references()
        self.target_aliases = sources.get("target_aliases") or {}
        self.global_templates = sources.get("global_templates") or {}
        self._predicate_modifier_names = self._scan_predicate_modifier_names()
        self.modifier_dynamic_keys = self._scan_modifier_dynamic_keys()
        self.monster_template_id = str(sources.get("monster_template_id") or self.enemy_id)
        self.config_skills = {
            str(s.get("Name")): s for s in self.config.get("SkillList") or [] if s.get("Name")
        }
        self.dynamic_keys, self.written_dynamic_keys = self._scan_dynamic_keys()
        self.dynamic_symbols = self._character_symbols()
        # 被写键的哈希 → dynamic_of 活读回落（最低优先级符号层）：PostfixExpr 读取
        # 本敌任意已登记动态键（含生成期被写键与 modifier 自槽）时不再"未知哈希"——
        # 活读走四层读链最高优先的帧覆盖层（写后读，#26 期 2/3）；同名哈希冲突不回落。
        # 全语料反查表（pipeline 生成物）先铺底：全局键/跨文件键的哈希在敌外定义，
        # 本敌扫描不可见——表只收语料级写入键（运行时读语义），内联参数族/冲突桶
        # 已在生成侧排除（scripts/mine_dynamic_key_table.py 口径）；本敌扫描覆盖
        # 全局层（近水楼台），跨层冲突整桶撤回落。
        from hsr_nous.pipeline.enemies.dynamic_key_table import DYNAMIC_KEY_HASH_TABLE
        from hsr_nous.sim_schema.config_ai import RUNTIME_DYNAMIC_DEFAULTS
        name_symbols: Dict[int, str] = {
            hashed: f"dynamic_of($self.actor_id, '{name}')"
            for hashed, name in DYNAMIC_KEY_HASH_TABLE.items()
        }
        # 运行时供给键补充注册（决策卡 #27）：全语料只读不写，挖矿表天然漏收——
        # 缺省值与运行侧读值共用 sim_schema RUNTIME_DYNAMIC_DEFAULTS 单一事实源。
        for name in RUNTIME_DYNAMIC_DEFAULTS:
            name_symbols[dynamic_value_hash(name)] = f"dynamic_of($self.actor_id, '{name}')"
        for name in self.dynamic_keys:
            if any(ch in name for ch in "'\"\\"):
                continue
            hashed = dynamic_value_hash(name)
            if hashed in name_symbols:
                existing = name_symbols[hashed]
                rendered = f"dynamic_of($self.actor_id, '{name}')"
                if existing != rendered:
                    name_symbols.pop(hashed, None)   # 跨层冲突撤回落（保持显式拒绝）
            else:
                name_symbols[hashed] = f"dynamic_of($self.actor_id, '{name}')"
        self.dynamic_name_symbols = name_symbols
        # 只读 CustomValue 与 SkillParam 分命名空间，保留 Switch 的哈希冲突检测。
        self.custom_value_symbols = {
            dynamic_value_hash(str(name)): value
            for name, value in self.custom_values.items()
            if _is_number(value) and self._custom_value_is_readonly(str(name))
        }

    def _scan_added_abilities(self, node_type: str, field: str) -> set[str]:
        added: set[str] = set()

        def visit(value: Any) -> None:
            if isinstance(value, dict):
                if value.get("$type") == node_type:
                    raw = value.get(field)
                    name = raw.get("Value") if isinstance(raw, dict) else raw
                    if name:
                        added.add(str(name))
                for child in value.values():
                    visit(child)
            elif isinstance(value, list):
                for child in value:
                    visit(child)

        visit(self.sources)
        return added

    def _character_symbols(self) -> Dict[int, Any]:
        out: Dict[int, Any] = {}
        for index, monster_id in enumerate((self.sources.get("summon_ids") or [])[:6]):
            if _is_number(monster_id):
                out[_SUMMON_ID_HASH_BASE + index] = monster_id
        floats = ((self.config.get("DynamicValues") or {}).get("Floats") or {})
        for raw_hash, item in floats.items():
            info = (item or {}).get("ReadInfo") or {}
            if info.get("Type") != "SkillParam":
                continue
            trigger = str(info.get("TriggerKey") or "")
            slot = info.get("Index")
            skill = self.skills.get(trigger) or {}
            params = skill.get("param_list") or []
            if isinstance(slot, int) and 0 <= slot < len(params):
                out[int(raw_hash)] = params[slot]
        # 跨变体 SkillParam 铺底（B48/#545）：共享 Ability 引用的哈希可能只在别的变体
        # Config 声明。全语料反查表给唯一 (TriggerKey, Index) 槽位映射（0 冲突），值仍取
        # 加载 Config 自身技能 param_list——技能缺失/槽越界不解析，不拉外变体技能行。
        # 自身 Floats 声明优先（已在 out 的哈希跳过）。
        from hsr_nous.pipeline.enemies.skillparam_hash_table import SKILLPARAM_HASH_TABLE
        for hashed, (trigger, slot) in SKILLPARAM_HASH_TABLE.items():
            if hashed in out:
                continue
            params = (self.skills.get(trigger) or {}).get("param_list") or []
            if isinstance(slot, int) and 0 <= slot < len(params):
                out[hashed] = params[slot]
        return out

    def _issue(self, ctx: _Context, path: str, node_type: str, reason: str) -> None:
        issue = {"path": path, "node_type": node_type, "reason": reason}
        if issue not in ctx.unsupported:
            ctx.unsupported.append(issue)

    @staticmethod
    def _add_effect(ctx: _Context, effect: Dict[str, Any]) -> None:
        if ctx.live_condition != "true":
            # 帧感知分支（写后读/概率）的 effect 级活读守卫：执行时求值，读得到帧
            # 覆盖层（#26 期 2/3）；与 hook 级快照条件（ctx.condition → _condition）
            # 正交互——两层都求值。
            effect = {**effect, "condition": AbilityCompiler._and_condition(
                str(effect.get("condition") or "true"), ctx.live_condition)}
        if ctx.condition != "true":
            effect = {**effect, "_condition": ctx.condition}
            target = effect.get("target")
            if "count_selected" in ctx.condition and isinstance(target, dict) and target.get("take") == 1:
                # 单目标计数门控改在效果执行期过滤，避免读到本事件前序效果前的旧快照。
                target = dict(target)
                target["where"] = AbilityCompiler._and_condition(
                    target.get("where", "true"), ctx.condition)
                effect = {**effect, "target": target, "_condition": "true"}
        if (ctx.mode == "action" and ctx.loop_depth
                and effect.get("effect_type") == "apply_modifier"):
            if effect not in ctx.hit_effects:
                ctx.hit_effects.append(effect)
            return
        if (ctx.mode == "action" and not ctx.seen_damage
                and effect.get("effect_type") != "set_hp_to_percent"):
            ctx.pre_effects.append(effect)
        else:
            ctx.effects.append(effect)

    @staticmethod
    def _add_live_effect(ctx: _Context, effect: Dict[str, Any], guard: str) -> None:
        """帧感知分支的效果入口：guard 链入 ctx.live_condition 后经 _add_effect 落
        **effect 级 condition**（执行时活读，读得到帧覆盖层）。"""
        previous = ctx.live_condition
        ctx.live_condition = AbilityCompiler._and_condition(previous, guard)
        AbilityCompiler._add_effect(ctx, effect)
        ctx.live_condition = previous

    @staticmethod
    def _stable_roll_key(path: str) -> str:
        """概率分支 roll 稳定键：节点路径 sanit 成表达式安全的标识（帧 rolls 表键）."""
        return "R" + "".join(ch if (ch.isalnum() or ch == "_") else "_"
                             for ch in str(path))[:96]

    @staticmethod
    def _make_hooks(ctx: _Context, base_condition: str, *,
                    event: Optional[str] = None,
                    effects: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
        groups: List[Tuple[str, List[Dict[str, Any]]]] = []
        selected = ctx.effects if effects is None else effects
        for effect in selected:
            condition = str(effect.get("_condition") or "true")
            clean = {key: value for key, value in effect.items() if key != "_condition"}
            if not groups or groups[-1][0] != condition:
                groups.append((condition, []))
            groups[-1][1].append(clean)
        if any("$last" in condition or "$prev" in condition for condition, _effects in groups):
            # 链内计数必须在同一 hook 内逐效果判定；拆钩会重置 $last/$prev。
            conditioned = []
            for condition, grouped in groups:
                for effect in grouped:
                    if condition != "true":
                        effect = dict(effect)
                        effect["condition"] = (f"({effect['condition']}) and ({condition})"
                                               if effect.get("condition") else condition)
                    conditioned.append(effect)
            return [{"event": event or ctx.event, "condition": base_condition,
                     "effects": conditioned}]
        hooks = []
        for condition, grouped in groups:
            hooks.append({
                "event": event or ctx.event,
                "condition": AbilityCompiler._and_condition(base_condition, condition),
                "effects": grouped,
            })
        return hooks

    def _value(self, raw: Any, ctx: _Context, path: str,
               symbols: Optional[Dict[int, Any]] = None) -> Any:
        selected = ({**self.dynamic_name_symbols, **self.custom_value_symbols,
                     **self.dynamic_symbols, **ctx.value_symbols, **ctx.count_expressions}
                    if symbols is None else {**self.dynamic_name_symbols,
                                             **self.custom_value_symbols, **symbols})
        if ctx.current_modifier:
            keys = self.modifier_dynamic_keys.get(ctx.current_modifier, set())
            definition = self.modifiers.get(ctx.current_modifier) or {}
            modifier_id = self._modifier_id(
                ctx.current_modifier, definition, str(ctx.skill.get("skill_id") or self.enemy_id))
            if keys and modifier_id == ctx.current_modifier:
                instance_symbols = {
                    dynamic_value_hash(key): (
                        f"modifier_dynamic_of($self.actor_id, '{modifier_id}', '{key}')")
                    for key in keys
                }
                selected = {**instance_symbols, **selected}
        try:
            return compile_dynamic_value(raw, selected)
        except ValueError as exc:
            self._issue(ctx, path, "DynamicValue", str(exc))
            return None

    def _number(self, raw: Any, ctx: _Context, path: str,
                symbols: Optional[Dict[int, Any]] = None) -> Optional[float]:
        value = self._value(raw, ctx, path, symbols)
        if value is None:
            return None
        if not _is_number(value):
            self._issue(ctx, path, "DynamicValue", f"需要静态数值，得到表达式 {value!r}")
            return None
        return value

    def _compile_tasks(self, tasks: Iterable[Dict[str, Any]], ctx: _Context,
                       path: str, stack: Tuple[str, ...]) -> None:
        rows = list(tasks or [])
        index = 0
        while index < len(rows):
            task = rows[index]
            node_path = f"{path}/{index}"
            node_type = str(task.get("$type") or "")
            if node_type == "RPG.GameCore.ByIsContainModifier":
                self._issue(ctx, node_path, node_type, "裸谓词仅允许出现在纯表现子树")
                index += 1
                continue
            if node_type == "RPG.GameCore.TaskConfig" and set(task) == {"$type"}:
                index += 1
                continue
            if (node_type == "OPBLGCPAKKI"
                    and set(task) == {"$type", "HPLBJMDGFGJ", "MPBNJEOANHL"}
                    and task.get("HPLBJMDGFGJ") == "Origin"
                    and task.get("MPBNJEOANHL") == "Root"):
                index += 1
                continue
            if node_type in IGNORED_TASK_TYPES:
                index += 1
                continue
            previous_task = rows[index - 1] if index > 0 else {}
            next_task = rows[index + 1] if index + 1 < len(rows) else {}
            if (node_type == "RPG.GameCore.DispelStatus"
                    and set(task) == {"$type", "TargetType", "BuffType"}
                    and task.get("BuffType") == "Other"
                    and set(previous_task) == {"$type", "TargetType"}
                    and previous_task.get("$type") == "RPG.GameCore.DispelStatus"
                    and previous_task.get("TargetType") == task.get("TargetType")):
                ctx.handled.append(node_type)
                index += 1
                continue
            if (node_type == "RPG.GameCore.AddModifier"
                    and (task.get("ModifierName") or {}).get("Value") == "MCommon_SkillTarget"
                    and self.modifiers.get("MCommon_SkillTarget") is None
                    and set(task) <= {"$type", "TargetType", "ModifierName"}
                    and self._alias(task) == self._alias(next_task) == "ParamEntity"
                    and next_task.get("$type") == "RPG.GameCore.TriggerModifierCustomEvent"
                    and (next_task.get("EventType") or {}).get("Value") == 1
                    and next_task.get("DynamicKey") == "DOT_TriggerRatio"):
                # 内建 DoT 事件的寻址标记；trigger_dot 直接寻址，不生成无定义 DSL 件。
                index += 1
                continue
            if node_type in {"RPG.GameCore.ExitBreakState", "RPG.GameCore.ResetStance"}:
                if (node_type == "RPG.GameCore.ExitBreakState"
                        and self._is_default_reset_stance(next_task)
                        and self._alias(next_task) == self._alias(task)):
                    ctx.handled.extend([node_type, "RPG.GameCore.ResetStance"])
                    self._compile_restore_toughness(task, ctx, node_path)
                    index += 2
                    continue
                if node_type == "RPG.GameCore.ResetStance" and task.get("ForbidWhenEmpty"):
                    self._issue(ctx, node_path, node_type,
                                "ResetStance 的 ForbidWhenEmpty=true 变体未收编")
                    index += 1
                    continue
            method_name = TASK_HANDLERS.get(node_type)
            if method_name is None:
                reason = self._UNREGISTERED_TASK_REASONS.get(node_type, "未注册任务节点")
                self._issue(ctx, node_path, node_type or "<missing $type>", reason)
                index += 1
                continue
            ctx.handled.append(node_type)
            getattr(self, method_name)(task, ctx, node_path, stack)
            index += 1

    @staticmethod
    def _is_default_reset_stance(task: Dict[str, Any]) -> bool:
        return (task.get("$type") == "RPG.GameCore.ResetStance"
                and "ConstantValue" not in task and "AddValue" not in task
                and not task.get("ForbidWhenEmpty"))

    def _compile_record_formation_index(self, task: Dict[str, Any], ctx: _Context,
                                        path: str, stack: Tuple[str, ...]) -> None:
        target = self._task_target(task, ctx, path)
        if target is None:
            self._issue(ctx, path, str(task.get("$type")), "记录站位的目标未注册")
            return
        self._add_effect(ctx, {"effect_type": "record_formation_index", "target": target})

    def _compile_clear_formation_record(self, task: Dict[str, Any], ctx: _Context,
                                        path: str, stack: Tuple[str, ...]) -> None:
        team = str(task.get("Team") or "")
        if team not in {"TeamDark", "TeamLight"}:
            self._issue(ctx, path, str(task.get("$type")), f"清除站位记录的阵营未注册：{team}")
            return
        self._add_effect(ctx, {
            "effect_type": "set_dynamic_value", "target": "$level",
            "dynamic_key": f"_FormationRecord:{team.removeprefix('Team').lower()}",
            "amount": 0,
        })

    def _compile_restore_toughness(self, task: Dict[str, Any], ctx: _Context, path: str) -> None:
        target = self._hook_target(self._alias(task), ctx)
        if target is None:
            self._issue(ctx, path, str(task.get("$type")), "韧性恢复目标未注册")
            return
        self._add_effect(ctx, {"effect_type": "restore_toughness", "target": target})

    def _compile_exit_break(self, task: Dict[str, Any], ctx: _Context,
                            path: str, stack: Tuple[str, ...]) -> None:
        target = self._hook_target(self._alias(task), ctx)
        if target is None:
            self._issue(ctx, path, str(task.get("$type")), "击破退出目标未注册")
            return
        self._add_effect(ctx, {"effect_type": "exit_break_state", "target": target})

    def _compile_reset_stance(self, task: Dict[str, Any], ctx: _Context,
                              path: str, stack: Tuple[str, ...]) -> None:
        target = self._hook_target(self._alias(task), ctx)
        if target is None:
            self._issue(ctx, path, str(task.get("$type")), "韧性重置目标未注册")
            return
        has_constant = "ConstantValue" in task
        has_add = "AddValue" in task
        if has_constant and has_add:
            self._issue(ctx, path, str(task.get("$type")), "ResetStance 同时带 ConstantValue 与 AddValue")
            return
        effect = {"effect_type": "reset_stance", "target": target}
        if has_constant or has_add:
            field = "AddValue" if has_add else "ConstantValue"
            amount = self._value(task.get(field), ctx, f"{path}/{field}")
            if amount is None:
                self._issue(ctx, path, str(task.get("$type")), "ResetStance 数值未注册")
                return
            effect.update({"mode": "add" if has_add else "set", "amount": amount})
        self._add_effect(ctx, effect)

    def _compile_ability(self, name: str, ctx: _Context, path: str,
                         stack: Tuple[str, ...],
                         dynamic_values: Optional[Dict[str, Any]] = None) -> None:
        if _is_camera_ability(name):
            return
        ability = self.abilities.get(name)
        if ability is None:
            self._issue(ctx, path, "AbilityReference", f"Ability 定义缺失：{name}")
            return
        if name in stack:
            self._issue(ctx, path, "AbilityReference", f"Ability 循环引用：{' → '.join(stack + (name,))}")
            return
        previous_ability = ctx.current_ability
        previous_symbols = ctx.value_symbols
        ctx.current_ability = name
        ctx.value_symbols = dict(previous_symbols)
        bound_values = dict(self.stage_ability_params.get(name, {}))
        bound_values.update(dynamic_values or {})
        try:
            for key, raw in bound_values.items():
                value = self._value(raw, ctx, f"{path}/DynamicValues/{key}")
                if value is None:
                    return
                ctx.value_symbols[dynamic_value_hash(str(key))] = value
            self._compile_tasks(ability.get("OnStart") or [], ctx, f"{path}:{name}/OnStart",
                                stack + (name,))
        finally:
            ctx.value_symbols = previous_symbols
            ctx.current_ability = previous_ability

    def _compile_trigger_modifier_custom_event(self, task: Dict[str, Any], ctx: _Context,
                                               path: str, stack: Tuple[str, ...]) -> None:
        event_value = (task.get("EventType") or {}).get("Value")
        if event_value in {1, 3, 4} and task.get("DynamicKey") == "DOT_TriggerRatio":
            target = self._hook_target(self._alias(task), ctx)
            ratio = self._value(task.get("Value"), ctx, f"{path}/Value")
            if target is None or ratio is None:
                self._issue(ctx, path, str(task.get("$type")), "DoT 引爆目标或比例未注册")
                return
            effect = {"effect_type": "trigger_dot", "target": target, "ratio": ratio}
            if event_value in {3, 4}:
                effect["dot_element"] = "thunder" if event_value == 3 else "wind"
            self._add_effect(ctx, effect)
            return
        if event_value in {8, 13}:
            if (task.get("DynamicKey") is not None
                    or self._alias(task) != "BattleAllEntity.GetAliveOrLimbo"):
                self._issue(ctx, path, str(task.get("$type")), "阶段自定义事件的目标或动态键未注册")
                return
            effect = {
                "effect_type": "emit_phase_custom_event",
                "phase_event": ("monster_phase_change_begin" if event_value == 13
                                else "monster_phase_change_end"),
                "include_limbo": bool(task.get("IncludeLimbo", False)),
            }
            if "OverrideParamEntity" in task:
                target = self._hook_target(
                    self._alias({"TargetType": task["OverrideParamEntity"]}), ctx)
                if target is None:
                    self._issue(ctx, path, str(task.get("$type")), "阶段事件 ParamEntity 目标未注册")
                    return
                effect["param_entity"] = target
            self._add_effect(ctx, effect)
            return
        if (isinstance(event_value, bool) or not isinstance(event_value, int)
                or set(task) - {"$type", "TargetType", "EventType", "DynamicKey", "Value"}
                or ("DynamicKey" in task and not isinstance(task["DynamicKey"], str))):
            self._issue(ctx, path, str(task.get("$type")), "通用自定义事件需整数 EventType 与已注册字段")
            return
        target = self._task_target(task, ctx, path)
        value = self._value(task.get("Value"), ctx, f"{path}/Value") if "Value" in task else 0
        if target is None or value is None:
            self._issue(ctx, path, str(task.get("$type")), "自定义事件目标或数值未注册")
            return
        effect = {"effect_type": "emit_modifier_custom_event", "target": target,
                  "event_type": event_value, "value": value}
        if "DynamicKey" in task:
            effect["dynamic_key"] = task["DynamicKey"]
        self._add_effect(ctx, effect)

    def _compile_add_stage_ability(self, task: Dict[str, Any], ctx: _Context,
                                   path: str, stack: Tuple[str, ...]) -> None:
        raw = task.get("StageAbilityName")
        name = raw.get("Value") if isinstance(raw, dict) else raw
        if not name:
            self._issue(ctx, path, str(task.get("$type")), "AddStageAbilityByName 缺名称")
            return
        if _is_camera_ability(str(name)):
            return
        if task.get("CanReplace") is True:
            self._issue(ctx, path, str(task.get("$type")), "关卡 Ability 的替换语义未收编")
            return
        params = {}
        for key, raw in (task.get("DynamicValues") or {}).items():
            value = self._value(raw, ctx, f"{path}/DynamicValues/{key}")
            if not _is_number(value):
                self._issue(ctx, path, str(task.get("$type")),
                            f"关卡 Ability 仅支持静态持久参数：{key}")
                return
            params[str(key)] = value
        ability = self.abilities.get(str(name))
        if ability is None:
            self._issue(ctx, path, "AbilityReference", f"Ability 定义缺失：{name}")
            return
        modifiers = (ability.get("Modifiers") or {}).values()
        if (self._presentation_only(ability.get("OnStart") or [])
                and all(self._visual_modifier(modifier) for modifier in modifiers)):
            return
        self.stage_ability_params[str(name)] = params
        if str(name) in self.gated_stage_abilities:
            key = f"_stage_ability_enabled:{name}"
            ctx.dynamic_writes.add(key)
            self._add_effect(ctx, {
                "effect_type": "set_dynamic_value", "target": "$level",
                "dynamic_key": key, "amount": 1,
            })

    def _compile_owner_add_ability(self, task: Dict[str, Any], ctx: _Context,
                                   path: str, stack: Tuple[str, ...]) -> None:
        raw = task.get("AbilityName")
        name = raw.get("Value") if isinstance(raw, dict) else raw
        if not name:
            self._issue(ctx, path, str(task.get("$type")), "OwnerEntityAddAbility 缺 AbilityName")
            return
        if _is_camera_ability(str(name)):
            return
        ability = self.abilities.get(str(name))
        if ability is None:
            self._issue(ctx, path, "AbilityReference", f"Ability 定义缺失：{name}")
            return
        modifiers = (ability.get("Modifiers") or {}).values()
        if (self._presentation_only(ability.get("OnStart") or [])
                and all(self._visual_modifier(modifier) for modifier in modifiers)):
            ctx.handled.append(str(task.get("$type")))
            return
        if str(name) in self.gated_abilities:
            key = f"_ability_enabled:{name}"
            ctx.dynamic_writes.add(key)
            self._add_effect(ctx, {
                "effect_type": "set_dynamic_value", "target": "self",
                "dynamic_key": key, "amount": 1,
            })

    def _compile_parallel_ability(self, task: Dict[str, Any], ctx: _Context,
                                  path: str, stack: Tuple[str, ...]) -> None:
        entries = task.get("ParallelAbilityList") or []
        if not entries:
            self._issue(ctx, path, str(task.get("$type")), "ParallelAbilityList 为空")
            return
        for index, entry in enumerate(entries):
            delay = self._number(entry.get("Delay", 0), ctx, f"{path}/{index}/Delay")
            raw_name = entry.get("AbilityName") or {}
            name = raw_name.get("Value") if isinstance(raw_name, dict) else raw_name
            if not name or delay is None:
                self._issue(ctx, f"{path}/{index}", str(task.get("$type")), "并行能力名或延迟未注册")
                continue
            if delay != 0:
                self._issue(ctx, f"{path}/{index}", str(task.get("$type")),
                            "非零并行 Delay 尚未接入时序")
                continue
            if _is_camera_ability(str(name)):
                continue
            ability = self.abilities.get(str(name))
            if ability is None:
                self._issue(ctx, f"{path}/{index}", "AbilityReference", f"Ability 定义缺失：{name}")
                continue
            tasks = ability.get("OnStart") or []
            if len(entries) != 1 and any(
                    str(row.get("$type")) != "RPG.GameCore.DamageByAttackProperty"
                    and str(row.get("$type")) not in IGNORED_TASK_TYPES for row in tasks):
                self._issue(ctx, f"{path}/{index}", str(task.get("$type")),
                            "仅支持无状态副作用的直接伤害并行子技能")
                continue
            target = None
            inherent = entry.get("AbilityInherentTargetType")
            if inherent is not None:
                target = self._target_spec(inherent, ctx, f"{path}/{index}/InherentTarget")
            elif entry.get("TargetType") is not None:
                target = self._target_spec(entry["TargetType"], ctx, f"{path}/{index}/Target")
            if target is None:
                default_target = str((ability.get("TargetInfo") or {}).get("TargetType") or "")
                if default_target == "Caster":
                    target = "self"
                elif default_target == "AbilityTargetEntity":
                    target = ctx.retarget or {"pool": "$event.target"}
            if target is None:
                self._issue(ctx, f"{path}/{index}", str(task.get("$type")), "并行子技能目标未注册")
                continue
            child_ctx = replace(ctx, retarget=target, current_ability=str(name))
            child_ctx.value_symbols = dict(child_ctx.value_symbols)
            for key, value in self.stage_ability_params.get(str(name), {}).items():
                child_ctx.value_symbols[dynamic_value_hash(key)] = value
            if str(name) in self.gated_abilities:
                key = self._string_literal(f"_ability_enabled:{name}")
                child_ctx.condition = self._and_condition(
                    child_ctx.condition, f"dynamic_of($self.actor_id, {key}) > 0")
            if str(name) in self.gated_stage_abilities:
                key = self._string_literal(f"_stage_ability_enabled:{name}")
                child_ctx.condition = self._and_condition(
                    child_ctx.condition, f"dynamic_of($level, {key}) > 0")
            child_tasks = []
            for row in tasks:
                if self._alias(row) == "AbilityTargetEntity":
                    row = {**row, "TargetType": {
                        "$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"}}
                child_tasks.append(row)
            self._compile_tasks(child_tasks, child_ctx, f"{path}/{index}:{name}/OnStart",
                                stack + (str(name),))

    def _compile_auto_ultra(self, task: Dict[str, Any], ctx: _Context,
                            path: str, stack: Tuple[str, ...]) -> None:
        names = task.get("BindUltraSkillNames") or []
        enabled = task.get("Enable", True)
        if (len(names) != 1 or not isinstance(names[0], str) or not names[0]
                or task.get("WaitCutinFinished") is not False
                or not isinstance(enabled, bool)):
            self._issue(ctx, path, str(task.get("$type")),
                        "仅支持单绑定技能、无切镜等待的终结技启停")
            return
        target = self._hook_target(self._alias({"TargetType": task.get("Target")}), ctx)
        if target is None:
            self._issue(ctx, path, str(task.get("$type")), "自动终结技启停目标未注册")
            return
        skill_id = str(ctx.skill.get("skill_id") or self.enemy_id)
        modifier_id = f"ENEMY_{skill_id}_AUTO_ULTRA_LOCK"
        if enabled:
            self._add_effect(ctx, {
                "effect_type": "remove_modifier", "target": target, "modifier_id": modifier_id,
            })
            return
        self._add_effect(ctx, {
            "effect_type": "apply_modifier", "target": target,
            "modifier": {
                "modifier_id": modifier_id, "name": "AutoUltimateLock", "modifier_type": "debuff",
                "duration": 0, "max_stack": 1, "stack_mode": "replace", "dispellable": False,
                "locked_action_types": ["ultimate"],
            },
        })

    def _compile_trigger_ability(self, task: Dict[str, Any], ctx: _Context,
                                 path: str, stack: Tuple[str, ...]) -> None:
        raw = task.get("AbilityName")
        name = (raw or {}).get("Value") if isinstance(raw, dict) else raw
        if not name:
            self._issue(ctx, path, str(task.get("$type")), "缺 AbilityName")
            return
        flags = set(task.get("AbortBehaviorFlags") or [])
        conditions = []
        if str(name) in self.gated_abilities:
            key = self._string_literal(f"_ability_enabled:{name}")
            conditions.append(f"dynamic_of($self.actor_id, {key}) > 0")
        if str(name) in self.gated_stage_abilities:
            key = self._string_literal(f"_stage_ability_enabled:{name}")
            conditions.append(f"dynamic_of($level, {key}) > 0")
        for flag in sorted(flags):
            if flag in {"STAT_CTRL", "STAT_Confine"}:
                conditions.append("not controlled($self.actor_id)")
            elif flag == "Break":
                conditions.append("not broken_of($self.actor_id)")
            elif flag == "DisableAction":
                conditions.append("not action_disabled($self.actor_id)")
            elif flag == "STAT_MonsterChangePhase":
                conditions.append(
                    "not has_behavior_flag($self.actor_id, 'STAT_MonsterChangePhase')")
            else:
                self._issue(ctx, path, "AbortBehaviorFlags", f"未注册中止旗标：{flag}")
                return
        previous = ctx.condition
        if conditions:
            ctx.condition = self._and_condition(previous, " and ".join(conditions))
        self._compile_ability(str(name), ctx, path, stack,
                              dynamic_values=task.get("DynamicValues"))
        ctx.condition = previous

    def _compile_animation_events(self, task: Dict[str, Any], ctx: _Context,
                                  path: str, stack: Tuple[str, ...]) -> None:
        for index, event in enumerate(task.get("EventList") or []):
            self._compile_tasks(event.get("TaskList") or [], ctx,
                                f"{path}/EventList/{index}/TaskList", stack)

    @staticmethod
    def _single_target_spec(spec: Dict[str, Any]) -> bool:
        pool = str(spec.get("pool") or "")
        return (spec.get("take") == 1 or pool in {"self", "$event.target", "$event.actor"}
                or pool.startswith("unique:"))

    def _compile_projectile(self, task: Dict[str, Any], ctx: _Context,
                            path: str, stack: Tuple[str, ...]) -> None:
        hits = task.get("OnProjectileHit") or []
        if not hits:
            return  # 无命中任务的投射物仅承担表现。
        if ctx.retarget is not None and not self._single_target_spec(ctx.retarget):
            self._issue(ctx, path, str(task.get("$type")), "Retarget 内投射物主目标未证明")
            return
        alias = self._alias(task)
        allowed_aliases = {"", "AbilityTargetEntity", "Caster", "ModifierOwnerEntity"}
        if ctx.retarget is not None:
            allowed_aliases.add("ParamEntity")
        if alias not in allowed_aliases:
            self._issue(ctx, path, str(task.get("$type")), "投射物目标不是 Action 主目标")
            return
        child_ctx = replace(ctx, retarget={"pool": "self"}) \
            if alias in {"Caster", "ModifierOwnerEntity"} else ctx
        coalesced_left: set[int] = set()
        coalesced_right: set[int] = set()
        if ctx.mode == "action" and ctx.retarget is None:
            for index in range(1, len(hits) - 1):
                trio = hits[index - 1:index + 2]
                if [self._alias(item) for item in trio] != [
                        "AbilityTargetEntity", "AbilityTargetLeftEntity",
                        "AbilityTargetRightEntity"]:
                    continue
                records = []
                for item in trio[1:]:
                    dry = replace(child_ctx, damages=[], effects=[], pre_effects=[],
                                  hit_effects=[], unsupported=[])
                    self._compile_damage(item, dry, f"{path}/OnProjectileHit/{index}/Pair", stack)
                    if dry.unsupported or len(dry.damages) != 1:
                        records = []
                        break
                    records.append({**dry.damages[0], "alias": "AbilityTargetAdjoinEntity"})
                if records and records[0] == records[1]:
                    coalesced_left.add(index)
                    coalesced_right.add(index + 1)
        for index, item in enumerate(hits):
            if index in coalesced_right:
                continue
            node_type = str(item.get("$type") or "")
            if node_type in IGNORED_TASK_TYPES:
                continue
            if node_type == "RPG.GameCore.DamageByAttackProperty":
                hit_alias = self._alias(item)
                if hit_alias not in {"ProjectileHitEntity", "AbilityTargetEntity",
                                     "AbilityTargetAdjoinEntity"} and index not in coalesced_left:
                    self._issue(ctx, f"{path}/OnProjectileHit/{index}", node_type,
                                "仅支持主目标/相邻目标直接命中伤害，其他命中任务尚未注册")
                    continue
                direct = dict(item)
                if hit_alias in {"ProjectileHitEntity", "AbilityTargetEntity"} \
                        or index in coalesced_left:
                    direct["TargetType"] = {
                        "$type": "RPG.GameCore.TargetAlias",
                        "Alias": ("AbilityTargetAdjoinEntity" if index in coalesced_left
                                  else "AbilityTargetEntity")}
                self._compile_damage(direct, child_ctx, f"{path}/OnProjectileHit/{index}", stack)
            else:
                self._compile_tasks([item], child_ctx, f"{path}/OnProjectileHit/{index}", stack)

    def _compile_wave_projectile(self, task: Dict[str, Any], ctx: _Context,
                                 path: str, stack: Tuple[str, ...]) -> None:
        if ctx.retarget is not None:
            self._issue(ctx, path, str(task.get("$type")), "Retarget 内 Wave 投射物主目标未证明")
            return
        if self._alias(task) not in {"", "EnemyTeamEntity", "AllEnemy", "AbilityTargetEntity"}:
            self._issue(ctx, path, str(task.get("$type")), "Wave 投射物目标未注册")
            return
        count = self._number(task.get("Count"), ctx, f"{path}/Count")
        if count is None or count < 1 or int(count) != count:
            self._issue(ctx, path, str(task.get("$type")), "Wave 投射物次数必须是正整数")
            return
        damage = task.get("PerProjectileDamage")
        if not isinstance(damage, dict):
            if damage is not None:
                self._issue(ctx, path, str(task.get("$type")), "Wave 投射物伤害节点未注册")
            return
        if not self._presentation_only(task.get("OnProjectileHitClientOnly") or []):
            self._issue(ctx, path, str(task.get("$type")), "Wave 投射物命中后任务未注册")
            return
        for index in range(int(count)):
            self._compile_damage(damage, ctx, f"{path}/PerProjectileDamage/{index}", stack)

    def _compile_parallel_templates(self, task: Dict[str, Any], ctx: _Context,
                                    path: str, stack: Tuple[str, ...]) -> None:
        for index, entry in enumerate(task.get("Templates") or []):
            base = self._number(entry.get("BaseDelay", 0), ctx, f"{path}/Templates/{index}/BaseDelay")
            interval = self._number(entry.get("DelayInterval", 0), ctx,
                                    f"{path}/Templates/{index}/DelayInterval")
            name = str(entry.get("Name") or "")
            if base != 0 or interval != 0 or not name:
                self._issue(ctx, path, str(task.get("$type")),
                            f"并行模板非零延迟或名称未注册：{name} / {base} / {interval}")
                continue
            self._compile_include_tasks({"$type": "RPG.GameCore.IncludeTaskListTemplate", "Name": name},
                                        ctx, f"{path}/Templates/{index}", stack)

    def _compile_include_tasks(self, task: Dict[str, Any], ctx: _Context,
                               path: str, stack: Tuple[str, ...]) -> None:
        if set(task) - {"$type", "Name", "DynamicValues", "ParamTarget"}:
            self._issue(ctx, path, str(task.get("$type")), "TaskListTemplate 含未注册字段")
            return
        template_name = str(task.get("Name") or "")
        owner = next((name for name in reversed(stack) if name in self.abilities), "")
        container = (self.abilities.get(owner) if owner
                     else self.modifiers.get(ctx.current_modifier) or {})
        if not container and not owner and ctx.current_modifier:
            container = (((self.abilities.get(ctx.current_ability) or {}).get("Modifiers") or {})
                         .get(ctx.current_modifier) or {})
        rows = container.get("TaskListTemplate") or []
        template = next((row for row in rows if row.get("Name") == template_name), None)
        if template is None:
            template = self.global_templates.get(template_name)
        if template is None:
            self._issue(ctx, path, str(task.get("$type")),
                        f"局部/GlobalTemplates 模板缺失或属未收编全局作用域：{template_name}")
            return
        scope = owner or ctx.current_modifier or "<unknown>"
        key = f"{scope}/TaskListTemplate/{template_name}"
        if key in stack:
            self._issue(ctx, path, str(task.get("$type")), f"TaskListTemplate 循环引用：{key}")
            return
        previous_retarget = ctx.retarget
        if "ParamTarget" in task:
            target_spec = self._target_spec(task.get("ParamTarget"), ctx, f"{path}/ParamTarget")
            if target_spec is None:
                return
            ctx.retarget = target_spec
        previous_symbols = ctx.value_symbols
        symbols = dict(previous_symbols)
        ctx.value_symbols = symbols
        try:
            for name, raw in (task.get("DynamicValues") or {}).items():
                value = self._value(raw, ctx, f"{path}/DynamicValues/{name}")
                if value is None:
                    return
                symbols[dynamic_value_hash(str(name))] = value
            self._compile_tasks(template.get("TaskList") or [], ctx, f"{path}:{key}", stack + (key,))
        finally:
            ctx.value_symbols = previous_symbols
            ctx.retarget = previous_retarget

    def _compile_sequence_config(self, task: Dict[str, Any], ctx: _Context,
                                 path: str, stack: Tuple[str, ...]) -> None:
        self._compile_tasks(task.get("TaskList") or [], ctx, path, stack)

    def _compile_loop(self, task: Dict[str, Any], ctx: _Context,
                      path: str, stack: Tuple[str, ...]) -> None:
        count = self._value(task.get("MaxLoopCount"), ctx, f"{path}/MaxLoopCount")
        if _is_number(count):
            if count < 1 or int(count) != count:
                self._issue(ctx, path, str(task.get("$type")), "循环次数必须是确定的正整数")
                return
            for index in range(int(count)):
                ctx.loop_depth += 1
                self._compile_tasks(task.get("TaskList") or [], ctx,
                                    f"{path}/Loop/{index}/TaskList", stack)
                ctx.loop_depth -= 1
            return
        if count is None:
            return
        nested = self._compile_runtime_loop_body(
            task.get("TaskList") or [], ctx, path, stack, "动态次数循环",
            str(task.get("$type")))
        if nested is None:
            return
        self._add_effect(ctx, {
            "effect_type": "loop_effects", "count": count, "effects": nested,
        })

    def _compile_runtime_loop_body(self, tasks: List[Dict[str, Any]], ctx: _Context,
                                   path: str, stack: Tuple[str, ...],
                                   reason_label: str, node_type: str) -> Optional[List[Dict[str, Any]]]:
        """动态/条件循环共用体编译：allowed 闸 + in_dynamic_loop 子语境 + 分支条件合一.

        返回嵌套 effects（可能为空列表）；含未收编机制任务记拒因并返回 None。
        """
        allowed = {"RPG.GameCore.SetDynamicValue", "RPG.GameCore.DefineDynamicValue",
                   "RPG.GameCore.AddModifier", "RPG.GameCore.RemoveModifier",
                   "RPG.GameCore.LoseHPByRatio", "RPG.GameCore.ForceKill",
                   "RPG.GameCore.SwitchCaseByDynamicValue", "RPG.GameCore.RandomConfig",
                   "RPG.GameCore.AddEntityToTeamFormation",
                   "RPG.GameCore.DamageByAttackProperty", "RPG.GameCore.IncludeTaskListTemplate",
                   "RPG.GameCore.SetDynamicValueByAddValue", "RPG.GameCore.SetDynamicValueByCopying",
                   "RPG.GameCore.SetDynamicValueByChangeValue", "RPG.GameCore.SetDynamicValueByProperty"}
        def allowed_loop_task(row: Dict[str, Any]) -> bool:
            if str(row.get("$type")) in allowed or self._presentation_only([row]):
                return True
            if row.get("$type") in {"RPG.GameCore.Retarget", "RPG.GameCore.RetargetList"}:
                return all(allowed_loop_task(child_row)
                           for field in ("TaskList", "FailedTaskList")
                           for child_row in row.get(field) or [])
            if row.get("$type") != "RPG.GameCore.PredicateTaskList":
                return False
            fields = ("SuccessTaskList", "FailedTaskList")
            return all(allowed_loop_task(child_row)
                       for field in fields for child_row in row.get(field) or [])

        if not tasks or any(not allowed_loop_task(row) for row in tasks):
            self._issue(ctx, path, node_type, f"{reason_label}含未收编机制任务")
            return None
        child = replace(ctx, damages=[], effects=[], pre_effects=[], hit_effects=[],
                        lifecycle_hooks=[], summons=[], retarget_damage=False,
                        retarget_damage_records=[], condition="true", live_condition="true",
                        in_dynamic_loop=True)
        self._compile_tasks(tasks, child, f"{path}/RuntimeLoop/TaskList", stack)
        if child.damages or child.summons or child.hit_effects:
            self._issue(ctx, path, node_type, f"{reason_label}含未收编机制任务")
            return None
        ctx.lifecycle_hooks.extend(child.lifecycle_hooks)
        nested = []
        for effect in [*child.pre_effects, *child.effects]:
            branch_condition = str(effect.get("_condition") or "true")
            clean = {key: value for key, value in effect.items() if key != "_condition"}
            if branch_condition != "true":
                clean["condition"] = self._and_condition(
                    branch_condition, str(clean.get("condition") or "true"))
            nested.append(clean)
        return nested

    def _compile_condition_loop(self, task: Dict[str, Any], ctx: _Context,
                                path: str, stack: Tuple[str, ...]) -> None:
        """ConditionLoopExecuteTaskList（Predicate+TaskList，无次数）→ 条件驱动 loop_effects.

        谓词编为条件表达式逐轮重求值；体复用动态循环同一 allowed 闸（#544）。
        WithInterval 间隔变体不在本通道，仍走未注册拒因。
        """
        condition = self._predicate_expr(task.get("Predicate") or {}, ctx,
                                         f"{path}/Predicate", allow_written=True)
        if condition is None:
            return
        nested = self._compile_runtime_loop_body(
            task.get("TaskList") or [], ctx, path, stack, "条件循环",
            str(task.get("$type")))
        if nested is None:
            return
        self._add_effect(ctx, {
            "effect_type": "loop_effects", "condition": condition, "effects": nested,
        })

    def _compile_obfuscated_control_mapping(self, task: Dict[str, Any], ctx: _Context,
                                            path: str, stack: Tuple[str, ...]) -> None:
        if set(task) != {"$type", "GFNJJEFJKPD", "IPOJMHGKIEH"} or any(
                not isinstance(task.get(key), str) or not task[key]
                for key in ("GFNJJEFJKPD", "IPOJMHGKIEH")):
            self._issue(ctx, path, str(task.get("$type")),
                        "混淆控制按钮映射仅接受控制字段与技能名两个非空字符串")

    def _compile_obfuscated_hp_bar_visibility(self, task: Dict[str, Any], ctx: _Context,
                                              path: str, stack: Tuple[str, ...]) -> None:
        if (set(task) - {"$type", "HILNFHCPEAD", "GNDCCBNILML"}
                or not isinstance(task.get("HILNFHCPEAD"), dict)
                or ("GNDCCBNILML" in task and not isinstance(task["GNDCCBNILML"], bool))):
            self._issue(ctx, path, str(task.get("$type")),
                        "部件血条显隐仅接受目标对象与可选布尔值")

    def _compile_obfuscated_empty_disable(self, task: Dict[str, Any], ctx: _Context,
                                          path: str, stack: Tuple[str, ...]) -> None:
        if (set(task) != {"$type", "HILNFHCPEAD", "ACJEBIJEHOK"}
                or not isinstance(task.get("HILNFHCPEAD"), dict)
                or task.get("ACJEBIJEHOK") != []):
            self._issue(ctx, path, str(task.get("$type")),
                        "混淆禁用节点仅接受目标对象与显式空列表")

    _AUTO_BP_PREFERENCES = frozenset({
        "BPSkillPriority", "AdvancedBPReserve", "BPHealingSkill", "IgnoreBPFail"})

    def _compile_obfuscated_auto_bp_preferences(self, task: Dict[str, Any], ctx: _Context,
                                                path: str, stack: Tuple[str, ...]) -> None:
        node_type = str(task.get("$type"))
        valid = isinstance(task.get("OELMOCMDEJI"), str) and bool(task["OELMOCMDEJI"])
        if node_type == "AIGHNCCAJPL":
            config = task.get("CHLBKIKJFLC")
            valid = (valid and set(task) == {"$type", "OELMOCMDEJI", "CHLBKIKJFLC"}
                     and isinstance(config, dict) and set(config) == self._AUTO_BP_PREFERENCES
                     and all(_is_number(_fixed(value)) for value in config.values()))
        else:
            names = task.get("DPBLGLBPFGK")
            valid = (valid and set(task) == {"$type", "OELMOCMDEJI", "DPBLGLBPFGK"}
                     and isinstance(names, list) and bool(names)
                     and set(names) <= self._AUTO_BP_PREFERENCES)
        if not valid:
            self._issue(ctx, path, node_type, "自动战斗 BP 偏好字段或静态数值未注册")

    def _compile_obfuscated_punchline(self, task: Dict[str, Any], ctx: _Context,
                                      path: str, stack: Tuple[str, ...]) -> None:
        effect_type = {"EGFCFCBHJJP": "gain_resource",
                       "DADCFBHGLOH": "set_resource"}.get(str(task.get("FKCKKFALPBK")))
        if (set(task) != {"$type", "AJHHCOHFIFA", "FKCKKFALPBK"}
                or effect_type is None):
            self._issue(ctx, path, str(task.get("$type")),
                        "笑点节点仅接受数值与已注册的 Add/Set 操作")
            return
        amount = self._value(task.get("AJHHCOHFIFA"), ctx, f"{path}/AJHHCOHFIFA")
        if amount is None:
            return
        self._add_effect(ctx, {
            "effect_type": effect_type, "resource_id": "punchline", "amount": amount,
        })

    def _compile_apply_operation(self, task: Dict[str, Any], ctx: _Context,
                                 path: str, stack: Tuple[str, ...]) -> None:
        if set(task) != {"$type"}:
            self._issue(ctx, path, str(task.get("$type")),
                        "ApplyOperation 非空操作对象/效果未注册")

    def _compile_obfuscated_empty_placeholder(self, task: Dict[str, Any], ctx: _Context,
                                              path: str, stack: Tuple[str, ...]) -> None:
        # 全语料键集严格只有 $type 的混淆空占位（#546，与 #535 ApplyOperation 同形）。
        if set(task) != {"$type"}:
            self._issue(ctx, path, str(task.get("$type")),
                        "混淆空占位仅接受无字段形态；出现参数仍需注册语义")

    def _compile_show_target_hp_bar(self, task: Dict[str, Any], ctx: _Context,
                                    path: str, stack: Tuple[str, ...]) -> None:
        if set(task) != {"$type", "TargetType"} or not isinstance(task.get("TargetType"), dict):
            self._issue(ctx, path, str(task.get("$type")),
                        "ShowTargetHPBar 仅接受目标对象的纯呈现形态")

    def _compile_wait_for(self, task: Dict[str, Any], ctx: _Context,
                          path: str, stack: Tuple[str, ...]) -> None:
        predicate = str((task.get("Predicate") or {}).get("$type") or "")
        if predicate not in {"RPG.GameCore.ByDieAnimFinished", "RPG.GameCore.ByHaveInsertUltraWait"}:
            self._issue(ctx, path, str(task.get("$type")), f"等待谓词未注册：{predicate}")

    def _presentation_only(self, tasks: Iterable[Dict[str, Any]]) -> bool:
        """条件分支是否纯表现；只有整棵子树都可证明无机制效果时才可忽略."""
        for task in tasks or []:
            node_type = str(task.get("$type") or "")
            if node_type in IGNORED_TASK_TYPES:
                continue
            if node_type == "RPG.GameCore.TriggerAbility":
                raw = task.get("AbilityName")
                name = (raw or {}).get("Value") if isinstance(raw, dict) else raw
                if _is_camera_ability(name):
                    continue
                return False
            if node_type == "RPG.GameCore.TriggerAnimStateWithMove":
                if all(self._presentation_only(event.get("TaskList") or [])
                       for event in task.get("EventList") or []):
                    continue
                return False
            if node_type == "RPG.GameCore.AddBuffPerform":
                if self._presentation_only(task.get("TaskList") or []):
                    continue
                return False
            if node_type == "RPG.GameCore.BattlePlayVideo":
                if all(self._presentation_only(task.get(field) or [])
                       for field in ("OnBeginPlay", "OnEndPlay", "OnFinish")):
                    continue
                return False
            if node_type == "RPG.GameCore.SetBossHPStanceChangeType":
                if task.get("ChangeType") == "Heal" and "ChangeTime" in task:
                    continue
                return False
            if node_type == "RPG.GameCore.PredicateTaskList":
                if (self._presentation_only(task.get("SuccessTaskList") or [])
                        and self._presentation_only(task.get("FailedTaskList") or [])):
                    continue
                return False
            if node_type in {"RPG.GameCore.Retarget", "RPG.GameCore.RetargetList",
                             "RPG.GameCore.Remodifier"}:
                if (self._presentation_only(task.get("TaskList") or [])
                        and self._presentation_only(task.get("FailedTaskList") or [])):
                    continue
                return False
            if node_type == "RPG.GameCore.RandomConfig":
                if all(self._presentation_only(
                        option if isinstance(option, list) else [option])
                        for option in task.get("TaskList") or []):
                    continue
                return False
            if node_type == "RPG.GameCore.SwitchCaseByAttackDamageType":
                branches = [row.get("TaskList") or [] for row in task.get("CaseTaskList") or []]
                branches.append(task.get("DefaultTaskList") or [])
                if all(self._presentation_only(branch) for branch in branches):
                    continue
                return False
            return False
        return True

    def _visual_tasks(self, tasks: Iterable[Dict[str, Any]]) -> bool:
        for task in tasks or []:
            node_type = str(task.get("$type") or "")
            if node_type in IGNORED_TASK_TYPES or node_type in {
                    "RPG.GameCore.RemoveModifier", "RPG.GameCore.RemoveSelfModifier"}:
                continue
            if node_type == "RPG.GameCore.AddModifier":
                raw = task.get("ModifierName")
                name = (raw or {}).get("Value") if isinstance(raw, dict) else raw
                if str(name) == "Monster_APShow" and self.modifiers.get(str(name)) is None:
                    continue
            if node_type == "RPG.GameCore.TriggerAbility":
                raw = task.get("AbilityName")
                name = (raw or {}).get("Value") if isinstance(raw, dict) else raw
                if _is_camera_ability(name):
                    continue
                return False
            if node_type == "RPG.GameCore.TriggerAnimStateWithMove":
                if all(self._visual_tasks(event.get("TaskList") or [])
                       for event in task.get("EventList") or []):
                    continue
                return False
            if node_type == "RPG.GameCore.PredicateTaskList":
                if (self._visual_tasks(task.get("SuccessTaskList") or [])
                        and self._visual_tasks(task.get("FailedTaskList") or [])):
                    continue
                return False
            return False
        return True

    def _visual_modifier(self, definition: Dict[str, Any]) -> bool:
        return all(self._visual_tasks(callback.get("CallbackConfig") or [])
                   or self._presentation_only(callback.get("CallbackConfig") or [])
                   for callback in definition.get("_CallbackList") or [])

    def _scan_predicate_modifier_names(self) -> set[str]:
        names: set[str] = set()

        def walk(value: Any) -> None:
            if isinstance(value, dict):
                if value.get("$type") == "RPG.GameCore.ByIsContainModifier":
                    raw = value.get("ModifierName")
                    wanted = raw.get("Value") if isinstance(raw, dict) else raw
                    if wanted:
                        names.add(str(wanted))
                for child in value.values():
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)

        for root in (self.abilities, self.modifiers, self.global_templates,
                     self.sources.get("config_ai") or {}):
            walk(root)
        return names

    def _modifier_used_in_predicates(self, name: str) -> bool:
        return name in self._predicate_modifier_names

    @staticmethod
    def _and_condition(left: str, right: str) -> str:
        if left == right == "true":
            return "true"
        if left == "true":
            return right
        if right == "true":
            return left
        return f"({left}) and ({right})"

    @staticmethod
    def _negate_condition(expression: str) -> str:
        return f"not {expression}" if " " not in expression else f"not ({expression})"

    @staticmethod
    def _compare_operator(raw: Any) -> Optional[str]:
        return {"Equal": "==", "NotEqual": "!=", "Greater": ">",
                "GreaterEqual": ">=", "Less": "<", "LessEqual": "<="}.get(str(raw or "Equal"))

    def _simple_compare(self, predicate: Dict[str, Any], ctx: _Context,
                        path: str, node_type: str, value_expr: str,
                        *, field: str = "CompareValue", allow_inverse: bool = True,
                        allow_dynamic: bool = False) -> Optional[str]:
        """通用比较谓词骨架（压缩公共件）：取值表达式 + CompareType + 比较值 → 表达式。
        各比较型谓词只负责给出 value_expr 与目标解析，比较/求值/Inverse 统一走这里。"""
        compare = (self._value(predicate.get(field), ctx, f"{path}/{field}") if allow_dynamic
                   else self._number(predicate.get(field), ctx, f"{path}/{field}"))
        operator = self._compare_operator(predicate.get("CompareType"))
        if compare is None or operator is None:
            self._issue(ctx, path, node_type, "比较值/比较符未注册")
            return None
        expr = f"{value_expr} {operator} {compare}"
        return self._negate_condition(expr) if allow_inverse and predicate.get("Inverse") else expr

    @staticmethod
    def _predicate_target(alias: str) -> Optional[str]:
        if alias.startswith("Monster_") and alias.endswith("_Self"):
            return "$self.actor_id"
        return {"ParamEntity": "$it", "AbilityTargetEntity": "$event.target",
                "DamageAttackerEntity": "$event.source", "DamageDefenderEntity": "$event.target",
                "ParamEntityAdjoinEntity": {"pool": "allies",
                                            "where": "is_adjacent($it, $event.target)"},
                "ParamEntity.GetCreator": "$event.source", "ProjectileHitEntity": "$event.target",
                "TurnActionEntitySkillTarget": "$event.target",
                "Caster": "$self.actor_id", "ModifierOwnerEntity": "$self.actor_id",
                "CurrentTurnOwnerEntity": "turn_owner_of()",
                "CurrentTurnActionEntity": "turn_owner_of()",
                "LevelEntity": "$level", "LightTeamEntity": "$light_team",
                "DarkTeamEntity": "$dark_team",
            "CasterSummoner": "summoner_of($self.actor_id)",
            "ParamEntitySummoner": "summoner_of($it)",
            "ParamEntity.GetSummoner": "summoner_of($it)",
            "ModifierOwnerSummoner": "summoner_of($self.actor_id)",
            "ModifierOwnerEntity.GetSummoner": "summoner_of($self.actor_id)",
            "ModifierOwnerEntity.GetCreator": "summoner_of($self.actor_id)",
            "CasterLeftEntity": {"pool": "enemies",
                                 "where": "position_delta($it, $self.actor_id) == -1"},
            "CasterRightEntity": {"pool": "enemies",
                                  "where": "position_delta($it, $self.actor_id) == 1"},
            "CasterSummonedMinions": {"pool": "enemies",
                                      "where": "$it.summoner_id == $self.actor_id"},
            "LastSummonMonsters": {"pool": "last_summons"},
            "ModifierOwnerSummonedMinions": {"pool": "enemies",
                                             "where": "$it.summoner_id == $self.actor_id"},
            "ModifierOwnerEntity.GetServant": {"pool": "enemies",
                                               "where": "$it.summoner_id == $self.actor_id"},
            "AbilityTargetLeftEntity": {
                "pool": "allies", "where": "position_delta($it, $event.target) == -1"},
            "AbilityTargetRightEntity": {
                "pool": "allies", "where": "position_delta($it, $event.target) == 1"},
            "AbilityTargetAdjoinEntity": {"pool": "allies",
                                          "where": "is_adjacent($it, $event.target)"},
            "AbilityTargetAndAdjoinEntity": {
                "pool": "allies",
                "where": "($it.actor_id == $event.target or is_adjacent($it, $event.target))"},
            "PartEntity0": "(summoner_of($self.actor_id) or $self.actor_id)",
            "": "$self.actor_id"}.get(alias)

    def _target_membership(self, spec: Dict[str, Any], target: str) -> str:
        serialized = self._string_literal(json.dumps(
            spec, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        return f"target_in_selected({serialized}, {target})"

    def _static_monster_predicate(self, predicate: Dict[str, Any]) -> Optional[bool]:
        """怪物 ID 及布尔组合的生成期选支；恒真/恒假可与其余未知分支短路."""
        node_type = str((predicate or {}).get("$type") or "")
        if node_type == "RPG.GameCore.ByCompareMonsterID":
            if self._alias(predicate) not in {"", "Caster", "ModifierOwnerEntity"}:
                return None
            raw = predicate.get("TargetMonsterID")
            if isinstance(raw, dict) and raw.get("IsDynamic"):
                return None
            value = _fixed(raw)
            if not _is_number(value):
                return None
            result = str(self.enemy_id) == str(int(value))
            return not result if predicate.get("Inverse") else result
        if node_type in {"RPG.GameCore.ByAnd", "RPG.GameCore.ByAny"}:
            values = [self._static_monster_predicate(child)
                      for child in predicate.get("PredicateList") or []]
            if not values:
                return None
            if node_type.endswith("ByAnd"):
                if any(value is False for value in values):
                    return False
                return True if all(value is True for value in values) else None
            if any(value is True for value in values):
                return True
            return False if all(value is False for value in values) else None
        if node_type == "RPG.GameCore.ByNot":
            value = self._static_monster_predicate(predicate.get("Predicate") or {})
            return None if value is None else not value
        return None

    def _predicate_reads_written(self, predicate: Dict[str, Any], ctx: _Context) -> bool:
        """谓词树是否读取了本技能已写入的动态值/阶段（写后读——必须走 effect 级活读，
        hook 级快照发生在任何 effect 之前，读不到帧覆盖层；#26 期 2/3）."""
        node_type = str((predicate or {}).get("$type") or "")
        if node_type == "RPG.GameCore.ByCompareDynamicValue":
            raw_key = predicate.get("DynamicKey") or {}
            key = raw_key.get("Value") if isinstance(raw_key, dict) else raw_key
            return str(key) in ctx.dynamic_writes
        if node_type == "RPG.GameCore.ByCompareMonsterPhase":
            return "current_phase" in ctx.dynamic_writes
        if node_type == "RPG.GameCore.ByRandomChance":
            return True   # 嵌套概率必须留在 effect 域，roll 首读时才采样
        if node_type in {"RPG.GameCore.ByAnd", "RPG.GameCore.ByAny"}:
            return any(self._predicate_reads_written(child, ctx)
                       for child in predicate.get("PredicateList") or [])
        if node_type == "RPG.GameCore.ByNot":
            return self._predicate_reads_written(predicate.get("Predicate") or {}, ctx)
        return False

    def _predicate_expr(self, predicate: Dict[str, Any], ctx: _Context,
                        path: str, *, allow_written: bool = False) -> Optional[str]:
        node_type = str((predicate or {}).get("$type") or "")
        if node_type == "RPG.GameCore.ByRandomChance":
            raw_chance = predicate.get("Chance", predicate.get("CompareValue"))
            chance = self._value(raw_chance, ctx, f"{path}/Chance")
            if chance is None:
                return None
            shown = f"({chance})" if isinstance(chance, str) else str(chance)
            key = self._stable_roll_key(f"{path}/ByRandomChance")
            less = f"roll('{key}') < {shown}"
            return f"roll('{key}') >= {shown}" if predicate.get("Inverse") else less
        alias = self._alias(predicate)
        raw_target = predicate.get("TargetType")
        target = (self._target_spec(raw_target, ctx, path)
                  if isinstance(raw_target, dict)
                  and (raw_target.get("$type") in {"RPG.GameCore.TargetSequence", "RPG.GameCore.TargetCompute"}
                       or alias in self.target_aliases)
                  else self._predicate_target(alias))
        if alias in {"ParamEntity", "ParamEntityList", "TemplateParamEntityList",
                     "ParamEntityActualOwner", "ParamEntity.WithSummoner"} \
                and ctx.retarget is None and not ctx.in_target_filter:
            target = self._hook_target(alias, ctx) or target
        elif alias == "ParamEntity2" and ctx.event in {"after_apply_modifier", "after_remove_modifier"}:
            target = "$event.target"
        elif alias == "ParamEntity2" and ctx.event in {"on_kill", "on_revive", "after_being_hit"}:
            target = "$event.source"
        elif alias == "ModifierOwnerSkillTargetEntityList" and ctx.event in {"before_action", "on_action"}:
            target = "$event.targets"
        if alias.startswith("unique:"):
            target = (f"unique_target({self._string_literal(alias[len('unique:'):])})"
                      if len(alias) > len("unique:") else None)
        if alias == "ParamEntity.GetCreator":
            if ctx.event == "actor_enter":
                target = "summoner_of($event.actor)"
            elif ctx.event == "after_being_hit":
                target = "summoner_of($event.target)"
            elif ctx.event != "battle_event_create":
                self._issue(ctx, path, node_type,
                            "GetCreator 仅支持 actor_enter/after_being_hit/battle_event_create 语境")
                return None
        if node_type == "RPG.GameCore.ByCompareParamString":
            raw = predicate.get("CompareValue")
            expected = raw.get("Value") if isinstance(raw, dict) else raw
            if not isinstance(expected, str) or not expected or not ctx.current_ability:
                self._issue(ctx, path, node_type, "参数串比较需要当前 Ability 名与非空字符串")
                return None
            result = ctx.current_ability == expected
            if predicate.get("Inverse"):
                result = not result
            return "1 == 1" if result else "1 == 0"
        if node_type == "RPG.GameCore.ByCompareStageID":
            stage = self._number(predicate.get("StageID"), ctx, f"{path}/StageID")
            operator = self._compare_operator(predicate.get("CompareType"))
            if stage is None or operator is None or int(stage) != stage:
                self._issue(ctx, path, node_type, "StageID 需静态整数与已注册比较符")
                return None
            expr = f"stage_id() {operator} {int(stage)}"
            return self._negate_condition(expr) if predicate.get("Inverse") else expr
        if node_type == "RPG.GameCore.ByTargetListIntersects":
            first = self._target_spec(predicate.get("FirstTargetType"), ctx, f"{path}/First")
            second = self._target_spec(predicate.get("SecondTargetType"), ctx, f"{path}/Second")
            if first is None or second is None:
                return None
            if predicate.get("FirstTargetAliveOnly") is False:
                first["include_dead"] = True
            if predicate.get("SecondTargetAliveOnly") is False:
                second["include_dead"] = True
            first_json = self._string_literal(json.dumps(first, separators=(",", ":")))
            second_json = self._string_literal(json.dumps(second, separators=(",", ":")))
            expr = f"target_lists_intersect({first_json}, {second_json})"
            return self._negate_condition(expr) if predicate.get("Inverse") else expr
        if node_type == "RPG.GameCore.ByTargetListAny":
            spec = self._target_spec(raw_target, ctx, path)
            if spec is None:
                return None
            previous_filter = ctx.in_target_filter
            ctx.in_target_filter = True
            try:
                inner = self._predicate_expr(predicate.get("Predicate") or {}, ctx,
                                             f"{path}/Predicate", allow_written=allow_written)
            finally:
                ctx.in_target_filter = previous_filter
            if inner is None:
                return None
            pool = self._string_literal(str(spec["pool"]))
            where = self._and_condition(str(spec.get("where", "true")), inner)
            expr = f"count_selected({pool}, {self._string_literal(where)}) > 0"
            return self._negate_condition(expr) if predicate.get("Inverse") else expr
        if isinstance(target, dict) and node_type not in {
                "RPG.GameCore.ByCompareCharacterNumber", "RPG.GameCore.ByCompareTargetCount"}:
            nested = dict(predicate)
            nested["TargetType"] = {"$type": "RPG.GameCore.TargetAlias", "Alias": "ParamEntity"}
            nested.pop("Inverse", None)
            previous_filter = ctx.in_target_filter
            ctx.in_target_filter = True
            try:
                inner = self._predicate_expr(nested, ctx, path, allow_written=allow_written)
            finally:
                ctx.in_target_filter = previous_filter
            if inner is None:
                return None
            pool = self._string_literal(str(target["pool"]))
            where = self._and_condition(str(target.get("where", "true")), inner)
            expr = f"count_selected({pool}, {self._string_literal(where)}) > 0"
            return self._negate_condition(expr) if predicate.get("Inverse") else expr
        if node_type == "RPG.GameCore.ByCompareParamValue":
            if ctx.event not in {"on_hp_decrease", "on_hp_increase", "on_skill_point_change",
                                 "on_energy_change"}:
                self._issue(ctx, path, node_type, "ParamValue 比较仅限 HP/战技点/能量变化事件")
                return None
            return self._simple_compare(predicate, ctx, path, node_type, self._param_change_value(ctx))
        if node_type == "RPG.GameCore.ByCompareDynamicValue":
            if alias in {"CasterSummoner", "ModifierOwnerSummoner"}:
                target = "summoner_of($self.actor_id)"   # 召唤者目标（HP 谓词同通道）
            if target is None:
                self._issue(ctx, path, node_type, f"动态值谓词目标未注册：{alias}")
                return None
            raw_key = predicate.get("DynamicKey") or {}
            key = raw_key.get("Value") if isinstance(raw_key, dict) else raw_key
            # 比较值允许动态表达式（与另一动态值/表达式比较），不再限静态数字
            compare = self._value(predicate.get("CompareValue"), ctx, f"{path}/CompareValue")
            operator = self._compare_operator(predicate.get("CompareType"))
            if not key or compare is None or operator is None:
                self._issue(ctx, path, node_type, "动态值键/比较值/比较符未注册")
                return None
            count_expr = ctx.count_expressions.get(dynamic_value_hash(str(key)))
            if count_expr is not None and target == "$self.actor_id":
                return f"({count_expr}) {operator} {compare}"
            if str(key) in ctx.dynamic_writes and not allow_written:
                # 调用方（Retarget where/目标过滤等无 effect 级 condition 承载的语境）
                # 无法表达写后读活读——保持拒绝；PredicateTaskList 分支走 allow_written。
                self._issue(ctx, path, node_type, "写后读谓词仅限 PredicateTaskList 分支活读")
                return None
            symbol = (ctx.value_symbols.get(dynamic_value_hash(str(key)))
                      if target == "$self.actor_id" else None)
            if symbol is not None:
                return f"({symbol}) {operator} {compare}"
            namespace = "$self" if target == "$self.actor_id" else target
            return f"dynamic_of({namespace}, '{key}') {operator} {compare}"
        if node_type == "RPG.GameCore.ByCompareMonsterPhase":
            if not isinstance(target, str):
                self._issue(ctx, path, node_type, f"阶段谓词目标未注册：{alias}")
                return None
            if target == "$self.actor_id" and "current_phase" in ctx.dynamic_writes and not allow_written:
                self._issue(ctx, path, node_type, "写后读阶段谓词仅限 PredicateTaskList 分支活读")
                return None
            compare = self._value(predicate.get("CompareValue"), ctx, f"{path}/CompareValue")
            operator = self._compare_operator(predicate.get("CompareType"))
            if compare is None or operator is None:
                self._issue(ctx, path, node_type, "阶段比较值/比较符未注册")
                return None
            namespace = "$self" if target == "$self.actor_id" else target
            return f"dynamic_of({namespace}, 'current_phase') {operator} {compare}"
        if node_type == "RPG.GameCore.ByCompareMonsterRank":
            if target is None:
                self._issue(ctx, path, node_type, f"怪物等级谓词目标未注册：{alias}")
                return None
            return self._simple_compare(predicate, ctx, path, node_type,
                                        f"monster_rank({target})")
        if node_type == "RPG.GameCore.ByCompareCharacterID":
            if target is None:
                self._issue(ctx, path, node_type, f"角色 ID 谓词目标未注册：{alias}")
                return None
            character_id = self._number(
                predicate.get("TargetCharacterID"), ctx, f"{path}/TargetCharacterID")
            if character_id is None:
                return None
            if alias == "ModifierOwnerSkillTargetEntityList":
                if predicate.get("CompareType") not in {None, "Equal"}:
                    self._issue(ctx, path, node_type, "目标列表的 CharacterID 仅支持 Equal")
                    return None
                expr = self._any_target_expr(target, f"character_id($it) == '{int(character_id)}'")
            else:
                expr = f"character_id({target}) == '{int(character_id)}'"
            return self._negate_condition(expr) if predicate.get("Inverse") else expr
        if node_type == "RPG.GameCore.ByCompareMonsterID":
            if alias.endswith("_Self"):
                alias = "Caster"   # Monster_*_Self = 自身特定形态
            monster_id = self._value(predicate.get("TargetMonsterID"), ctx, f"{path}/TargetMonsterID")
            if monster_id is None:
                return None
            if isinstance(monster_id, str):
                if alias.startswith("Monster_"):
                    self._issue(ctx, path, node_type, "字面怪物目标的动态 ID 比较未收编")
                    return None
                if target is None:
                    self._issue(ctx, path, node_type, f"怪物 ID 谓词目标未注册：{alias}")
                    return None
                expr = f"monster_id_equals({target}, {monster_id})"
                return self._negate_condition(expr) if predicate.get("Inverse") else expr
            if alias.startswith("Monster_"):
                return "1 == 1" if alias == str(int(monster_id)) else "1 == 0"
            if target is None:
                self._issue(ctx, path, node_type, f"怪物 ID 谓词目标未注册：{alias}")
                return None
            if alias in {"", "Caster"}:
                expr = "1 == 1" if str(self.enemy_id) == str(int(monster_id)) else "1 == 0"
            else:
                expr = f"monster_id({target}) == '{int(monster_id)}'"
            return self._negate_condition(expr) if predicate.get("Inverse") else expr
        if node_type == "RPG.GameCore.ByCompareMonsterTemplateID":
            if target is None:
                self._issue(ctx, path, node_type, f"怪物模板 ID 谓词目标未注册：{alias}")
                return None
            monster_id = self._number(
                predicate.get("TargetMonsterTemplateID"), ctx, f"{path}/TargetMonsterTemplateID")
            if monster_id is None:
                return None
            if alias in {"", "Caster", "ModifierOwnerEntity"}:
                expr = "1 == 1" if self.monster_template_id == str(int(monster_id)) else "1 == 0"
            else:
                expr = f"monster_id({target}) == '{int(monster_id)}'"
            return self._negate_condition(expr) if predicate.get("Inverse") else expr
        if node_type == "RPG.GameCore.ByCheckCustomValueBool":
            if target is None:
                self._issue(ctx, path, node_type, f"CustomValueBool 目标未注册：{alias}")
                return None
            raw_key = predicate.get("Key") or {}
            if raw_key.get("Value") is not None:
                tags = [str(raw_key["Value"])]
            else:
                try:
                    key_hash = int(raw_key.get("Hash"))
                except (TypeError, ValueError):
                    self._issue(ctx, path, node_type, "CustomValueBool 缺有效 Key.Hash")
                    return None
                tags = [tag for tag in self.custom_value_tags
                        if dynamic_value_hash(str(tag)) == key_hash]
            if len(tags) != 1 or "'" in tags[0]:
                self._issue(ctx, path, node_type, "CustomValueBool 哈希缺失、冲突或含非法字符")
                return None
            expr = f"in_group({target}, '{tags[0]}')"
            return self._negate_condition(expr) if predicate.get("Inverse") else expr
        if node_type == "RPG.GameCore.ByCompareModifierValue":
            raw_name = predicate.get("ModifierName")
            name = (raw_name.get("Value") if isinstance(raw_name, dict) else raw_name) \
                or ctx.current_modifier
            value_type = predicate.get("ValueType", "Count")
            if value_type not in {"Count", "Layer", "LifeTime", "MaxLayer"} or target is None or not name:
                self._issue(ctx, path, node_type, "modifier 数值类型/目标/名称未注册")
                return None
            compare = self._value(predicate.get("CompareValue"), ctx, f"{path}/CompareValue")
            operator = self._compare_operator(predicate.get("CompareType"))
            if compare is None or operator is None:
                self._issue(ctx, path, node_type, "modifier 数值比较值/比较符未注册")
                return None
            definition = self.modifiers.get(str(name)) or {}
            modifier_id = self._modifier_id(
                str(name), definition, str(ctx.skill.get("skill_id") or self.enemy_id))
            reader = {"Count": "has_modifier", "Layer": "stacks", "LifeTime": "modifier_duration",
                      "MaxLayer": "modifier_max_stacks"}[value_type]
            return f"{reader}({target}, '{modifier_id}') {operator} {compare}"
        if node_type == "RPG.GameCore.ByContainBehaviorFlag":
            if target is None:
                self._issue(ctx, path, node_type, f"BehaviorFlag 目标未注册：{alias}")
                return None
            raw_flags = predicate.get("Flags")
            if raw_flags is not None and predicate.get("Flag") is not None:
                self._issue(ctx, path, node_type, "Flag/Flags 不能同时声明")
                return None
            if raw_flags is not None:
                if not isinstance(raw_flags, list) or not raw_flags:
                    self._issue(ctx, path, node_type, "Flags 须为非空列表")
                    return None
                if predicate.get("ContainType", "Or") not in {"Or", "And"}:
                    self._issue(ctx, path, node_type, "ContainType 仅支持 Or/And")
                    return None
                flags = list(raw_flags)
            else:
                flags = [predicate.get("Flag")]
            expressions = []
            for flag in flags:
                if flag == "Shield":
                    expr = f"has_shield({target})"
                elif flag in {"STAT_CTRL", "STAT_Confine"}:
                    expr = f"controlled({target})"
                elif flag == "Break":
                    expr = f"broken_of({target})"
                elif flag == "STAT_DOT":
                    expr = f"dot_count({target}) > 0"
                elif flag == "STAT_DOT_Electric":
                    expr = f"dot_kind({target}, 'shock')"
                elif flag == "DisableAction":
                    expr = f"action_disabled({target})"
                elif flag == "Taunt":
                    expr = f"controlled({target}, 'taunt')"
                elif flag == "STAT_CTRL_Frozen":
                    expr = f"controlled({target}, 'freeze')"
                elif flag == "STAT_CTRL_Stun":
                    expr = f"controlled({target}, 'stun')"
                elif flag == "STAT_Entangle":
                    expr = f"controlled({target}, 'entangle')"
                elif flag == "ImmuneDebuff":
                    expr = f"immune_debuff({target})"
                elif isinstance(flag, str) and flag:
                    expr = f"has_behavior_flag({target}, {self._string_literal(flag)})"
                else:
                    self._issue(ctx, path, node_type, "BehaviorFlag 需为非空字符串")
                    return None
                expressions.append(expr)
            joiner = " and " if predicate.get("ContainType") == "And" else " or "
            expr = expressions[0] if len(expressions) == 1 else "(" + joiner.join(expressions) + ")"
            return self._negate_condition(expr) if predicate.get("Inverse") else expr
        if node_type in {"RPG.GameCore.ByCompareCurrentModifierStatusType",
                         "RPG.GameCore.ByCheckModifierCallBackStatusType"}:
            status = predicate.get("TargetStatusType")
            if ctx.event != "after_apply_modifier" or status not in {"Buff", "Debuff"}:
                self._issue(ctx, path, node_type, "当前 modifier 类型需添加事件与 Buff/Debuff")
                return None
            expr = f"$event.modifier_type == '{str(status).lower()}'"
            return self._negate_condition(expr) if predicate.get("Inverse") else expr
        if node_type == "RPG.GameCore.ByCheckModifierCallBackBehaviorFlag":
            flag = predicate.get("Flag")
            if not flag or ctx.event not in {"after_apply_modifier", "after_remove_modifier"}:
                self._issue(ctx, path, node_type, "回调行为旗标需 modifier 添加/移除事件语境与 Flag")
                return None
            expr = f"{self._string_literal(str(flag))} in $event.behavior_flags"
            return self._negate_condition(expr) if predicate.get("Inverse") else expr
        if node_type == "RPG.GameCore.ByCheckModifierDeathSource":
            source = predicate.get("DeathSource")
            if ctx.event != "after_remove_modifier" or source != "CasterDead":
                self._issue(ctx, path, node_type,
                            f"modifier 移除原因需 after_remove_modifier/CasterDead：{ctx.event} / {source}")
                return None
            expr = "$event.reason == 'source_death'"
            return self._negate_condition(expr) if predicate.get("Inverse") else expr
        if node_type == "RPG.GameCore.ByCheckModifierCallBackName":
            raw = predicate.get("ModifierName") or {}
            name = raw.get("Value") if isinstance(raw, dict) else raw
            if not ctx.current_modifier or not name:
                self._issue(ctx, path, node_type, "缺少 modifier 回调语境或回调名")
                return None
            definition = self.modifiers.get(str(name)) or {}
            modifier_id = self._modifier_id(
                str(name), definition, str(ctx.skill.get("skill_id") or self.enemy_id))
            expr = f"$event.modifier_id == '{modifier_id}'"
            return self._negate_condition(expr) if predicate.get("Inverse") else expr
        if node_type == "RPG.GameCore.ByCheckModifierCallBackModifierValue":
            if ctx.event != "after_apply_modifier" or predicate.get("ValueType") != "Layer":
                self._issue(ctx, path, node_type, "回调 modifier 数值仅支持添加事件的 Layer")
                return None
            return self._simple_compare(
                predicate, ctx, path, node_type, "stacks($event.target, $event.modifier_id)")
        if node_type == "RPG.GameCore.ByIsContainModifier":
            if target is None:
                self._issue(ctx, path, node_type, f"modifier 谓词目标未注册：{alias}")
                return None
            raw = predicate.get("ModifierName") or {}
            name = raw.get("Value") if isinstance(raw, dict) else raw
            definition = self.modifiers.get(str(name)) or {}
            modifier_id = self._modifier_id(
                str(name), definition, str(ctx.skill.get("skill_id") or self.enemy_id))
            target_list = target if alias == "ModifierOwnerSkillTargetEntityList" else ""
            expr_target = "$it" if target_list else target
            source = predicate.get("CasterFilter")
            if source is None:
                expr = f"has_modifier({expr_target}, '{modifier_id}')"
            else:
                source_alias = self._alias({"TargetType": source})
                if source_alias == "ModifierOwnerEntity":
                    source_expr = "$self.actor_id"
                elif source_alias == "Caster":
                    if ctx.event in {"on_apply", "after_remove_modifier"}:
                        source_expr = "$event.source"
                    elif ctx.event == "before_actor_exit":
                        current_definition = self.modifiers.get(ctx.current_modifier) or {}
                        current_id = self._modifier_id(
                            ctx.current_modifier, current_definition,
                            str(ctx.skill.get("skill_id") or self.enemy_id))
                        source_expr = f"modifier_source($event.actor, '{current_id}')"
                    else:
                        source_expr = "$self.actor_id"
                else:
                    self._issue(ctx, path, node_type, f"CasterFilter 未注册：{source_alias}")
                    return None
                expr = f"has_modifier({expr_target}, '{modifier_id}', {source_expr})"
            if target_list:
                expr = self._any_target_expr(target_list, expr)
            return self._negate_condition(expr) if predicate.get("Inverse") else expr
        if node_type == "RPG.GameCore.ByHasSummonRelation":
            summoner = self._predicate_target(self._alias({"TargetType": predicate.get("SummonerType")}))
            servant = self._predicate_target(self._alias({"TargetType": predicate.get("ServantType")}))
            if summoner is None or servant is None:
                self._issue(ctx, path, node_type, "召唤关系目标未注册")
                return None
            expr = f"summoner_of({servant}) == {summoner}"
            return self._negate_condition(expr) if predicate.get("Inverse") else expr
        if node_type == "RPG.GameCore.ByIsBattleEventEntity":
            if target is None:
                self._issue(ctx, path, node_type, f"战斗事件实体谓词目标未注册：{alias}")
                return None
            expr = f"actor_type_of({target}) == 'battle_event'"
            return self._negate_condition(expr) if predicate.get("Inverse") else expr
        if node_type == "RPG.GameCore.ByTargetEntityType":
            mask = predicate.get("EntityTypeMask")
            alive_mask = predicate.get("AliveStateMask")
            if target is None or mask not in {"Avatar", "Servant", "Monster", "BattleEvent"} \
                    or alive_mask not in {None, "Anyone", "Mask_AliveOnly"}:
                self._issue(ctx, path, node_type,
                            f"实体类型目标/掩码未注册：{alias} / {mask} / {alive_mask}")
                return None
            expr = {
                "Avatar": f"actor_type_of({target}) == 'character'",
                "Servant": f"actor_type_of({target}) == 'summon' or summoner_of({target}) != ''",
                "Monster": f"actor_type_of({target}) == 'monster' or actor_type_of({target}) == 'enemy'",
                "BattleEvent": f"actor_type_of({target}) == 'battle_event'",
            }[mask]
            if alive_mask == "Mask_AliveOnly":
                expr = f"actor_alive({target}) and ({expr})"
            return self._negate_condition(expr) if predicate.get("Inverse") else expr
        if node_type == "RPG.GameCore.ByCompareTarget":
            other_raw = predicate.get("CompareType") or {}
            other = self._alias({"TargetType": other_raw})
            if target is None:
                self._issue(ctx, path, node_type, f"目标比较未注册：{alias} / {other}")
                return None
            if target == "$it":
                target = "$it.actor_id"
            if other in {"Caster", "ModifierOwnerEntity", "CurrentTurnOwnerEntity"}:
                other_expr = ("turn_owner_of()" if other == "CurrentTurnOwnerEntity"
                              else "$self.actor_id")
                expr = f"{target} == {other_expr}"
            elif other == "ParamEntity":
                other_target = "$it" if ctx.in_target_filter or ctx.mode == "action" \
                    else self._hook_target(other, ctx)
                if isinstance(other_target, dict):
                    expr = self._target_membership(other_target, target)
                elif isinstance(other_target, str):
                    expr = f"{target} == {other_target}"
                else:
                    self._issue(ctx, path, node_type, f"目标比较未注册：{alias} / {other}")
                    return None
            elif other.startswith("unique:") and len(other) > len("unique:"):
                unique_name = self._string_literal(other[len("unique:"):])
                expr = f"{target} == unique_target({unique_name})"
            elif other == "CasterSummonedMinions":
                expr = f"summoner_of({target}) == $self.actor_id"
            elif other:
                spec = self._target_spec(other_raw, ctx, f"{path}/CompareType")
                if spec is None:
                    return None
                expr = self._target_membership(spec, target)
            else:
                self._issue(ctx, path, node_type, f"目标比较未注册：{alias} / {other}")
                return None
            return self._negate_condition(expr) if predicate.get("Inverse") else expr
        if node_type == "RPG.GameCore.ByAvatarBaseType":
            raw_types = predicate.get("BaseTypeList") or []
            paths = [PATH_ALIASES.get(str(value).lower(), str(value).lower())
                     for value in raw_types]
            if target is None or not paths or any(path not in PATHS for path in paths):
                self._issue(ctx, path, node_type,
                            f"命途类型/目标未注册：{raw_types} / {alias}")
                return None
            expr = " or ".join(f"path_of({target}) == '{path}'" for path in paths)
            return self._negate_condition(expr) if predicate.get("Inverse") else f"({expr})"
        if node_type == "RPG.GameCore.ByCompareStance":
            if target is None:
                self._issue(ctx, path, node_type, f"韧性谓词目标未注册：{alias}")
                return None
            return self._simple_compare(predicate, ctx, path, node_type,
                                        f"toughness_of({target})")
        if node_type == "RPG.GameCore.ByCompareStanceCount":
            if target is None:
                self._issue(ctx, path, node_type, f"韧性条数谓词目标未注册：{alias}")
                return None
            return self._simple_compare(predicate, ctx, path, node_type,
                                        f"stance_count_of({target})")
        if node_type == "RPG.GameCore.ByCompareTurnActionEntityTeamType":
            team = predicate.get("Team")
            if team not in {"TeamDark", "TeamLight"}:
                self._issue(ctx, path, node_type, f"回合阵营未注册：{team}")
                return None
            operator = "==" if team == "TeamDark" else "!="
            expr = f"actor_type_of(turn_owner_of()) {operator} 'monster'"
            return self._negate_condition(expr) if predicate.get("Inverse") else expr
        if node_type == "RPG.GameCore.ByCurrentSkillTargetType":
            target_type = {"AllEnemy": "aoe"}.get(predicate.get("TargetType"))
            if target_type is None or ctx.event != "on_action":
                self._issue(ctx, path, node_type,
                            f"当前技能目标类型需 on_action 语境与已注册类型：{predicate.get('TargetType')}")
                return None
            expr = f"$event.target_type == '{target_type}'"
            return self._negate_condition(expr) if predicate.get("Inverse") else expr
        if node_type == "RPG.GameCore.ByIsMatchTeammateCount":
            team = predicate.get("TeamType")
            if team not in {"TeamDark", "TeamLight"}:
                self._issue(ctx, path, node_type, f"队伍阵营未注册：{team}")
                return None
            raw_count = predicate.get("CountType")
            count = {"Count0": 0, "Count1": 1, "Count2": 2, "Count3": 3}.get(
                raw_count, 0 if raw_count is None else None)
            if count is None:
                self._issue(ctx, path, node_type, f"队伍人数类型未注册：{raw_count}")
                return None
            side = "dark" if team == "TeamDark" else "light"
            expr = f"side_size($self.actor_id, '{side}') == {count}"
            return self._negate_condition(expr) if predicate.get("Inverse") else expr
        if node_type == "RPG.GameCore.ByCompareWaveCount":
            return self._simple_compare(predicate, ctx, path, node_type, "wave_index()")
        if node_type == "RPG.GameCore.ByCompareAliveEnemyNumber":
            if target is None:
                self._issue(ctx, path, node_type, f"存活敌人数谓词目标未注册：{alias}")
                return None
            opposing_side = f"((actor_type_of({target}) == 'monster') ? 'light' : 'dark')"
            return self._simple_compare(predicate, ctx, path, node_type,
                                        f"side_size({target}, {opposing_side})")
        if node_type == "RPG.GameCore.ByIsTeammate":
            if target is None:
                self._issue(ctx, path, node_type, f"同阵营谓词目标未注册：{alias}")
                return None
            expr = (f"((actor_type_of({target}) == 'monster') == "
                    f"(actor_type_of($self.actor_id) == 'monster'))")
            return self._negate_condition(expr) if predicate.get("Inverse") else expr
        if node_type == "RPG.GameCore.ByIsTargetUnselectable":
            if target is None:
                self._issue(ctx, path, node_type, f"不可选谓词目标未注册：{alias}")
                return None
            source = self._alias({"TargetType": predicate.get("SourceEntity")})
            side = {"": "", "DarkTeamEntity": "dark", "LightTeamEntity": "light"}.get(source)
            if side is None:
                self._issue(ctx, path, node_type, f"不可选来源阵营未注册：{source}")
                return None
            expr = f"target_unselectable({target}, '{side}')" if side \
                else f"target_unselectable({target})"
            return self._negate_condition(expr) if predicate.get("Inverse") else expr
        if node_type == "RPG.GameCore.ByCasterAliveOrLimbo":
            if predicate.get("AliveStateMask", "Mask_AliveOrLimbo") not in {
                    "Mask_AliveOnly", "Mask_AliveOrLimbo"}:
                self._issue(ctx, path, node_type, "Caster 存活掩码未注册")
                return None
            expr = "actor_alive($self.actor_id)"
            return self._negate_condition(expr) if predicate.get("Inverse") else expr
        if node_type == "RPG.GameCore.ByIsTopActionDelayTarget":
            compare_alias = self._alias({"TargetType": predicate.get("CompareTargetType")})
            team = {"": "", "AllLightTeam": "light", "AllDarkTeam": "dark",
                    "AllTeamMember": "dark", "AllTeammate": "dark"}.get(compare_alias)
            if target is None or team is None:
                self._issue(ctx, path, node_type, "行动条首位目标或比较阵营未注册")
                return None
            expr = f"is_top_action_delay_target({target}, '{team}')"
            return self._negate_condition(expr) if predicate.get("Inverse") else expr
        if node_type == "RPG.GameCore.ByTargetAliveState":
            if alias in {"CasterSummoner", "ModifierOwnerSummoner"}:
                target = "summoner_of($self.actor_id)"
            if predicate.get("AliveStateMask") == "Bit_OnStage" and target == "$it":
                return "not $it.banished"
            if target is None or predicate.get("AliveStateMask") not in {
                    "Mask_AliveOnly", "Mask_AliveOrLimbo"}:
                self._issue(ctx, path, node_type,
                            f"存活谓词目标/掩码未注册：{alias} / {predicate.get('AliveStateMask')}")
                return None
            expr = f"actor_alive({target})"
            return self._negate_condition(expr) if predicate.get("Inverse") else expr
        if node_type == "RPG.GameCore.ByIsEntityActionState":
            state = predicate.get("ActionState", True)
            if target is None or not isinstance(state, bool):
                self._issue(ctx, path, node_type, "行动状态谓词需已注册目标与布尔 ActionState")
                return None
            expr = (f"not action_disabled({target})" if state
                    else f"action_disabled({target})")
            return self._negate_condition(expr) if predicate.get("Inverse") else expr
        if node_type == "RPG.GameCore.ByIsTargetValid":
            if target is None or predicate.get("AliveOnly", True) is not True:
                self._issue(ctx, path, node_type,
                            f"有效目标谓词仅支持 AliveOnly=true 的已注册目标：{alias}")
                return None
            expr = f"actor_alive({target})"
            return self._negate_condition(expr) if predicate.get("Inverse") else expr
        if node_type == "RPG.GameCore.ByTurnOwnerHasPendingOneMore":
            if target is None:
                self._issue(ctx, path, node_type, f"再动挂起谓词目标未注册：{alias}")
                return None
            return f"has_pending_one_more({target})"
        if node_type == "RPG.GameCore.ByCompareBattleEventID":
            raw_event_id = predicate.get("EventID", predicate.get("TargetBattleEventID"))
            event_id = self._number(raw_event_id, ctx, f"{path}/EventID")
            if event_id is None or int(event_id) != event_id:
                self._issue(ctx, path, node_type, "EventID 需静态整数")
                return None
            if "TargetBattleEventID" in predicate and ctx.event == "battle_event_create":
                expr = f"$event.event_id == {int(event_id)}"
                return self._negate_condition(expr) if predicate.get("Inverse") else expr
            return f"battle_event_exists({int(event_id)})"
        if node_type == "RPG.GameCore.ByCharacterDamageType":
            if target is None:
                self._issue(ctx, path, node_type, f"伤害属性谓词目标未注册：{alias}")
                return None
            element = _element(predicate.get("DamageType"))
            if not element:
                self._issue(ctx, path, node_type, "伤害属性词表外")
                return None
            expr = f"element_of({target}) == '{element}'"
            return self._negate_condition(expr) if predicate.get("Inverse") else expr
        if node_type == "RPG.GameCore.ByCompareAbilityProperty":
            value_expr = {
                "CurrentHP": f"hp_of({target})",
                "BaseSpeed": f"base_stat_of({target}, 'spd')",
                "ActionDelay": f"action_delay_of({target})",
                "CurrentSpecialSP": f"special_sp_of({target})",
                "Shield": f"shield_of({target})",
                "MaxSpecialSP": f"max_special_sp_of({target})",
            }.get(predicate.get("Property"))
            if not isinstance(target, str) or value_expr is None:
                self._issue(ctx, path, node_type,
                            f"AbilityProperty 目标/属性未注册：{alias} / {predicate.get('Property')}")
                return None
            return self._simple_compare(predicate, ctx, path, node_type, value_expr, allow_dynamic=True)
        if node_type == "RPG.GameCore.ByCompareTeamFormationRowIndex":
            if target is None:
                self._issue(ctx, path, node_type, f"排号谓词目标未注册：{alias}")
                return None
            return self._simple_compare(
                predicate, ctx, path, node_type, f"dynamic_of({target}, '_FormationRow')")
        if node_type == "RPG.GameCore.ByCompareHP":
            if alias in {"CasterSummoner", "ModifierOwnerSummoner"}:
                target = "summoner_of($self.actor_id)"
            if target is None:
                self._issue(ctx, path, node_type, f"HP 谓词目标未注册：{alias}")
                return None
            return self._simple_compare(predicate, ctx, path, node_type,
                                        f"hp_of({target})", allow_inverse=False)

        if node_type == "RPG.GameCore.ByCompareSPRatio":
            if target is None:
                self._issue(ctx, path, node_type, f"能量比例谓词目标未注册：{alias}")
                return None
            return self._simple_compare(
                predicate, ctx, path, node_type,
                f"(energy_of({target}) / max_energy_of({target}))",
                allow_inverse=False, allow_dynamic=True)
        if node_type == "RPG.GameCore.ByCompareHPRatio":
            if alias in {"CasterSummoner", "ModifierOwnerSummoner"}:
                target = "summoner_of($self.actor_id)"
            if target is None:
                self._issue(ctx, path, node_type, f"HP 比例谓词目标未注册：{alias}")
                return None
            return self._simple_compare(predicate, ctx, path, node_type,
                                        f"(hp_of({target}) / max_hp_of({target}))",
                                        allow_inverse=False, allow_dynamic=True)
        if node_type in {"RPG.GameCore.ByCompareCharacterNumber", "RPG.GameCore.ByCompareTargetCount"}:
            target_raw = predicate.get("TargetType")
            if (predicate.get("Predicate") or alias in self.target_aliases
                    or alias == "GridFight_AllBackEnd"
                    or (node_type == "RPG.GameCore.ByCompareTargetCount"
                        and not predicate.get("AliveOnly"))
                    or alias in {
                        "AbilityTargetAdjoinEntity", "AbilityTargetAndAdjoinEntity",
                        "ParamEntityAdjoinEntity", "CasterAdjoinEntity", "AllLightTeam.RemoveServant",
                        "CasterSummonedMinions", "ModifierOwnerSummonedMinions",
                        "Monster_W4_Griffin_00_LocalLegend_Partner",
                        "ParamEntityList", "TemplateParamEntityList"}
                    or (alias.startswith("PartEntity")
                        and alias.removeprefix("PartEntity").isdigit())
                    or (isinstance(target_raw, dict)
                        and target_raw.get("$type") == "RPG.GameCore.TargetSequence")):
                count_expr = self._count_expression(
                    target_raw, ctx, path, predicate.get("Predicate"),
                    include_dead=(node_type == "RPG.GameCore.ByCompareTargetCount"
                                  and not predicate.get("AliveOnly")))
            else:
                count_expr = {
                    "AllTeammate": "enemies_alive()", "AllDarkTeam": "enemies_alive()",
                    "AllTeamMember": "enemies_alive()",
                    "AllDarkTeamWithAllDarkTeamUnselectable": "enemies_alive()",
                    "AllDarkTeam - Caster": "(enemies_alive() - 1)",
                    "AllEnemy": "count($team.actor_id)", "AllLightTeam": "count($team.actor_id)",
                    "AllLightTeamIgnoreServant": "count_selected(\"allies\", \"actor_type_of($it) != 'summon'\")",
                }.get(alias)
            raw_compare = (predicate.get("CompareNumber")
                           if node_type == "RPG.GameCore.ByCompareCharacterNumber"
                           else predicate.get("Number"))
            compare = self._number(raw_compare, ctx, f"{path}/CompareNumber")
            operator = self._compare_operator(predicate.get("CompareType"))
            if count_expr is None or compare is None or operator is None:
                self._issue(ctx, path, node_type, f"人数谓词目标/比较值未注册：{alias}")
                return None
            return f"{count_expr} {operator} {compare}"
        if node_type in {"RPG.GameCore.ByAnd", "RPG.GameCore.ByAny"}:
            joiner = " and " if node_type.endswith("ByAnd") else " or "
            parts = [self._predicate_expr(child, ctx, f"{path}/PredicateList/{index}",
                                          allow_written=allow_written)
                     for index, child in enumerate(predicate.get("PredicateList") or [])]
            if not parts or any(part is None for part in parts):
                return None
            return "(" + joiner.join(parts) + ")"
        if node_type == "RPG.GameCore.ByNot":
            child = self._predicate_expr(predicate.get("Predicate") or {}, ctx, f"{path}/Predicate",
                                         allow_written=allow_written)
            return self._negate_condition(child) if child is not None else None
        if node_type == "RPG.GameCore.ByIsTeamLocationIndexType":
            # 站位 = 同侧存活列表序；缺省/Left=最左，Right/Max=最右。
            if target is None:
                self._issue(ctx, path, node_type, f"站位谓词目标未注册：{alias}")
                return None
            team = str(predicate.get("TeamType") or "")
            if team not in ("TeamDark", "TeamLight"):
                self._issue(ctx, path, node_type, f"站位阵营未注册：{team}")
                return None
            team_arg = "dark" if team == "TeamDark" else "light"
            pos = f"position_of({target}, '{team_arg}')"
            size = f"side_size({target}, '{team_arg}')"
            ptype = predicate.get("Type")
            if ptype in (None, "", "Left"):
                expr = f"{pos} == 1"
            elif ptype in ("Right", "Max"):
                expr = f"{pos} == {size}"
            elif ptype == "Medium":
                expr = f"{pos} > 1 and {pos} < {size}"
            elif isinstance(ptype, str) and ptype.startswith("Pos") and ptype[3:].isdigit():
                expr = f"{pos} == {int(ptype[3:])}"
            else:
                self._issue(ctx, path, node_type, f"站位类型词表外：{ptype!r}")
                return None
            if predicate.get("Inverse"):
                expr = f"not ({expr})"
            return f"({expr})"
        if node_type == "RPG.GameCore.ByIsTargetAbleToAction":
            if target is None:
                self._issue(ctx, path, node_type, f"行动能力谓词目标未注册：{alias}")
                return None
            expr = f"not action_disabled({target})"
            return self._negate_condition(expr) if predicate.get("Inverse") else expr
        if node_type == "RPG.GameCore.ByTargetLockHP":
            if target is None:
                self._issue(ctx, path, node_type, f"锁血谓词目标未注册：{alias}")
                return None
            expr = f"hp_locked({target})"
            return self._negate_condition(expr) if predicate.get("Inverse") else expr
        if node_type == "RPG.GameCore.ByIsInElationTime":
            expr = "in_elation_time()"
            return self._negate_condition(expr) if predicate.get("Inverse") else expr
        if node_type == "RPG.GameCore.ByTurnOwnerActionPhaseEnd":
            expr = "turn_owner_action_phase_end()"
            return self._negate_condition(expr) if predicate.get("Inverse") else expr
        if node_type == "RPG.GameCore.ByTargetTeam":
            team = str(predicate.get("Team") or "")
            types = {"TeamDark": ("monster", "enemy"), "TeamLight": ("character", "summon")}.get(team)
            if not isinstance(target, str) or types is None:
                self._issue(ctx, path, node_type, f"队伍谓词目标/队伍未注册：{alias} / {team}")
                return None
            expr = " or ".join(f"actor_type_of({target}) == '{actor_type}'" for actor_type in types)
            return self._negate_condition(expr) if predicate.get("Inverse") else f"({expr})"
        translated = self._translate_longtail_predicate(predicate, ctx, path, node_type,
                                                        alias, target)
        if translated is not None:
            return translated or None   # "" = 已记拒因的失败分支
        reason = self._UNREGISTERED_PREDICATE_REASONS.get(node_type, "未注册条件谓词")
        self._issue(ctx, path, node_type or "<missing $type>", reason)
        return None

    #: 谓词长尾族逐型拒因（14_policy.md 任务节点长尾节）——未注册谓词 default 查表。
    _UNREGISTERED_PREDICATE_REASONS = {
        "RPG.GameCore.ByCompareStageType": "关卡类型语境运行时无载体（编译器不知关卡）",
        "RPG.GameCore.ByTargetListIntersects": "目标集交集的目标规格未注册",
        "RPG.GameCore.ByCompareAbilityProperty": "仅 CurrentHP/BaseSpeed/ActionDelay/SpecialSP 已收编；其他属性运行时载体待补",
        "RPG.GameCore.ByCompareParamString": "参数串比较语境未收编",
        "RPG.GameCore.ByCompareSomatoType": "体型（somato）体系未收编",
        "RPG.GameCore.ByCharacterSomatoWidthType": "体宽体系未收编",
        "RPG.GameCore.ByIsTurnActionEntity": "行动实体判定仅回合语境可翻——见语境拒因",
        "RPG.GameCore.ByDistance": "距离体系（站位域）未收编",
        "RPG.GameCore.ByCompareCustomValue": "CustomValue 数值比较语境未收编",
    }

    #: 当前技能类型词表（ByCurrentSkillType → 事件载荷 action_type）
    _ACTION_PAYLOAD_EVENTS = frozenset({
        "before_action", "on_action", "on_action_end", "before_take_damage", "after_being_hit", "on_hp_decrease"})
    _SKILL_TYPE_TO_ACTION = {"Ultra": "ultimate", "Ultimate": "ultimate",
                             "Skill": "skill", "BPSkill": "skill", "Elation": "elation_skill",
                             "Normal": "basic", "Attack": "basic"}

    def _translate_longtail_predicate(self, predicate: Dict[str, Any], ctx: _Context,
                                      path: str, node_type: str, alias: str,
                                      target: Optional[str]) -> Optional[str]:
        """谓词长尾族翻译（14_policy.md）：当前技能名/类型（action_type 载荷语境）、伤害
        属性（伤害事件语境）、持有弱点（has_weakness 宿主）、UniqueID 自身静态支。
        语境不符显式拒（谓词语境无对应事件载荷），不猜。"""
        if node_type == "RPG.GameCore.ByCurrentTurnState":
            states = [str(state) for state in predicate.get("TurnStates") or []]
            if not states or any(state not in {
                    "InsertAbilityActionPhase", "InsertUltraSkillExecuting", "ModifierPhase1Begin"}
                                 for state in states):
                self._issue(ctx, path, node_type, f"当前回合状态词表外：{states}")
                return ""
            expr = " or ".join(f"current_turn_state('{state}')" for state in states)
            return self._negate_condition(f"({expr})") if predicate.get("Inverse") else f"({expr})"
        if node_type == "RPG.GameCore.ByTurnOwnerHasActionInTurn":
            expr = "turn_owner_has_action_in_turn()"
            return self._negate_condition(expr) if predicate.get("Inverse") else expr
        if node_type == "RPG.GameCore.ByCurrentSkillName":
            if ctx.event not in self._ACTION_PAYLOAD_EVENTS:
                self._issue(ctx, path, node_type,
                            f"当前技能名谓词需 action_type 载荷语境（实得 {ctx.event}）")
                return ""
            raw_names = predicate.get("SkillNameList")
            if raw_names is None:
                names = [str(predicate.get("SkillName") or "")]
            elif isinstance(raw_names, list) and raw_names and all(
                    isinstance(name, str) and name for name in raw_names):
                names = list(raw_names)
            else:
                self._issue(ctx, path, node_type, "SkillNameList 须为非空字符串列表")
                return ""
            action_ids = []
            for trigger in names:
                skill = self.skills.get(trigger)
                if skill is None:
                    self._issue(ctx, path, node_type, f"技能名未绑定 TBGD 技能：{trigger!r}")
                    return ""
                action_ids.append(str(skill["skill_id"]))
            expr = " or ".join(f"$event.action_id == '{action_id}'" for action_id in action_ids)
            return f"({expr})" if raw_names is not None else expr
        if node_type == "RPG.GameCore.ByCurrentSkillType":
            if ctx.event not in self._ACTION_PAYLOAD_EVENTS:
                self._issue(ctx, path, node_type,
                            f"当前技能类型谓词需 action_type 载荷语境（实得 {ctx.event}）")
                return ""
            raw_skill_type = predicate.get("SkillType")
            skill_type = {"0": "Normal", "1": "Skill", "2": "Ultra", "3": "Servant"}.get(
                str(raw_skill_type) if raw_skill_type is not None else "0", raw_skill_type or "Normal")
            if skill_type == "Servant":
                source = "$event.actor" if ctx.event in {"before_action", "on_action", "on_action_end"} else "$event.source"
                return f"actor_type_of({source}) == 'summon'"
            mapped = self._SKILL_TYPE_TO_ACTION.get(skill_type)
            if mapped is None:
                self._issue(ctx, path, node_type,
                            f"技能类型词表外：{predicate.get('SkillType')!r}")
                return ""
            return f"$event.action_type == '{mapped}'"
        if node_type == "RPG.GameCore.ByIsTriggeredBlockDamage":
            if ctx.event != "after_being_hit" or target != "$self.actor_id":
                self._issue(ctx, path, node_type,
                            f"免伤屏障触发谓词需持有者受击后语境（实得 {ctx.event} / {alias}）")
                return ""
            expr = "$event.block_damage_triggered"
            return self._negate_condition(expr) if predicate.get("Inverse") else expr
        if node_type == "RPG.GameCore.ByIsIndirectDamage":
            if ctx.event not in {"after_being_hit", "before_take_damage"}:
                self._issue(ctx, path, node_type,
                            f"间接伤害谓词需伤害事件语境（实得 {ctx.event}）")
                return ""
            expr = "$event.is_indirect"
            return self._negate_condition(expr) if predicate.get("Inverse") else expr
        if node_type == "RPG.GameCore.ByCompareDamageTag":
            if ctx.event not in {"after_being_hit", "before_take_damage"}:
                self._issue(ctx, path, node_type,
                            f"伤害标签谓词需伤害事件语境（实得 {ctx.event}）")
                return ""
            tags = predicate.get("DamageTagList") or []
            if len(tags) != 1 or not isinstance(tags[0], dict) \
                    or tags[0].get("EnumIndex") != 3 \
                    or isinstance(tags[0].get("Value"), bool) \
                    or not isinstance(tags[0].get("Value"), int):
                self._issue(ctx, path, node_type, "仅支持单个 EnumIndex=3 的整数伤害标签")
                return ""
            expr = f"{tags[0]['Value']} in $event.damage_tags"
            return self._negate_condition(expr) if predicate.get("Inverse") else expr
        if node_type == "RPG.GameCore.ByCompareDamageCustomName":
            if ctx.event not in {"after_being_hit", "before_take_damage"}:
                self._issue(ctx, path, node_type,
                            f"伤害自定义名谓词需伤害事件语境（实得 {ctx.event}）")
                return ""
            raw_name = predicate.get("CustomName")
            name = raw_name.get("Value") if isinstance(raw_name, dict) else raw_name
            if not name:
                self._issue(ctx, path, node_type, "伤害自定义名不能为空")
                return ""
            expr = f"$event.damage_custom_name == {self._string_literal(str(name))}"
            return self._negate_condition(expr) if predicate.get("Inverse") else expr
        if node_type == "RPG.GameCore.ByIsSplitDamage":
            if ctx.event not in {"after_being_hit", "before_take_damage"}:
                self._issue(ctx, path, node_type,
                            f"均分伤害谓词需伤害事件语境（实得 {ctx.event}）")
                return ""
            expr = "$event.split != ''"
            return self._negate_condition(expr) if predicate.get("Inverse") else expr
        if node_type == "RPG.GameCore.ByIsDamageType":
            if ctx.event not in {"after_being_hit", "before_take_damage", "on_hp_decrease"}:
                self._issue(ctx, path, node_type,
                            f"伤害属性谓词需伤害事件语境（实得 {ctx.event}）")
                return ""
            if target is None:
                self._issue(ctx, path, node_type, f"伤害属性谓词目标未注册：{alias}")
                return ""
            elements = [_element(raw) for raw in predicate.get("DamageTypeList") or []]
            if not elements or any(not e for e in elements):
                self._issue(ctx, path, node_type, "伤害属性词表外")
                return ""
            checks = [f"$event.damage_type == '{e}'" for e in elements]
            return "(" + " or ".join(checks) + ")"
        if node_type == "RPG.GameCore.ByCheckCharacterFly":
            if target is None:
                self._issue(ctx, path, node_type, f"飞行谓词目标未注册：{alias}")
                return ""
            return "1 == 0"
        if node_type == "RPG.GameCore.ByCompareSpecialAvatarType":
            if target is None:
                self._issue(ctx, path, node_type, f"特殊 Avatar 类型谓词目标未注册：{alias}")
                return ""
            if predicate.get("CompareType") in {"TYPE_TRIAL", "TYPE_MISSION", "TYPE_PLOT"}:
                return "1 == 0"
            self._issue(ctx, path, node_type, f"未注册特殊 Avatar 类型：{predicate.get('CompareType')}")
            return ""
        if node_type == "RPG.GameCore.ByIsControlSkillDisable":
            if target is None:
                self._issue(ctx, path, node_type, f"控制技能禁用谓词目标未注册：{alias}")
                return ""
            return f"has_behavior_flag({target}, 'Charm')"
        if node_type == "RPG.GameCore.ByContainsParamFlag":
            if predicate.get("Flag") == "IsFakeAvatarAttack":
                return "1 == 0"
            self._issue(ctx, path, node_type, f"未注册 ParamFlag：{predicate.get('Flag')}")
            return ""
        if node_type == "RPG.GameCore.ByAttackType":
            if ctx.event not in {"after_being_hit", "before_take_damage"}:
                self._issue(ctx, path, node_type,
                            f"攻击类型谓词需伤害事件语境（实得 {ctx.event}）")
                return ""
            mapped_map = {"DOT": "dot", "Insert": "follow_up", "Pursued": "follow_up",
                          "Skill": "skill", "BPSkill": "skill", "ElationDamage": "elation_damage",
                          "Ultra": "ultimate", "Normal": "basic"}
            raw_types = [str(t) for t in predicate.get("AttackTypes") or []]
            mapped = [mapped_map.get(t) for t in raw_types]
            unknown = [t for t, m in zip(raw_types, mapped)
                       if m is None and t not in {"TrueDamage", "Servant", "Maze"}]
            if not raw_types or unknown:
                self._issue(ctx, path, node_type, f"攻击类型词表外：{unknown}")
                return ""
            checks = [("$event.damage_type == 'true'" if t == "TrueDamage"
                       else "(actor_type_of($event.source) == 'summon' or "
                            "summoner_of($event.source) != '')" if t == "Servant"
                       else "1 == 0" if t == "Maze"
                       else f"$event.action_type == '{m}'") for t, m in zip(raw_types, mapped)]
            return "(" + " or ".join(checks) + ")"
        if node_type == "RPG.GameCore.ByCompareStanceRatio":
            compare = self._number(predicate.get("CompareValue"), ctx, f"{path}/CompareValue")
            if target is None or compare != 0 or predicate.get("CompareType") != "Greater":
                self._issue(ctx, path, node_type, "韧性比例仅支持 Greater 0 的未清空边界")
                return ""
            expr = f"toughness_of({target}) > 0"
            return self._negate_condition(expr) if predicate.get("Inverse") else expr
        if node_type == "RPG.GameCore.ByTargetIsStanceWeak":
            attacker_alias = self._alias({"TargetType": predicate.get("AttackerType")})
            attacker = self._predicate_target(attacker_alias)
            if target is None or attacker is None:
                self._issue(ctx, path, node_type,
                            f"弱点谓词目标/攻击者未注册：{alias} / {attacker_alias}")
                return ""
            expr = f"has_weakness({target}, element_of({attacker}))"
            return self._negate_condition(expr) if predicate.get("Inverse") else expr
        if node_type == "RPG.GameCore.ByHasStanceWeak":
            if target is None:
                self._issue(ctx, path, node_type, f"弱点谓词目标未注册：{alias}")
                return ""
            element = _element((predicate.get("WeakType") or {}).get("DamageType")
                               if isinstance(predicate.get("WeakType"), dict)
                               else predicate.get("WeakType"))
            if not element:
                self._issue(ctx, path, node_type, "弱点元素词表外")
                return ""
            return f"has_weakness({target}, '{element}')"
        if node_type == "RPG.GameCore.ByCompareMonsterUniqueID":
            # UniqueID = 模板 ID // 10（决策卡 #30，映射经全词表实证）。
            # 自身静态支按同规则编译期求值；ParamEntity 等运行时目标走
            # monster_unique_id($it) 逐候选判定（实例 __ 后缀由函数归一化）。
            value = _fixed(predicate.get("TargetMonsterUniqueID"))
            if not _is_number(value):
                self._issue(ctx, path, node_type, "UniqueID 比较值必须是静态数值")
                return ""
            if target is None:
                self._issue(ctx, path, node_type, f"UniqueID 谓词目标未注册：{alias}")
                return ""
            if alias in {"", "Caster", "ModifierOwnerEntity"}:
                hit = self.enemy_id.isdigit() and int(self.enemy_id) // 10 == int(value)
                return "1 == 1" if hit else "1 == 0"
            expr = f"monster_unique_id({target}) == {int(value)}"
            return self._negate_condition(expr) if predicate.get("Inverse") else expr
        if node_type in {"RPG.GameCore.ByIsTurnOwnerEntity", "RPG.GameCore.ByIsTurnActionEntity"}:
            if target is None:
                self._issue(ctx, path, node_type, f"回合实体谓词目标未注册：{alias}")
                return ""
            # 全语境回合归属者（引擎跟踪当前回合 actor，不再限回合/行动事件）
            return f"turn_owner_of() == {target}"
        return None  # 未接管——走 _UNREGISTERED_PREDICATE_REASONS

    def _damage_only_records(self, tasks: Iterable[Dict[str, Any]], ctx: _Context,
                             path: str, stack: Tuple[str, ...]) -> Optional[List[Dict[str, Any]]]:
        """在隔离上下文中验证任务树是否仅含主动伤害，不污染正式效果/写入状态."""
        if ctx.condition != "true":
            return None
        probe = _Context(
            mode=ctx.mode, skill=ctx.skill, event=ctx.event, condition=ctx.condition,
            loop_depth=ctx.loop_depth, retarget=ctx.retarget,
            current_modifier=ctx.current_modifier, param_modifier=ctx.param_modifier,
            current_ability=ctx.current_ability,
            dynamic_writes=set(ctx.dynamic_writes),
            before_dying_stack=ctx.before_dying_stack,
            modifier_stack=ctx.modifier_stack, value_symbols=dict(ctx.value_symbols),
        )
        self._compile_tasks(tasks, probe, path, stack)
        if (probe.unsupported or probe.effects or probe.pre_effects or probe.hit_effects
                or probe.lifecycle_hooks or probe.summons or probe.retarget_damage
                or probe.conditional_damage
                or probe.dynamic_writes != ctx.dynamic_writes or not probe.damages):
            return None
        return probe.damages

    def _compile_probability_guards(self, task: Dict[str, Any], ctx: _Context,
                                    path: str) -> Optional[Tuple[str, str]]:
        """`ByRandomChance` 谓词 → (success 守卫, failed 守卫)；非该谓词或不可用返回 None.

        真实数据 109 节点全为静态 `Chance`（0-1）+ 无 Inverse；Chance 可动态（表达式）。
        守卫用 effect 级 condition 承载——hook 级快照发生在任何 effect 之前，概率分支
        必须落 effect 级（执行帧 §23.15）。"""
        predicate = task.get("Predicate") or {}
        if str(predicate.get("$type") or "") != "RPG.GameCore.ByRandomChance":
            return None
        raw_chance = predicate.get("Chance", predicate.get("CompareValue"))
        chance = self._value(raw_chance, ctx, f"{path}/Predicate/Chance")
        if chance is None:
            self._issue(ctx, path, str(predicate.get("$type")), "概率分支的 Chance 未注册")
            return None
        shown = f"({chance})" if isinstance(chance, str) else str(chance)
        key = self._stable_roll_key(f"{path}/Predicate/ByRandomChance")
        less = f"roll('{key}') < {shown}"
        no_less = f"roll('{key}') >= {shown}"
        if predicate.get("Inverse"):
            less, no_less = no_less, less
        self._add_live_effect(ctx, {
            "effect_type": "bind_roll", "roll_key": key}, "true")
        return less, no_less

    def _compile_live_branch(self, tasks: List[Dict[str, Any]], guard: str,
                             ctx: _Context, path: str, stack: Tuple[str, ...]) -> None:
        """帧感知分支编译：守卫落 effect 级活读（写后读/概率共用），伤害记录按分支
        条件重发为 deal_damage（同既有条件伤害口径，但条件走 effect 级）。"""
        previous = ctx.live_condition
        ctx.live_condition = self._and_condition(previous, guard)
        before = len(ctx.damages)
        self._compile_tasks(tasks, ctx, path, stack)
        if len(ctx.damages) != before:
            # 条件主伤同样转条件 deal_damage（决策卡 #33）——行动无无条件主伤时
            # 由条件效果承载伤害，不再拒。
            added = list(ctx.damages[before:])
            del ctx.damages[before:]
            for record in added:
                target = self._hook_target(record["alias"], ctx)
                if target is None:
                    self._issue(ctx, path, "ConditionalDamage",
                                f"条件附加段目标未注册：{record['alias']}")
                    continue
                self._add_live_effect(ctx, {
                    "effect_type": "deal_damage", "target": target,
                    "damage_type": record["element"],
                    "damage_custom_name": record["damage_custom_name"],
                    "scaling_hp" if record["formula"] == "ByMaxHP" else "scaling_atk": record["ratio"],
                    "toughness_dmg": (record["stance_value"] if record["stance_value"] is not None
                                      else float(ctx.skill.get("sp_hit_base") or 0)
                                      * (record["stance_ratio"] or 0)),
                }, "true")
        ctx.live_condition = previous

    def _compile_predicate_tasks(self, task: Dict[str, Any], ctx: _Context,
                                 path: str, stack: Tuple[str, ...]) -> None:
        if (self._presentation_only(task.get("SuccessTaskList") or [])
                and self._presentation_only(task.get("FailedTaskList") or [])):
            return
        if task.get("SuccessTaskList") == task.get("FailedTaskList"):
            shared = task.get("SuccessTaskList") or []
            shared_path = f"{path}/SharedTaskList"
            if ctx.condition == "true" and ctx.live_condition == "true":
                self._compile_tasks(shared, ctx, shared_path, stack)
            else:
                self._compile_live_branch(shared, "true", ctx, shared_path, stack)
            return
        static_branch = self._static_monster_predicate(task.get("Predicate") or {})
        if static_branch is False:
            self._compile_tasks(task.get("FailedTaskList") or [], ctx,
                                f"{path}/FailedTaskList", stack)
            return
        is_chance = str((task.get("Predicate") or {}).get("$type") or "") == \
            "RPG.GameCore.ByRandomChance"
        probability: Optional[Tuple[str, str]] = None
        if is_chance:
            probability = self._compile_probability_guards(task, ctx, path)
            if probability is None:
                return   # Chance 不可用已记 unsupported
        live = probability is not None or self._predicate_reads_written(
            task.get("Predicate") or {}, ctx)
        predicate = None
        if probability is not None:
            success_guard, failed_guard = probability
        else:
            predicate = self._predicate_expr(
                task.get("Predicate") or {}, ctx, f"{path}/Predicate",
                allow_written=live)
            if predicate is None:
                self._issue(ctx, path, str(task.get("$type")), "条件谓词或分支未完整支持")
                return
            success_guard, failed_guard = predicate, self._negate_condition(predicate)
        success = self._damage_only_records(
            task.get("SuccessTaskList") or [], ctx, f"{path}/SuccessTaskList", stack)
        failed = self._damage_only_records(
            task.get("FailedTaskList") or [], ctx, f"{path}/FailedTaskList", stack)
        if success is not None and success == failed:
            # 两支规范化伤害完全相同：条件与伤害无关，只在原位置结算一次。
            self._compile_tasks(task.get("SuccessTaskList") or [], ctx,
                                f"{path}/SharedDamage", stack)
            return
        if live:
            # 帧感知路径：守卫全落 effect 级活读，不动 hook 级 ctx.condition
            # （外层快照条件若存在仍叠加生效——_add_live_effect 正交互）。
            base_counts = dict(ctx.count_expressions)
            self._compile_live_branch(
                task.get("SuccessTaskList") or [], success_guard,
                ctx, f"{path}/SuccessTaskList", stack)
            ctx.count_expressions = dict(base_counts)
            self._compile_live_branch(
                task.get("FailedTaskList") or [], failed_guard,
                ctx, f"{path}/FailedTaskList", stack)
            ctx.count_expressions = base_counts
            return
        base = ctx.condition
        base_counts = dict(ctx.count_expressions)
        for branch, tasks in (("SuccessTaskList", task.get("SuccessTaskList") or []),
                              ("FailedTaskList", task.get("FailedTaskList") or [])):
            condition = predicate if branch == "SuccessTaskList" else self._negate_condition(predicate)
            ctx.condition = self._and_condition(base, condition)
            ctx.count_expressions = dict(base_counts)
            before = len(ctx.damages)
            self._compile_tasks(tasks, ctx, f"{path}/{branch}", stack)
            if len(ctx.damages) != before:
                added = list(ctx.damages[before:])
                del ctx.damages[before:]
                for record in added:
                    target = record.get("target_spec") or self._hook_target(record["alias"], ctx)
                    if target is None:
                        self._issue(ctx, f"{path}/{branch}", "ConditionalDamage",
                                    f"条件附加段目标未注册：{record['alias']}")
                        continue
                    self._add_effect(ctx, {
                        "effect_type": "deal_damage", "target": target,
                        "damage_type": record["element"],
                        "damage_custom_name": record["damage_custom_name"],
                        "scaling_hp" if record["formula"] == "ByMaxHP" else "scaling_atk": record["ratio"],
                        "toughness_dmg": (record["stance_value"] if record["stance_value"] is not None
                                          else float(ctx.skill.get("sp_hit_base") or 0)
                                          * (record["stance_ratio"] or 0)),
                    })
        ctx.condition = base
        ctx.count_expressions = base_counts

    @staticmethod
    def _string_literal(text: str) -> str:
        return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'

    def _any_target_expr(self, target: str, where: str) -> str:
        spec = self._string_literal(json.dumps(
            {"pool": target, "where": where},
            ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        return f"count_selected({spec}, \"true\") > 0"

    def _target_spec(self, raw: Any, ctx: _Context, path: str,
                     seen: Tuple[str, ...] = ()) -> Optional[Dict[str, Any]]:
        if not isinstance(raw, dict):
            self._issue(ctx, path, "TargetType", "目标规格不是对象")
            return None
        node_type = str(raw.get("$type") or "")
        if node_type == "RPG.GameCore.TargetAlias":
            alias = str(raw.get("Alias") or "")
            if alias in seen:
                self._issue(ctx, path, node_type, f"目标别名循环引用：{alias}")
                return None
            if alias in self.target_aliases:
                return self._target_spec(self.target_aliases[alias], ctx, path, seen + (alias,))
            if alias.endswith(".GetAliveOnly"):
                base = self._target_spec(
                    {"$type": "RPG.GameCore.TargetAlias", "Alias": alias[:-len(".GetAliveOnly")]},
                    ctx, path, seen)
                if base is not None:
                    base["include_dead"] = False
                return base
            if alias.endswith(".RemoveUnselectable"):
                base = self._target_spec(
                    {"$type": "RPG.GameCore.TargetAlias", "Alias": alias[:-len(".RemoveUnselectable")]},
                    ctx, path, seen)
                if base is None:
                    return None
                condition = "$it.enemy_targetable and $it.ally_targetable"
                if base.get("include_summons"):
                    return {"concat": [base], "where": condition}
                base["where"] = self._and_condition(str(base.get("where") or "true"), condition)
                return base
            if alias.endswith(".RemoveServant") and alias not in _INCLUSIVE_TEAM_TARGETS:
                base = self._target_spec(
                    {"$type": "RPG.GameCore.TargetAlias", "Alias": alias[:-len(".RemoveServant")]},
                    ctx, path, seen)
                if base is None:
                    return None
                condition = "not $it.summoner_id"
                if base.get("include_summons"):
                    return {"concat": [base], "where": condition}
                base["where"] = self._and_condition(str(base.get("where") or "true"), condition)
                return base
            if alias.endswith(".WithServant"):
                base = self._target_spec(
                    {"$type": "RPG.GameCore.TargetAlias", "Alias": alias[:-len(".WithServant")]},
                    ctx, path, seen)
                if base is not None:
                    base["include_summons"] = True
                return base
            if alias.endswith(".Shuffle"):
                base = self._target_spec(
                    {"$type": "RPG.GameCore.TargetAlias", "Alias": alias[:-len(".Shuffle")]},
                    ctx, path, seen)
                if base is not None:
                    base["mode"] = "shuffle"
                return base
            base_alias, select_marker, raw_position = alias.rpartition(".Select")
            if select_marker and raw_position.isdigit() and int(raw_position) >= 1:
                base = self._target_spec(
                    {"$type": "RPG.GameCore.TargetAlias", "Alias": base_alias}, ctx, path, seen)
                if base is None:
                    return None
                if base.get("mode", "deterministic") != "deterministic":
                    self._issue(ctx, path, node_type, "随机/洗牌后的 SelectN 顺序未收编")
                    return None
                base["index"] = int(raw_position) - 1
                return base
            if alias == "Elation_BE":
                return dict(_ELATION_BE_TARGET)
            if alias.startswith("PartEntity") and alias.removeprefix("PartEntity").isdigit():
                target = self._hook_target(alias, ctx)
                if isinstance(target, dict):
                    return target
                self._issue(ctx, path, node_type, f"{alias} 缺少配置的部位怪物 ID")
                return None
            if alias in {"ParamEntity", "ParamEntityList", "TemplateParamEntityList",
                         "ParamEntityActualOwner", "ParamEntity2", "ParamEntity.WithSummoner",
                         "Trailblazer"} \
                    or ("+" not in alias and " - " not in alias
                        and alias not in _INCLUSIVE_TEAM_TARGETS
                        and alias.endswith((".GetServant", ".GetSummoner", ".GetBattleEvent"))) \
                    or (" - " in alias and alias not in _INCLUSIVE_TEAM_TARGETS
                        and not alias.startswith("AllTeammate - MMonster_")):
                target = self._hook_target(alias, ctx)
                if isinstance(target, dict):
                    return target
                if target is not None:
                    return {"pool": target}
                self._issue(ctx, path, node_type, f"{alias} 缺少 Retarget/ParamTarget/事件语境")
                return None
            if alias in {"AttackTargetList", "ParamEntityAttackTargetList"} and ctx.event == "on_action_end":
                return {"pool": "$event.hit_targets"}
            if alias in {"SkillTargetEntityList", "ModifierOwnerSkillTargetEntityList"} \
                    and ctx.event in {"before_action", "on_action"}:
                return {"pool": "$event.targets"}
            composite = self._composite_battle_event_target(alias)
            if composite is not None:
                return composite
            pool = {
                "AllTeammate": "enemies", "AllDarkTeam": "enemies", "AllTeamMember": "enemies",
                "AllDarkTeamWithAllDarkTeamUnselectable": "enemies",
                "AllEnemy": "allies", "AllLightTeam": "allies", "AllLightTeamIgnoreServant": "allies",
                "AllLightTeam.RemoveServant": "allies", "TauntOrRandomEnemy": "enemy_targets",
                "TauntOrRandomEnemyWithoutServant": "enemy_targets",
                "TauntOrRandomEnemy.RemoveServant": "enemy_targets",
                "Caster": "self", "ModifierOwnerEntity": "self", "AbilityTargetAdjoinEntity": "allies",
                "AbilityTargetAndAdjoinEntity": "allies", "ParamEntityAdjoinEntity": "allies",
                "CasterAdjoinEntity": "enemies",
                "CasterLeftEntity": "enemies", "CasterRightEntity": "enemies",
                "AbilityTargetLeftEntity": "allies", "AbilityTargetRightEntity": "allies",
                "CasterSummonedMinions": "enemies", "ModifierOwnerSummonedMinions": "enemies",
                "LastSummonMonsters": "last_summons",
                "AbilityTargetEntity": "$event.target",
                "LevelEntity": "$level", "LightTeamEntity": "$light_team", "DarkTeamEntity": "$dark_team",
            }.get(alias, (_INCLUSIVE_TEAM_TARGETS.get(alias) or {}).get("pool"))
            if pool is None:
                concat = self._concat_alias(alias, ctx)
                if concat is not None:
                    return concat
                self._issue(ctx, path, node_type, f"目标别名未注册：{alias}")
                return None
            spec: Dict[str, Any] = {**_INCLUSIVE_TEAM_TARGETS.get(alias, {}), "pool": pool}
            if alias in {"TauntOrRandomEnemy", "TauntOrRandomEnemyWithoutServant",
                         "TauntOrRandomEnemy.RemoveServant"}:
                spec.update({"take": 1, "mode": "taunt_or_random"})
                if alias != "TauntOrRandomEnemy":
                    spec["where"] = "not $it.summoner_id"
            if alias in {"CasterSummonedMinions", "ModifierOwnerSummonedMinions"}:
                spec["where"] = "$it.summoner_id == $self.actor_id"
            elif alias == "AllDarkTeam - Caster":
                spec["where"] = "$it.actor_id != $self.actor_id"
            elif alias == "AllLightTeamIgnoreServant":
                spec["where"] = "actor_type_of($it) != 'summon'"
            elif alias == "AllLightTeam.RemoveServant":
                spec["where"] = "not $it.summoner_id"
            elif alias in {"AbilityTargetAdjoinEntity", "ParamEntityAdjoinEntity"}:
                spec["where"] = "is_adjacent($it, $event.target)"
            elif alias == "AbilityTargetAndAdjoinEntity":
                spec["where"] = (
                    "($it.actor_id == $event.target or is_adjacent($it, $event.target))")
            elif alias == "CasterAdjoinEntity":
                spec["where"] = "is_adjacent($it, $self.actor_id)"
            elif alias == "CasterLeftEntity":
                spec["where"] = "position_delta($it, $self.actor_id) == -1"
            elif alias == "CasterRightEntity":
                spec["where"] = "position_delta($it, $self.actor_id) == 1"
            elif alias == "AbilityTargetLeftEntity":
                spec["where"] = "position_delta($it, $event.target) == -1"
            elif alias == "AbilityTargetRightEntity":
                spec["where"] = "position_delta($it, $event.target) == 1"
            return spec
        if node_type == "RPG.GameCore.TargetFetchUniqueNameEntity":
            alias = self._alias({"TargetType": raw})
            if len(alias) == len("unique:"):
                self._issue(ctx, path, node_type, "UniqueName 为空")
                return None
            return {"pool": alias}
        if node_type == "RPG.GameCore.TargetCompute":
            if raw.get("ComputeType") != "Minus" or len(raw.get("Targets") or []) != 2:
                self._issue(ctx, path, node_type, "仅支持两个目标的 TargetCompute(Minus)")
                return None
            base = self._target_spec(raw["Targets"][0], ctx, f"{path}/Targets/0", seen)
            excluded = self._target_spec(raw["Targets"][1], ctx, f"{path}/Targets/1", seen)
            if base is None or excluded is None:
                return None
            serialized = self._string_literal(json.dumps(
                excluded, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
            base["where"] = self._and_condition(
                str(base.get("where", "true")), f"not target_in_selected({serialized}, $it)")
            return base
        if node_type == "RPG.GameCore.TargetConcat":
            rows = raw.get("Targets") or []
            if not rows:
                self._issue(ctx, path, node_type, "TargetConcat 缺少子目标")
                return None
            children = [self._target_spec(item, ctx, f"{path}/Targets/{index}", seen)
                        for index, item in enumerate(rows)]
            if any(child is None for child in children):
                return None
            return {"concat": children}
        if node_type == "RPG.GameCore.TargetQuery":
            if (not raw.get("TeamTypeMask") and not raw.get("EntityTypeMask")
                    and raw.get("AliveStateMask") == "Bit_Deathrattle"):
                return {"pool": "all", "include_dead": True, "where": "not actor_alive($it)"}
            if (raw.get("TeamTypeMask"), raw.get("EntityTypeMask"), raw.get("AliveStateMask")) == (
                    "TeamLight", "Avatar", "Mask_AliveOnly"):
                return {"pool": "allies",
                        "where": "actor_type_of($it) == 'character' and actor_alive($it)"}
            self._issue(ctx, path, node_type,
                        "TargetQuery 目前仅支持 TeamLight/Avatar/Mask_AliveOnly 或纯 Bit_Deathrattle")
            return None
        if node_type != "RPG.GameCore.TargetSequence":
            self._issue(ctx, path, node_type or "<missing $type>", "目标规格类型未注册")
            return None
        spec: Dict[str, Any] = {}
        has_base = False
        for index, item in enumerate(raw.get("Sequence") or []):
            item_type = str(item.get("$type") or "")
            if item_type in {"RPG.GameCore.TargetAlias", "RPG.GameCore.TargetConcat",
                             "RPG.GameCore.TargetSequence"}:
                if has_base:
                    self._issue(ctx, path, item_type, "TargetSequence 多基础别名尚未注册")
                    return None
                base = self._target_spec(item, ctx, f"{path}/Sequence/{index}", seen)
                if base is None:
                    return None
                spec = base
                has_base = True
            elif item_type == "RPG.GameCore.TargetFilterAliveState":
                mask = str(item.get("Mask") or "")
                if mask == "Mask_AliveOrLimbo":
                    continue
                if mask == "Bit_OnStage":
                    spec["where"] = self._and_condition(spec.get("where", "true"), "not $it.banished")
                elif mask == "Mask_AliveOnly":
                    spec["where"] = self._and_condition(spec.get("where", "true"), "actor_alive($it)")
                else:
                    self._issue(ctx, path, item_type, f"TargetFilterAliveState 掩码未注册：{mask}")
                    return None
            elif item_type == "RPG.GameCore.TargetFilter":
                previous_filter = ctx.in_target_filter
                ctx.in_target_filter = True
                try:
                    where = self._predicate_expr(item.get("Predicate") or {}, ctx,
                                                 f"{path}/Sequence/{index}/Predicate")
                finally:
                    ctx.in_target_filter = previous_filter
                if where is None:
                    return None
                spec["where"] = self._and_condition(spec.get("where", "true"), where)
            elif item_type == "RPG.GameCore.TargetSortByModifierValue":
                modifier_name = str(item.get("ModifierName") or "")
                if not modifier_name or item.get("ValueType") != "Layer":
                    self._issue(ctx, path, item_type, "TargetSortByModifierValue 仅支持 Layer")
                    return None
                spec["order_by"] = ("-" if item.get("HighestFirst") else "") + \
                    f"stacks($it.actor_id, '{modifier_name}')"
            elif item_type == "RPG.GameCore.TargetSortMonsterRank":
                spec["order_by"] = ("-" if item.get("HighestFirst") else "") + "monster_rank($it)"
            elif item_type == "RPG.GameCore.TargetShuffle":
                spec["pre_shuffle"] = True
            elif item_type == "RPG.GameCore.TargetSortByFormation":
                spec["order_by"] = "-formation" if item.get("HighestFirst") else "formation"
            elif item_type == "RPG.GameCore.TargetSortByActionOrder":
                spec["order_by"] = "action_delay_of($it.actor_id) / stat_of($it.actor_id, 'spd')"
            elif item_type == "RPG.GameCore.TargetIndex":
                if item.get("IndexType", "IndexStrict") != "IndexStrict":
                    self._issue(ctx, path, item_type, "TargetIndex 仅支持 IndexStrict")
                    return None
                index_value = self._number(item.get("IndexValue", 0), ctx,
                                           f"{path}/Sequence/{index}/IndexValue")
                if index_value is None or index_value < 0 or int(index_value) != index_value:
                    self._issue(ctx, path, item_type, "TargetIndex 需非负整数索引")
                    return None
                spec["index"] = int(index_value)
            elif item_type == "RPG.GameCore.TargetTake":
                count = self._number(item.get("Count"), ctx, f"{path}/Sequence/{index}/Count")
                if count is None or count < 1 or int(count) != count:
                    self._issue(ctx, path, item_type, "TargetTake 需要正整数")
                    return None
                spec["take"] = int(count)
            else:
                self._issue(ctx, path, item_type or "<missing $type>", "TargetSequence 子节点未注册")
                return None
        if not has_base:
            self._issue(ctx, path, node_type, "TargetSequence 缺基础别名")
            return None
        return spec

    def _count_expression(self, raw: Any, ctx: _Context, path: str,
                          extra_predicate: Optional[Dict[str, Any]] = None,
                          include_dead: bool = False) -> Optional[str]:
        spec = self._target_spec(raw, ctx, path)
        if spec is None:
            return None
        if extra_predicate is not None:
            where = self._predicate_expr(extra_predicate, ctx, f"{path}/Predicate")
            if where is None:
                return None
            spec["where"] = self._and_condition(spec.get("where", "true"), where)
        if include_dead:
            spec["include_dead"] = True
        where_text = str(spec.get("where", "true"))
        if (include_dead or "concat" in spec or "take" in spec
                or str(spec["pool"]).startswith("$event.")):
            def counting_spec(value: Any) -> Any:
                if isinstance(value, dict):
                    return {key: counting_spec(child) for key, child in value.items()
                            if key not in {"mode", "order_by"}}
                if isinstance(value, list):
                    return [counting_spec(child) for child in value]
                return value

            serialized = self._string_literal(json.dumps(
                counting_spec(spec), ensure_ascii=False, sort_keys=True))
            return f"count_selected({serialized}, \"true\")"
        pool = self._string_literal(str(spec["pool"]))
        where = self._string_literal(where_text)
        include_unselectable = (", 1" if self._alias({"TargetType": raw}) == "GridFight_AllBackEnd"
                                and spec.get("include_unselectable") else "")
        return f"count_selected({pool}, {where}{include_unselectable})"

    def _compile_remodifier(self, task: Dict[str, Any], ctx: _Context,
                            path: str, stack: Tuple[str, ...]) -> None:
        if set(task) - {"$type", "TargetType", "ModifierName", "TaskList", "FailedTaskList", "MaxNumber", "CasterFilter", "IncludeLimbo", "StatusTypeMask", "PredicateFilter"} \
                or task.get("StatusTypeMask") not in {None, "Buff"} \
                or (task.get("IncludeLimbo") and self._alias(task) not in {"Caster", "ModifierOwnerEntity"}):
            self._issue(ctx, path, str(task.get("$type")),
                        "Remodifier 的 PredicateFilter/非自身 IncludeLimbo/StatusTypeMask 未收编")
            return
        raw = task.get("ModifierName")
        name = (raw or {}).get("Value") if isinstance(raw, dict) else raw
        if not name:
            self._issue(ctx, path, str(task.get("$type")), "Remodifier 缺 ModifierName")
            return
        modifier_source = ""
        if "CasterFilter" in task:
            filter_alias = self._alias({"TargetType": task.get("CasterFilter")})
            if filter_alias in {"Caster", "ModifierOwnerEntity"}:
                modifier_source = "$self.actor_id"
            else:
                filter_target = self._hook_target(filter_alias, ctx)
                if not isinstance(filter_target, dict) and (
                        not isinstance(filter_target, str) or not filter_target.startswith("$event.")):
                    self._issue(ctx, path, str(task.get("$type")),
                                f"Remodifier 来源过滤目标未注册：{filter_alias}")
                    return
                modifier_source = filter_target
        definition = self.modifiers.get(str(name)) or {}
        modifier_id = self._modifier_id(
            str(name), definition, str(ctx.skill.get("skill_id") or self.enemy_id))
        modifier_filter = ""
        if task.get("StatusTypeMask") == "Buff":
            modifier_filter = f"modifier_kind($it, '{modifier_id}') == 'buff'"
        predicate = task.get("PredicateFilter")
        if predicate is not None:
            key = str(predicate.get("DynamicKey") or "")
            operator = self._compare_operator(predicate.get("CompareType"))
            value = self._value(predicate.get("CompareValue"), ctx,
                                f"{path}/PredicateFilter/CompareValue")
            if (predicate.get("$type") != "RPG.GameCore.ByCompareModifierCallBackDynamicValue"
                    or set(predicate) - {"$type", "DynamicKey", "CompareType", "CompareValue", "Inverse"}
                    or not key or operator is None or value is None):
                self._issue(ctx, path, str(task.get("$type")),
                            "Remodifier 仅收实例动态值 PredicateFilter 的已注册比较形态")
                return
            condition = (f"modifier_dynamic_of($it, '{modifier_id}', '{key}') "
                         f"{operator} {_format(_atom(value))}")
            if predicate.get("Inverse"):
                condition = self._negate_condition(condition)
            modifier_filter = (self._and_condition(modifier_filter, condition)
                               if modifier_filter else condition)
        self._compile_retarget(
            task, ctx, path, stack, modifier_id=modifier_id,
            modifier_source=modifier_source, modifier_filter=modifier_filter)

    def _compile_retarget_list(self, task: Dict[str, Any], ctx: _Context,
                               path: str, stack: Tuple[str, ...]) -> None:
        self._compile_retarget(task, ctx, path, stack)

    def _compile_retarget(self, task: Dict[str, Any], ctx: _Context,
                          path: str, stack: Tuple[str, ...], modifier_id: str = "",
                          modifier_source: str = "", modifier_filter: str = "") -> None:
        alias = self._alias(task)
        spec = self._target_spec(task.get("TargetType"), ctx, path)
        if spec is None:
            return
        number = self._value(task.get("MaxNumber"), ctx, f"{path}/MaxNumber") \
            if "MaxNumber" in task else None
        if number is not None:
            if _is_number(number):
                if number < 1 or int(number) != number:
                    self._issue(ctx, path, str(task.get("$type")), "Retarget 上限需要正整数")
                    return
                spec["take"] = int(number)
            else:
                spec["take"] = number
        # 非随机缺省 MaxNumber 取全部候选；ByRandom 缺省随机取 1。ConfigAI target_override 不介入。
        if task.get("ByRandom"):
            spec.setdefault("mode", "random")
            if "MaxNumber" not in task:
                spec["take"] = 1
        predicate = task.get("Predicate")
        if predicate:
            predicate_type = str(predicate.get("$type") or "")
            if predicate_type == "RPG.GameCore.ByIsPropertyValueMinOrMax":
                compare_alias = self._alias({"TargetType": predicate.get("CompareTargetType")})
                if (predicate.get("PropertyRatioType") != "HPRatio" or compare_alias != alias
                        or predicate.get("MinOrMax") not in {"Min", "Max"}):
                    self._issue(ctx, path, predicate_type, "Retarget 属性极值/比较池未注册")
                    return
                spec["order_by"] = (("-" if predicate["MinOrMax"] == "Max" else "")
                                    + "$it.hp / $it.max_hp")
            else:
                previous_filter = ctx.in_target_filter
                ctx.in_target_filter = True
                try:
                    where = self._predicate_expr(predicate, ctx, f"{path}/Predicate",
                                                 allow_written=True)
                finally:
                    ctx.in_target_filter = previous_filter
                if where is None:
                    self._issue(ctx, path, str(task.get("$type")), "Retarget 谓词未注册")
                    return
                if spec.get("where"):
                    spec["where"] = self._and_condition(spec["where"], where)
                else:
                    spec["where"] = where
        if modifier_id:
            condition = f"has_modifier($it, '{modifier_id}')"
            if isinstance(modifier_source, dict):
                serialized = self._string_literal(json.dumps(
                    modifier_source, ensure_ascii=False, sort_keys=True))
                condition = self._and_condition(
                    condition, f"target_in_selected({serialized}, "
                               f"modifier_source($it, '{modifier_id}'))")
            elif modifier_source:
                condition = f"has_modifier($it, '{modifier_id}', {modifier_source})"
            if modifier_filter:
                condition = self._and_condition(condition, modifier_filter)
            spec["where"] = self._and_condition(spec.get("where", "true"), condition)
        previous = ctx.retarget
        previous_param_modifier = ctx.param_modifier
        before = len(ctx.damages)
        ctx.retarget = spec
        if modifier_id:
            ctx.param_modifier = modifier_id
        self._compile_tasks(task.get("TaskList") or [], ctx, f"{path}/TaskList", stack)
        if len(ctx.damages) != before:
            self._issue(ctx, path, str(task.get("$type")), "Retarget 伤害目标尚未接入 Action")
            del ctx.damages[before:]
        ctx.retarget = previous
        ctx.param_modifier = previous_param_modifier
        failed_tasks = task.get("FailedTaskList") or []
        if not self._presentation_only(failed_tasks):
            where_text = str(spec.get("where", "true"))
            if "concat" in spec or str(spec["pool"]).startswith("$event.") or "$event." in where_text:
                def counting_spec(value: Any) -> Any:
                    if isinstance(value, dict):
                        return {key: counting_spec(child) for key, child in value.items()
                                if key not in {"take", "mode", "order_by"}}
                    if isinstance(value, list):
                        return [counting_spec(child) for child in value]
                    return value

                serialized = self._string_literal(json.dumps(
                    counting_spec(spec), ensure_ascii=False, sort_keys=True))
                empty = f"count_selected({serialized}, \"true\") == 0"
            else:
                pool = self._string_literal(str(spec["pool"]))
                where = self._string_literal(where_text)
                empty = f"count_selected({pool}, {where}) == 0"
            self._compile_live_branch(failed_tasks, empty, ctx, f"{path}/FailedTaskList", stack)

    def _compile_character_count(self, task: Dict[str, Any], ctx: _Context,
                                 path: str, stack: Tuple[str, ...]) -> None:
        key = str(task.get("DynamicKey") or "")
        expression = self._count_expression(
            task.get("ReadTargetType"), ctx, path, task.get("Predicate"))
        if not key or expression is None:
            self._issue(ctx, path, str(task.get("$type")), "人数动态键或目标规格未注册")
            return
        ctx.count_expressions[dynamic_value_hash(key)] = expression
        ctx.dynamic_writes.add(key)
        self._add_effect(ctx, {
            "effect_type": "set_dynamic_value", "target": "self",
            "dynamic_key": key, "amount": expression,
        })

    def _dynamic_write_is_dead(self, task: Dict[str, Any], key: str,
                               allowed_readers: Tuple[Dict[str, Any], ...] = (),
                               ignore_assignment_keys: bool = False) -> bool:
        key_hash = dynamic_value_hash(key)

        def walk(value: Any, assignment_key: bool = False) -> bool:
            if value is task or any(value is reader for reader in allowed_readers):
                return False
            if isinstance(value, dict):
                expr = value.get("PostfixExpr") or {}
                if key_hash in (expr.get("DynamicHashes") or []):
                    return True
                for field, child in value.items():
                    if not isinstance(child, str) or child != key:
                        continue
                    if (ignore_assignment_keys and field in {"DynamicKey", "Key"}
                            and value.get("$type") in {"RPG.GameCore.SetDynamicValue",
                                                       "RPG.GameCore.DefineDynamicValue"}):
                        continue
                    if assignment_key and field == "Value":
                        continue
                    return True
                assignment_parent = (ignore_assignment_keys and value.get("$type") in {
                    "RPG.GameCore.SetDynamicValue", "RPG.GameCore.DefineDynamicValue"})
                return any(walk(child, assignment_parent and field in {"DynamicKey", "Key"})
                           for field, child in value.items())
            if isinstance(value, list):
                return any(walk(child) for child in value)
            return False

        return not walk(self.sources)

    def _compile_delay_cumulate(self, task: Dict[str, Any], ctx: _Context,
                                path: str, stack: Tuple[str, ...]) -> None:
        key = str(task.get("DynamicKey") or "")
        if key and self._dynamic_write_is_dead(task, key):
            return
        self._issue(ctx, path, str(task.get("$type")), "DelayCumulate 语义未定；仅无引用 dead store 可消除")

    def _compile_stance_count_value(self, task: Dict[str, Any], ctx: _Context,
                                    path: str, stack: Tuple[str, ...]) -> None:
        key = str(task.get("DynamicKey") or "")
        target = self._hook_target(self._alias({"TargetType": task.get("ReadTargetType")}), ctx)
        if not key or target != "self":
            self._issue(ctx, path, str(task.get("$type")), "韧性条计数仅支持写入自身并读取自身")
            return
        ctx.dynamic_writes.add(key)
        self._add_effect(ctx, {
            "effect_type": "set_dynamic_value", "target": "self",
            "dynamic_key": key, "amount": "stance_count_of($self.actor_id)",
        })

    def _compile_dynamic_add(self, task: Dict[str, Any], ctx: _Context,
                             path: str, stack: Tuple[str, ...]) -> None:
        raw_key = task.get("Key") or {}
        key = raw_key.get("Value") if isinstance(raw_key, dict) else raw_key
        # AddValue/Min/Max 允许已解析表达式（动态槽经 PostfixExpr 符号层）——钳制用
        # min/max 内联组合，不加引擎原语；读旧值走 dynamic_of 四层读链（帧覆盖层
        # 优先），语义 = 帧内累积（#26 期 2/3，14_policy.md）。
        add = self._value(task.get("AddValue"), ctx, f"{path}/AddValue")
        minimum = self._value(task.get("Min"), ctx, f"{path}/Min") if "Min" in task else None
        maximum = self._value(task.get("Max"), ctx, f"{path}/Max") if "Max" in task else None
        target = self._hook_target(self._alias(task), ctx)
        if target == "summoner_of($self.actor_id)":
            target = dict(_INCLUSIVE_TEAM_TARGETS["CasterSummoner"])
        if target == "all_enemies" or target == "all_allies":
            target = {"pool": "enemies" if target == "all_enemies" else "allies"}
        target_kind = ("self" if target == "self" else "level" if target == "$level"
                       else "event" if target == "$event.target"
                       else "algebra" if isinstance(target, dict)
                       else "pseudo" if target == "$light_team" or target == "$dark_team"
                       else "")
        if (not key or add is None
                or ("Min" in task and minimum is None)
                or ("Max" in task and maximum is None)
                or not target_kind):
            self._issue(ctx, path, str(task.get("$type")), "动态加值键/增量/钳制/目标未注册")
            return
        value_ref = {"self": "$self", "level": "$level", "event": "$event.target",
                     "algebra": "$target"}.get(target_kind, target)
        expression = f"dynamic_of({value_ref}, '{key}') + ({add})"
        if minimum is not None:
            expression = f"max({expression}, ({minimum}))"
        if maximum is not None:
            expression = f"min({expression}, ({maximum}))"
        ctx.dynamic_writes.add(str(key))
        self._add_effect(ctx, {
            "effect_type": "set_dynamic_value", "target": target,
            "dynamic_key": str(key), "amount": expression,
        })

    @staticmethod
    def _param_change_value(ctx: _Context) -> str:
        if ctx.event in {"on_skill_point_change", "on_energy_change"}:
            return "$event.after - $event.before"
        return "-$event.amount" if ctx.event == "on_hp_decrease" else "$event.amount"

    def _compile_change_value(self, task: Dict[str, Any], ctx: _Context,
                              path: str, stack: Tuple[str, ...]) -> None:
        key = str(task.get("DynamicKey") or "")
        target = self._hook_target(self._alias(task) or "Caster", ctx)
        is_bp = task.get("$type") == "RPG.GameCore.SetDynamicValueByBPChange"
        valid_event = (ctx.event == "on_skill_point_change" if is_bp
                       else ctx.event in {"on_hp_decrease", "on_hp_increase", "on_energy_change"})
        if (is_bp and task.get("ValueType") != "RawDelta") \
                or (ctx.event == "on_energy_change" and task.get("ValueType") != "RawDelta") \
                or not key or target != "self" or not valid_event:
            self._issue(ctx, path, str(task.get("$type")),
                        "变化量写入需匹配 HP/RawDelta 战技点事件并写入自身")
            return
        ctx.dynamic_writes.add(key)
        self._add_effect(ctx, {
            "effect_type": "set_dynamic_value", "target": "self",
            "dynamic_key": key, "amount": self._param_change_value(ctx),
        })

    def _compile_max_bp(self, task: Dict[str, Any], ctx: _Context,
                        path: str, stack: Tuple[str, ...]) -> None:
        key = task.get("DynamicKey")
        if set(task) != {"$type", "DynamicKey"} or not isinstance(key, str) or not key:
            self._issue(ctx, path, str(task.get("$type")), "MaxBP 仅含 DynamicKey 的形态已注册")
            return
        ctx.dynamic_writes.add(key)
        self._add_effect(ctx, {
            "effect_type": "set_dynamic_value", "target": "self",
            "dynamic_key": key, "amount": "max_skill_points()",
        })

    def _compile_damage_data_value(self, task: Dict[str, Any], ctx: _Context,
                                   path: str, stack: Tuple[str, ...]) -> None:
        key = str(task.get("DynamicKey") or "")
        alias = self._alias({"TargetType": task.get("ReadTargetType")}) or "Caster"
        if not key or alias not in {"Caster", "ModifierOwnerEntity", "ParamEntity"} \
                or ctx.event not in {"before_take_damage", "after_being_hit"}:
            self._issue(ctx, path, str(task.get("$type")), "伤害数据写入需受击事件与自身/事件目标")
            return
        ctx.dynamic_writes.add(key)
        self._add_effect(ctx, {
            "effect_type": "set_dynamic_value", "target": "self",
            "dynamic_key": key, "amount": "$event.amount",
        })

    def _compile_dynamic_copying(self, task: Dict[str, Any], ctx: _Context,
                                 path: str, stack: Tuple[str, ...]) -> None:
        """SetDynamicValueByCopying：ToKey := 来源动态值。
        来源可为自身、关卡、事件目标、召唤者或目标代数；FromModifierName 读取
        该来源持有的 modifier 实例值。ParamModifier 只从 Remodifier 或 modifier 事件取当前实例。"""
        raw_to = task.get("ToDynamicKey") or {}
        raw_from = task.get("FromDynamicKey") or {}
        raw_from_modifier = task.get("FromModifierName")
        to_key = raw_to.get("Value") if isinstance(raw_to, dict) else raw_to
        from_key = raw_from.get("Value") if isinstance(raw_from, dict) else raw_from
        from_modifier = (raw_from_modifier.get("Value") if isinstance(raw_from_modifier, dict)
                         else raw_from_modifier)
        from_alias = str((task.get("FromTargetType") or {}).get("Alias") or "")
        to_alias = str((task.get("ToTargetType") or {}).get("Alias") or "")
        from_target = ("self" if from_alias in {"", "Caster", "ModifierOwnerEntity"}
                       else self._hook_target(from_alias, ctx))
        if from_target == "summoner_of($self.actor_id)":
            from_target = dict(_INCLUSIVE_TEAM_TARGETS["CasterSummoner"])
        amount_target = from_target if isinstance(from_target, dict) else None
        source = ("$self" if from_target == "self" else "$level" if from_target == "$level"
                  else "$event.target" if from_target == "$event.target"
                  else "$target" if amount_target is not None else "")
        if (not to_key or not from_key or not source
                or to_alias not in {"", "Caster", "ModifierOwnerEntity", "LevelEntity"}
                or (raw_from_modifier is not None and not from_modifier)):
            self._issue(ctx, path, str(task.get("$type")), "动态拷贝的源/目标键或来源未注册")
            return
        amount = f"dynamic_of({source}, '{from_key}')"
        if from_modifier == "ParamModifier":
            if ctx.param_modifier:
                modifier_ref = f"'{ctx.param_modifier}'"
            elif ctx.event in {"after_apply_modifier", "after_remove_modifier"}:
                modifier_ref = "$event.modifier_id"
            else:
                self._issue(ctx, path, str(task.get("$type")),
                            "ParamModifier 需要 Remodifier 或 modifier 事件作用域")
                return
            amount = f"modifier_dynamic_of({source}, {modifier_ref}, '{from_key}')"
        elif from_modifier:
            definition = self.modifiers.get(str(from_modifier)) or {}
            modifier_id = self._modifier_id(
                str(from_modifier), definition, str(ctx.skill.get("skill_id") or self.enemy_id))
            if modifier_id != from_modifier:
                self._issue(ctx, path, str(task.get("$type")), "跨技能改名 modifier 的动态值读取未收编")
                return
            amount = f"modifier_dynamic_of({source}, '{from_modifier}', '{from_key}')"
        ctx.dynamic_writes.add(str(to_key))
        effect = {
            "effect_type": "set_dynamic_value",
            "target": "$level" if to_alias == "LevelEntity" else "self",
            "dynamic_key": str(to_key), "amount": amount,
        }
        if amount_target is not None:
            effect["amount_target"] = amount_target
        self._add_effect(ctx, effect)

    def _compile_random_config(self, task: Dict[str, Any], ctx: _Context,
                               path: str, stack: Tuple[str, ...]) -> None:
        """RandomConfig 权重掷（无战斗级记忆字段时）→ bind_roll + 累计权重区间守卫.

        与上游 `rng.random()*Σ <= 累计` 同浮点序（bind 绑 u×Σ，守卫比累计值）；
        单独 RandomUnique 不代表跨局记忆：无 RandomCount/mask 时仍是单次抽取，
        唯一性无可观察效果；多抽与 mask 组合保持显式 unsupported。"""
        memory_fields = [field for field in ("RandomMaskKey", "RandomMaskTarget",
                                             "AutoResetRandomMask", "RandomCount")
                         if field in task]
        if "RandomUnique" in task and memory_fields:
            memory_fields.insert(0, "RandomUnique")
        if memory_fields:
            self._issue(ctx, path, str(task.get("$type")),
                        f"战斗级随机记忆字段尚未注册：{sorted(memory_fields)}")
            return
        task_list = task.get("TaskList") or []
        odds = task.get("OddsList") or []
        options = [option if isinstance(option, list) else [option]
                   for option in task_list]
        if all(self._presentation_only(option) for option in options):
            return   # 纯表现权重掷：无可观察效果，不消耗随机流
        if not options or len(options) != len(odds):
            self._issue(ctx, path, str(task.get("$type")), "RandomConfig 权重/任务表缺数或对齐")
            return
        weights: List[Any] = []
        for index, raw in enumerate(odds):
            weight = self._value(raw, ctx, f"{path}/OddsList/{index}")
            if weight is None:
                self._issue(ctx, path, str(task.get("$type")), "RandomConfig 权重需已注册数值或表达式")
                return
            weights.append(weight)
        if any(_is_number(weight) and weight < 0 for weight in weights):
            self._issue(ctx, path, str(task.get("$type")), "RandomConfig 权重须非负")
            return
        total: Any = 0.0
        for weight in weights:
            total = _binary("+", total, weight)
        if _is_number(total) and total <= 0:
            self._issue(ctx, path, str(task.get("$type")), "RandomConfig 权重和须为正")
            return
        key = self._stable_roll_key(f"{path}/RandomConfig")
        self._add_live_effect(ctx, {
            "effect_type": "bind_roll", "roll_key": key,
            "scale": total if _is_number(total) else _format(total)}, "true")
        previous = ctx.live_condition
        acc_before: Any = 0.0
        for index, weight in enumerate(weights):
            acc_after = _binary("+", acc_before, weight)  # 运行和累计——与上游同浮点序，不做减法
            upper = f"roll('{key}') <= {_format(acc_after)}"
            guard = upper if index == 0 else \
                f"roll('{key}') > {_format(acc_before)} and {upper}"
            ctx.live_condition = self._and_condition(previous, guard)
            self._compile_tasks(options[index], ctx, f"{path}/Odds/{index}", stack)
            acc_before = acc_after
        ctx.live_condition = previous

    #: 任务位未注册节点的逐型拒因（14_policy.md 任务节点长尾节）——default 分支查表，
    #: 不再只报"未注册任务节点"。键=上游 $type 全名，值=写清理由的拒因文本。
    _UNREGISTERED_TASK_REASONS = {
        "RPG.GameCore.SetIronTombProgress": "BOSS 进度语义未钉，不能按纯 UI 忽略",
        "RPG.GameCore.RemoveBpFeature": "特殊 BP 特性移除依赖 BP 体系，不能按普通 modifier 摘除近似",
            "RPG.GameCore.TaskConfig": "仅支持无字段空占位；出现配置字段仍需注册语义",
        "RPG.GameCore.MoveStageOnTargetForward": "Stage 前移与行动值推进的关系待实测，不按 ModifyActionDelay 近似",
        "RPG.GameCore.IncludeGlobalTaskListTemplate": "引用的全局 TaskListTemplate 不在当前数据闭包，不能凭空展开",
        "RPG.GameCore.DefineHPSharedGroup": "HP 共享组（连坐血条）未收编",
        "RPG.GameCore.SetDynamicValueByVariateType": "CurWaveIndex/TargetCharacterID/MaxMonsterPhase/HP ParamValue 已收编；其他变体语境待补",
        "RPG.GameCore.SetModifierValue": "Layer/LifeTime 的 Set/Add 已收编；其他 ModifyFunction/ValueType 未钉",
        "RPG.GameCore.SetEntityActionState": "普通实体 ActionState 已收编；GetBattleEvent 等非 Actor 目标未收编",
        "RPG.GameCore.ConstructBodyPart": "部位构造（PartName/MonsterID 组装）未收编",
        "RPG.GameCore.StackProperty": "任务位立即面板改写无 modifier 载体语义待钉（OnStack 回调内才是已收编形态）",
        "RPG.GameCore.StackStatusResistance": "任务位立即效果抵抗改写无载体语义待钉",
        "RPG.GameCore.StackWeakResistance": "任务位立即效果抵抗改写无载体语义待钉",
        "RPG.GameCore.SetActionDelayNearTarget": "近目标 AV 对齐改写未收编",
        "RPG.GameCore.AttachEntityVisible": "实体可见性开关（条件显隐机制）未收编",
        "RPG.GameCore.HideMonsterHUD": "HUD 显隐（纯表现遗漏件）",
    }

    _ALL_WEAKNESS = {"Physical", "Fire", "Ice", "Thunder", "Wind", "Quantum", "Imaginary"}

    def _stack_property_spec(self, task: Dict[str, Any], ctx: _Context,
                             path: str, symbols: Dict[int, Any]) -> List[Tuple[str, Any, bool]]:
        prop = str(task.get("Property") or "")
        if prop == "AllDamageTypeResistance":
            value = self._value(task.get("PropertyValue"), ctx, path, symbols)
            return [] if value is None else [
                (f"res_{_element(element)}", value, False)
                for element in sorted(self._ALL_WEAKNESS)]
        stat = {
            "AllDamageReduce": "dmg_dmg_reduction",
            "AllDamageTypeAddedRatio": "all_dmg",
            "AllDamageTypePenetrate": "res_pen",
            "AllDamageTypeTakenRatio": "vulnerability",
            "Monster_DamageTakenRatio": "vulnerability",
            "Level_FinalDamageAddedRatio": "dmg_final_dmg_boost",
            "AttackAddedRatio": "atk_pct", "AttackDelta": "atk",
            "PhysicalResistanceDelta": "res_physical", "FireResistanceDelta": "res_fire",
            "IceResistanceDelta": "res_ice", "ThunderResistanceDelta": "res_thunder",
            "WindResistanceDelta": "res_wind", "QuantumResistanceDelta": "res_quantum",
            "ImaginaryResistanceDelta": "res_imaginary",
            "CriticalDamageBase": "crit_dmg", "DefenceAddedRatio": "def_pct",
            "HPAddedRatio": "hp_pct", "HPDelta": "hp",
            "DirtyHPRatio": "recoverable_hp_reduction",
            "DirtyHPDelta": "recoverable_hp_delta",
            "SPRatioBase": "energy_regen", "SpeedAddedRatio": "spd_pct",
            "StatusResistanceBase": "effect_res", "BreakDamageAddedRatioBase": "break_effect",
            "SpeedDelta": "spd", "StanceBreakAddedRatio": "break_efficiency_boost",
            "StanceBreakTakenRatio": "toughness_taken",
        }.get(prop)
        override = {"BaseSpeed": "spd", "CriticalChanceBase": "crit_rate",
                    "SpeedOverride": "spd", "MaxStance": "max_toughness"}.get(prop)
        if prop == "StanceBreakResistance":
            value = self._value(task.get("PropertyValue"), ctx, path)
            if value is None:
                return []
            return [("toughness_taken", -value if _is_number(value) else f"-({value})", False)]
        if stat is None and override is None:
            self._issue(ctx, path, str(task.get("$type")), f"未注册属性：{prop}")
            return []
        value = self._value(task.get("PropertyValue"), ctx, path, symbols)
        return [] if value is None else [(override or stat, value, override is not None)]

    @staticmethod
    def _toughness_lock_id(skill_id: str) -> str:
        return f"ENEMY_{skill_id}_TOUGHNESS_LOCK"

    def _compile_reduce_stance_ratio(self, task: Dict[str, Any], ctx: _Context,
                                     path: str, stack: Tuple[str, ...]) -> None:
        target = self._task_target(task, ctx, path)
        ratio = self._value(task.get("ReduceValue"), ctx, f"{path}/ReduceValue")
        if target is None or ratio is None:
            self._issue(ctx, path, str(task.get("$type")), "比例削韧目标或比例未注册")
            return
        namespace = "$self" if target == "self" else "$target"
        self._add_effect(ctx, {
            "effect_type": "reduce_toughness", "target": target,
            "amount": f"base_stat_of({namespace}.actor_id, 'max_toughness') * ({ratio})",
        })

    def _compile_damage_stance(self, task: Dict[str, Any], ctx: _Context,
                               path: str, stack: Tuple[str, ...]) -> None:
        """DamageStance（ForceStanceDamage=true）→ reduce_toughness（14_policy.md 长尾节）.

        DefenderTargetType=被削韧者；StanceValue=削韧量（表达式通道）。StanceDamageType
        属性与 Force=false 的削韧减免交互引擎无载体——Force=false 显式拒，属性照算为已知近似。"""
        if not task.get("ForceStanceDamage"):
            self._issue(ctx, path, str(task.get("$type")),
                        "ForceStanceDamage=false 的削韧减免交互未收编（只收 Force=true）")
            return
        target = self._hook_target(self._alias({"TargetType": task.get("DefenderTargetType")}), ctx)
        value = self._value(task.get("StanceValue"), ctx, f"{path}/StanceValue")
        if target is None or value is None:
            self._issue(ctx, path, str(task.get("$type")), "削韧目标或削韧量未注册")
            return
        self._add_effect(ctx, {"effect_type": "reduce_toughness", "target": target,
                               "amount": value})

    def _compile_add_weakness(self, task: Dict[str, Any], ctx: _Context,
                              path: str, stack: Tuple[str, ...]) -> None:
        """AddWeakness → 永久弱点植入 modifier（weakness_add 引擎消费点在案：有效弱点并集）."""
        element = _element(task.get("DamageType"))
        target = self._hook_target(self._alias(task), ctx)
        if not element or target is None:
            self._issue(ctx, path, str(task.get("$type")), "弱点元素或目标未注册")
            return
        skill_id = str(ctx.skill.get("skill_id") or self.enemy_id)
        self._add_effect(ctx, {
            "effect_type": "apply_modifier", "target": target,
            "modifier": {
                "modifier_id": f"ENEMY_{skill_id}_WEAKNESS_{element.upper()}",
                "name": f"Weakness {element}",
                "modifier_type": "debuff", "duration": 0, "dispellable": False,
                "weakness_add": [element],
            },
        })

    def _compile_lock_stance(self, task: Dict[str, Any], ctx: _Context,
                             path: str, stack: Tuple[str, ...]) -> None:
        ratio = self._number(task.get("StanceValueRatio"), ctx, f"{path}/StanceValueRatio")
        if ratio is None:
            return
        if ratio not in {0, 1}:
            self._issue(ctx, path, str(task.get("$type")),
                        "锁韧仅支持 StanceValueRatio=0 或满值恢复 1")
            return
        target = self._hook_target(self._alias(task) or "ModifierOwnerEntity", ctx)
        if target is None:
            self._issue(ctx, path, str(task.get("$type")), "锁韧目标未注册")
            return
        if ratio == 1:
            self._add_effect(ctx, {"effect_type": "reset_stance", "target": target})
        skill_id = str(ctx.skill.get("skill_id") or self.enemy_id)
        self._add_effect(ctx, {
            "effect_type": "apply_modifier", "target": target,
            "modifier": {
                "modifier_id": self._toughness_lock_id(skill_id),
                "name": "Toughness Lock", "modifier_type": "buff",
                "duration": 0, "max_stack": 1, "stack_mode": "replace",
                "dispellable": False, "toughness_lock": True,
            },
        })

    def _compile_stance_vulnerable(self, task: Dict[str, Any], ctx: _Context,
                                   path: str, stack: Tuple[str, ...]) -> None:
        target = self._hook_target(self._alias(task) or "Caster", ctx)
        if target is None:
            self._issue(ctx, path, str(task.get("$type")), "韧性易伤目标未注册")
            return
        skill_id = str(ctx.skill.get("skill_id") or self.enemy_id)
        lock_id = self._toughness_lock_id(skill_id)
        if task.get("IsVulnerable", True):
            self._add_effect(ctx, {
                "effect_type": "remove_modifier", "target": target,
                "modifier_id": lock_id, "reason": "stance_vulnerable",
            })
        else:
            self._add_effect(ctx, {
                "effect_type": "apply_modifier", "target": target,
                "modifier": {
                    "modifier_id": lock_id, "name": "Toughness Lock", "modifier_type": "buff",
                    "duration": 0, "max_stack": 1, "stack_mode": "replace",
                    "dispellable": False, "toughness_lock": True,
                },
            })

    def _compile_trigger_stance_countdown(self, task: Dict[str, Any], ctx: _Context,
                                          path: str, stack: Tuple[str, ...]) -> None:
        target = self._task_target(task, ctx, path)
        if target is None:
            self._issue(ctx, path, str(task.get("$type")), "倒计时事件目标未注册")
            return
        self._add_effect(ctx, {
            "effect_type": "trigger_stance_countdown", "target": target,
            "ignore_mute_break": bool(task.get("IgnoreMuteBreak", False)),
        })

    def _compile_trigger_break(self, task: Dict[str, Any], ctx: _Context,
                               path: str, stack: Tuple[str, ...]) -> None:
        if set(task) - {"$type", "TargetType", "IgnoreMuteBreak"}:
            self._issue(ctx, path, str(task.get("$type")), "强制击破含未注册字段")
            return
        target = self._task_target(task, ctx, path)
        if target is None:
            self._issue(ctx, path, str(task.get("$type")), "强制击破目标未注册")
            return
        self._add_effect(ctx, {
            "effect_type": "trigger_break", "target": target,
            "damage_type": "$event.element" if ctx.event == "on_break" else "physical",
            "ignore_mute_break": bool(task.get("IgnoreMuteBreak", False)),
        })

    def _compile_set_stance_count(self, task: Dict[str, Any], ctx: _Context,
                                  path: str, stack: Tuple[str, ...]) -> None:
        extra = set(task) - {"$type", "TargetType"}
        if extra:
            self._issue(ctx, path, str(task.get("$type")),
                        f"韧性条数重置/增减形态未收编：{sorted(extra)}")

    def _weakness_list(self, task: Dict[str, Any], field: str) -> List[str]:
        values = [str(value) for value in task.get(field) or []]
        return sorted(self._ALL_WEAKNESS) if values == ["AllType"] else values

    def _compile_stack_weakness_task(self, task: Dict[str, Any], ctx: _Context,
                                     path: str, stack: Tuple[str, ...]) -> None:
        """任务位 StackWeakness：全七 Protected 沿用全韧性锁，部分元素逐件记录保护；
        缺省 OPType 覆写，Attach 追加，Secret 仅记录显示状态。"""
        target = self._hook_target(self._alias(task), ctx)
        weak_list = self._weakness_list(task, "WeakList")
        if task.get("OPType") == "Protected":
            if target is None or not weak_list or set(weak_list) - self._ALL_WEAKNESS:
                self._issue(ctx, path, str(task.get("$type")), "Protected 目标或元素未注册")
                return
            skill_id = str(ctx.skill.get("skill_id") or self.enemy_id)
            if set(weak_list) == self._ALL_WEAKNESS:
                specs = [{"id": self._toughness_lock_id(skill_id), "toughness_lock": True}]
            else:
                specs = [{"id": f"ENEMY_{skill_id}_PROTECTED_{element.upper()}",
                          "protected_weakness": [_element(element)]}
                         for element in weak_list]
            for spec in specs:
                modifier_id = spec.pop("id")
                self._add_effect(ctx, {
                    "effect_type": "apply_modifier", "target": target,
                    "modifier": {"modifier_id": modifier_id, "name": "Weakness Protection",
                                 "modifier_type": "buff", "duration": 0, "dispellable": False,
                                 "max_stack": 1, "stack_mode": "replace", **spec},
                })
            return
        secret_list = self._weakness_list(task, "SecretList")
        if target is None or set(weak_list) - self._ALL_WEAKNESS \
                or set(secret_list) - self._ALL_WEAKNESS:
            self._issue(ctx, path, str(task.get("$type")), "WeakList/SecretList 目标或元素未注册")
            return
        if task.get("OPType") == "Attach" and weak_list:
            for element in weak_list:
                proxy = {"TargetType": task.get("TargetType"), "DamageType": element}
                self._compile_add_weakness(proxy, ctx, path, stack)
            return
        if task.get("OPType") is None:
            skill_id = str(ctx.skill.get("skill_id") or self.enemy_id)
            self._add_effect(ctx, {
                "effect_type": "apply_modifier", "target": target,
                "modifier": {
                    "modifier_id": f"ENEMY_{skill_id}_WEAKNESS_OVERRIDE",
                    "name": "Weakness Override", "modifier_type": "debuff",
                    "duration": 0, "dispellable": False, "max_stack": 1,
                    "stack_mode": "replace",
                    "weakness_override": [_element(element) for element in weak_list],
                    **({"secret_weakness": [_element(element) for element in secret_list]}
                       if secret_list else {}),
                },
            })
            return
        self._issue(ctx, path, str(task.get("$type")),
                    f"任务位 StackWeakness 形态未收编：OPType={task.get('OPType')!r} "
                    f"WeakList={weak_list!r}")

    def _compile_clear_weakness(self, task: Dict[str, Any], ctx: _Context,
                                path: str, stack: Tuple[str, ...]) -> None:
        """Protected 按元素解除；全七同时摘除既有全韧性锁件。"""
        target = self._hook_target(self._alias(task), ctx)
        weak_list = set(self._weakness_list(task, "WeakList"))
        if task.get("OPType") == "Secret":
            if not weak_list or weak_list - self._ALL_WEAKNESS or target is None:
                self._issue(ctx, path, str(task.get("$type")), "Secret 清除目标或元素未注册")
                return
            self._add_effect(ctx, {
                "effect_type": "clear_secret_weakness", "target": target,
                "weak_list": sorted(_element(element) for element in weak_list),
            })
            return
        if task.get("OPType") == "Attach":
            if not weak_list or weak_list - self._ALL_WEAKNESS or target is None:
                self._issue(ctx, path, str(task.get("$type")), "Attach 清除目标或元素未注册")
                return
            self._add_effect(ctx, {
                "effect_type": "clear_attached_weakness", "target": target,
                "weak_list": sorted(_element(element) for element in weak_list),
            })
            return
        if (task.get("OPType", "Protected") != "Protected" or not weak_list
                or weak_list - self._ALL_WEAKNESS or target is None):
            self._issue(ctx, path, str(task.get("$type")), "Protected 清除目标或元素未注册")
            return
        self._add_effect(ctx, {
            "effect_type": "clear_protected_weakness", "target": target,
            "weak_list": sorted(_element(element) for element in weak_list),
        })
        if weak_list == self._ALL_WEAKNESS:
            skill_id = str(ctx.skill.get("skill_id") or self.enemy_id)
            self._add_effect(ctx, {
                "effect_type": "remove_modifier", "target": target,
                "modifier_id": self._toughness_lock_id(skill_id), "reason": "weakness_clear",
            })

    def _compile_change_config_param(self, task: Dict[str, Any], ctx: _Context,
                                     path: str, stack: Tuple[str, ...]) -> None:
        # HUD/模型/动画/碰撞/受击反应等级均为表现配置，不进入数值模拟。
        return

    def _compile_boss_hp_stance_change(self, task: Dict[str, Any], ctx: _Context,
                                       path: str, stack: Tuple[str, ...]) -> None:
        if task.get("ChangeType") != "Heal" or "ChangeTime" not in task:
            self._issue(ctx, path, str(task.get("$type")), "仅支持 Boss 血条 Heal 演出时长")

    def _compile_battle_play_video(self, task: Dict[str, Any], ctx: _Context,
                                   path: str, stack: Tuple[str, ...]) -> None:
        callback_fields = ("OnBeginPlay", "OnEndPlay", "OnFinish")
        if all(self._presentation_only(task.get(field) or []) for field in callback_fields):
            ctx.handled.append(str(task.get("$type")))
        else:
            self._issue(ctx, path, str(task.get("$type")), "视频播放回调含机制任务")

    def _compile_add_buff_perform(self, task: Dict[str, Any], ctx: _Context,
                                  path: str, stack: Tuple[str, ...]) -> None:
        if set(task) - {"$type", "TargetType", "TaskList", "AddPerformTime"}:
            self._issue(ctx, path, str(task.get("$type")), "Buff 表现节点含未注册字段")
        elif not self._presentation_only(task.get("TaskList") or []):
            self._issue(ctx, path, str(task.get("$type")), "Buff 表现容器含机制任务")
        else:
            ctx.handled.append(str(task.get("$type")))

    def _compile_perform_delay_execute(self, task: Dict[str, Any], ctx: _Context,
                                       path: str, stack: Tuple[str, ...]) -> None:
        """PerformDelayExecute：纯表现内容忽略（语料 88 节点全表现——Perform 时点
        模型/特效对齐）；机制内容显式拒（延迟执行时机未收编）。"""
        tasks = task.get("PerformTaskList") or []
        if self._presentation_only(tasks):
            ctx.handled.append(str(task.get("$type")))
            return
        self._issue(ctx, path, str(task.get("$type")),
                    "Perform 时点延迟执行（机制内容）时机未收编")

    def _compile_variate(self, task: Dict[str, Any], ctx: _Context,
                         path: str, stack: Tuple[str, ...]) -> None:
        variate = str(task.get("VariateType") or "")
        raw_key = task.get("DynamicKey") or task.get("Key") or {}
        key = raw_key.get("Value") if isinstance(raw_key, dict) else raw_key
        write_alias = self._alias({"TargetType": task.get("WriteTargetType")}) or "Caster"
        write_target = self._hook_target(write_alias, ctx)
        allowed = {"self", "$level", "summoner_of($self.actor_id)", "summoner_of($it)"}
        minion_pool = {"pool": "enemies", "where": "$it.summoner_id == $self.actor_id"}
        target_ok = (isinstance(write_target, str) and write_target in allowed) \
            or write_target == minion_pool
        if not key or not target_ok:
            self._issue(ctx, path, str(task.get("$type")),
                        f"VariateType 动态键/写入目标未注册：{key} / {write_alias}")
            return
        effect = {"effect_type": "set_dynamic_value", "target": write_target,
                  "dynamic_key": str(key)}
        if variate == "CurWaveIndex":
            effect["amount"] = "wave_index()"
        elif variate == "MaxMonsterPhase":
            maximum = self.config.get("MaxMonsterPhase")
            if not isinstance(maximum, (int, float)) or int(maximum) < 1:
                phases = []
                containers = [*self.abilities.values(), *self.modifiers.values(),
                              *self.global_templates.values()]

                def collect_phase(value: Any) -> None:
                    if isinstance(value, dict):
                        phase = value.get("PhaseNum")
                        if (value.get("$type") == "RPG.GameCore.SetMonsterPhase"
                                and _is_number(phase) and int(phase) >= 1):
                            phases.append(int(phase))
                        for child in value.values():
                            collect_phase(child)
                    elif isinstance(value, list):
                        for child in value:
                            collect_phase(child)

                collect_phase(containers)
                maximum = max(phases, default=0)
            if not isinstance(maximum, (int, float)) or int(maximum) < 1:
                self._issue(ctx, path, str(task.get("$type")),
                            "MaxMonsterPhase 配置及闭包显式阶段写入均缺失")
                return
            effect["amount"] = int(maximum)
        elif variate == "TargetCharacterID":
            read_alias = self._alias({"TargetType": task.get("ReadTargetType")})
            ref = {"Caster": "$self.actor_id", "ModifierOwnerEntity": "$self.actor_id",
                   "AbilityTargetEntity": "$event.target", "ParamEntity": "$target",
                   "CasterSummoner": "summoner_of($self.actor_id)",
                   "ModifierOwnerSummoner": "summoner_of($self.actor_id)"}.get(read_alias)
            if read_alias == "ParamEntity":
                if ctx.retarget is None:
                    ref = None
                else:
                    effect["amount_target"] = dict(ctx.retarget)
            if ref is None:
                self._issue(ctx, path, str(task.get("$type")),
                            f"TargetCharacterID 读取目标未注册：{read_alias}")
                return
            effect["amount"] = f"character_id({ref})"
        elif variate == "ParamValue" and ctx.event in {
                "on_hp_decrease", "on_hp_increase", "on_skill_point_change"}:
            effect["amount"] = self._param_change_value(ctx)
        else:
            self._issue(ctx, path, str(task.get("$type")),
                        f"VariateType 未收编：{variate}")
            return
        ctx.dynamic_writes.add(str(key))
        self._add_effect(ctx, effect)

    def _compile_set_modifier_value(self, task: Dict[str, Any], ctx: _Context,
                                    path: str, stack: Tuple[str, ...]) -> None:
        value_type = str(task.get("ValueType") or "Layer")
        operation = str(task.get("ModifyFunction") or "Set")
        if operation not in {"Add", "Set"} or value_type not in {"Layer", "LifeTime"}:
            self._issue(ctx, path, str(task.get("$type")),
                        f"SetModifierValue 形式未注册：{task.get('ModifyFunction')} / {value_type}")
            return
        raw = task.get("ModifierName") or {}
        name = (raw.get("Value") if isinstance(raw, dict) else raw) or ctx.current_modifier
        target = self._hook_target(self._alias(task) or "Caster", ctx)
        if not name or target is None:
            self._issue(ctx, path, str(task.get("$type")), "SetModifierValue 的 modifier 或目标未注册")
            return
        definition = self.modifiers.get(str(name)) or {}
        modifier_id = self._modifier_id(
            str(name), definition, str(ctx.skill.get("skill_id") or self.enemy_id))
        raw_value = task.get("Value") if "Value" in task else (
            {"IsDynamic": False, "FixedValue": {"Value": 1}} if operation == "Add" else None)
        value = self._value(raw_value, ctx, f"{path}/Value")
        if value is None:
            self._issue(ctx, path, str(task.get("$type")), "SetModifierValue 数值未注册")
            return
        target_expr = "$self.actor_id" if target == "self" else target
        if value_type == "LifeTime":
            delta = value if operation == "Add" else \
                f"({value}) - modifier_duration({target_expr}, '{modifier_id}')"
            self._add_effect(ctx, {
                "effect_type": "adjust_duration", "target": target, "modifier_id": modifier_id,
                "delta": delta,
            })
        else:
            delta = value if operation == "Add" else \
                f"({value}) - stacks({target_expr}, '{modifier_id}')"
            self._add_effect(ctx, {
                "effect_type": "adjust_stacks", "target": target,
                "modifier_id": modifier_id, "delta": delta,
            })

    def _compile_define_dynamic(self, task: Dict[str, Any], ctx: _Context,
                                path: str, stack: Tuple[str, ...]) -> None:
        raw_key = task.get("DynamicKey") or task.get("Key") or {}
        key = raw_key.get("Value") if isinstance(raw_key, dict) else raw_key
        alias = self._alias(task)
        if not alias and task.get("$type") in {"RPG.GameCore.SetDynamicValue",
                                               "RPG.GameCore.DefineDynamicValue"}:
            # 上游省略 TargetType 的动态写由施放者持有；ConfigAI 也从自身读取该键。
            alias = "Caster"
        target = self._hook_target(alias, ctx)
        raw_value = task["ResetValue"] if "ResetValue" in task else task.get("Value")
        # 自指/被写键的哈希读取经 _value 的 dynamic_name_symbols 统一回落活读
        # （与 ConfigAI 解释器同口径：Define/Set 均为绝对写，ResetValue/Value 皆写）。
        issue_count = len(ctx.unsupported)
        value = self._value(raw_value, ctx, f"{path}/Value") if raw_value is not None else 0
        # 动态值按任意 actor_id 持久化；允许已注册实体/目标代数，不接受未知裸别名。
        allowed = {"self", "$level", "all_enemies", "all_allies", "$light_team", "$dark_team",
                   "$event.target", "$event.actor", "$event.targets", "$event.hit_targets",
                   "summoner_of($self.actor_id)", "summoner_of($it)"}
        target_ok = isinstance(target, dict) or (isinstance(target, str) and target in allowed)
        if not key or value is None or not target_ok:
            if (key and value is None and target == "self" and isinstance(raw_value, dict)
                    and raw_value.get("IsDynamic") and self._dynamic_write_is_dead(
                        task, str(key), ignore_assignment_keys=True)):
                del ctx.unsupported[issue_count:]
                return
            self._issue(ctx, path, str(task.get("$type")), "动态键/值/自指目标未注册")
            return
        ctx.dynamic_writes.add(str(key))
        self._add_effect(ctx, {
            "effect_type": "set_dynamic_value", "target": target,
            "dynamic_key": str(key), "amount": value,
        })

    def _compile_battle_target_progress(self, task: Dict[str, Any], ctx: _Context,
                                        path: str, stack: Tuple[str, ...]) -> None:
        battle_target_id = self._number(task.get("BattleTargetID"), ctx, f"{path}/BattleTargetID")
        value = self._value(task.get("ModifyValue"), ctx, f"{path}/ModifyValue")
        if (battle_target_id is None or battle_target_id <= 0
                or not float(battle_target_id).is_integer() or value is None):
            self._issue(ctx, path, str(task.get("$type")),
                        "关卡目标 ID 需为正整数，ModifyValue 需为已注册数值或表达式")
            return
        key = f"_battle_target_progress:{int(battle_target_id)}"
        ctx.dynamic_writes.add(key)
        self._add_effect(ctx, {
            "effect_type": "set_dynamic_value", "target": "$level",
            "dynamic_key": key,
            "amount": f"dynamic_of($level, '{key}') + ({value})",
        })

    def _compile_battle_target_param(self, task: Dict[str, Any], ctx: _Context,
                                     path: str, stack: Tuple[str, ...]) -> None:
        key = str(task.get("DynamicKey") or "")
        try:
            battle_target_id = int(task.get("BattleTargetID"))
        except (TypeError, ValueError):
            battle_target_id = -1
        params = self.sources.get("battle_target_params")
        if params is None:
            from hsr_nous.pipeline.enemies.loader import get_battle_target_param
            try:
                value = get_battle_target_param(battle_target_id)
            except (FileNotFoundError, TypeError, ValueError):
                value = None
        else:
            value = params.get(battle_target_id, params.get(str(battle_target_id)))
        if not key or battle_target_id < 0 or not _is_number(value):
            self._issue(ctx, path, str(task.get("$type")),
                        "BattleTargetConfig 缺失或 BattleTargetID/TargetParam/DynamicKey 未注册")
            return
        ctx.dynamic_writes.add(key)
        self._add_effect(ctx, {
            "effect_type": "set_dynamic_value", "target": "self",
            "dynamic_key": key, "amount": value,
        })

    def _compile_obfuscated_property_value(self, task: Dict[str, Any], ctx: _Context,
                                           path: str, stack: Tuple[str, ...]) -> None:
        if set(task) - {"$type", "FHLJGDGMMHK", "OLPAJJAEEHH", "IMOPHAJMIFO"}:
            self._issue(ctx, path, str(task.get("$type")), "混淆属性读取含未注册字段")
            return
        self._compile_property_value({
            "$type": "RPG.GameCore.SetDynamicValueByProperty",
            "DynamicKey": task.get("FHLJGDGMMHK"),
            "ReadTargetType": task.get("OLPAJJAEEHH"),
            "Value": task.get("IMOPHAJMIFO", "MaxHP"),
        }, ctx, path, stack)

    def _compile_stack_property_task(self, task: Dict[str, Any], ctx: _Context,
                                     path: str, stack: Tuple[str, ...]) -> None:
        if task.get("Property") != "RallyHP":
            self._issue(ctx, path, str(task.get("$type")),
                        "任务位立即面板改写无 modifier 载体语义待钉（OnStack 回调内才是已收编形态）")
            return
        value = self._value(task.get("PropertyValue"), ctx, f"{path}/PropertyValue")
        target = self._task_target(task, ctx, path)
        if value is None or target is None:
            self._issue(ctx, path, str(task.get("$type")), "RallyHP 数值或目标未注册")
            return
        self._add_effect(ctx, {
            "effect_type": "gain_resource", "resource_id": "rally_hp", "amount": value,
            "target": target,
        })

    def _compile_property_value(self, task: Dict[str, Any], ctx: _Context,
                                path: str, stack: Tuple[str, ...]) -> None:
        key = str(task.get("DynamicKey") or "")
        alias = self._alias({"TargetType": task.get("ReadTargetType")})
        ref = {"Caster": "$self.actor_id", "ModifierOwnerEntity": "$self.actor_id",
               "AbilityTargetEntity": "$event.target", "ParamEntity": "$target",
               "ModifierOwnerSummoner": "summoner_of($self.actor_id)",
               "CasterSummoner": "summoner_of($self.actor_id)",
               "LightTeamEntity": "$light_team", "DarkTeamEntity": "$dark_team"}.get(alias)
        if alias.startswith("unique:") and len(alias) > len("unique:"):
            ref = f"unique_target({alias[len('unique:'):]!r})"
        if alias == "ParamEntity2" and ctx.event == "after_being_hit":
            ref = "$event.source"
        if alias == "SnapshotPropertyEntity" and ctx.event == "on_apply":
            ref = "$event.source"
        if alias == "ParamEntity" and ctx.retarget is None:
            ref = "$event.target" if ctx.event in {
                "on_hp_decrease", "on_hp_increase", "before_take_damage", "after_being_hit",
            } else None
        amount_target = dict(ctx.retarget) if alias == "ParamEntity" and ctx.retarget is not None else None
        stat = {
            "MaxHP": ("max_hp_of", ""),
            "MaxStance": ("base_stat_of", "max_toughness"),
            "CurrentStance": ("toughness_of", ""),
            "CurrentHP": ("hp_of", ""),
            "NegativeHP": ("hp_of", ""),
            "RallyHP": ("resource_of", "rally_hp"),
            "CurrentSP": ("energy_of", ""),
            "MaxSP": ("max_energy_of", ""),
            "CurrentSpecialSP": ("special_sp_of", ""),
            "MaxSpecialSP": ("max_special_sp_of", ""),
            "Shield": ("shield_of", ""),
            "DirtyHPRatio": ("stat_of", "recoverable_hp_reduction"),
            "Attack": ("stat_of", "atk"),
            "Defence": ("stat_of", "def_"),
            "Speed": ("stat_of", "spd"),
            "BaseAttack": ("base_stat_of", "atk"),
            "BaseSpeed": ("base_stat_of", "spd"),
            "ActionDelay": ("action_delay_of", ""),
        }.get(task.get("Value"))
        if ref is None and stat is not None:
            dynamic_target = self._hook_target(alias, ctx)
            if isinstance(dynamic_target, dict):
                ref = "$target"
                amount_target = dynamic_target
        if not key or ref is None or stat is None:
            self._issue(ctx, path, str(task.get("$type")),
                        f"属性动态键/读取目标/属性未注册：{key} / {alias} / {task.get('Value')}")
            return
        function, stat_name = stat
        expression = (f"max(0, -hp_of({ref}))" if task.get("Value") == "NegativeHP"
                      else f"{function}({ref})" if not stat_name
                      else f"{function}({ref}, '{stat_name}')")
        ctx.dynamic_writes.add(key)
        effect = {
            "effect_type": "set_dynamic_value", "target": "self",
            "dynamic_key": key, "amount": expression,
        }
        if amount_target is not None:
            effect["amount_target"] = amount_target
        self._add_effect(ctx, effect)

    def _compile_modifier_value(self, task: Dict[str, Any], ctx: _Context,
                                path: str, stack: Tuple[str, ...]) -> None:
        key = str(task.get("DynamicKey") or "")
        raw_target = task.get("ReadTargetType")
        alias = self._alias({"TargetType": raw_target}) if raw_target is not None \
            else "ModifierOwnerEntity"
        ref = {"Caster": "$self.actor_id", "ModifierOwnerEntity": "$self.actor_id",
               "ParamEntity": "$target", "CasterSummoner": "summoner_of($self.actor_id)",
               "LightTeamEntity": "$light_team", "DarkTeamEntity": "$dark_team",
               "ModifierOwnerEntity.GetSummoner": "summoner_of($self.actor_id)"}.get(alias)
        amount_target = dict(ctx.retarget) if alias == "ParamEntity" and ctx.retarget is not None else None
        event_ref = {
            "before_action": "$event.actor", "on_action": "$event.actor", "on_action_end": "$event.actor",
            "actor_enter": "$event.actor", "actor_exit": "$event.actor",
            "after_being_hit": "$event.target", "after_apply_modifier": "$event.target",
            "before_take_damage": "$event.target",
            "after_remove_modifier": "$event.target", "on_hp_decrease": "$event.target",
            "on_hp_increase": "$event.target", "on_kill": "$event.target",
            "monster_phase_changed": "$event.actor", "battle_event_create": "$event.actor",
            "modifier_custom_event": "$event.target",
        }.get(ctx.event)
        if ctx.mode == "action" and ctx.event == "on_action":
            event_ref = "$event.target"
        if alias == "ParamEntity" and ctx.retarget is None:
            ref = event_ref
        elif alias == "ParamEntitySummoner" and event_ref is not None:
            ref = f"summoner_of({event_ref})"
        if ref is None:
            dynamic_target = self._hook_target(alias, ctx)
            if isinstance(dynamic_target, dict):
                ref = "$target"
                amount_target = dynamic_target
        name = str(task.get("ModifierName") or ctx.current_modifier or "")
        definition = self.modifiers.get(name) or {}
        skill_id = str(ctx.skill.get("skill_id") or self.enemy_id)
        modifier_id = self._modifier_id(name, definition, skill_id) if name else ""
        multiplier = self._value(task.get("Multiplier", 1), ctx, f"{path}/Multiplier")
        value_type = task.get("ValueType", "Count")
        if value_type not in {"Count", "Layer", "LifeTime", "MaxLayer", "CurrentShield"} \
                or not key or ref is None or not modifier_id:
            self._issue(ctx, path, str(task.get("$type")),
                        "仅支持已绑定 modifier 的 Count/Layer/LifeTime/MaxLayer/CurrentShield 读取与已注册目标")
            return
        trigger = str(ctx.skill.get("trigger_key") or "")
        entry = str((self.config_skills.get(trigger) or {}).get("EntryAbility") or "")
        if ("STAT_DOT" in set(definition.get("BehaviorFlagList") or [])
                and not self._ability_adds_modifier(entry, name)):
            self._issue(ctx, path, str(task.get("$type")), "跨技能 DoT 数值读取未能绑定来源技能")
            return
        if multiplier is None:
            return
        reader = {"Count": "has_modifier", "Layer": "stacks", "LifeTime": "modifier_duration",
                  "MaxLayer": "modifier_max_stacks", "CurrentShield": "shield_of"}[value_type]
        expression = _format(_binary(
            "*", _atom(f"{reader}({ref}, '{modifier_id}')"), _atom(multiplier)))
        ctx.dynamic_writes.add(key)
        effect = {
            "effect_type": "set_dynamic_value", "target": "self",
            "dynamic_key": key, "amount": expression,
        }
        if amount_target is not None:
            effect["amount_target"] = amount_target
        self._add_effect(ctx, effect)

    def _compile_hp_ratio_dynamic(self, task: Dict[str, Any], ctx: _Context,
                                  path: str, stack: Tuple[str, ...]) -> None:
        key = str(task.get("DynamicKey") or "")
        alias = self._alias({"TargetType": task.get("ReadTargetType")})
        ref = {"Caster": "$self.actor_id", "ModifierOwnerEntity": "$self.actor_id",
               "AbilityTargetEntity": "$event.target"}.get(alias)
        amount_target = None
        if alias == "ParamEntity":
            if ctx.retarget is not None:
                ref = "$target"
                amount_target = dict(ctx.retarget)
            elif ctx.event in {"on_hp_decrease", "on_hp_increase"}:
                ref = "$event.target"
        raw_target = task.get("ReadTargetType")
        if ref is None and isinstance(raw_target, dict) and (
                alias in self.target_aliases or raw_target.get("$type") in {
                    "RPG.GameCore.TargetSequence", "RPG.GameCore.TargetCompute"}):
            amount_target = self._target_spec(raw_target, ctx, f"{path}/ReadTargetType")
            if amount_target is not None:
                ref = "$target"
        if not key or ref is None:
            self._issue(ctx, path, str(task.get("$type")),
                        f"HP 比例动态键/读取目标未注册：{key} / {alias}")
            return
        ctx.dynamic_writes.add(key)
        effect = {
            "effect_type": "set_dynamic_value", "target": "self",
            "dynamic_key": key, "amount": f"hp_of({ref}) / max_hp_of({ref})",
        }
        if amount_target is not None:
            effect["amount_target"] = amount_target
        self._add_effect(ctx, effect)

    def _compile_skill_max_hit_split_count(self, task: Dict[str, Any], ctx: _Context,
                                           path: str, stack: Tuple[str, ...]) -> None:
        key = task.get("DynamicKey")
        alias = self._alias({"TargetType": task.get("ReadTargetType")})
        if (not isinstance(key, str) or not key or alias != "ParamEntity2"
                or ctx.event != "after_being_hit"
                or set(task) - {"$type", "DynamicKey", "ReadTargetType"}):
            self._issue(ctx, path, str(task.get("$type")),
                        "技能总段数仅支持 after_being_hit 的 ParamEntity2 读取与自身写入")
            return
        ctx.dynamic_writes.add(key)
        self._add_effect(ctx, {
            "effect_type": "set_dynamic_value", "target": "self",
            "dynamic_key": key, "amount": "$event.max_hit_split_count",
        })

    def _compile_formation_index(self, task: Dict[str, Any], ctx: _Context,
                                 path: str, stack: Tuple[str, ...]) -> None:
        key = str(task.get("DynamicKey") or "")
        alias = self._alias({"TargetType": task.get("ReadTargetType")})
        ref = {"Caster": "$self.actor_id", "ModifierOwnerEntity": "$self.actor_id"}.get(alias)
        amount_target = None
        if alias == "ParamEntity" and ctx.retarget is not None:
            ref = "$target"
            amount_target = dict(ctx.retarget)
        if not key or ref is None:
            self._issue(ctx, path, str(task.get("$type")), "编队索引仅支持自身或 Retarget 的 ParamEntity")
            return
        effect = {"effect_type": "set_dynamic_value", "target": "self", "dynamic_key": key,
                  "amount": f"position_of({ref}, 'dark')"}
        if amount_target is not None:
            effect["amount_target"] = amount_target
        ctx.dynamic_writes.add(key)
        self._add_effect(ctx, effect)

    def _scan_skill_param_triggers(self) -> set[str]:
        triggers: set[str] = set()

        def walk(value: Any) -> None:
            if isinstance(value, dict):
                info = value.get("ReadInfo")
                if isinstance(info, dict) and info.get("Type") == "SkillParam" and info.get("TriggerKey"):
                    triggers.add(str(info["TriggerKey"]))
                for child in value.values():
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)

        walk(self.sources)
        return triggers

    def _scan_config_ai_references(self) -> set[str]:
        references: set[str] = set()

        def walk(value: Any) -> None:
            if isinstance(value, dict):
                for child in value.values():
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)
            elif isinstance(value, str):
                references.add(value)

        walk(self.sources.get("config_ai"))
        return references

    def _scan_dynamic_keys(self) -> Tuple[set[str], set[str]]:
        """收集 Ability/Modifier/全局 TaskListTemplate/ConfigAI 的动态键及 Set/Define 写入键."""
        all_keys: set[str] = set()
        written_keys: set[str] = set()
        containers = [*self.abilities.values(), *self.modifiers.values(),
                      *self.global_templates.values(), self.sources.get("config_ai")]

        def walk(value: Any) -> None:
            if isinstance(value, dict):
                node_type = str(value.get("$type") or "")
                for field in ("DynamicKey", "Key", "ToDynamicKey", "FromDynamicKey"):
                    raw = value.get(field)
                    candidate = raw.get("Value") if isinstance(raw, dict) else raw
                    if candidate is not None and str(candidate):
                        all_keys.add(str(candidate))
                        if field != "FromDynamicKey" and node_type.startswith((
                                "RPG.GameCore.SetDynamicValue", "RPG.GameCore.DefineDynamicValue")):
                            written_keys.add(str(candidate))
                for child in value.values():
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)

        for container in containers:
            walk(container)
        return all_keys, written_keys

    def _scan_modifier_dynamic_keys(self) -> Dict[str, set[str]]:
        out: Dict[str, set[str]] = {}

        def walk(value: Any) -> None:
            if isinstance(value, dict):
                if value.get("$type") == "RPG.GameCore.AddModifier":
                    raw = value.get("ModifierName")
                    name = raw.get("Value") if isinstance(raw, dict) else raw
                    keys = set((value.get("DynamicValues") or {}).keys())
                    if name and keys:
                        out.setdefault(str(name), set()).update(str(key) for key in keys)
                for child in value.values():
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)

        walk(self.sources)
        return out

    def _custom_value_is_readonly(self, name: str) -> bool:
        return name not in self.written_dynamic_keys

    def _switch_value(self, raw: Any, ctx: _Context, path: str) -> Optional[Tuple[str, Any]]:
        """Switch 解析：("static", 值) = 生成期唯一选支（SkillParam 符号/只读 CustomValue/
        静态数值）；("live", 键名) = 被写动态键或生成期可见写入的可变 CustomValue——
        由 `_compile_switch` 翻活读（dynamic_of 条件守卫）；不可用记 unsupported 返 None。"""
        if not isinstance(raw, dict) or not raw.get("IsDynamic"):
            value = self._number(raw, ctx, path)
            return ("static", value) if value is not None else None
        expr = raw.get("PostfixExpr") or {}
        hashes = expr.get("DynamicHashes") or []
        if expr.get("OpCodes") != "AQAR" or expr.get("FixedValues") or len(hashes) != 1:
            self._issue(ctx, path, "SwitchCaseByDynamicValue", "Switch 只支持 AQAR 单动态值")
            return None
        try:
            key_hash = int(hashes[0])
        except (TypeError, ValueError):
            self._issue(ctx, path, "SwitchCaseByDynamicValue", "Switch 哈希无效")
            return None
        matches = [(name, value) for name, value in self.custom_values.items()
                   if dynamic_value_hash(str(name)) == key_hash]
        hash_names = {name for name in self.dynamic_keys
                      if dynamic_value_hash(str(name)) == key_hash}
        if (len(matches) > 1 or len(hash_names) > 1
                or (matches and key_hash in self.dynamic_symbols)
                or (matches and any(name != matches[0][0] for name in hash_names))):
            self._issue(ctx, path, "SwitchCaseByDynamicValue", "动态键/CustomValue 哈希命名空间冲突")
            return None
        if key_hash in self.dynamic_symbols:
            value = self.dynamic_symbols[key_hash]
            if not _is_number(value):
                self._issue(ctx, path, "SwitchCaseByDynamicValue", "运行时 Switch 尚未注册")
                return None
            return ("static", value)
        if not matches and key_hash in ctx.value_symbols:
            value = ctx.value_symbols[key_hash]
            if isinstance(value, str) and value:
                return ("expression", value)
            if not _is_number(value):
                self._issue(ctx, path, "SwitchCaseByDynamicValue", "运行时 Switch 尚未注册")
                return None
            return ("static", value)
        if not matches and len(hash_names) == 1:
            return ("live", self._validated_switch_key(ctx, path, str(next(iter(hash_names)))))
        if not matches:
            self._issue(ctx, path, "SwitchCaseByDynamicValue", "CustomValue 哈希缺失或冲突")
            return None
        name, value = matches[0]
        if not self._custom_value_is_readonly(name):
            if name in self.dynamic_keys:
                return ("live", self._validated_switch_key(ctx, path, str(name)))
            self._issue(ctx, path, "SwitchCaseByDynamicValue",
                        f"可变 CustomValue 的运行时 Switch 尚未注册：{name}")
            return None
        value = value or 0
        if not _is_number(value):
            self._issue(ctx, path, "SwitchCaseByDynamicValue", f"CustomValue 非数值：{name}")
            return None
        return ("static", value)

    @staticmethod
    def _validated_switch_key(ctx: _Context, path: str, name: str) -> Optional[str]:
        if any(ch in name for ch in "'\"\\"):
            AbilityCompiler._issue(ctx, path, "SwitchCaseByDynamicValue",
                                   f"活读 Switch 键名非法：{name!r}")
            return None
        return name

    def _compile_switch(self, task: Dict[str, Any], ctx: _Context,
                        path: str, stack: Tuple[str, ...]) -> None:
        resolved = self._switch_value(task.get("Switch"), ctx, f"{path}/Switch")
        cases: List[Tuple[float, List[Dict[str, Any]]]] = []
        seen = set()
        for index, row in enumerate(task.get("CaseTaskList") or []):
            case_value = self._number(row.get("Case"), ctx, f"{path}/CaseTaskList/{index}/Case")
            if case_value is None:
                self._issue(ctx, path, "SwitchCaseByDynamicValue", "Case 必须是静态数值")
                return
            if case_value in seen:
                self._issue(ctx, path, "SwitchCaseByDynamicValue", f"Case 值重复：{case_value}")
                return
            seen.add(case_value)
            cases.append((case_value, row.get("TaskList") or []))
        if resolved is not None and resolved[0] == "static":
            selected = next((tasks for value, tasks in cases if value == resolved[1]),
                            task.get("DefaultTaskList") or [])
            self._compile_tasks(selected, ctx, f"{path}/Selected", stack)
            return
        if resolved is None or resolved[1] is None:
            return   # Switch 不可用已记 unsupported
        # 活读翻译：各 Case 编译为 effect 级条件守卫，读取动态键或已注册模板表达式；
        # DefaultTaskList 守卫为
        # 全部 Case 值不等。
        key_name = resolved[1]
        switch_expression = (f"dynamic_of($self, '{key_name}')" if resolved[0] == "live"
                             else f"({key_name})")
        default_tasks = task.get("DefaultTaskList") or []
        if not cases and not default_tasks:
            return
        previous = ctx.live_condition
        for case_value, tasks in cases:
            ctx.live_condition = self._and_condition(
                previous, f"{switch_expression} == {case_value}")
            self._compile_tasks(tasks, ctx, f"{path}/Case/{case_value}", stack)
        if default_tasks:
            unmatched = " and ".join(
                f"{switch_expression} != {case_value}"
                for case_value, _tasks in cases)
            ctx.live_condition = (self._and_condition(previous, unmatched)
                                  if unmatched else previous)
            self._compile_tasks(default_tasks, ctx, f"{path}/Default", stack)
        ctx.live_condition = previous

    def _compile_switch_cases(self, task: Dict[str, Any], ctx: _Context,
                              path: str, stack: Tuple[str, ...]) -> None:
        if task.get("WithBreak") is not False \
                or not self._presentation_only(task.get("DefaultTask") or []):
            self._issue(ctx, path, str(task.get("$type")),
                        "仅支持 WithBreak=false 且无机制默认分支的谓词列表")
            return
        for index, row in enumerate(task.get("TaskList") or []):
            self._compile_predicate_tasks(row, ctx, f"{path}/TaskList/{index}", stack)

    def _compile_switch_damage_type(self, task: Dict[str, Any], ctx: _Context,
                                    path: str, stack: Tuple[str, ...]) -> None:
        branches = [row.get("TaskList") or [] for row in task.get("CaseTaskList") or []]
        branches.append(task.get("DefaultTaskList") or [])
        if all(self._presentation_only(branch) for branch in branches):
            return
        source = task.get("Source") or {}
        read_target = self._hook_target(
            self._alias({"TargetType": source.get("ReadTargetType")}), ctx)
        if (source.get("SourceType") != "ReadTargetType"
                or str(source.get("DamageType") or "AllType") != "AllType"
                or read_target is None):
            self._issue(ctx, path, str(task.get("$type")), "攻击属性 Switch 来源未注册")
            return
        previous = ctx.live_condition
        seen = set()
        for index, row in enumerate(task.get("CaseTaskList") or []):
            element = _element(row.get("Case"))
            if element not in ELEMENTS or element in seen:
                self._issue(ctx, f"{path}/CaseTaskList/{index}", str(task.get("$type")),
                            f"攻击属性 Case 非法或重复：{row.get('Case')!r}")
                continue
            seen.add(element)
            ctx.live_condition = self._and_condition(previous, f"$event.damage_type == '{element}'")
            self._compile_tasks(row.get("TaskList") or [], ctx,
                                f"{path}/Case/{element}", stack)
        default_tasks = task.get("DefaultTaskList") or []
        if default_tasks:
            unmatched = " and ".join(f"$event.damage_type != '{element}'" for element in seen)
            ctx.live_condition = self._and_condition(previous, unmatched) if unmatched else previous
            self._compile_tasks(default_tasks, ctx, f"{path}/Default", stack)
        ctx.live_condition = previous

    def _compile_monster_view_phase(self, task: Dict[str, Any], ctx: _Context,
                                    path: str, stack: Tuple[str, ...]) -> None:
        if task.get("PhaseType") != "Form":
            self._issue(ctx, path, str(task.get("$type")),
                        f"ViewPhase 类型未注册：{task.get('PhaseType')}")
            return
        phase = self._number(task.get("PhaseNum"), ctx, f"{path}/PhaseNum")
        target = self._hook_target(self._alias(task), ctx)
        if phase is None or phase < 1 or int(phase) != phase or target != "self":
            self._issue(ctx, path, str(task.get("$type")), "ViewPhase 需自身正整数 Form 阶段")
            return
        ctx.dynamic_writes.add("current_phase")
        self._add_effect(ctx, {
            "effect_type": "set_dynamic_value", "target": target,
            "dynamic_key": "current_phase", "amount": int(phase),
        })

    def _compile_empty_phase_override(self, task: Dict[str, Any], ctx: _Context,
                                      path: str, stack: Tuple[str, ...]) -> None:
        if set(task) != {"$type"}:
            self._issue(ctx, path, str(task.get("$type")),
                        "阶段 OverrideConfig 仅支持无参数的表现/空间覆写")

    def _compile_monster_phase(self, task: Dict[str, Any], ctx: _Context,
                               path: str, stack: Tuple[str, ...]) -> None:
        mode = task.get("SetMode")
        if mode not in {None, "Inc"}:
            self._issue(ctx, path, str(task.get("$type")),
                        f"只支持 SetMode=Inc 或缺省直设，得到 {mode!r}")
            return
        target = self._hook_target(self._alias(task) or "Caster", ctx)
        if target is None:
            self._issue(ctx, path, str(task.get("$type")), "阶段写入目标未注册")
            return
        if mode == "Inc":
            if "PhaseNum" in task or not (
                    target == "self" or target == "$event.target" or isinstance(target, dict)):
                self._issue(ctx, path, str(task.get("$type")),
                            "Inc 需不带 PhaseNum 且目标可逐目标求值")
                return
            amount: Any = ("dynamic_of($self, 'current_phase') + 1" if target == "self"
                           else "dynamic_of($target, 'current_phase') + 1")
        else:
            phase = self._number(task.get("PhaseNum", 1), ctx, f"{path}/PhaseNum")
            if phase is None or phase < 1 or int(phase) != phase:
                self._issue(ctx, path, str(task.get("$type")), "PhaseNum 必须是正整数")
                return
            amount = int(phase)
        ctx.dynamic_writes.add("current_phase")
        self._add_effect(ctx, {
            "effect_type": "set_dynamic_value", "target": target,
            "dynamic_key": "current_phase", "amount": amount,
        })

    def _compile_summon_monster(self, task: Dict[str, Any], ctx: _Context,
                                path: str, stack: Tuple[str, ...]) -> None:
        rows = task.get("SummonMonsterDataList") or []
        if not rows:
            self._issue(ctx, path, str(task.get("$type")), "SummonMonsterDataList 为空")
            return
        for index, row in enumerate(rows):
            raw_id = row.get("MonsterID")
            if "MonsterIDFromCustomValue" in row:
                try:
                    key_hash = int((row.get("MonsterIDFromCustomValue") or {}).get("Hash"))
                except (TypeError, ValueError):
                    self._issue(ctx, f"{path}/{index}", "SummonMonster", "CustomValue 哈希缺失")
                    continue
                values = [value for name, value in self.custom_values.items()
                          if dynamic_value_hash(str(name)) == key_hash]
                if not values or any(value != values[0] for value in values[1:]):
                    self._issue(ctx, f"{path}/{index}", "SummonMonster",
                                "CustomValue 怪物 ID 哈希缺失或冲突")
                    continue
                raw_id = values[0]
            monster_value = self._value(raw_id, ctx, f"{path}/{index}/MonsterID")
            delay = self._number(row.get("DelayRatio", 0), ctx, f"{path}/{index}/DelayRatio")
            if monster_value is None or delay is None:
                continue
            dynamic_id = isinstance(monster_value, str)
            candidates = sorted({int(value) for value in self.sources.get("summon_ids") or []
                                 if _is_number(value) and int(value) == value and value > 0}) \
                if dynamic_id else []
            if dynamic_id and not candidates:
                self._issue(ctx, f"{path}/{index}", "SummonMonster",
                            "动态怪物 ID 需要非空 SummonIDList 作为候选闭集")
                continue
            if not dynamic_id and int(monster_value) != monster_value:
                self._issue(ctx, f"{path}/{index}", "SummonMonster", "怪物 ID 必须为整数")
                continue
            if delay != 0:
                self._issue(ctx, f"{path}/{index}", "SummonMonster",
                            "非零召唤 DelayRatio 尚未接入行动时序")
                continue
            summon_id = ""
            variants = {}
            for candidate in candidates or [int(monster_value)]:
                candidate_id = f"{candidate}__{self.enemy_id}_s{len(ctx.summons) + 1}"
                ctx.summons.append({
                    "summon_id": candidate_id, "enemy_template": str(candidate),
                    "level": self.level,
                })
                if dynamic_id:
                    variants[str(candidate)] = candidate_id
                else:
                    summon_id = candidate_id
            # LocationType（First/KeepOnFirst=队首，Last/KeepOnLast=队尾；LastDie = on_kill 死亡目标原位）为布场方向唯一事实源；
            # RefreshTeamLocation=true（重排站位）未收编显式拒；其余值待实测。
            location = str(row.get("LocationType") or "")
            refresh = row.get("RefreshTeamLocation")
            if refresh:
                self._issue(ctx, f"{path}/{index}", "SummonMonster",
                            "RefreshTeamLocation=true（召唤后重排站位）未收编")
                continue
            # 词表实证：First=队首 / Last=队尾 / BeforeCaster/AfterCaster=召唤者前后 /
            # AroundCasterOnEdge=环绕召唤者边缘（紧邻同义，按 after_owner 右邻实现；
            # 多单位的左右交替分配待实测）。
            location_map = {"First": "first", "Last": "last", "LastDie": "last_die",
                            "KeepOnFirst": "first", "KeepOnLast": "last",
                            "BeforeCaster": "before_owner", "AfterCaster": "after_owner",
                            "AroundCasterOnEdge": "after_owner",
                            "FormationRecord": "formation_record"}
            if location == "LastDie" and ctx.event != "on_kill":
                self._issue(ctx, f"{path}/{index}", "SummonMonster",
                            "LastDie 仅支持 on_kill 语境，需要本次死亡目标的原站位")
                continue
            if location and location not in location_map:
                self._issue(ctx, f"{path}/{index}", "SummonMonster",
                            f"召唤布场 LocationType={location} 语义待实测")
                continue
            effect = {"effect_type": "summon", "summon_group": f"{self.enemy_id}:{path}"}
            if dynamic_id:
                effect["summon_id_source"] = monster_value
                effect["summon_variants"] = variants
            else:
                effect["summon_id"] = summon_id
            if location:
                effect["position"] = location_map[location]
            self._add_effect(ctx, effect)

    def _ability_adds_modifier(self, ability_name: str, modifier_name: str,
                               seen: Optional[set] = None) -> bool:
        seen = set() if seen is None else seen
        if ability_name in seen or ability_name not in self.abilities:
            return False
        seen.add(ability_name)

        def walk(value: Any) -> bool:
            if isinstance(value, dict):
                node_type = str(value.get("$type") or "")
                if node_type == "RPG.GameCore.AddModifier":
                    raw = value.get("ModifierName")
                    name = raw.get("Value") if isinstance(raw, dict) else raw
                    if str(name) == modifier_name:
                        return True
                if node_type in {"RPG.GameCore.TriggerAbility", "RPG.GameCore.TurnInsertAbility"}:
                    raw = value.get("AbilityName")
                    child = raw.get("Value") if isinstance(raw, dict) else raw
                    if child and self._ability_adds_modifier(str(child), modifier_name, seen):
                        return True
                return any(walk(child) for child in value.values())
            if isinstance(value, list):
                return any(walk(child) for child in value)
            return False

        return walk(self.abilities[ability_name])

    def _compile_dispel_status(self, task: Dict[str, Any], ctx: _Context,
                               path: str, stack: Tuple[str, ...]) -> None:
        buff_type = task.get("BuffType")
        if task.get("Order", "LastAdded") not in {"LastAdded", "FirstAdded"} \
                or buff_type not in {None, "Buff", "Unknown"}:
            self._issue(ctx, path, str(task.get("$type")), "驱散类型/顺序未注册")
            return
        flags = set(task.get("BehaviorFlags") or [])
        filters = {
            "STAT_CTRL": "$mod.kind == 'control'",
            "STAT_DOT": "$mod.kind == 'dot'",
            "DisableAction": "$mod.prevent_action",
            "Break": "'Break' in $mod.behavior_flags",
        }
        if flags and (buff_type == "Buff" or not flags.issubset(filters)):
            self._issue(ctx, path, str(task.get("$type")), f"驱散类型/旗标组合未注册：{sorted(flags)}")
            return
        target = self._hook_target(self._alias(task), ctx)
        count = None
        if "Numbers" in task:
            count = self._number(task.get("Numbers"), ctx, f"{path}/Numbers")
        if target is None or ("Numbers" in task and (count is None or count < 1 or int(count) != count)):
            self._issue(ctx, path, str(task.get("$type")), "驱散目标或正整数数量未注册")
            return
        if task.get("OnlyAlive") is False:
            if isinstance(target, dict):
                target = {**target, "include_dead": True}
            else:
                pool = {
                    "AllTeammate": "enemies", "AllTeamMember": "enemies", "AllDarkTeam": "enemies",
                    "AllEnemy": "allies", "AllLightTeam": "allies",
                    "all_enemies": "enemies", "all_allies": "allies",
                }.get(target)
                if pool is not None:
                    target = {"pool": pool, "include_dead": True}
        effect = {
            "effect_type": "remove_modifier", "target": target,
            "filter": (f"({' or '.join(filters[flag] for flag in sorted(flags))})" if len(flags) > 1
                       else filters[next(iter(flags))] if flags else (
                           "$mod.kind == 'buff'" if buff_type == "Buff" else "1 == 1")),
            "reason": "dispel",
        }
        if "Order" in task:
            effect["order"] = "oldest" if task["Order"] == "FirstAdded" else "newest"
        if count is not None:
            effect["max_count"] = int(count)
        self._add_effect(ctx, effect)
        count_key = str(task.get("DispelCountKey") or "")
        if count_key:
            if ctx.mode != "action":
                self._issue(ctx, path, str(task.get("$type")), "驱散计数仅支持行动效果链")
                return
            ctx.count_expressions[dynamic_value_hash(count_key)] = "$last.removed_count"
            ctx.dynamic_writes.add(count_key)
            self._add_effect(ctx, {
                "effect_type": "set_dynamic_value", "target": "self",
                "dynamic_key": count_key, "amount": "$last.removed_count",
            })

    def _compile_remove_modifier_by_behavior_flag(self, task: Dict[str, Any], ctx: _Context,
                                                  path: str, stack: Tuple[str, ...]) -> None:
        flags = set(task.get("ModifierBehaviorFlags") or [])
        filters = {
            "STAT_CTRL": "$mod.kind == 'control'",
            "STAT_DOT": "$mod.kind == 'dot'",
            "DisableAction": "$mod.prevent_action",
        }
        if not flags:
            self._issue(ctx, path, str(task.get("$type")), "行为旗标摘除列表为空")
            return
        target = self._hook_target(self._alias(task), ctx)
        if target is None:
            self._issue(ctx, path, "TargetAlias", f"未注册行为旗标摘除目标：{self._alias(task)}")
            return
        ordered = sorted(flags, key=str)
        conditions = [filters.get(flag, f"{flag!r} in $mod.behavior_flags") for flag in ordered]
        filter_expr = conditions[0] if len(conditions) == 1 else "(" + " or ".join(conditions) + ")"
        self._add_effect(ctx, {
            "effect_type": "remove_modifier", "target": target,
            "filter": filter_expr, "reason": "dispel",
        })

    def _compile_remove_self_modifier(self, task: Dict[str, Any], ctx: _Context,
                                      path: str, stack: Tuple[str, ...]) -> None:
        if not ctx.current_modifier:
            self._issue(ctx, path, str(task.get("$type")), "RemoveSelfModifier 缺少当前 modifier 名")
            return
        self._add_effect(ctx, {
            "effect_type": "remove_modifier", "target": "self",
            "modifier_id": ctx.current_modifier,
        })

    def _compile_remove_modifier(self, task: Dict[str, Any], ctx: _Context,
                                 path: str, stack: Tuple[str, ...]) -> None:
        raw = task.get("ModifierName")
        name = (raw or {}).get("Value") if isinstance(raw, dict) else raw
        if name == "ParamModifier" and ctx.param_modifier:
            name = ctx.param_modifier
        if str(name) in {"OneMore", "OneMorePerTurn", "Monster_APShow"} \
                and self.modifiers.get(str(name)) is None:
            # grant_extra_turn 不产生 modifier 实例，内建 OneMore/APShow 清理无需 DSL 状态。
            return
        if (str(name).startswith("Monster_APShow_")
                and self.modifiers.get(str(name)) is None
                and not self._modifier_used_in_predicates(str(name))):
            return
        definition = self.modifiers.get(str(name)) or {}
        target = self._task_target(task, ctx, path)
        if target is None:
            self._issue(ctx, path, str(task.get("$type")),
                        f"摘除目标未注册：{self._alias(task)}")
            return
        trigger = str(ctx.skill.get("trigger_key") or "")
        entry = str((self.config_skills.get(trigger) or {}).get("EntryAbility") or "")
        if ("STAT_DOT" in set(definition.get("BehaviorFlagList") or [])
                and not self._ability_adds_modifier(entry, str(name))):
            self._issue(ctx, path, str(task.get("$type")), "跨技能 DoT 摘除未能绑定来源技能")
            return
        skill_id = str(ctx.skill.get("skill_id") or self.enemy_id)
        effect = {
            "effect_type": "remove_modifier", "target": target,
            "modifier_id": self._modifier_id(str(name), definition, skill_id),
        }
        if task.get("OnlyRemoveCasterAdded"):
            if ctx.event in {"on_apply", "after_remove_modifier"}:
                effect["filter"] = "$mod.source == $event.source"
            elif ctx.event == "before_actor_exit":
                current_definition = self.modifiers.get(ctx.current_modifier) or {}
                current_id = self._modifier_id(ctx.current_modifier, current_definition, skill_id)
                effect["filter"] = f"$mod.source == modifier_source($event.actor, '{current_id}')"
            else:
                effect["filter"] = "$mod.source == $self.actor_id"
        self._add_effect(ctx, effect)

    @staticmethod
    def _alias(task: Dict[str, Any]) -> str:
        target = task.get("TargetType")
        if isinstance(target, dict):
            if target.get("$type") == "RPG.GameCore.TargetFetchUniqueNameEntity":
                raw_name = target.get("UniqueName")
                name = raw_name.get("RawString") if isinstance(raw_name, dict) else raw_name
                return f"unique:{name or ''}"
            alias = str(target.get("Alias") or target.get("TargetType") or "")
            event_id = alias.removeprefix("BattleEvent_")
            if event_id != alias and event_id.isdigit():
                return f"unique:$battle_event:{event_id}"
            if "_BattleEvent_" in alias:
                return f"unique:{alias.rsplit('_BattleEvent_', 1)[1]}"
            return alias
        return str(target or "")

    @staticmethod
    def _composite_battle_event_target(alias: str) -> Optional[Dict[str, Any]]:
        for separator in (" + ", " - "):
            base, found, event_alias = alias.partition(separator)
            base_spec = _INCLUSIVE_TEAM_TARGETS.get(base)
            event_id = event_alias.removeprefix("BattleEvent_")
            if (not found or base_spec is None or event_id == event_alias
                    or not event_id.isdigit()):
                continue
            event_spec = {"pool": f"unique:$battle_event:{event_id}"}
            if separator == " + ":
                return {"concat": [dict(base_spec), event_spec]}
            spec = dict(base_spec)
            exclusion = f"$it.actor_id != unique_target('$battle_event:{event_id}')"
            spec["where"] = AbilityCompiler._and_condition(spec.get("where", "true"), exclusion)
            return spec
        return None

    def _concat_alias(self, alias: str, ctx: _Context) -> Optional[Dict[str, Any]]:
        parts = [part.strip() for part in alias.split("+")]
        if len(parts) < 2 or any(not part for part in parts):
            return None
        children = []
        for part in parts:
            target = self._hook_target(part, ctx)
            if isinstance(target, str):
                target = {"all_enemies": "enemies", "all_allies": "allies"}.get(target, target)
                if target == "self" or target.startswith("$event."):
                    target = {"pool": target}
                elif target in {"allies", "enemies", "enemy_targets"}:
                    target = {"pool": target}
                else:
                    return None
            if not isinstance(target, dict):
                return None
            children.append(target)
        return {"concat": children}

    def _hook_target(self, alias: str, ctx: Optional[_Context] = None) -> Any:
        if ctx is not None and alias in self.target_aliases:
            return self._target_spec(self.target_aliases[alias], ctx, f"TargetAlias/{alias}")
        if alias.endswith(".GetAliveOnly"):
            base = self._hook_target(alias[:-len(".GetAliveOnly")], ctx)
            if isinstance(base, str):
                base = {"all_enemies": "enemies", "all_allies": "allies"}.get(base, base)
                if base in {"self", "allies", "enemies", "enemy_targets"} or base.startswith("$event."):
                    base = {"pool": base}
                else:
                    return None
            if not isinstance(base, dict):
                return None
            return {**base, "include_dead": False}
        if alias.endswith(".RemoveUnselectable"):
            base = self._hook_target(alias[:-len(".RemoveUnselectable")], ctx)
            if isinstance(base, str):
                base = {"all_enemies": "enemies", "all_allies": "allies"}.get(base, base)
                if base in {"self", "allies", "enemies", "enemy_targets"} or base.startswith("$event."):
                    base = {"pool": base}
                else:
                    return None
            if not isinstance(base, dict):
                return None
            spec = dict(base)
            condition = "$it.enemy_targetable and $it.ally_targetable"
            if spec.get("include_summons"):
                return {"concat": [spec], "where": condition}
            spec["where"] = self._and_condition(str(spec.get("where") or "true"), condition)
            return spec
        if alias.endswith(".RemoveServant") and alias not in _INCLUSIVE_TEAM_TARGETS:
            base = self._hook_target(alias[:-len(".RemoveServant")], ctx)
            if isinstance(base, str):
                base = {"all_enemies": "enemies", "all_allies": "allies"}.get(base, base)
                if base in {"self", "allies", "enemies", "enemy_targets"} or base.startswith("$event."):
                    base = {"pool": base}
                else:
                    return None
            if not isinstance(base, dict):
                return None
            condition = "not $it.summoner_id"
            if base.get("include_summons"):
                return {"concat": [base], "where": condition}
            spec = dict(base)
            spec["where"] = self._and_condition(str(spec.get("where") or "true"), condition)
            return spec
        if alias.endswith(".WithServant"):
            base = self._hook_target(alias[:-len(".WithServant")], ctx)
            if isinstance(base, str):
                base = {"all_enemies": "enemies", "all_allies": "allies"}.get(base, base)
                if base in {"self", "allies", "enemies", "enemy_targets"} or base.startswith("$event."):
                    base = {"pool": base}
                else:
                    return None
            if not isinstance(base, dict):
                return None
            spec = dict(base)
            spec["include_summons"] = True
            return spec
        if alias.endswith(".Shuffle"):
            base = self._hook_target(alias[:-len(".Shuffle")], ctx)
            if isinstance(base, str):
                base = {"all_enemies": "enemies", "all_allies": "allies"}.get(base, base)
                if base in {"self", "allies", "enemies", "enemy_targets"} or base.startswith("$event."):
                    base = {"pool": base}
                else:
                    return None
            if not isinstance(base, dict):
                return None
            spec = dict(base)
            spec["mode"] = "shuffle"
            return spec
        base_alias, select_marker, raw_position = alias.rpartition(".Select")
        if select_marker and raw_position.isdigit() and int(raw_position) >= 1:
            base = self._hook_target(base_alias, ctx)
            if isinstance(base, str):
                base = {"all_enemies": "enemies", "all_allies": "allies"}.get(base, base)
                if base in {"self", "allies", "enemies", "enemy_targets"} or base.startswith("$event."):
                    base = {"pool": base}
                else:
                    return None
            if not isinstance(base, dict) or base.get("mode", "deterministic") != "deterministic":
                return None
            spec = dict(base)
            spec["index"] = int(raw_position) - 1
            return spec
        if alias in {"AttackTargetList", "ParamEntityAttackTargetList"}:
            return "$event.hit_targets" if ctx is not None and ctx.event == "on_action_end" else None
        if alias in {"SkillTargetEntityList", "ModifierOwnerSkillTargetEntityList"}:
            return ("$event.targets" if ctx is not None
                    and ctx.event in {"before_action", "on_action"} else None)
        composite = self._composite_battle_event_target(alias)
        if composite is not None:
            return composite
        if alias.startswith("unique:"):
            return {"pool": alias} if len(alias) > len("unique:") else None
        if alias.endswith("_Self"):
            alias = "Caster"   # Monster_*_Self = 自身特定形态
        if alias == "Elation_BE":
            return dict(_ELATION_BE_TARGET)
        if alias == "PartEntity0":
            return {"pool": "all", "where": (
                "$it.actor_id == (summoner_of($self.actor_id) or $self.actor_id)")}
        if alias.startswith("PartEntity") and alias.removeprefix("PartEntity").isdigit():
            from hsr_nous.pipeline.enemies.loader import get_body_part_values
            values = get_body_part_values(self.enemy_id)
            monster_id = values.get(f"{alias}_MonsterID")
            if not _is_number(monster_id):
                return None
            return {"pool": "enemies", "where": f"monster_id($it) == '{int(monster_id)}'"}
        if alias == "Trailblazer":
            return _trailblazer_target_spec()
        if alias == "ParamEntity2" and ctx is not None:
            if ctx.event in {"after_being_hit", "on_kill", "on_revive", "modifier_custom_event"}:
                return "$event.source"
            if ctx.event in {"after_apply_modifier", "after_remove_modifier"}:
                return "$event.target"
        if alias == "ParamEntity.GetCreator" and ctx is not None and ctx.event == "after_being_hit":
            return {"pool": "all", "where": "$it.actor_id == summoner_of($event.target)"}
        if alias == "ParamEntity.WithSummoner":
            target = self._hook_target("ParamEntity", ctx)
            summoner = self._hook_target("ParamEntity.GetSummoner", ctx)
            if not isinstance(target, str) or not isinstance(summoner, dict):
                return None
            target = "$self.actor_id" if target == "self" else target
            return {"concat": [{"pool": target}, summoner]}
        if alias == "ParamEntityActualOwner":
            reference = self._hook_target("ParamEntity", ctx)
            if not isinstance(reference, str):
                return None
            reference = "$self.actor_id" if reference == "self" else reference
            return {"pool": "all", "where": (
                f"$it.actor_id == (summoner_of({reference}) or {reference})")}
        if ("+" not in alias and " - " not in alias and alias not in _INCLUSIVE_TEAM_TARGETS
                and alias.endswith((".GetServant", ".GetSummoner"))):
            base_alias = alias.rsplit(".", 1)[0]
            reference = self._hook_target(base_alias, ctx)
            if not isinstance(reference, str) or reference in {
                    "all_allies", "all_enemies", "allies", "enemies", "all", "enemy_targets"}:
                return None
            reference = "$self.actor_id" if reference == "self" else reference
            if alias.endswith(".GetServant"):
                return {"pool": "all", "where": f"$it.summoner_id == {reference}"}
            return {"pool": "all", "where": f"$it.actor_id == summoner_of({reference})"}
        if ("+" not in alias and " - " not in alias and alias not in _INCLUSIVE_TEAM_TARGETS
                and alias.endswith(".GetBattleEvent")):
            reference = self._hook_target(alias[:-len(".GetBattleEvent")], ctx)
            if not isinstance(reference, str) or reference in {
                    "all_allies", "all_enemies", "allies", "enemies", "all", "enemy_targets"}:
                return None
            reference = "$self.actor_id" if reference == "self" else reference
            return {"pool": "battle_events", "where": f"$it.summoner_id == {reference}"}
        if alias in {"ParamEntity", "ParamEntityList", "TemplateParamEntityList"}:
            if alias == "ParamEntity" and ctx is not None and ctx.mode == "event" \
                    and ctx.event in {"on_action", "before_action"}:
                return "$event.actor"
            if ctx is not None and ctx.retarget is not None:
                # F14：交出副本——调用方就地写 where/include_dead/mode/index 等
                # 不污染共享 ctx.retarget（同 Retarget 下后续 effect 静默多带过滤）
                return copy.deepcopy(ctx.retarget)
            if alias in {"ParamEntityList", "TemplateParamEntityList"} and ctx.retarget is None:
                return "$event.targets"
            if alias == "ParamEntity" and ctx is not None:
                return {
                    "actor_enter": "$event.actor",
                    "actor_exit": "$event.actor",
                    "before_actor_exit": "$event.actor",
                    "on_action_end": "$event.actor",
                    "on_turn_start": "$event.actor",
                    "on_turn_end": "$event.actor",
                    "toughness_recovered": "$event.target",
                    "before_take_damage": "$event.target",
                    "on_break": "$event.target",
                    "after_apply_modifier": "$event.target",
                    "after_remove_modifier": "$event.target",
                    "after_being_hit": "$event.target",
                    "on_kill": "$event.target",
                    "on_revive": "$event.target",
                    "on_hp_decrease": "$event.target",
                    "on_hp_increase": "$event.target",
                    "on_energy_change": "$event.target",
                    "on_skill_point_change": "$event.consumer",
                    "on_unselectable_start": "$event.target",
                    "on_unselectable_end": "$event.target",
                    "modifier_custom_event": "$event.target",
                    "monster_phase_changed": "$event.actor",
                    "battle_event_create": "$event.actor",
                }.get(ctx.event)
            return None
        if alias in {"CasterSummoner", "ModifierOwnerSummoner"}:
            return "summoner_of($self.actor_id)"
        if alias == "ParamEntitySummoner":
            return "summoner_of($it)"
        if alias in _INCLUSIVE_TEAM_TARGETS:
            return dict(_INCLUSIVE_TEAM_TARGETS[alias])
        if (" - " in alias and not alias.startswith("AllTeammate - MMonster_")):
            left_raw, right_raw = alias.split(" - ", 1)
            left = self._hook_target(left_raw, ctx)
            right = self._hook_target(right_raw, ctx)
            def as_spec(target: Any) -> Optional[Dict[str, Any]]:
                if isinstance(target, dict):
                    return target
                if isinstance(target, str):
                    target = {"all_enemies": "enemies", "all_allies": "allies"}.get(target, target)
                    if target in {"self", "allies", "enemies", "enemy_targets"} \
                            or target.startswith(("$event.", "unique:")):
                        return {"pool": target}
                return None
            left_spec, right_spec = as_spec(left), as_spec(right)
            if left_spec is None or right_spec is None:
                return None
            return {"concat": [left_spec],
                    "where": self._negate_condition(self._target_membership(right_spec, "$it"))}
        if ctx is not None:
            concat = self._concat_alias(alias, ctx)
            if concat is not None:
                return concat
        if alias.startswith("Monster_"):
            from hsr_nous.pipeline.enemies.loader import get_monster_ids_by_config_alias
            monster_ids = get_monster_ids_by_config_alias(alias)
            if not monster_ids:
                return alias
            condition = (f"monster_id($it) == '{monster_ids[0]}'" if len(monster_ids) == 1
                         else f"monster_id($it) in {list(monster_ids)!r}")
            return {"pool": "enemies", "where": condition}
        if alias.startswith("AllTeammate - MMonster_"):
            modifier_name = alias.removeprefix("AllTeammate - ")
            return {"pool": "enemies", "where": f"not has_modifier($it, '{modifier_name}')"}
        return {
            "Caster": "self",
            "ModifierOwnerEntity": "self",
            "AbilityTargetEntity": "$event.target",
            "DamageAttackerEntity": "$event.source",
            "DamageDefenderEntity": "$event.target",
            "ProjectileHitEntity": "$event.target",
            "TurnActionEntitySkillTarget": "$event.target",
            "AllTeammate": "all_enemies",
            "AllTeamMember": "all_enemies",
            "AllDarkTeam": "all_enemies",
            "AllDarkTeamWithAllDarkTeamUnselectable": "all_enemies",
            "AllEnemy": "all_allies",
            "AllLightTeam": "all_allies",
            "AllLightTeamIgnoreServant": {
                "pool": "allies", "where": "actor_type_of($it) != 'summon'"},
            "AllLightTeam.RemoveServant": {
                "pool": "allies", "where": "not $it.summoner_id"},
            "LevelEntity": "$level",
            "LightTeamEntity": "$light_team",
            "DarkTeamEntity": "$dark_team",
            "TauntOrRandomEnemy": {
                "pool": "enemy_targets", "take": 1, "mode": "taunt_or_random"},
            "TauntOrRandomEnemyWithoutServant": {
                "pool": "enemy_targets", "where": "not $it.summoner_id",
                "take": 1, "mode": "taunt_or_random"},
            "TauntOrRandomEnemy.RemoveServant": {
                "pool": "enemy_targets", "where": "not $it.summoner_id",
                "take": 1, "mode": "taunt_or_random"},
            "CasterLeftEntity": {"pool": "enemies",
                                 "where": "position_delta($it, $self.actor_id) == -1"},
            "CasterRightEntity": {"pool": "enemies",
                                  "where": "position_delta($it, $self.actor_id) == 1"},
            "CasterSummonedMinions": {
                "pool": "enemies", "where": "$it.summoner_id == $self.actor_id"},
            "ModifierOwnerSummonedMinions": {
                "pool": "enemies", "where": "$it.summoner_id == $self.actor_id"},
            "LastSummonMonsters": {"pool": "last_summons"},
            "AbilityTargetLeftEntity": {
                "pool": "allies", "where": "position_delta($it, $event.target) == -1"},
            "AbilityTargetRightEntity": {
                "pool": "allies", "where": "position_delta($it, $event.target) == 1"},
            "AbilityTargetAdjoinEntity": {
                "pool": "allies", "where": "is_adjacent($it, $event.target)"},
            "AbilityTargetAndAdjoinEntity": {
                "pool": "allies",
                "where": "($it.actor_id == $event.target or is_adjacent($it, $event.target))"},
            "ParamEntityAdjoinEntity": {
                "pool": "allies", "where": "is_adjacent($it, $event.target)"},
            "CasterAdjoinEntity": {
                "pool": "enemies", "where": "is_adjacent($it, $self.actor_id)"},
        }.get(alias)

    def _compile_damage(self, task: Dict[str, Any], ctx: _Context,
                        path: str, stack: Tuple[str, ...]) -> None:
        attack = task.get("AttackProperty") or {}
        definition = self.modifiers.get(ctx.current_modifier) or {}
        direct_dot = (attack.get("AttackType") == "DOT" and ctx.mode == "event"
                      and bool(ctx.current_modifier) and "DamagePercentage" in attack
                      and "STAT_DOT" not in set(definition.get("BehaviorFlagList") or []))
        if attack.get("AttackType") == "DOT" and not direct_dot:
            self._issue(ctx, path, str(task.get("$type")), "DoT 伤害须由 modifier 定义编译")
            return
        damage_tags = attack.get("DamageTag") or []
        if direct_dot and any(not isinstance(tag, dict) or tag.get("EnumIndex") != 3
                              or isinstance(tag.get("Value"), bool)
                              or not isinstance(tag.get("Value"), int) for tag in damage_tags):
            self._issue(ctx, path, str(task.get("$type")),
                        "直接 DOT 段仅支持 EnumIndex=3 的整数 DamageTag")
            return
        alias = self._alias(task)
        ratio = self._value(attack.get("DamagePercentage"), ctx, f"{path}/DamagePercentage")
        if ratio is None:
            return
        ctx.seen_damage = True
        if ctx.condition != "true":
            ctx.conditional_damage = True
        record = {
            "alias": alias,
            "ratio": ratio,
            "element": _element(attack.get("DamageType")),
            "formula": attack.get("FormulaType") or "ByAttack",
            "damage_custom_name": str((attack.get("CustomName") or {}).get("Value")
                                      if isinstance(attack.get("CustomName"), dict)
                                      else attack.get("CustomName") or ""),
            "stance_ratio": self._number(attack.get("SPHitRatio", 1), ctx,
                                         f"{path}/SPHitRatio"),
            "stance_value": self._value(attack["StanceValue"], ctx, f"{path}/StanceValue")
            if "StanceValue" in attack else None,
        }
        if not alias and isinstance(task.get("TargetType"), dict):
            target_spec = self._target_spec(task["TargetType"], ctx, path)
            if target_spec is not None:
                record["target_spec"] = target_spec
        dot_fields = ({"action_type": "dot",
                       "damage_tags": [tag["Value"] for tag in damage_tags]}
                      if direct_dot else {})
        if ctx.retarget is not None:
            if ctx.mode == "action":
                ctx.retarget_damage = True
                ctx.retarget_damage_records.append(record)
            effect = {
                "effect_type": "deal_damage", "target": ctx.retarget,
                "damage_type": record["element"],
                "damage_custom_name": record["damage_custom_name"],
                "scaling_hp" if record["formula"] == "ByMaxHP" else "scaling_atk": ratio,
                "toughness_dmg": (record["stance_value"] if record["stance_value"] is not None
                                  else float(ctx.skill.get("sp_hit_base") or 0)
                                  * (record["stance_ratio"] or 0)),
                **dot_fields,
            }
            self._add_effect(ctx, effect)
            return
        if ctx.mode == "event":
            target = record.get("target_spec") or self._hook_target(alias, ctx)
            if target is None:
                self._issue(ctx, path, "TargetAlias", f"未注册事件目标别名：{alias}")
                return
            effect = {
                "effect_type": "deal_damage", "target": target,
                "damage_type": record["element"],
                "damage_custom_name": record["damage_custom_name"],
                "scaling_hp" if record["formula"] == "ByMaxHP" else "scaling_atk": ratio,
                "toughness_dmg": record["stance_value"] or 0,
                **dot_fields,
            }
            self._add_effect(ctx, effect)
        elif ctx.in_dynamic_loop:
            target = record.get("target_spec") or self._hook_target(alias, ctx)
            if target is None:
                self._issue(ctx, path, "TargetAlias", f"未注册循环伤害目标别名：{alias}")
                return
            self._add_effect(ctx, {
                "effect_type": "deal_damage", "target": target,
                "damage_type": record["element"],
                "damage_custom_name": record["damage_custom_name"],
                "scaling_hp" if record["formula"] == "ByMaxHP" else "scaling_atk": ratio,
                "toughness_dmg": (record["stance_value"] if record["stance_value"] is not None
                                  else float(ctx.skill.get("sp_hit_base") or 0)
                                  * (record["stance_ratio"] or 0)),
            })
        else:
            ctx.damages.append(record)

    _BUILTIN_BEHAVIOR_FLAGS = {
        "MCommon_Confine": {"STAT_CTRL", "STAT_Confine", "DisableAction", "STAT_SpeedDown", "AvatarBreak"},
        "MCommon_FatigueRatio": {"STAT_Fatigue"},
        "MCommon_CTRL_Crazy": {"STAT_Crazy", "Crazy", "AvatarBreak", "STAT_CTRL", "DispelPriorityHigh"},
        "MCommon_CTRL_Frozen": {"DisableAction", "STAT_CTRL_Frozen_Effect", "STAT_CTRL_Frozen", "STAT_CTRL"},
        "MCommon_CTRL_Stun": {"DisableAction", "IdleStun", "STAT_CTRL_Stun", "STAT_CTRL"},
        "MCommon_CTRL_Taunt": {"Taunt", "RemoveWhenCasterDead", "RemoveWhenCasterUnstage"},
    }

    def _compile_builtin_modifier(self, name: str, task: Dict[str, Any], ctx: _Context,
                                  path: str) -> bool:
        if name not in {"MCommon_Confine", "MCommon_FatigueRatio", "MCommon_CTRL_Crazy",
                         "MCommon_CTRL_Frozen", "MCommon_CTRL_Stun", "MCommon_CTRL_Taunt",
                         "MCommon_FastAction", "WMonster_TY_Elite01_00_Skill07_Mark"}:
            return False
        target = self._hook_target(self._alias(task), ctx)
        chance = self._value(task.get("Chance", 1), ctx, f"{path}/Chance")
        duration = self._value(task.get("LifeTime", 0), ctx, f"{path}/LifeTime")
        if target is None or chance is None or duration is None:
            self._issue(ctx, path, "BuiltinModifier", f"内建 modifier 目标/概率/时长未注册：{name}")
            return True
        skill_id = str(ctx.skill.get("skill_id") or self.enemy_id)
        behavior_flags = set((self.modifiers.get(name) or {}).get("BehaviorFlagList")
                             or self._BUILTIN_BEHAVIOR_FLAGS.get(name) or ())
        base = {
            "duration": int(duration) if _is_number(duration) else duration,
            "max_stack": 1, "stack_mode": "refresh", "dispellable": True,
            **({"behavior_flags": sorted(behavior_flags)} if behavior_flags else {}),
        }
        if name == "MCommon_CTRL_Taunt":
            modifier = {
                "modifier_id": f"ENEMY_{skill_id}_TAUNT", "name": "Taunt",
                "modifier_type": "debuff", "debuff_kind": "control", "control_kind": "taunt",
                "forced_taunt": True, "remove_on_source_death": True,
                "remove_on_source_exit": True, **base,
            }
        elif name == "MCommon_CTRL_Stun":
            modifier = {
                "modifier_id": name, "name": name, "modifier_type": "debuff",
                "debuff_kind": "control", "control_kind": "stun",
                "prevent_action": True, **base,
            }
        elif name == "MCommon_CTRL_Frozen":
            modifier = {
                "modifier_id": name, "name": name, "modifier_type": "control",
                "debuff_kind": "control", "control_kind": "freeze",
                "prevent_action": True, **base,
            }
            ratio = self._value(
                (task.get("DynamicValues") or {}).get("Modifier_Frozen_DamagePercentage"),
                ctx, f"{path}/Modifier_Frozen_DamagePercentage")
            if ratio is None:
                self._issue(ctx, path, "Modifier_Frozen_DamagePercentage", "冻结追击倍率未注册")
                return True
            ctx.lifecycle_hooks.append({
                "event": "on_turn_start",
                "condition": f"has_modifier($event.actor, '{name}')",
                "effects": [{
                    "effect_type": "deal_damage", "target": "$event.actor",
                    "damage_type": "ice", "action_type": "follow_up", "scaling_atk": ratio,
                }],
            })
        elif name == "WMonster_TY_Elite01_00_Skill07_Mark":
            modifier = {"modifier_id": name, "name": name, "modifier_type": "debuff", **base}
        elif name == "MCommon_CTRL_Crazy":
            modifier = {
                "modifier_id": "ENEMY_OUTRAGE", "name": "Outrage", "modifier_type": "debuff",
                "debuff_kind": "control", "control_kind": "outrage", **base,
            }
        elif name == "MCommon_Confine":
            modifier = {
                "modifier_id": f"ENEMY_{skill_id}_IMPRISON", "name": "Imprisonment",
                "modifier_type": "debuff", "debuff_kind": "control", "control_kind": "imprison",
                **base,
            }
            raw_ratio = (task.get("DynamicValues") or {}).get("MDF_ActionDelayRatio")
            ratio = self._value(raw_ratio, ctx, f"{path}/MDF_ActionDelayRatio")
            if ratio is None:
                return True
            modifier["on_apply"] = [{
                "effect_type": "delay_action", "target": "self",
                "amount": f"({ratio}) * 100" if isinstance(ratio, str) else ratio * 100,
            }]
        elif name == "MCommon_FastAction":
            modifier = {
                "modifier_id": f"ENEMY_{skill_id}_STORMRIDE", "name": "Stormride",
                "modifier_type": "buff",
                "on_apply": [{"effect_type": "immediate_action", "target": "self"}],
                **base,
            }
        else:
            raw_value = (task.get("DynamicValues") or {}).get("MDF_PropertyValue")
            value = self._value(raw_value, ctx, f"{path}/MDF_PropertyValue")
            if value is None:
                return True
            modifier = {
                "modifier_id": f"ENEMY_{skill_id}_WEAKEN", "name": "Weaken",
                "modifier_type": "debuff",
                **({"stat_exprs": {"all_dmg": f"-({value})"}} if isinstance(value, str)
                   else {"stat_effects": {"all_dmg": -value}}),
                **base,
            }
        self._add_effect(ctx, {
            "effect_type": "apply_modifier", "target": target,
            "apply_chance": chance, "modifier": modifier,
        })
        return True

    #: OnStack 回调的 visit_stack 消费集（`_compile_property_modifier`——仅非 DoT 定义）
    _ONSTACK_CONSUMED_TASKS = {
        "RPG.GameCore.PredicateTaskList", "RPG.GameCore.SetDynamicValueByModifierValue",
        "RPG.GameCore.StackProperty", "RPG.GameCore.StackWeakness",
        "RPG.GameCore.AttachSkillTypeDisable", "RPG.GameCore.StackWeakResistance",
        "RPG.GameCore.StackStatusResistance",
        "RPG.GameCore.EnableNegativeHP", "RPG.GameCore.SetMonsterStanceVulnerable",
        "RPG.GameCore.LockStance", "RPG.GameCore.StackCustomUnselectable",
        "RPG.GameCore.InitShield",
    }
    #: OnPhase1 回调的 _compile_dot 消费集（仅 DoT 定义）
    _ONPHASE1_CONSUMED_TASKS = {
        "RPG.GameCore.SetDynamicValueByProperty", "RPG.GameCore.SetDynamicValueByModifierValue",
        "RPG.GameCore.DamageByAttackProperty", "RPG.GameCore.SetDynamicValue",
        "RPG.GameCore.DefineDynamicValue", "RPG.GameCore.PredicateTaskList",
    }

    def _compile_one_more_family(self, name: str, modifier: Dict[str, Any],
                                 ctx: _Context) -> None:
        """OneMorePerTurn 族（boss 多动配额，决策卡 #27）专用收编.

        数据语义：OnCreate/OnListenTurnEnd 额度重置为 MaxOneMoreCount（运行时供给键，
        默认 1 + caveats 待实测）；OnPhase1 发 OneMore 许可（额度有余才授予额外行动）；
        OnActionEnd 额度扣 1。发放只在普通回合开始（modifier 相位不走额外回合）；
        重置监听所有回合结束（含额外回合）——无限续杯由发放侧相位过滤断绝。
        """
        max_expr = "dynamic_of($self.actor_id, 'MaxOneMoreCount')"
        count_expr = "dynamic_of($self.actor_id, 'OneMoreCount')"
        modifier.setdefault("on_apply", []).append({
            "effect_type": "set_dynamic_value", "target": "self",
            "dynamic_key": "OneMoreCount", "amount": max_expr})
        modifier.setdefault("on_remove", []).append({
            "effect_type": "set_dynamic_value", "target": "self",
            "dynamic_key": "OneMoreCount", "amount": 0})
        ctx.lifecycle_hooks.extend([
            {"event": "on_turn_start",
             "condition": f"$event.actor == $self.actor_id and $event.kind == 'normal' and {count_expr} > 0",
             "effects": [{"effect_type": "grant_extra_turn", "target": "self"}]},
            {"event": "on_action_end",
             "condition": "$event.actor == $self.actor_id",
             "effects": [{"effect_type": "set_dynamic_value", "target": "self",
                          "dynamic_key": "OneMoreCount",
                          "amount": f"{count_expr} - 1"}]},
            {"event": "on_turn_end",
             "condition": "$event.actor == $self.actor_id",
             "effects": [{"effect_type": "set_dynamic_value", "target": "self",
                          "dynamic_key": "OneMoreCount", "amount": max_expr}]},
        ])
        ctx.handled.extend(["OnCreate", "OnDestroy", "OnPhase1",
                            "OnActionEnd", "OnListenTurnEnd"])

    def _compile_modifier_lifecycle(self, name: str, definition: Dict[str, Any],
                                    modifier: Dict[str, Any], ctx: _Context, path: str) -> None:
        """创建/摘除写入实例；死亡前编译为全局 hook，避免递归 modifier 定义.

        非生命周期回调事件走 `_PASSIVE_EVENT_MAP`（14_policy.md 被动事件族节）：
        hook 载体编译为全局钩（持有者窄化）；definition 载体由定义编译期消费、
        非常消费任务显式拒；无载体事件显式 unsupported（纯表现回调安全忽略）。"""
        if name.startswith(("OneMorePerTurn", "MoreOneMorePerTurn")):
            self._compile_one_more_family(name, modifier, ctx)
            return
        if name in ctx.modifier_stack:
            return   # 重复施加由已注册运行时钩覆盖，不再递归展开同一生命周期。
        slots = {"OnCreate": "on_apply", "OnDestroy": "on_remove"}
        events = {"OnCreate": "on_apply", "OnDestroy": "after_remove_modifier",
                  "OnBeforeDying": "before_actor_exit"}
        for index, callback in enumerate(definition.get("_CallbackList") or []):
            event = str(callback.get("Event") or "")
            callback_path = f"{path}/_CallbackList/{index}/{event}"
            if event not in {*slots, "OnBeforeDying"}:
                # 主动/被动共用同一映射；未注册事件由统一编译器显式拒绝。
                if event in EVENT_HANDLERS and name in ctx.passive_deathrattle_names:
                    continue
                self._compile_mapped_callback(name, definition, callback, event,
                                              ctx, callback_path, modifier=modifier)
                continue
            if event == "OnBeforeDying" and name in ctx.before_dying_stack:
                continue  # 同一死亡回调的循环施加由既有全局 hook 覆盖，不递归展开。
            if self._presentation_only(callback.get("CallbackConfig") or []):
                ctx.handled.append(event)
                continue
            sub = _Context(
                mode="event", skill=ctx.skill, event=events[event], current_modifier=name,
                current_ability=ctx.current_ability, before_dying_stack=(ctx.before_dying_stack + (name,)
                                    if event == "OnBeforeDying" else ctx.before_dying_stack),
                modifier_stack=ctx.modifier_stack + (name,), value_symbols=dict(ctx.value_symbols),
            )
            self._compile_tasks(callback.get("CallbackConfig") or [], sub, callback_path, ())
            ctx.handled.extend([event, *sub.handled])
            ctx.lifecycle_hooks.extend(sub.lifecycle_hooks)
            for issue in sub.unsupported:
                self._issue(ctx, issue["path"], issue["node_type"], issue["reason"])
            if (sub.damages or sub.pre_effects or sub.hit_effects or sub.summons
                    or sub.retarget_damage or sub.retarget_damage_records):
                self._issue(ctx, callback_path, event, "生命周期伤害/召唤/分段效果尚未注册")
            if event == "OnBeforeDying":
                skill_id = str(ctx.skill.get("skill_id") or self.enemy_id)
                modifier_id = self._modifier_id(name, definition, skill_id)
                for effect in sub.effects:
                    if effect.get("effect_type") == "apply_modifier":
                        effect.setdefault("source", f"modifier:{modifier_id}")
                condition = (f"$event.reason == 'death' "
                             f"and has_modifier($event.actor, '{modifier_id}')")
                ctx.lifecycle_hooks.extend(self._make_hooks(
                    sub, condition, event="before_actor_exit"))
                continue
            effects = []
            for effect in sub.effects:
                condition = str(effect.get("_condition") or "true")
                clean = {key: value for key, value in effect.items() if key != "_condition"}
                if condition != "true":
                    clean["condition"] = condition
                if clean.get("effect_type") == "apply_modifier":
                    clean.setdefault("source", "$event.source")
                effects.append(clean)
            if effects:
                modifier.setdefault(slots[event], []).extend(effects)

    def _compile_mapped_callback(self, name: str, definition: Dict[str, Any],
                                 callback: Dict[str, Any], event: str,
                                 ctx: _Context, callback_path: str,
                                 modifier: Optional[Dict[str, Any]] = None) -> None:
        """`_PASSIVE_EVENT_MAP` 消费：hook 载体编译全局钩 / definition 消费核查 /
        无载体显式拒。`*_CL` 客户端表现事件与纯表现回调安全忽略。"""
        tasks = callback.get("CallbackConfig") or []
        if event.endswith("_CL") or self._presentation_only(tasks):
            ctx.handled.append(event)
            return
        hit_events = {"OnBeforeHit", "OnBeforeHitAll", "OnBeforeBeingHit", "OnBeforeBeingHitAll"}
        if modifier is not None and event in hit_events:
            if self._compile_before_hit_scoped_ratio(
                    name, tasks, modifier, ctx, callback_path):
                ctx.handled.append(event)
                return
            remaining = []
            for index, task in enumerate(tasks):
                if (str(task.get("$type") or "") == "RPG.GameCore.PredicateTaskList"
                        and self._compile_before_hit_scoped_ratio(
                            name, [task], modifier, ctx, f"{callback_path}/{index}")):
                    continue
                remaining.append(task)
            if len(remaining) != len(tasks):
                ctx.handled.append(event)
                if not remaining:
                    return
                tasks = remaining
        if (modifier is not None and event == "OnBeforeHitAll"
                and self._compile_before_hit_zero_defence(
                    name, tasks, modifier, ctx, callback_path)):
            ctx.handled.append(event)
            return
        if (event == "OnBeforeBeingHeal" and modifier is not None
                and self._compile_before_hit_scoped_ratio(
                    name, tasks, modifier, ctx, callback_path,
                    engine_event="on_hp_increase",
                    fields={"Target_HealTakenRatio": "incoming_heal"})):
            ctx.handled.append(event)
            return
        if event in {"OnHPChange", "OnListenHPChange"}:
            for engine_event, condition in (
                    ("on_hp_decrease", "true" if event == "OnListenHPChange" else "$event.target == $self.actor_id"),
                    ("on_hp_increase", "true" if event == "OnListenHPChange" else "$event.target == $self.actor_id")):
                sub = _Context(mode="event", skill=ctx.skill, event=engine_event,
                               current_modifier=name, current_ability=ctx.current_ability,
                               value_symbols=dict(ctx.value_symbols))
                self._compile_tasks(tasks, sub, callback_path, ())
                for issue in sub.unsupported:
                    self._issue(ctx, issue["path"], issue["node_type"], issue["reason"])
                if (sub.damages or sub.pre_effects or sub.hit_effects or sub.summons
                        or sub.retarget_damage or sub.retarget_damage_records):
                    self._issue(ctx, callback_path, event, "回调伤害/召唤/分段效果尚未注册")
                ctx.lifecycle_hooks.extend(sub.lifecycle_hooks)
                ctx.lifecycle_hooks.extend(self._make_hooks(sub, condition, event=engine_event))
            ctx.handled.append(event)
            return
        if (event == "OnCustomEvent"
                and "CustomEvent_MonsterChangePhaseTrigger" in set(
                    definition.get("BehaviorFlagList") or [])):
            mapped = ("hook", "monster_phase_change_end", "$self.actor_id in $event.targets")
        elif event == "OnCustomEvent" and "STAT_DOT" in set(
                definition.get("BehaviorFlagList") or []):
            mapped = ("definition", "", "")
        elif event == "OnCustomEvent":
            mapped = ("hook", "modifier_custom_event", "$event.target == $self.actor_id")
        elif event in {"OnPhase1", "OnPhase2"} and "STAT_DOT" not in set(
                definition.get("BehaviorFlagList") or []):
            mapped = ("hook", "on_turn_start" if event == "OnPhase1" else "on_turn_end",
                      "$event.actor == $self.actor_id")
        else:
            mapped = _PASSIVE_EVENT_MAP.get(event)
        if mapped is None:
            self._issue(ctx, callback_path, event or "<missing Event>",
                        "未注册的 modifier 回调事件（_PASSIVE_EVENT_MAP 无载体）")
            return
        kind, engine_event, condition = mapped
        if kind == "definition":
            self._check_definition_consumed(name, definition, tasks, event,
                                            ctx, callback_path)
            ctx.handled.append(event)
            return
        if kind is None:
            self._issue(ctx, callback_path, event, condition)
            return
        if condition == "__limbo__":
            modifier_id = self._modifier_id(
                name, definition, str(ctx.skill.get("skill_id") or self.enemy_id))
            condition = (
                f"$event.target == $self.actor_id and hp_of($event.target) <= 0 "
                f"and has_modifier($self.actor_id, '{modifier_id}')")
        sub = _Context(mode="event", skill=ctx.skill, event=engine_event,
                       current_modifier=name, current_ability=ctx.current_ability,
                       value_symbols=dict(ctx.value_symbols),
                       modifier_stack=ctx.modifier_stack + (name,))
        self._compile_tasks(tasks, sub, callback_path, ())
        ctx.handled.extend([event, *sub.handled])
        ctx.lifecycle_hooks.extend(sub.lifecycle_hooks)
        for issue in sub.unsupported:
            self._issue(ctx, issue["path"], issue["node_type"], issue["reason"])
        ctx.summons.extend(sub.summons)
        if (sub.damages or sub.pre_effects or sub.hit_effects
                or sub.retarget_damage or sub.retarget_damage_records):
            self._issue(ctx, callback_path, event, "回调分段伤害状态尚未注册")
        ctx.lifecycle_hooks.extend(self._make_hooks(sub, condition, event=engine_event))

    def _check_definition_consumed(self, name: str, definition: Dict[str, Any],
                                   tasks: List[Dict[str, Any]], event: str,
                                   ctx: _Context, path: str) -> None:
        """definition 载体（OnStack/OnPhase1/OnPhase2/OnStage/OnCustomEvent）的消费核查——按真实
        消费点（visit_stack 走非 DoT 的 OnStack；_compile_dot 走 DoT 的 OnPhase1 及 OnStack 层数读取，
        trigger_dot 复用同一 DoT 定义结算 OnCustomEvent）逐任务核对，没有被消费点的机制任务显式拒，不静默丢。"""
        flags = set(definition.get("BehaviorFlagList") or [])
        is_dot = "STAT_DOT" in flags
        if event == "OnStack":
            if is_dot:
                consumable: set = {"RPG.GameCore.SetDynamicValueByModifierValue"}
            else:
                # 属性定义（visit_stack）+ 任务注册表（on_stack 运行时钩）双通道消费
                consumable = set(self._ONSTACK_CONSUMED_TASKS) | set(TASK_HANDLERS)
        elif not is_dot and event == "OnStage":
            consumable = set(TASK_HANDLERS)
        else:  # OnPhase1/OnPhase2/OnStage/OnCustomEvent：仅 DoT 的相位/引爆有消费点
            consumable = set(self._ONPHASE1_CONSUMED_TASKS) if (
                is_dot and event in {"OnPhase1", "OnCustomEvent"}) else set()
        for index, task in enumerate(tasks):
            node_type = str((task or {}).get("$type") or "")
            if not node_type or node_type in IGNORED_TASK_TYPES:
                continue   # 纯表现/动画节点不占消费点
            if node_type in consumable:
                continue
            if is_dot and event == "OnStack" and node_type == "RPG.GameCore.DefineDynamicValue":
                raw_key = task.get("DynamicKey") or {}
                key = raw_key.get("Value") if isinstance(raw_key, dict) else raw_key
                if key and self._dynamic_write_is_dead(task, str(key), ignore_assignment_keys=True):
                    continue
            where = (f"{event} 回调任务未被定义编译消费"
                     + ("（DoT 定义的 OnStack 仅支持层数读取）" if is_dot and event == "OnStack"
                        else "（非 DoT modifier 的相位回调无消费点）"
                        if not is_dot and event != "OnStack" else ""))
            self._issue(ctx, f"{path}/{index}", node_type or "<missing $type>", where)

    def _compile_turn_insert_action(self, task: Dict[str, Any], ctx: _Context,
                                    path: str, stack: Tuple[str, ...]) -> None:
        """TurnInsertAction（插入行动/再动）：给目标授予额外回合（决策卡 #38）。"""
        target = self._hook_target(self._alias(task), ctx)
        if target is None:
            self._issue(ctx, path, "TurnInsertAction", f"插入行动目标未注册：{self._alias(task)}")
            return
        self._add_effect(ctx, {"effect_type": "grant_extra_turn", "target": target})

    def _compile_character_leave_stage(self, task: Dict[str, Any], ctx: _Context,
                                       path: str, stack: Tuple[str, ...]) -> None:
        target = self._hook_target(self._alias(task) or "Caster", ctx)
        if target is None or task.get("ReasonKey") != "Vanish" or task.get("AliveOnly") is not False:
            self._issue(ctx, path, str(task.get("$type")),
                        "CharacterLeaveStage 仅支持 ReasonKey=Vanish 且 AliveOnly=false")
            return
        self._add_effect(ctx, {
            "effect_type": "leave_battle", "target": target, "reason": "vanish"})

    def _compile_escape_from_battle(self, task: Dict[str, Any], ctx: _Context,
                                    path: str, stack: Tuple[str, ...]) -> None:
        """EscapeFromBattle（逃逸离场）：leave_battle reason=flee（决策卡 #38）。"""
        self._add_effect(ctx, {"effect_type": "leave_battle",
                               "target": self._hook_target(self._alias(task), ctx) or "self",
                               "reason": "flee"})

    def _compile_remove_shield(self, task: Dict[str, Any], ctx: _Context,
                               path: str, stack: Tuple[str, ...]) -> None:
        """RemoveShield（移除目标护盾，决策卡 #38）。"""
        target = self._hook_target(self._alias(task), ctx)
        if target is None:
            self._issue(ctx, path, "RemoveShield", f"移除护盾目标未注册：{self._alias(task)}")
            return
        self._add_effect(ctx, {"effect_type": "remove_shield", "target": target})

    def _compile_loop_execute(self, task: Dict[str, Any], ctx: _Context,
                              path: str, stack: Tuple[str, ...]) -> None:
        """LoopExecuteTaskListWithInterval（间隔循环执行）：静态 MaxLoopCount 编译期展开；
        动态次数显式拒（DSL 禁运行时循环，循环只存在于编译期）。"""
        count = self._number(task.get("MaxLoopCount"), ctx, f"{path}/MaxLoopCount")
        if count is None or not float(count).is_integer() or count < 1:
            self._issue(ctx, path, "LoopExecuteTaskListWithInterval",
                        "循环次数需静态正整数（动态次数不展开）")
            return
        for i in range(int(count)):
            self._compile_tasks(task.get("TaskList") or [], ctx, f"{path}/Loop{i}", stack)

    def _compile_add_to_formation(self, task: Dict[str, Any], ctx: _Context,
                                  path: str, stack: Tuple[str, ...]) -> None:
        """AddEntityToTeamFormation（编队加装）：按本敌召唤规格召唤上场（与 summon 同义）。"""
        if not ctx.summons:
            return   # 无召唤规格 = 空操作
        for spec in ctx.summons:
            self._add_effect(ctx, {"effect_type": "summon", "summon_id": spec["summon_id"]})

    def _compile_attach_unselectable(self, task: Dict[str, Any], ctx: _Context,
                                     path: str, stack: Tuple[str, ...]) -> None:
        target = self._hook_target(self._alias(task) or "Caster", ctx)
        if target is None:
            self._issue(ctx, path, str(task.get("$type")), "不可选目标未注册")
            return
        self._add_effect(ctx, {
            "effect_type": "set_targetable", "target": target,
            "enemy_targetable": False, "ally_targetable": False,
        })

    def _compile_always_idle(self, task: Dict[str, Any], ctx: _Context,
                             path: str, stack: Tuple[str, ...]) -> None:
        target = self._hook_target(self._alias(task) or "Caster", ctx)
        if target is None:
            self._issue(ctx, path, str(task.get("$type")), "AlwaysIdle 目标未注册")
            return
        if task.get("On", True):
            self._add_effect(ctx, {
                "effect_type": "apply_modifier", "target": target,
                "modifier": {
                    "modifier_id": "ALWAYS_IDLE", "name": "Always Idle", "modifier_type": "debuff",
                    "duration": 0, "max_stack": 1, "stack_mode": "replace",
                    "dispellable": False, "prevent_action": True,
                },
            })
        else:
            self._add_effect(ctx, {
                "effect_type": "remove_modifier", "target": target,
                "modifier_id": "ALWAYS_IDLE", "reason": "idle_off",
            })

    def _compile_entity_action_state(self, task: Dict[str, Any], ctx: _Context,
                                     path: str, stack: Tuple[str, ...]) -> None:
        name = str(task.get("UniqueName") or "")
        target = self._hook_target(self._alias(task) or "Caster", ctx)
        if not name or target is None:
            self._issue(ctx, path, str(task.get("$type")), "ActionState 名称或目标未注册")
            return
        modifier_id = f"ENTITY_ACTION_{name}"
        if task.get("ActionState", True):
            self._add_effect(ctx, {
                "effect_type": "remove_modifier", "target": target,
                "modifier_id": modifier_id, "reason": "action_state_enable",
            })
        else:
            self._add_effect(ctx, {
                "effect_type": "apply_modifier", "target": target,
                "modifier": {
                    "modifier_id": modifier_id, "name": f"ActionState {name}",
                    "modifier_type": "debuff", "duration": 0, "max_stack": 1,
                    "stack_mode": "replace", "dispellable": False, "prevent_action": True,
                },
            })

    def _compile_set_entity_param(self, task: Dict[str, Any], ctx: _Context,
                                  path: str, stack: Tuple[str, ...]) -> None:
        """SetDynamicEntityParam（动态目标绑定）：把动态键绑定到目标实体
        （DynamicTarget 机制——后续动态目标选择按绑定取目标；决策卡 #39）。
        简单形态写入目标自身；TauntOrRandomEnemy 分离 Caster 持有者与选中值。"""
        key = str(task.get("DynamicKey") or "")
        read_alias = self._alias({"TargetType": task.get("ReadTargetType")})
        target_alias = self._alias({"TargetType": task.get("ParamTargetType")})
        if key and read_alias == "Caster" and target_alias in {
                "TauntOrRandomEnemy", "TauntOrRandomEnemyWithoutServant",
                "TauntOrRandomEnemy.RemoveServant"}:
            self._add_effect(ctx, {
                "effect_type": "set_dynamic_target", "dynamic_key": key,
                "owner": "self", "target": self._hook_target(target_alias, ctx)})
            return
        if key and target_alias.startswith("unique:") and len(target_alias) > len("unique:"):
            self._add_effect(ctx, {
                "effect_type": "set_dynamic_target", "dynamic_key": key,
                "target": {"pool": target_alias}})
            return
        if key and target_alias:
            bound_target = self._hook_target(target_alias, ctx)
            if isinstance(bound_target, dict):
                self._add_effect(ctx, {
                    "effect_type": "set_dynamic_target", "dynamic_key": key,
                    "owner": "self", "target": bound_target})
                return
        if not key or target_alias not in {"Caster", "ModifierOwnerEntity",
                                          "ModifierOwnerSummoner", "CasterSummoner"}:
            self._issue(ctx, path, "SetDynamicEntityParam",
                        f"动态目标绑定形态未注册：{target_alias}")
            return
        self._add_effect(ctx, {"effect_type": "set_dynamic_target",
                               "dynamic_key": key,
                               "target": "self" if target_alias in {"Caster", "ModifierOwnerEntity"}
                               else "summoner_of($self.actor_id)"})

    def _compile_loop_target_list(self, task: Dict[str, Any], ctx: _Context,
                                   path: str, stack: Tuple[str, ...]) -> None:
        """LoopTargetList（目标列表遍历）：对每个技能目标逐个执行 TaskList——
        效果本就按目标池逐个应用，直接内联（决策卡 #42）。"""
        tasks = [row for row in task.get("TaskList") or []
                 if not (row.get("$type") == "RPG.GameCore.GoNextTargetInList"
                         and set(row) == {"$type"})]
        self._compile_tasks(tasks, ctx, f"{path}/TaskList", stack)

    def _compile_lock_hp(self, task: Dict[str, Any], ctx: _Context,
                         path: str, stack: Tuple[str, ...]) -> None:
        """LockHP（锁血阈值）：hp_lock 锁血 modifier（决策卡 #43）。"""
        target = self._hook_target(self._alias(task) or "Caster", ctx)
        if target is None:
            self._issue(ctx, path, "LockHP", f"锁血目标未注册：{self._alias(task)}")
            return
        threshold = self._value(task.get("Threshold"), ctx, f"{path}/Threshold")
        if threshold is None:
            self._issue(ctx, path, "LockHP", "锁血阈值未注册")
            return
        self._add_effect(ctx, {"effect_type": "apply_modifier", "target": target,
                               "modifier": {"modifier_id": f"ENEMY_LOCK_HP_{self.enemy_id}",
                                            "name": "锁血", "modifier_type": "buff",
                                            "hp_lock": True, "lock_threshold": threshold,
                                            "duration": 0, "max_stack": 1, "dispellable": True}})

    def _compile_unlock_hp(self, task: Dict[str, Any], ctx: _Context,
                           path: str, stack: Tuple[str, ...]) -> None:
        target = self._hook_target(self._alias(task) or "Caster", ctx)
        if target is None:
            self._issue(ctx, path, str(task.get("$type")),
                        f"解锁血目标未注册：{self._alias(task)}")
            return
        self._add_effect(ctx, {
            "effect_type": "remove_modifier", "target": target,
            "modifier_id": f"ENEMY_LOCK_HP_{self.enemy_id}",
        })

    def _compile_set_modifier_dynamic_value(self, task: Dict[str, Any], ctx: _Context,
                                            path: str, stack: Tuple[str, ...]) -> None:
        """SetModifierDynamicValue 写具名实例的 DynamicValues，支持 Set/Add。"""
        key = str((task.get("DynamicKey") or {}).get("Value") or "")
        value = self._value(task.get("NewValue"), ctx, f"{path}/NewValue")
        target = self._hook_target(self._alias(task) or "Caster", ctx)
        raw_name = task.get("ModifierName")
        name = raw_name.get("Value") if isinstance(raw_name, dict) else raw_name
        modify_function = str(task.get("ModifyFunction") or "Set")
        if (not key or value is None or target is None or not name
                or modify_function not in {"Set", "Add"}):
            self._issue(ctx, path, "SetModifierDynamicValue", "动态键/值/目标/modifier/写入方式未注册")
            return
        if name == "ParamModifier":
            self._issue(ctx, path, "SetModifierDynamicValue", "ParamModifier 动态写入未收编")
            return
        if name == "OneMorePerTurn" and key == "OneMoreCount":
            if target != "self":
                self._issue(ctx, path, "SetModifierDynamicValue", "额外回合配额仅支持 Caster.Set/Add")
                return
            amount = value if modify_function == "Set" else _format(_binary(
                "+", _atom("dynamic_of($self.actor_id, 'OneMoreCount')"), _atom(value)))
            self._add_effect(ctx, {"effect_type": "set_dynamic_value", "target": target,
                                   "dynamic_key": key, "amount": amount})
            return
        definition = self.modifiers.get(str(name)) or {}
        if key == "Modifier_Bleed_DamagePercentage" and not definition:
            self._issue(ctx, path, "SetModifierDynamicValue", "跨技能 Bleed 动态写入未绑定实例")
            return
        modifier_id = self._modifier_id(
            str(name), definition, str(ctx.skill.get("skill_id") or self.enemy_id))
        if modifier_id != name:
            self._issue(ctx, path, "SetModifierDynamicValue", "跨技能改名 modifier 的动态写入未收编")
            return
        self._add_effect(ctx, {
            "effect_type": "set_modifier_dynamic_value", "target": target,
            "modifier_id": str(name), "dynamic_key": key, "amount": value,
            "mode": modify_function.lower()})

    def _compile_set_unique_name(self, task: Dict[str, Any], ctx: _Context,
                                 path: str, stack: Tuple[str, ...]) -> None:
        raw_name = task.get("UniqueName")
        name = raw_name.get("RawString") if isinstance(raw_name, dict) else raw_name
        target = self._hook_target(self._alias(task), ctx)
        if not name or target is None:
            self._issue(ctx, path, str(task.get("$type")), "UniqueName 名称或绑定目标未注册")
            return
        self._add_effect(ctx, {
            "effect_type": "set_dynamic_target", "dynamic_key": str(name),
            "target": target, "scope": "unique_name",
        })

    def _compile_create_battle_event(self, task: Dict[str, Any], ctx: _Context,
                                     path: str, stack: Tuple[str, ...]) -> None:
        """CreateBattleEvent（战斗事件创建）：执行 OnBattleEventCreate 创建效果
        + 注册 EventID（供 ByCompareBattleEventID 判定；决策卡 #44）。"""
        event_id = self._number(task.get("EventID"), ctx, f"{path}/EventID")
        if event_id is None or int(event_id) != event_id:
            self._issue(ctx, path, "CreateBattleEvent", "EventID 需静态整数")
            return
        self._add_effect(ctx, {"effect_type": "create_battle_event",
                               "event_id": int(event_id),
                               "team": str(task.get("Team") or "")})
        previous_retarget = ctx.retarget
        ctx.retarget = {"pool": f"unique:$battle_event:{int(event_id)}"}
        try:
            self._compile_tasks(task.get("OnBattleEventCreate") or [], ctx,
                                f"{path}/OnBattleEventCreate", stack)
        finally:
            ctx.retarget = previous_retarget

    def _compile_add_modifier(self, task: Dict[str, Any], ctx: _Context,
                              path: str, stack: Tuple[str, ...]) -> None:
        raw = task.get("ModifierName")
        name = (raw or {}).get("Value") if isinstance(raw, dict) else raw
        alias = self._alias(task)
        retarget_where = str((ctx.retarget or {}).get("where") or "") \
            if isinstance(ctx.retarget, dict) else ""
        servant_target = alias == "CasterSummonedMinions" or (
            alias == "ParamEntity" and "$it.summoner_id ==" in retarget_where)
        if str(name) == "MCommon_Servant" and servant_target:
            # 内建 Servant 标记与 summon spec 的 summoner_id 同义；公共定义存在也不重复造件。
            return
        if str(name) == "Monster_APShow" and self.modifiers.get(str(name)) is None:
            return  # 内建行动条显示件，不进入战斗状态。
        if str(name) in {"OneMore", "OneMorePerTurn"} and self.modifiers.get(str(name)) is None:
            target = self._hook_target(self._alias(task), ctx)
            if target is None:
                self._issue(ctx, path, "TargetAlias", "OneMore 目标未注册")
                return
            self._add_effect(ctx, {"effect_type": "grant_extra_turn", "target": target})
            return
        if (self.modifiers.get(str(name)) is None
                and str(name).startswith("MAvatar_AvatarChange_")
                and str(name).endswith("_ResetCameraDither")
                and not self._modifier_used_in_predicates(str(name))):
            return
        if (self.modifiers.get(str(name)) is None and str(name).startswith("Monster_APShow_")
                and not self._modifier_used_in_predicates(str(name))):
            return
        if (self.modifiers.get(str(name)) is None
                and str(name) == "Modifier_FateRin_MonsterPreview_PreCal"
                and not self._modifier_used_in_predicates(str(name))):
            return
        if self._compile_builtin_modifier(str(name), task, ctx, path):
            return
        definition = self.modifiers.get(str(name))
        if definition is None:
            raw_reference = task.get("ReferenceModifierName")
            reference = (raw_reference.get("Value") if isinstance(raw_reference, dict)
                         else raw_reference)
            if reference:
                definition = self.modifiers.get(str(reference))
        if definition is None:
            self._issue(ctx, path, str(task.get("$type")), f"modifier 定义缺失：{name}")
            return
        flags = set(definition.get("BehaviorFlagList") or [])
        if (self._visual_modifier(definition) and not self._modifier_used_in_predicates(str(name))
                and not flags):
            return
        target = self._hook_target(self._alias(task) or "Caster", ctx)
        if target is None:
            self._issue(ctx, path, "TargetAlias", f"未注册 modifier 目标：{self._alias(task)}")
            return
        chance = self._value(task.get("Chance", 1), ctx, f"{path}/Chance")
        if chance == 0:
            return
        if "STAT_DOT" in flags:
            modifier = self._compile_dot(name, task, definition, ctx, path)
        else:
            modifier = self._compile_property_modifier(name, task, definition, ctx, path)
        if modifier is None or chance is None:
            return
        previous_symbols = ctx.value_symbols
        symbols = dict(previous_symbols)
        dynamic_values: Dict[str, Any] = {}
        for key, raw in (task.get("DynamicValues") or {}).items():
            value = self._value(raw, ctx, f"{path}/DynamicValues/{key}")
            if value is None:
                return
            dynamic_values[str(key)] = value
            symbols[dynamic_value_hash(str(key))] = value
        if dynamic_values:
            modifier["dynamic_values"] = dynamic_values
        ctx.value_symbols = symbols
        try:
            self._compile_modifier_lifecycle(str(name), definition, modifier, ctx, path)
        finally:
            ctx.value_symbols = previous_symbols
        self._add_effect(ctx, {
            "effect_type": "apply_modifier", "target": target,
            "apply_chance": chance, "modifier": modifier,
        })

    @staticmethod
    def _modifier_id(name: str, definition: Dict[str, Any], skill_id: str) -> str:
        kind = next((str(flag).split("STAT_DOT_", 1)[1] for flag in
                     definition.get("BehaviorFlagList") or []
                     if str(flag).startswith("STAT_DOT_")), "")
        if "AttackSign" in set(definition.get("BehaviorFlagList") or []):
            return f"ENEMY_{skill_id}_LOCK_ON"
        return f"ENEMY_{skill_id}_{kind.upper()}" if kind else name

    def _modifier_defaults(self, name: str, task: Dict[str, Any], definition: Dict[str, Any],
                           ctx: _Context, path: str) -> Optional[Dict[str, Any]]:
        duration = self._value(task.get("LifeTime", definition.get("LifeTime", 0)),
                               ctx, f"{path}/LifeTime")
        maximum = self._value(task.get("MaxLayer", definition.get("MaxLayer", 1)),
                              ctx, f"{path}/MaxLayer")
        raw_stacks = task.get("LayerAddWhenStack", definition.get("LayerAddWhenStack", 1))
        stack_expr = (raw_stacks.get("PostfixExpr") or {}) if isinstance(raw_stacks, dict) else {}
        default_single = (stack_expr.get("OpCodes") == "AQAR"
                          and not stack_expr.get("FixedValues")
                          and stack_expr.get("DynamicHashes") == [_DEFAULT_LAYER_ADD_HASH])
        stacks = 1 if default_single else self._value(raw_stacks, ctx, f"{path}/LayerAddWhenStack")
        if duration is None or maximum is None or stacks is None:
            return None
        stacking = definition.get("Stacking") or "Refresh"
        stack_mode = {"Replace": "replace", "ReplaceByCaster": "refresh",
                      "Refresh": "refresh", "Merge": "refresh", "Prolong": "refresh",
                      "ReplaceButKeepLifeTime": "replace_keep_duration",
                      "RetainGlobalLatestUnique": "replace", "Multiple": "multiple"}.get(stacking)
        if stack_mode is None:
            self._issue(ctx, path, "ModifierStacking", f"未注册叠加语义：{stacking}")
            return None
        flags = set(definition.get("BehaviorFlagList") or [])
        return {
            "duration": int(duration) if _is_number(duration) else duration,
            "max_stack": int(maximum) if _is_number(maximum) else maximum,
            "stacks": int(stacks) if _is_number(stacks) else stacks,
            "stack_mode": stack_mode, "dispellable": "CannotDispel" not in flags,
            **({"singleton_group": f"global:{name}"}
               if stacking == "RetainGlobalLatestUnique" else {}),
            **({"behavior_flags": sorted(flags, key=str)} if flags else {}),
            **({"remove_on_source_death": True} if "RemoveWhenCasterDead" in flags else {}),
        }

    def _compile_dot(self, name: str, task: Dict[str, Any], definition: Dict[str, Any],
                     ctx: _Context, path: str) -> Optional[Dict[str, Any]]:
        defaults = self._modifier_defaults(name, task, definition, ctx, path)
        if defaults is None:
            return None
        symbols = dict(self.dynamic_symbols)
        for key, raw in (task.get("DynamicValues") or {}).items():
            value = self._value(raw, ctx, f"{path}/DynamicValues/{key}")
            if value is not None:
                symbols[dynamic_value_hash(str(key))] = value
        damage = None
        for callback in definition.get("_CallbackList") or []:
            event = callback.get("Event")
            if event not in {"OnPhase1", "OnCustomEvent", "OnStack"}:
                continue
            for item in callback.get("CallbackConfig") or []:
                node_type = str(item.get("$type") or "")
                if self._presentation_only([item]):
                    continue
                if node_type == "RPG.GameCore.SetDynamicValueByModifierValue":
                    if item.get("ValueType") != "Layer" or self._number(
                            item.get("Multiplier", 1), ctx, path) != 1:
                        self._issue(ctx, path, node_type, "只支持一比一读取 DoT 层数")
                        continue
                    symbols[dynamic_value_hash(str(item.get("DynamicKey")))] = \
                        "max(1, $modifier.stacks)"
                elif event not in {"OnPhase1", "OnCustomEvent"}:
                    continue
                elif node_type == "RPG.GameCore.SetDynamicValueByProperty":
                    alias = self._alias({"TargetType": item.get("ReadTargetType")})
                    prop = str(item.get("Value") or "")
                    if alias == "SnapshotPropertyEntity":
                        dot_property = {"MaxHP": "$snapshot.max_hp", "Attack": "$snapshot.atk"}.get(prop)
                    elif alias in {"", "ModifierOwnerEntity"}:
                        dot_property = {"MaxHP": "$self.max_hp", "CurrentHP": "$self.hp",
                                        "Attack": "$self.atk" if alias else "$snapshot.atk"}.get(prop)
                    else:
                        dot_property = None
                    if dot_property is None:
                        self._issue(ctx, path, node_type,
                                    f"未注册 DoT 属性/读取目标：{alias} / {item.get('Value')}")
                        continue
                    symbols[dynamic_value_hash(str(item.get("DynamicKey")))] = dot_property
                elif node_type == "RPG.GameCore.SetDynamicValue":
                    raw_key = item.get("DynamicKey") or {}
                    key = raw_key.get("Value") if isinstance(raw_key, dict) else raw_key
                    if not key or self._alias(item) not in {"", "ModifierOwnerEntity"}:
                        self._issue(ctx, path, node_type, "DoT 动态赋值的键/目标未注册")
                        continue
                    value = self._value(item.get("Value"), ctx, f"{path}/SetDynamicValue/{key}", symbols)
                    if value is not None:
                        symbols[dynamic_value_hash(str(key))] = value
                elif node_type == "RPG.GameCore.PredicateTaskList":
                    branch_values: Dict[str, Any] = {}
                    branch_key = None
                    valid = True
                    for branch_name in ("SuccessTaskList", "FailedTaskList"):
                        branch = [task for task in item.get(branch_name) or []
                                  if str(task.get("$type") or "") not in IGNORED_TASK_TYPES]
                        if len(branch) != 1 or branch[0].get("$type") != "RPG.GameCore.SetDynamicValue":
                            valid = False
                            break
                        assignment = branch[0]
                        raw_key = assignment.get("DynamicKey") or {}
                        key = raw_key.get("Value") if isinstance(raw_key, dict) else raw_key
                        if not key or (branch_key is not None and key != branch_key) \
                                or self._alias(assignment) not in {"", "ModifierOwnerEntity"}:
                            valid = False
                            break
                        branch_key = str(key)
                        value = self._value(assignment.get("Value"), ctx,
                                            f"{path}/{branch_name}/{key}", symbols)
                        if value is None:
                            valid = False
                            break
                        branch_values[branch_name] = value
                    if not valid:
                        self._issue(ctx, path, node_type, "DoT 条件分支仅支持双分支对同一持有者键赋值")
                        continue
                    previous_symbols = ctx.value_symbols
                    ctx.value_symbols = symbols
                    try:
                        predicate = self._predicate_expr(item.get("Predicate") or {}, ctx,
                                                         f"{path}/DoTPredicate", allow_written=True)
                    finally:
                        ctx.value_symbols = previous_symbols
                    if predicate is not None:
                        symbols[dynamic_value_hash(str(branch_key))] = (
                            f"(({predicate}) ? ({branch_values['SuccessTaskList']}) : "
                            f"({branch_values['FailedTaskList']}))")
                elif node_type == "RPG.GameCore.DamageByAttackProperty" and event == "OnPhase1":
                    damage = item
        if damage is None:
            self._issue(ctx, path, "ModifierDOT", "OnPhase1 缺 DoT DamageByAttackProperty")
            return None
        attack = damage.get("AttackProperty") or {}
        ratio = None
        ratio_fields = [field for field in ("DamageValue", "DamagePercentage", "BreakDamagePercentage")
                        if field in attack]
        for index, field in enumerate(ratio_fields):
            issue_count = len(ctx.unsupported)
            ratio = self._value(attack[field], ctx, f"{path}/DOT/{field}", symbols)
            if ratio is not None:
                break
            if index + 1 < len(ratio_fields):
                del ctx.unsupported[issue_count:]
        if ratio is None:
            self._issue(ctx, path, "ModifierDOT", "DoT 伤害倍率缺失或无法解析")
            return None
        kind = next((str(flag).split("STAT_DOT_", 1)[1] for flag in
                     definition.get("BehaviorFlagList") or [] if str(flag).startswith("STAT_DOT_")),
                    "dot")
        skill_id = str(ctx.skill.get("skill_id") or self.enemy_id)
        return {
            "modifier_id": self._modifier_id(name, definition, skill_id),
            "name": kind.capitalize(), "modifier_type": "dot",
            "dot_element": _element(attack.get("DamageType")),
            "dot_ratio_expr": ratio if isinstance(ratio, str) else str(ratio),
            "dot_base_chance": self._number(task.get("Chance", 1), ctx, f"{path}/Chance"),
            **defaults,
        }

    def _compile_property_modifier(self, name: str, task: Dict[str, Any],
                                   definition: Dict[str, Any], ctx: _Context,
                                   path: str) -> Optional[Dict[str, Any]]:
        callbacks = definition.get("_CallbackList") or []
        flags = set(definition.get("BehaviorFlagList") or [])
        grants_immune = ["debuff", "dot", "control"] if "ImmuneDebuff" in flags else []
        if "AttackSign" in flags and all(
                callback.get("Event") == "OnCreate" and not callback.get("CallbackConfig")
                for callback in callbacks):
            defaults = self._modifier_defaults(name, task, definition, ctx, path)
            if defaults is None:
                return None
            defaults["stack_mode"] = "replace"
            skill_id = str(ctx.skill.get("skill_id") or self.enemy_id)
            return {
                "modifier_id": self._modifier_id(name, definition, skill_id),
                "name": name, "modifier_type": "debuff", "lock_on": True, **defaults,
            }
        defaults = self._modifier_defaults(name, task, definition, ctx, path)
        if defaults is None:
            return None
        symbols = dict(self.dynamic_symbols)
        for key, raw in (task.get("DynamicValues") or {}).items():
            value = self._value(raw, ctx, f"{path}/DynamicValues/{key}")
            if value is not None:
                symbols[dynamic_value_hash(str(key))] = value
        max_layer_hash = dynamic_value_hash("MDF_MaxLayer")
        if (str(max_layer_hash) in ((definition.get("DynamicValues") or {}).get("Floats") or {})
                and max_layer_hash not in symbols):
            skill_id = str(ctx.skill.get("skill_id") or self.enemy_id)
            parent_id = self._modifier_id(name, definition, skill_id)
            symbols[max_layer_hash] = f"modifier_max_stacks($self.actor_id, '{parent_id}')"
        stats: Dict[str, Any] = {}
        overrides: Dict[str, Any] = {}
        toughness_lock = False
        custom_unselectable: Dict[str, set[str]] = {}
        protected_weakness: set[str] = set()
        weakness_add: set[str] = set()
        weakness_override: Optional[set[str]] = None
        secret_weakness: set[str] = set()
        locked_action_types: List[str] = []
        allow_negative_hp = False
        scoped_hit_values: Dict[str, Any] = {}
        has_cleanup = False
        previous_modifier = ctx.current_modifier
        previous_condition = ctx.condition
        previous_value_symbols = ctx.value_symbols
        ctx.value_symbols = symbols
        ctx.current_modifier = name

        runtime_stack_tasks: List[Dict[str, Any]] = []

        def visit_stack(tasks: Iterable[Dict[str, Any]]) -> None:
            ctx.current_modifier = name
            nonlocal toughness_lock, allow_negative_hp, weakness_override, secret_weakness
            for item in tasks:
                node_type = str(item.get("$type") or "")
                if node_type in IGNORED_TASK_TYPES:
                    continue
                if node_type == "RPG.GameCore.PredicateTaskList":
                    if (self._presentation_only(item.get("SuccessTaskList") or [])
                            and self._presentation_only(item.get("FailedTaskList") or [])):
                        continue
                    branch = self._static_monster_predicate(item.get("Predicate") or {})
                    if branch is not None:
                        visit_stack(item.get("SuccessTaskList" if branch else "FailedTaskList") or [])
                        continue
                    # 运行时条件属性分支（决策卡 #36）：谓词可翻则属性改条件表达式
                    predicate = self._predicate_expr(
                        item.get("Predicate") or {}, ctx, f"{path}/Predicate",
                        allow_written=self._predicate_reads_written(item.get("Predicate") or {}, ctx))
                    if predicate is None:
                        self._issue(ctx, path, node_type, "OnStack 属性分支谓词未注册")
                        continue
                    branch_values: Dict[str, Dict[str, Any]] = {"SuccessTaskList": {},
                                                                "FailedTaskList": {}}
                    for branch_name, branch_tasks in (
                            ("SuccessTaskList", item.get("SuccessTaskList") or []),
                            ("FailedTaskList", item.get("FailedTaskList") or [])):
                        branch_condition = predicate if branch_name == "SuccessTaskList"                             else self._negate_condition(predicate)
                        for task in branch_tasks:
                            if str(task.get("$type")) in IGNORED_TASK_TYPES:
                                continue
                            task_type = str(task.get("$type"))
                            if task_type not in {"RPG.GameCore.StackProperty",
                                                 "RPG.GameCore.StackStatusResistance",
                                                 "RPG.GameCore.StackWeakResistance"}:
                                if task_type in TASK_HANDLERS:
                                    runtime_stack_tasks.append((task, branch_condition))
                                else:
                                    self._issue(ctx, path, task_type,
                                                "OnStack 条件分支的非属性任务待收编")
                                continue
                            if task_type == "RPG.GameCore.StackProperty" \
                                    and task.get("Property") == "RallyHP":
                                runtime_stack_tasks.append((task, branch_condition))
                                continue
                            if task_type == "RPG.GameCore.StackWeakResistance":
                                if self._alias(task) not in {"", "Caster", "ModifierOwnerEntity"}:
                                    self._issue(ctx, path, task_type, "条件分支仅支持父件自身的弱点抵抗")
                                    continue
                                entries = task.get("StackResistanceList") or []
                                if not entries:
                                    self._issue(ctx, path, task_type, "StackWeakResistance 缺抗性列表")
                                for index, entry in enumerate(entries):
                                    element = _element(entry.get("DamageType"))
                                    value = self._value(entry.get("Value"), ctx,
                                                        f"{path}/StackResistanceList/{index}/Value", symbols)
                                    if element is None or value is None:
                                        self._issue(ctx, path, task_type,
                                                    f"抗性元素/数值未注册：{entry.get('DamageType')}")
                                        continue
                                    branch_values[branch_name][f"res_{element}"] = value
                                continue
                            if task_type == "RPG.GameCore.StackStatusResistance":
                                if (self._alias(task) not in {"", "Caster", "ModifierOwnerEntity"}
                                        or task.get("BehaviorFlag") not in {"STAT_CTRL", "Taunt"}):
                                    self._issue(ctx, path, task_type,
                                                "仅支持父件自身的 STAT_CTRL/Taunt 类型抵抗")
                                    continue
                                stat = "control_type_res"
                            else:
                                property_specs = self._stack_property_spec(task, ctx, path, symbols)
                                if any(is_override for _stat, _value, is_override in property_specs):
                                    self._issue(ctx, path, task_type, "条件分支中的覆写属性尚未注册")
                                    continue
                                for stat, value, _override in property_specs:
                                    branch_values[branch_name][stat] = value
                                continue
                            if stat is None:
                                self._issue(ctx, path, task_type,
                                            f"未注册属性：{task.get('Property')}")
                                continue
                            raw_value = (task.get("Resistance") if task_type.endswith("StackStatusResistance")
                                         else task.get("PropertyValue"))
                            value = self._value(raw_value, ctx, f"{path}/StackProperty/{stat}", symbols)
                            if value is not None:
                                branch_values[branch_name][stat] = value
                    for stat, success_value in branch_values["SuccessTaskList"].items():
                        failed_value = branch_values["FailedTaskList"].get(stat, 0)
                        # 双分支合一条件表达式：cond ? 成功值 : 失败值（缺省 0）
                        stats[stat] = f"(({predicate}) ? ({success_value}) : ({failed_value}))"
                elif node_type == "RPG.GameCore.SetDynamicValueByModifierValue":
                    if item.get("ValueType") == "Layer":
                        symbols[dynamic_value_hash(str(item.get("DynamicKey")))] = \
                            "max(1, $modifier.stacks)"
                elif node_type == "RPG.GameCore.StackProperty":
                    prop = str(item.get("Property") or "")
                    if prop == "RallyHP":
                        runtime_stack_tasks.append((item, None))
                        continue
                    element = (_element(prop.removesuffix("TakenRatio"))
                               if prop.endswith("TakenRatio") else None)
                    if element not in {value.lower() for value in self._ALL_WEAKNESS}:
                        element = None
                    if element:
                        value = self._value(item.get("PropertyValue"), ctx,
                                            f"{path}/StackProperty/{prop}", symbols)
                        if value is not None:
                            scoped_hit_values[element] = value
                        continue
                    for stat, value, is_override in self._stack_property_spec(
                            item, ctx, f"{path}/StackProperty", symbols):
                        if is_override:
                            overrides[stat] = value
                        else:
                            stats[stat] = value
                elif node_type == "RPG.GameCore.StackStatusResistance":
                    if (self._alias(item) not in {"", "Caster", "ModifierOwnerEntity"}
                            or item.get("BehaviorFlag") not in {"STAT_CTRL", "Taunt"}):
                        self._issue(ctx, path, node_type, "仅支持父件自身的 STAT_CTRL/Taunt 类型抵抗")
                        continue
                    value = self._value(item.get("Resistance"), ctx,
                                        f"{path}/StackStatusResistance/control_type_res", symbols)
                    if value is not None:
                        stats["control_type_res"] = value
                elif node_type == "RPG.GameCore.EnableNegativeHP":
                    allow_negative_hp = True
                elif node_type == "RPG.GameCore.AttachSkillTypeDisable":
                    raw_types = [str(value) for value in item.get("Types") or []]
                    mapped = [{"Ultra": "ultimate", "Normal": "basic", "Skill": "skill"}.get(value)
                              for value in raw_types]
                    if not raw_types or item.get("ControlSkillTypes") or any(value is None for value in mapped):
                        self._issue(ctx, path, node_type,
                                    f"AttachSkillTypeDisable 类型未注册：{raw_types or item.get('ControlSkillTypes')}")
                    else:
                        locked_action_types.extend(mapped)
                elif node_type == "RPG.GameCore.StackWeakResistance":
                    entries = item.get("StackResistanceList") or []
                    if not entries:
                        self._issue(ctx, path, node_type, "StackWeakResistance 缺抗性列表")
                    for index, entry in enumerate(entries):
                        element = _element(entry.get("DamageType"))
                        value = self._value(entry.get("Value"), ctx,
                                            f"{path}/StackResistanceList/{index}/Value", symbols)
                        if element is None or value is None:
                            self._issue(ctx, path, node_type,
                                        f"抗性元素/数值未注册：{entry.get('DamageType')}")
                            continue
                        stats[f"res_{element}"] = value
                elif node_type == "RPG.GameCore.StackWeakness" and item.get("OPType") == "Protected":
                    elements = set(self._weakness_list(item, "WeakList"))
                    if not elements or elements - self._ALL_WEAKNESS \
                            or self._hook_target(self._alias(item), ctx) != "self":
                        self._issue(ctx, path, node_type, "Protected 目标或元素未注册")
                        continue
                    if elements == self._ALL_WEAKNESS:
                        toughness_lock = True
                    else:
                        protected_weakness.update(_element(element) for element in elements)
                elif node_type == "RPG.GameCore.StackWeakness" \
                        and item.get("OPType") in {None, "Attach"}:
                    elements = set(self._weakness_list(item, "WeakList"))
                    secrets = set(self._weakness_list(item, "SecretList"))
                    if (elements - self._ALL_WEAKNESS or secrets - self._ALL_WEAKNESS
                            or self._hook_target(self._alias(item), ctx) != "self"):
                        self._issue(ctx, path, node_type, "WeakList/SecretList 目标或元素未注册")
                        continue
                    if item.get("OPType") is None:
                        weakness_override = {_element(element) for element in elements}
                        secret_weakness = {_element(element) for element in secrets}
                    else:
                        weakness_add.update(_element(element) for element in elements)
                elif node_type == "RPG.GameCore.ClearWeakness" and item.get("OPType") == "Protected":
                    elements = set(self._weakness_list(item, "WeakList"))
                    if not elements or elements - self._ALL_WEAKNESS \
                            or self._hook_target(self._alias(item), ctx) != "self":
                        self._issue(ctx, path, node_type, "Protected 清除目标或元素未注册")
                        continue
                    if elements == self._ALL_WEAKNESS:
                        toughness_lock = False
                        protected_weakness.clear()
                    else:
                        protected_weakness.difference_update(_element(element) for element in elements)
                elif node_type == "RPG.GameCore.StackCustomUnselectable":
                    condition = item.get("Condition") or {}
                    raw_name = str((condition.get("ModifierName") or {}).get("Value") or "")
                    raw_teams = item.get("TeamTypes")
                    team_values = ([raw_teams] if isinstance(raw_teams, str)
                                   else raw_teams if isinstance(raw_teams, list) else [])
                    teams = [{"TeamLight": "light", "TeamDark": "dark",
                              "TeamNeutral": "neutral"}.get(team) for team in team_values]
                    if (set(item) - {"$type", "TeamTypes", "EntityTypes", "Condition"}
                            or item.get("EntityTypes") != "All"
                            or condition.get("$type") != "RPG.GameCore.ByIsContainModifier"
                            or set(condition) - {"$type", "TargetType", "ModifierName"}
                            or self._alias(condition) != "ParamEntity" or not raw_name
                            or not teams or any(team is None for team in teams)):
                        self._issue(ctx, path, node_type,
                                    "仅支持 All 实体与 ParamEntity 单 modifier 条件的来源不可选规则")
                        continue
                    skill_id = str(ctx.skill.get("skill_id") or self.enemy_id)
                    source_modifier = self._modifier_id(
                        raw_name, self.modifiers.get(raw_name) or {}, skill_id)
                    custom_unselectable.setdefault(source_modifier, set()).update(teams)
                elif node_type == "RPG.GameCore.LockStance":
                    ratio = self._number(item.get("StanceValueRatio"), ctx,
                                         f"{path}/StanceValueRatio", symbols)
                    if ratio is None:
                        continue
                    if ratio not in {0, 1}:
                        self._issue(ctx, path, node_type,
                                    "锁韧仅支持 StanceValueRatio=0 或满值恢复 1")
                        continue
                    if self._hook_target(self._alias(item) or "ModifierOwnerEntity", ctx) != "self":
                        self._issue(ctx, path, node_type, "OnStack 锁韧目标必须是 modifier 持有者")
                        continue
                    toughness_lock = True
                    if ratio == 1:
                        runtime_stack_tasks.append(({
                            "$type": "RPG.GameCore.ResetStance",
                            "TargetType": {"$type": "RPG.GameCore.TargetAlias",
                                           "Alias": "ModifierOwnerEntity"},
                        }, None))
                elif node_type == "RPG.GameCore.SetDynamicValue":
                    raw_key = item.get("DynamicKey") or item.get("Key") or {}
                    key = raw_key.get("Value") if isinstance(raw_key, dict) else raw_key
                    raw_value = item.get("Value")
                    if not key or raw_value is None:
                        self._issue(ctx, path, node_type, "OnStack 动态键/值缺失")
                        continue
                    value = self._value(raw_value, ctx, f"{path}/SetDynamicValue", symbols)
                    if value is None:
                        continue
                    symbols[dynamic_value_hash(str(key))] = value
                    runtime_stack_tasks.append((item, None))
                elif node_type in TASK_HANDLERS:
                    # 叠层触发型行为（AddModifier/LockHP 等）——编译为 after_apply_modifier 运行时钩
                    runtime_stack_tasks.append((item, None))
                else:
                    self._issue(ctx, path, node_type, "OnStack 回调任务未被定义编译消费")

        for callback in callbacks:
            event = callback.get("Event")
            if event in {"OnPhase2", "OnStage"}:
                before = len(ctx.effects)
                ctx.current_modifier = name
                ctx.condition = self._and_condition(
                    previous_condition, f"has_modifier($self.actor_id, '{name}')")
                self._compile_tasks(callback.get("CallbackConfig") or [], ctx,
                                    f"{path}/{event}", ())
                has_cleanup = has_cleanup or len(ctx.effects) > before
                ctx.condition = previous_condition
                ctx.current_modifier = previous_modifier
                continue
            if event == "OnStack":
                visit_stack(callback.get("CallbackConfig") or [])
                if runtime_stack_tasks and name not in ctx.modifier_stack:
                    skill_id = str(ctx.skill.get("skill_id") or self.enemy_id)
                    modifier_id = self._modifier_id(name, definition, skill_id)
                    for task, branch_condition in runtime_stack_tasks:
                        sub = _Context(mode="event", skill=ctx.skill,
                                       event="after_apply_modifier", current_modifier=name,
                                       current_ability=ctx.current_ability,
                                       value_symbols=dict(symbols),
                                       modifier_stack=ctx.modifier_stack + (name,))
                        self._compile_tasks([task], sub, f"{path}/OnStack", ())
                        ctx.handled.extend(sub.handled)
                        ctx.lifecycle_hooks.extend(sub.lifecycle_hooks)
                        for issue in sub.unsupported:
                            self._issue(ctx, issue["path"], issue["node_type"], issue["reason"])
                        condition = (f"$event.modifier_id == '{modifier_id}' "
                                     f"and $event.target == $self.actor_id")
                        if branch_condition is not None:
                            condition = f"({condition}) and ({branch_condition})"
                        ctx.lifecycle_hooks.extend(
                            self._make_hooks(sub, condition, event="after_apply_modifier"))
        ctx.value_symbols = previous_value_symbols
        ctx.current_modifier = previous_modifier
        # 生命周期声明保留部分结果；纯表现与否由 _visual_modifier 独立判定。
        has_lifecycle = bool(ctx.lifecycle_hooks) or any(
            callback.get("Event") in {"OnCreate", "OnDestroy", "OnBeforeDying"}
            for callback in callbacks)
        # 主动/被动共用同一映射；含机制内容的已映射回调属于 modifier 语义。
        has_mapped = any(
            (str(callback.get("Event") or "") in _PASSIVE_EVENT_MAP
             or str(callback.get("Event") or "") in {"OnHPChange", "OnListenHPChange"}
             or (str(callback.get("Event") or "") == "OnCustomEvent"
                 and "CustomEvent_MonsterChangePhaseTrigger" in flags))
            and not self._presentation_only(callback.get("CallbackConfig") or [])
            for callback in callbacks)
        if (not stats and not overrides and not toughness_lock and not custom_unselectable
                and not protected_weakness and not weakness_add
                and weakness_override is None and not secret_weakness
                and not locked_action_types and not allow_negative_hp and not grants_immune
                and not has_cleanup and not has_lifecycle and not scoped_hit_values
                and not has_mapped and not self._visual_modifier(definition)
                and "RemoveWhenCasterDead" not in flags):
            self._issue(ctx, path, "Modifier", f"未注册 modifier 语义：{name}")
            return None
        if scoped_hit_values and (stats or overrides):
            self._issue(ctx, path, "Modifier",
                        f"元素承伤命中域不能与普通面板属性混挂同件：{name}")
            return None
        skill_id = str(ctx.skill.get("skill_id") or self.enemy_id)
        stat_effects = {key: value for key, value in stats.items() if not isinstance(value, str)}
        stat_exprs = {key: value for key, value in stats.items() if isinstance(value, str)}
        modifier_type = "buff"
        for stat, value in stats.items():
            if (isinstance(value, str) or (stat == "vulnerability" and value > 0)
                    or (stat != "vulnerability" and value < 0)):
                modifier_type = "debuff"  # 未判号或任一减益项保持保守口径。
                break
        hit_fields: Dict[str, Any] = {}
        if scoped_hit_values:
            elements = sorted(scoped_hit_values)
            hit_condition = " or ".join(f"$event.damage_type == '{element}'" for element in elements)
            value_expression = ""
            for element in reversed(elements):
                value = scoped_hit_values[element]
                value_expression = (str(value) if not value_expression else
                                    f"($event.damage_type == '{element}' ? ({value}) : ({value_expression}))")
            hit_fields = {"hit_condition": hit_condition,
                          "hit_stat_exprs": {"vulnerability": value_expression}}
            if any(isinstance(value, str) or value > 0 for value in scoped_hit_values.values()):
                modifier_type = "debuff"
        override_exprs = {stat: value for stat, value in overrides.items() if isinstance(value, str)}
        overrides = {stat: value for stat, value in overrides.items() if not isinstance(value, str)}
        return {
            "modifier_id": self._modifier_id(name, definition, skill_id),
            "name": name, "modifier_type": "debuff" if "AttackSign" in flags else modifier_type,
            **({"lock_on": True} if "AttackSign" in flags else {}),
            **({"stat_effects": stat_effects} if stat_effects else {}),
            **({"stat_exprs": stat_exprs} if stat_exprs else {}),
            **hit_fields,
            **({"override_effects": overrides} if overrides else {}),
            **({"override_exprs": override_exprs} if override_exprs else {}),
            **({"toughness_lock": True} if toughness_lock else {}),
            **({"custom_unselectable": {key: sorted(teams)
                                               for key, teams in custom_unselectable.items()}}
               if custom_unselectable else {}),
            **({"protected_weakness": sorted(protected_weakness)} if protected_weakness else {}),
            **({"weakness_add": sorted(weakness_add)} if weakness_add else {}),
            **({"weakness_override": sorted(weakness_override)}
               if weakness_override is not None else {}),
            **({"secret_weakness": sorted(secret_weakness)} if secret_weakness else {}),
            **({"locked_action_types": sorted(set(locked_action_types))} if locked_action_types else {}),
            **({"allow_negative_hp": True} if allow_negative_hp else {}),
            **({"grants_immune": grants_immune} if grants_immune else {}), **defaults,
        }

    def _compile_init_shield(self, task: Dict[str, Any], ctx: _Context,
                             path: str, stack: Tuple[str, ...]) -> None:
        target = self._hook_target(self._alias(task) or "Caster", ctx)
        shield: Dict[str, Any] = {}
        if "ShieldValue" in task:
            value = self._value(task.get("ShieldValue"), ctx, f"{path}/ShieldValue")
            if value is None:
                self._issue(ctx, path, str(task.get("$type")), "ShieldValue 未注册")
                return
            shield["flat"] = value
        formula = task.get("FormulaType")
        if formula is not None:
            if formula != "ShieldByCasterMaxHP":
                self._issue(ctx, path, str(task.get("$type")), f"护盾公式未注册：{formula}")
                return
            percentage = self._value(task.get("ShieldPercentage"), ctx, f"{path}/ShieldPercentage")
            if percentage is None:
                self._issue(ctx, path, str(task.get("$type")), "ShieldPercentage 未注册")
                return
            shield["scaling"] = {"hp": percentage}
        if target is None or not shield:
            self._issue(ctx, path, str(task.get("$type")), "护盾目标或数值未注册")
            return
        skill_id = str(ctx.skill.get("skill_id") or self.enemy_id)
        if ctx.current_modifier:
            definition = self.modifiers.get(ctx.current_modifier) or {}
            shield["modifier_id"] = self._modifier_id(
                ctx.current_modifier, definition, skill_id)
        self._add_effect(ctx, {
            "effect_type": "apply_modifier", "target": target,
            "modifier": {
                "modifier_id": f"ENEMY_{skill_id}_INIT_SHIELD", "name": "Init Shield",
                "modifier_type": "buff", "duration": 0, "max_stack": 1,
                "stack_mode": "replace", "dispellable": True, "shield": shield,
            },
        })

    def _compile_shield_update(self, task: Dict[str, Any], ctx: _Context,
                               path: str, maximum: bool) -> None:
        operation = task.get("ModifyOp") or ("Set" if maximum else "Add")
        if (maximum and operation != "Set") or (not maximum and operation not in {"Set", "Add"}):
            self._issue(ctx, path, str(task.get("$type")),
                        f"盾值操作未收编：{operation} / max={maximum}")
            return
        target = self._hook_target(self._alias(task) or "Caster", ctx)
        modifier_ids = task.get("ShieldModifiers") or []
        value = self._value(task.get("FormulaValue"), ctx, f"{path}/FormulaValue")
        if (target is None or not isinstance(modifier_ids, list) or not modifier_ids
                or any(not isinstance(item, str) or not item for item in modifier_ids)):
            self._issue(ctx, path, str(task.get("$type")), "盾值目标或 ShieldModifiers 未注册")
            return
        if value is None or (_is_number(value) and value < 0):
            self._issue(ctx, path, str(task.get("$type")), "盾值/上限需要非负数值")
            return
        self._add_effect(ctx, {
            "effect_type": "modify_shield", "target": target, "max": maximum,
            "modifier_ids": list(modifier_ids), "amount": value,
            "mode": operation.lower(),
            **({"allow_expand_max": bool(task.get("AllowExpandMax"))} if not maximum else {}),
        })

    def _compile_modify_shield_max(self, task: Dict[str, Any], ctx: _Context,
                                   path: str, stack: Tuple[str, ...]) -> None:
        self._compile_shield_update(task, ctx, path, True)

    def _compile_modify_shield(self, task: Dict[str, Any], ctx: _Context,
                               path: str, stack: Tuple[str, ...]) -> None:
        self._compile_shield_update(task, ctx, path, False)

    def _compile_set_hp(self, task: Dict[str, Any], ctx: _Context,
                        path: str, stack: Tuple[str, ...]) -> None:
        if set(task) - {"$type", "TargetType", "ModifyValue", "ModifyRatio", "ShowText",
                        "SourceType"} or ("ModifyValue" in task) == ("ModifyRatio" in task):
            self._issue(ctx, path, str(task.get("$type")), "SetHP 字段变体未收编")
            return
        source_alias = self._alias({"TargetType": task.get("SourceType")})
        if "SourceType" in task and (source_alias != "Caster" or not ctx.current_modifier):
            self._issue(ctx, path, str(task.get("$type")),
                        "SetHP.SourceType 仅支持 modifier 回调内的 Caster")
            return
        field = "ModifyValue" if "ModifyValue" in task else "ModifyRatio"
        value = self._value(task.get(field), ctx, f"{path}/{field}")
        target = self._hook_target(self._alias(task), ctx)
        if value is None or target is None:
            self._issue(ctx, path, str(task.get("$type")),
                        f"HP 数值或目标未注册：{self._alias(task)}")
            return
        percent = (_format(_binary("/", _atom(value), _atom("$target.max_hp")))
                   if field == "ModifyValue" else value)
        effect = {"effect_type": "set_hp_to_percent", "target": target, "percent": percent}
        if source_alias:
            definition = self.modifiers.get(ctx.current_modifier) or {}
            modifier_id = self._modifier_id(
                ctx.current_modifier, definition, str(ctx.skill.get("skill_id") or self.enemy_id))
            effect["source"] = f"modifier:{modifier_id}"
        self._add_effect(ctx, effect)

    def _compile_heal_hp(self, task: Dict[str, Any], ctx: _Context,
                         path: str, stack: Tuple[str, ...]) -> None:
        formula = task.get("FormulaType", "HealByHealerAttack")
        if formula not in {"HealByTargetMaxHP", "HealByHealerMaxHP", "HealByBaseValue",
                           "HealByHealerAttack"}:
            self._issue(ctx, path, str(task.get("$type")), f"未注册治疗公式：{formula}")
            return
        fields = [field for field in ("HealPercentage", "ModifyValue") if field in task]
        if len(fields) != 1:
            self._issue(ctx, path, str(task.get("$type")),
                        "治疗需要且只能声明 HealPercentage 或 ModifyValue 之一")
            return
        if task.get("AliveOnly") is False:
            self._issue(ctx, path, str(task.get("$type")), "复活/死亡目标治疗尚未注册")
            return
        healer_alias = self._alias({"TargetType": task.get("HealerTargetType")}) \
            if task.get("HealerTargetType") is not None else ""
        if healer_alias not in {"", "Caster", "ModifierOwnerEntity"}:
            self._issue(ctx, path, str(task.get("$type")),
                        f"独立治疗来源目标尚未注册：{healer_alias}")
            return
        ratio = self._value(task[fields[0]], ctx, f"{path}/{fields[0]}")
        target = self._hook_target(self._alias(task), ctx)
        if ratio is None:
            return
        if target is None:
            self._issue(ctx, path, "TargetAlias", f"未注册治疗目标：{self._alias(task)}")
            return
        effect = {
            "effect_type": "heal", "target": target,
            "ratio": ratio if formula == "HealByHealerMaxHP" else 0,
            "amount": ratio if formula == "HealByBaseValue" else 0,
        }
        if formula == "HealByTargetMaxHP":
            effect["amount"] = _format(_binary("*", _atom(ratio), _atom("$target.max_hp")))
        elif formula == "HealByHealerAttack":
            effect["amount"] = _format(_binary("*", _atom(ratio), _atom("$self.atk")))
        self._add_effect(ctx, effect)
        if task.get("IsHealRallyHP"):
            self._add_effect(ctx, {
                "effect_type": "gain_resource", "target": target, "resource_id": "rally_hp",
                "amount": "-$last.actual_amount",
            })

    def _compile_modify_lose_hp(self, task: Dict[str, Any], ctx: _Context,
                                path: str, stack: Tuple[str, ...]) -> None:
        self._compile_const_final_amount(task, ctx, path, "ConstFinalDamage")

    def _compile_before_hit_zero_defence(self, name: str, tasks: List[Dict[str, Any]],
                                         modifier: Dict[str, Any], ctx: _Context,
                                         path: str) -> bool:
        mechanism = [task for task in tasks if not self._presentation_only([task])]
        if len(mechanism) != 2:
            return False
        read, change = mechanism
        if (read.get("$type") != "RPG.GameCore.SetDynamicValueByProperty"
                or set(read) != {"$type", "DynamicKey", "ReadTargetType", "Value"}
                or read.get("Value") != "Defence"
                or self._alias({"TargetType": read.get("ReadTargetType")}) != "ParamEntity"
                or change.get("$type") != "RPG.GameCore.ModifyDamageData"
                or set(change) != {"$type", "Defender_DefenceDelta"}):
            return False
        key = str(read.get("DynamicKey") or "")
        postfix = (change["Defender_DefenceDelta"].get("PostfixExpr") or {})
        fixed = postfix.get("FixedValues") or []
        if (not key or len(fixed) != 1 or fixed[0].get("Value") != 0
                or postfix.get("DynamicHashes") != [dynamic_value_hash(key)]
                or postfix.get("OpCodes") != "AAABAAMR"):
            return False
        if modifier.get("hit_condition") not in {None, "true"} \
                or "def_pen" in modifier.get("hit_stat_exprs", {}):
            self._issue(ctx, path, "OnBeforeHitAll", "防御归 0 与既有命中条件/def_pen 冲突")
            return True
        modifier.setdefault("hit_stat_exprs", {})["def_pen"] = 1.0
        return True

    def _compile_before_hit_scoped_ratio(self, name: str, tasks: List[Dict[str, Any]],
                                         modifier: Dict[str, Any], ctx: _Context,
                                         path: str, *, engine_event: str = "before_take_damage",
                                         fields: Optional[Dict[str, str]] = None) -> bool:
        mechanism = [task for task in tasks if not self._presentation_only([task])]
        task_types = {"RPG.GameCore.ModifyDamageData", "RPG.GameCore.ModifyHealData"}
        predicate = None
        assignment = None
        switch = None
        predicate_switch = None
        if len(mechanism) in {1, 2} and mechanism[-1].get("$type") in task_types:
            task = mechanism[-1]
            assignment = mechanism[0] if len(mechanism) == 2 else None
        elif len(mechanism) == 1 and mechanism[0].get("$type") == "RPG.GameCore.SwitchCase":
            predicate_switch = mechanism[0]
            task = {}
        elif len(mechanism) == 1 and mechanism[0].get("$type") == "RPG.GameCore.PredicateTaskList":
            branch = mechanism[0]
            success = [task for task in branch.get("SuccessTaskList") or []
                       if not self._presentation_only([task])]
            failed = [task for task in branch.get("FailedTaskList") or []
                      if not self._presentation_only([task])]
            if success and failed:
                return False
            if failed:
                if not self._presentation_only(branch.get("SuccessTaskList") or []):
                    return False
                selected = failed
                predicate = {"$type": "RPG.GameCore.ByNot",
                             "Predicate": branch.get("Predicate") or {}}
            else:
                if not self._presentation_only(branch.get("FailedTaskList") or []):
                    return False
                selected = success
                predicate = branch.get("Predicate") or {}
            if (len(selected) == 1
                    and selected[0].get("$type") in {
                        "RPG.GameCore.SwitchCaseByDynamicValue", "RPG.GameCore.SwitchCase"}):
                if selected[0].get("$type") == "RPG.GameCore.SwitchCase":
                    predicate_switch = selected[0]
                else:
                    switch = selected[0]
                task = {}
            elif len(selected) in {1, 2} and selected[-1].get("$type") in task_types:
                task = selected[-1]
                assignment = selected[0] if len(selected) == 2 else None
            else:
                return False
        else:
            return False
        fields = fields or {
            "Attacker_AllDamageTypeAddedRatio": "all_dmg",
            "Attacker_FixedCriticalChance": "fixed_crit_rate",
            "Attacker_ForceStanceBreakRatio": "force_stance_break",
            "Defender_AllDamageReduce": "dmg_dmg_reduction",
            "Defender_AllDamageTypeTakenRatio": "vulnerability",
            "Defender_Monster_DamageTakenRatio": "vulnerability",
        }
        case_tasks: List[List[Dict[str, Any]]] = []
        default_tasks: List[Dict[str, Any]] = []
        branch_tasks: List[Dict[str, Any]] = []
        predicate_rows = (predicate_switch.get("TaskList") or []) if predicate_switch is not None else []
        if predicate_switch is not None:
            if predicate_switch.get("WithBreak") is not False \
                    or not self._presentation_only(predicate_switch.get("DefaultTask") or []):
                return False
            for row in predicate_rows:
                success = [task for task in row.get("SuccessTaskList") or []
                           if not self._presentation_only([task])]
                if len(success) != 1 or not self._presentation_only(row.get("FailedTaskList") or []):
                    return False
                branch_tasks.append(success[0])
            branch_fields = {next((field for field in fields if field in task), "")
                             for task in branch_tasks}
            field = branch_fields.pop() if len(branch_fields) == 1 else ""
            if not field or any(task.get("$type") not in task_types
                                or set(task) != {"$type", field} for task in branch_tasks):
                return False
        elif switch is not None:
            case_tasks = [row.get("TaskList") or [] for row in switch.get("CaseTaskList") or []]
            default_tasks = switch.get("DefaultTaskList") or []
            for branch in [*case_tasks, *([default_tasks] if default_tasks else [])]:
                meaningful = [task for task in branch if not self._presentation_only([task])]
                if len(meaningful) != 1:
                    return False
                branch_tasks.append(meaningful[0])
            branch_fields = {next((field for field in fields if field in task), "")
                             for task in branch_tasks}
            field = branch_fields.pop() if len(branch_fields) == 1 else ""
            if (not field or any(task.get("$type") not in task_types
                                 or set(task) != {"$type", field} for task in branch_tasks)):
                return False
        else:
            field = next((field for field in fields if field in task), "")
        if not field or (switch is None and predicate_switch is None
                         and (task.get("$type") not in task_types
                              or set(task) != {"$type", field})):
            return False
        assignment_key = ""
        if assignment is not None:
            raw_key = assignment.get("DynamicKey") or {}
            assignment_key = str(raw_key.get("Value") if isinstance(raw_key, dict) else raw_key or "")
            assignment_type = str(assignment.get("$type") or "")
            if assignment_type == "RPG.GameCore.SetDynamicValue":
                valid_assignment = (set(assignment) == {"$type", "DynamicKey", "TargetType", "Value"}
                                    and self._alias(assignment) in {"", "ModifierOwnerEntity"})
            elif assignment_type == "RPG.GameCore.SetDynamicValueByModifierValue":
                valid_assignment = (
                    set(assignment) == {"$type", "ReadTargetType", "ValueType",
                                        "Multiplier", "DynamicKey"}
                    and assignment.get("ValueType") == "Layer"
                    and self._alias({"TargetType": assignment.get("ReadTargetType")})
                    == "ModifierOwnerEntity")
            else:
                return False
            if (not valid_assignment or not assignment_key
                    or not self._dynamic_write_is_dead(assignment, assignment_key, (task,),
                                                       ignore_assignment_keys=True)):
                return False
        sub = _Context(mode="event", skill=ctx.skill, event=engine_event,
                       current_modifier=name, current_ability=ctx.current_ability,
                       value_symbols=dict(ctx.value_symbols),
                       modifier_stack=ctx.modifier_stack + (name,))
        condition = "true"
        if predicate is not None:
            parsed = self._predicate_expr(predicate, sub, f"{path}/Predicate", allow_written=True)
            if parsed is not None:
                condition = parsed
        if assignment is not None:
            if assignment.get("$type") == "RPG.GameCore.SetDynamicValue":
                assigned = self._value(
                    assignment["Value"], sub, f"{path}/Assignment/{assignment_key}")
            else:
                dry = replace(sub, damages=[], effects=[], pre_effects=[],
                              hit_effects=[], unsupported=[])
                self._compile_modifier_value(
                    assignment, dry, f"{path}/Assignment/{assignment_key}", ())
                for issue in dry.unsupported:
                    self._issue(sub, issue["path"], issue["node_type"], issue["reason"])
                assigned = (dry.effects[0].get("amount")
                            if not dry.unsupported and len(dry.effects) == 1 else None)
            if assigned is not None:
                sub.value_symbols[dynamic_value_hash(assignment_key)] = assigned
        value = None
        if predicate_switch is not None:
            value = 0
            for index, (row, branch_task) in enumerate(zip(predicate_rows, branch_tasks)):
                branch_condition = self._predicate_expr(
                    row.get("Predicate") or {}, sub, f"{path}/TaskList/{index}/Predicate",
                    allow_written=True)
                branch_value = self._value(
                    branch_task[field], sub, f"{path}/TaskList/{index}/{field}")
                if branch_condition is None or branch_value is None:
                    value = None
                    break
                term = f"(({branch_condition}) ? ({branch_value}) : (0))"
                value = term if value == 0 else f"({value}) + ({term})"
        elif switch is None:
            value = self._value(task[field], sub, f"{path}/{field}")
        else:
            resolved = self._switch_value(switch.get("Switch"), sub, f"{path}/Switch")
            cases = []
            seen = set()
            for index, (row, branch_task) in enumerate(
                    zip(switch.get("CaseTaskList") or [], branch_tasks)):
                case_value = self._number(row.get("Case"), sub, f"{path}/CaseTaskList/{index}/Case")
                if case_value is None:
                    break
                if case_value in seen:
                    self._issue(sub, path, "SwitchCaseByDynamicValue", f"Case 值重复：{case_value}")
                    break
                seen.add(case_value)
                cases.append((case_value, branch_task))
            else:
                default_task = branch_tasks[-1] if default_tasks else None
                if resolved is not None and resolved[0] == "static":
                    selected = next((branch_task for case_value, branch_task in cases
                                     if case_value == resolved[1]), default_task)
                    value = (self._value(selected[field], sub, f"{path}/Selected/{field}")
                             if selected is not None else 0)
                elif resolved is not None and resolved[1] is not None:
                    value = (self._value(default_task[field], sub, f"{path}/Default/{field}")
                             if default_task is not None else 0)
                    for case_value, branch_task in reversed(cases):
                        branch_value = self._value(
                            branch_task[field], sub, f"{path}/Case/{case_value}/{field}")
                        if branch_value is None:
                            value = None
                            break
                        value = (f"(dynamic_of($self, '{resolved[1]}') == {case_value} ? "
                                 f"({branch_value}) : ({value}))")
        for issue in sub.unsupported:
            self._issue(ctx, issue["path"], issue["node_type"], issue["reason"])
        if value is None or (predicate is not None and condition == "true"):
            return True
        if field == "Attacker_ForceStanceBreakRatio" and value != 1:
            self._issue(ctx, path, "RPG.GameCore.ModifyDamageData",
                        "Attacker_ForceStanceBreakRatio 仅支持静态值 1 的无视弱点削韧")
            return True
        if modifier.get("hit_condition") not in {None, condition}:
            self._issue(ctx, path, engine_event, "命中属性与既有 hit_condition 冲突")
            return True
        if condition != "true":
            modifier["hit_condition"] = condition
        stat = fields[field]
        expressions = modifier.setdefault("hit_stat_exprs", {})
        expressions[stat] = (f"({expressions[stat]}) + ({value})"
                             if stat in expressions else value)
        return True

    def _compile_modify_damage_data(self, task: Dict[str, Any], ctx: _Context,
                                    path: str, stack: Tuple[str, ...]) -> None:
        if set(task) == {"$type", "AttackData_FinalDamageMax"}:
            maximum = self._value(task["AttackData_FinalDamageMax"], ctx,
                                  f"{path}/AttackData_FinalDamageMax")
            if maximum is not None:
                self._add_effect(ctx, {
                    "effect_type": "modify_amount",
                    "amount": f"min($event.amount, ({maximum}))"})
            return
        self._compile_const_final_amount(task, ctx, path, "AttackData_ConstFinalDamage")

    def _compile_const_final_amount(self, task: Dict[str, Any], ctx: _Context,
                                    path: str, field: str) -> None:
        if set(task) != {"$type", field}:
            self._issue(ctx, path, str(task.get("$type")), f"仅支持 {field} 扣量改写")
            return
        amount = self._value(task.get(field), ctx, f"{path}/{field}")
        if amount is not None:
            self._add_effect(ctx, {"effect_type": "modify_amount", "amount": amount})

    def _compile_lose_hp_absolute(self, task: Dict[str, Any], ctx: _Context,
                                  path: str, stack: Tuple[str, ...]) -> None:
        source_alias = self._alias({"TargetType": task.get("SourceType")})
        if source_alias not in {"", "Caster"}:
            self._issue(ctx, path, str(task.get("$type")), "LoseHP 仅支持缺省/Caster 来源")
            return
        target = self._hook_target(self._alias(task) or "Caster", ctx)
        if target == "self" and ctx.event in {"on_hp_decrease", "on_hp_increase"}:
            self._issue(ctx, path, str(task.get("$type")), "自身 HP 回调的 LoseHP 回流语义未核定")
            return
        if self._alias(task).startswith("Monster_") and target == self._alias(task):
            self._issue(ctx, path, str(task.get("$type")), "字面怪物目标未能唯一解析")
            return
        amount = self._value(task.get("DamageValue"), ctx, f"{path}/DamageValue")
        if target is None or amount is None or (_is_number(amount) and amount < 0):
            self._issue(ctx, path, str(task.get("$type")), "LoseHP 目标或扣血量未注册")
            return
        self._add_effect(ctx, {"effect_type": "drain_hp", "target": target,
                               "amount": amount, "drain_ratio": 0.0})

    def _compile_lose_hp(self, task: Dict[str, Any], ctx: _Context,
                         path: str, stack: Tuple[str, ...]) -> None:
        ratio_type = task.get("RatioType")
        if ratio_type not in {"MaxHP", "CurrentHP"}:
            self._issue(ctx, path, str(task.get("$type")), f"未注册 RatioType：{ratio_type}")
            return
        ratio = self._value(task.get("Ratio"), ctx, f"{path}/Ratio")
        floor = self._value(task.get("Floor", 0), ctx, f"{path}/Floor")
        target = self._hook_target(self._alias(task), ctx)
        if self._alias(task) in {"CasterSummoner", "ModifierOwnerSummoner"}:
            target = dict(_INCLUSIVE_TEAM_TARGETS[self._alias(task)])
        if ratio is None or floor is None or target is None:
            self._issue(ctx, path, "TargetAlias", f"未注册自伤目标：{self._alias(task)}")
            return
        namespace = "$self" if target == "self" else "$target"
        stat = "max_hp" if ratio_type == "MaxHP" else "hp"
        amount = _binary("*", _atom(f"{namespace}.{stat}"), _atom(ratio))
        self._add_effect(ctx, {"effect_type": "drain_hp", "target": target,
                            "amount": _format(amount), "drain_ratio": 0.0, "floor": floor})

    def _compile_team_location(self, task: Dict[str, Any], ctx: _Context,
                               path: str, stack: Tuple[str, ...]) -> None:
        target = self._hook_target(self._alias(task), ctx)
        if "Row" in task:
            row = self._number(task.get("Row"), ctx, f"{path}/Row")
            if (target is not None and row is not None and row >= 0 and int(row) == row
                    and set(task) <= {"$type", "TargetType", "Row"}):
                ctx.dynamic_writes.add("_FormationRow")
                self._add_effect(ctx, {
                    "effect_type": "set_dynamic_value", "target": target,
                    "dynamic_key": "_FormationRow", "amount": int(row),
                })
                return
            self._issue(ctx, path, str(task.get("$type")), "Row 需为静态非负整数")
            return
        position = {
            "KeepOnFirst": "first", "KeepOnLast": "last",
            "BeforeCaster": "before_owner", "AfterCaster": "after",
        }.get(str(task.get("Location") or ""))
        if target is None or position is None:
            self._issue(ctx, path, str(task.get("$type")), "编队移动目标或位置未注册")
            return
        effect = {"effect_type": "set_team_location", "target": target, "position": position}
        if position in {"before_owner", "after"}:
            reference = self._hook_target(
                self._alias({"TargetType": task.get("CustomCaster")}) or "Caster", ctx)
            if reference is None:
                self._issue(ctx, path, str(task.get("$type")), "编队移动参照目标未注册")
                return
            effect["reference"] = reference
        self._add_effect(ctx, effect)

    def _compile_lock_action_delay(self, task: Dict[str, Any], ctx: _Context,
                                   path: str, stack: Tuple[str, ...]) -> None:
        reason = task.get("WhitelistChangeReason")
        change_type = task.get("WhitelistChangeType", "")
        if reason not in {None, "Mask_TurnBasedAdvance"} or change_type not in {"", "Bit_Decrease"}:
            self._issue(ctx, path, str(task.get("$type")),
                        f"未核定行动条锁原因/方向：{reason!r}/{change_type!r}")
            return
        target_lock = str(task.get("$type")) == "RPG.GameCore.LockTargetActionDelay"
        target_field = "TargetType" if target_lock else "LockTargetType"
        target = self._hook_target(self._alias({"TargetType": task.get(target_field)}), ctx)
        whitelist = task.get("WhitelistSourceEntity")
        whitelist_target = (self._hook_target(self._alias({"TargetType": whitelist}), ctx)
                            if whitelist is not None else None)
        if target is None or (whitelist is not None and whitelist_target != "self"):
            self._issue(ctx, path, str(task.get("$type")),
                        "行动条锁目标未注册，来源豁免仅支持自身")
            return
        key = str(ctx.current_modifier or ctx.skill.get("skill_id") or self.enemy_id)
        locked = task.get("Lock", True) if target_lock else task.get("IsLock", True)
        effect = {"effect_type": "lock_action_delay", "target": target,
                  "lock_id": f"{self.enemy_id}:{key}", "locked": locked}
        if whitelist is not None:
            effect["whitelist_source"] = "self"
        if change_type:
            effect["whitelist_change_type"] = "decrease"
        self._add_effect(ctx, effect)

    def _compile_current_skill_delay(self, task: Dict[str, Any], ctx: _Context,
                                     path: str, stack: Tuple[str, ...]) -> None:
        if task.get("ModifyFunction") not in {None, "Set"}:
            self._issue(ctx, path, str(task.get("$type")), "当次技能 AV 仅支持 Set/缺省设值")
            return
        value = self._value(task.get("NormalizedValue"), ctx, f"{path}/NormalizedValue")
        if value is None or (_is_number(value) and value < 0):
            self._issue(ctx, path, str(task.get("$type")), "当次技能 AV 需非负归一化设值")
            return
        self._add_effect(ctx, {
            "effect_type": "set_action_delay", "target": "self",
            "amount": value * 100.0 if _is_number(value)
                      else _format(_binary("*", _atom(value), _atom(100.0)))})

    def _compile_modify_action_delay(self, task: Dict[str, Any], ctx: _Context,
                                     path: str, stack: Tuple[str, ...]) -> None:
        special = next((key for key in ("AddValue", "InitModify") if key in task), None)
        if "AddNormalizedValue" not in task or special is not None:
            self._issue(ctx, path, str(task.get("$type")),
                        f"仅支持 AddNormalizedValue 推拉条；特殊字段：{special}")
            return
        value = self._value(task.get("AddNormalizedValue"), ctx, f"{path}/AddNormalizedValue")
        alias = self._alias(task)
        target = self._task_target(task, ctx, path)
        semantic = self.semantics.get(str(ctx.skill.get("trigger_key")), {})
        description = str(semantic.get("desc") or "").lower()
        if alias == "AllTeammate" and ("except this unit" in description
                                       or "apart from this unit" in description):
            target = {"pool": "enemies", "where": "$it.actor_id != $self.actor_id"}
        if value is None:
            return
        if target is None:
            self._issue(ctx, path, "TargetAlias", f"未注册推拉条目标：{alias}")
            return
        if value == 0:
            return
        if isinstance(value, str):
            amount = _format(_binary("*", _atom(f"abs({value})"), _atom(100.0)))
            for effect_type, operator in (("delay_action", ">"), ("advance_action", "<")):
                self._add_effect(ctx, {"effect_type": effect_type, "target": target,
                                       "amount": amount, "condition": f"({value}) {operator} 0"})
            return
        self._add_effect(ctx, {
            "effect_type": "delay_action" if value > 0 else "advance_action",
            "target": target, "amount": abs(value) * 100.0,
        })

    def _compile_modify_special_sp(self, task: Dict[str, Any], ctx: _Context,
                                   path: str, stack: Tuple[str, ...]) -> None:
        if "FixedAddValue" not in task or task.get("IgnoreBlock") is not True:
            self._issue(ctx, path, str(task.get("$type")), "仅支持 FixedAddValue 且 IgnoreBlock=true")
            return
        target = self._hook_target(self._alias(task), ctx)
        symbols = {
            dynamic_value_hash("MaxSpecialSP"): "max_special_sp_of($target)",
            dynamic_value_hash("CurrentSpecialSP"): "special_sp_of($target)",
        }
        value = self._value(task.get("FixedAddValue"), ctx, f"{path}/FixedAddValue", symbols)
        if target is None or value is None:
            self._issue(ctx, path, str(task.get("$type")), "特殊充能目标或增减量未注册")
            return
        self._add_effect(ctx, {
            "effect_type": "modify_special_sp", "target": target, "amount": value,
        })

    def _compile_modify_energy(self, task: Dict[str, Any], ctx: _Context,
                               path: str, stack: Tuple[str, ...]) -> None:
        fields = [key for key in ("AddValue", "FixedAddValue", "AddMaxSPRatio", "FixedAddMaxSPRatio",
                                  "SetValue") if key in task]
        if len(fields) != 1:
            self._issue(ctx, path, str(task.get("$type")), "必须且只能声明一种能量修改方式")
            return
        field = fields[0]
        if field == "SetValue":
            value = self._value(task[field], ctx, f"{path}/{field}")
            target = self._hook_target(self._alias(task), ctx)
            valid_target = (target == "self" or target == "all_allies"
                            or target == "$event.target" or isinstance(target, dict))
            if value is None or not valid_target or (_is_number(value) and value < 0):
                self._issue(ctx, path, str(task.get("$type")), "SetValue 的能量值或目标未注册")
                return
            self._add_effect(ctx, {"effect_type": "set_energy", "target": target, "amount": value})
            return
        value = self._value(task[field], ctx, f"{path}/{field}")
        if value is None:
            return
        alias = self._alias(task)
        if alias == "AllLightTeamOnlyAddSPOnceForServant":
            target = dict(_INCLUSIVE_TEAM_TARGETS[alias])
        else:
            target = self._hook_target(alias, ctx)
        valid_target = ((isinstance(target, str) and target in {"self", "all_allies", "$event.target"})
                        or (ctx.event == "battle_event_create" and target == "$event.actor")
                        or (isinstance(target, dict) and (
                            target.get("pool") in {"allies", "enemy_targets", "unselectable"}
                            or "concat" in target
                            or str(target.get("pool", "")).startswith("unique:"))))
        if not valid_target:
            self._issue(ctx, path, "TargetAlias", f"未注册玩家侧能量目标：{alias}")
            return
        if value == 0:
            return
        amount: Any = abs(value) if _is_number(value) else f"abs({value})"
        if field.endswith("MaxSPRatio"):
            amount = _format(_binary("*", _atom("$target.max_energy"), _atom(amount)))
        if isinstance(value, str):
            for effect_type, operator in (("gain_energy", ">"), ("consume_energy", "<")):
                effect = {"effect_type": effect_type, "target": target, "amount": amount,
                          "condition": f"({value}) {operator} 0"}
                if effect_type == "gain_energy" and field.startswith("Fixed"):
                    effect["err_exempt"] = True
                self._add_effect(ctx, effect)
            return
        effect = {
            "effect_type": "gain_energy" if value > 0 else "consume_energy",
            "target": target, "amount": amount,
        }
        if value > 0 and field.startswith("Fixed"):
            effect["err_exempt"] = True
        self._add_effect(ctx, effect)

    def _compile_modify_skill_point(self, task: Dict[str, Any], ctx: _Context,
                                    path: str, stack: Tuple[str, ...]) -> None:
        operation = task.get("ModifyFunction")
        if operation not in {"Add", "Set"}:
            self._issue(ctx, path, str(task.get("$type")), "仅支持 Add/Set 战技点增减与设值")
            return
        value = self._value(task.get("ModifyValue"), ctx, f"{path}/ModifyValue")
        if value is None:
            return
        if _is_number(value) and int(value) != value:
            self._issue(ctx, path, str(task.get("$type")), "战技点增减必须为整数")
            return
        if operation == "Set":
            if _is_number(value) and value < 0:
                self._issue(ctx, path, str(task.get("$type")), "战技点设值必须为非负整数")
                return
            self._add_effect(ctx, {"effect_type": "set_skill_point",
                                   "amount": int(value) if _is_number(value) else value})
            return
        if value == 0:
            return
        # IsSilence 仅控制提示；Add 统一走队级 SP 增减通道。
        self._add_effect(ctx, {"effect_type": "gain_skill_point",
                               "amount": int(value) if _is_number(value) else value})

    def _compile_modify_skill_point_max(self, task: Dict[str, Any], ctx: _Context,
                                        path: str, stack: Tuple[str, ...]) -> None:
        if task.get("ModifyFunction") != "Set":
            self._issue(ctx, path, str(task.get("$type")), "战技点上限仅支持 Set 设值")
            return
        value = self._number(task.get("ModifyValue"), ctx, f"{path}/ModifyValue")
        if value is None:
            return
        if value < 0 or int(value) != value:
            self._issue(ctx, path, str(task.get("$type")), "战技点上限必须是非负整数")
            return
        self._add_effect(ctx, {"effect_type": "set_sp_max", "amount": int(value)})

    def _compile_reset_action_delay(self, task: Dict[str, Any], ctx: _Context,
                                    path: str, stack: Tuple[str, ...]) -> None:
        target = self._task_target(task, ctx, path)
        if target is None or task.get("SkipTargetTurn") is not True:
            self._issue(ctx, path, str(task.get("$type")),
                        "ResetActionDelay 仅支持 SkipTargetTurn=true 的结束当前回合形态")
            return
        self._add_effect(ctx, {"effect_type": "end_current_turn", "target": target})

    def _compile_action_delay_near(self, task: Dict[str, Any], ctx: _Context,
                                   path: str, stack: Tuple[str, ...]) -> None:
        if task.get("NearType") != "After" or task.get("IsInit") is not True:
            self._issue(ctx, path, str(task.get("$type")), "仅支持 After + IsInit=true 的近目标后排布")
            return
        target = self._task_target(task, ctx, path)
        near = self._task_target({"TargetType": task.get("NearTargetType")}, ctx, path)
        if target is None or near is None:
            self._issue(ctx, path, str(task.get("$type")), "近目标或待排布目标未注册")
            return
        self._add_effect(ctx, {
            "effect_type": "set_action_delay", "target": target, "near_target": near,
        })

    def _compile_action_delay(self, task: Dict[str, Any], ctx: _Context,
                              path: str, stack: Tuple[str, ...]) -> None:
        raw = task["NormalizedValue"] if "NormalizedValue" in task else task.get("Value")
        value = self._value(raw, ctx, f"{path}/Value")
        alias = self._alias(task)
        target = self._task_target(task, ctx, path)
        semantic = self.semantics.get(str(ctx.skill.get("trigger_key")), {})
        if alias == "AllTeammate" and "apart from this unit" in str(semantic.get("desc") or ""):
            target = {"pool": "enemies", "where": "$it.actor_id != $self.actor_id"}
        if value is None or target is None:
            self._issue(ctx, path, str(task.get("$type")), "行动条设值或目标未注册")
            return
        if value == 0:
            self._add_effect(ctx, {"effect_type": "immediate_action", "target": target})
            return
        if _is_number(value) and value < 0:
            self._issue(ctx, path, str(task.get("$type")), "行动条设值必须是非负比例")
            return
        self._add_effect(ctx, {
            "effect_type": "set_action_delay", "target": target,
            "amount": value * 100.0 if _is_number(value)
                      else _format(_binary("*", _atom(value), _atom(100.0))),
        })

    def _compile_set_die(self, task: Dict[str, Any], ctx: _Context,
                         path: str, stack: Tuple[str, ...]) -> None:
        alias = self._alias(task) if "TargetType" in task else "Caster"
        target = self._hook_target(alias, ctx)
        if target is None:
            self._issue(ctx, path, "TargetAlias", f"未注册即死目标：{alias}")
            return
        if ctx.event in {"on_kill", "before_actor_exit"} and target == "self":
            return  # 已处于对应死亡链，自灭是 no-op，不递归重入。
        self._add_effect(ctx, {"effect_type": "set_hp_to_percent", "target": target, "percent": 0.0})

    def _compile_destroy_character(self, task: Dict[str, Any], ctx: _Context,
                                   path: str, stack: Tuple[str, ...]) -> None:
        unique_name = task.get("CharacterUniqueName")
        if unique_name and "TargetType" not in task:
            task = {**task, "TargetType": {
                "$type": "RPG.GameCore.TargetFetchUniqueNameEntity", "UniqueName": unique_name}}
        self._compile_force_kill(task, ctx, path, stack)

    def _task_target(self, task: Dict[str, Any], ctx: _Context, path: str) -> Any:
        target = self._hook_target(self._alias(task), ctx)
        if target == "self" and isinstance(ctx.retarget, dict) \
                and ctx.retarget.get("pool") == "self":
            target = dict(ctx.retarget)
        raw_target = task.get("TargetType")
        if (target is None and isinstance(raw_target, dict)
                and raw_target.get("$type") != "RPG.GameCore.TargetAlias"):
            target = self._target_spec(raw_target, ctx, path)
        return target

    def _compile_force_kill(self, task: Dict[str, Any], ctx: _Context,
                            path: str, stack: Tuple[str, ...]) -> None:
        target = self._task_target(task, ctx, path)
        if target is None:
            self._issue(ctx, path, "TargetAlias", f"未注册击杀目标：{self._alias(task)}")
            return
        if ctx.event == "before_actor_exit" and target == "self":
            return
        self._add_effect(ctx, {"effect_type": "set_hp_to_percent", "target": target, "percent": 0.0})

    def _target_type(self, config_skill: Dict[str, Any]) -> Optional[str]:
        info = config_skill.get("TargetInfo") or {}
        target = info.get("TargetType")
        if target == "Caster":
            return "self"
        if target == "EnemySelect":
            return "blast" if info.get("SubTargetType") == "TargetAdjoinEntity" else "single"
        if target == "AllEnemy":
            return "aoe"
        if target == "AllTeamMember":
            return "ally_aoe"
        if target == "FriendSelect":
            return "ally_single"
        return None

    def _action(self, ctx: _Context, config_skill: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        skill = ctx.skill
        skill_id = str(skill["skill_id"])
        semantic = self.semantics.get(str(skill.get("trigger_key")), {})
        target_type = self._target_type(config_skill)
        if target_type is None:
            self._issue(ctx, "SkillList/TargetInfo", "TargetInfo",
                        f"未注册技能目标：{config_skill.get('TargetInfo')}")
            return None
        action: Dict[str, Any] = {
            "action_id": skill_id, "name": semantic.get("name") or skill_id,
            "action_type": "skill", "target_type": target_type,
            "energy_gain": 0, "energy_grant": float(semantic.get("energy") or 0.0),
        }
        if not ctx.damages and ctx.retarget_damage:
            first = ctx.retarget_damage_records[0]
            toughness = (first["stance_value"] if first["stance_value"] is not None
                         else float(skill.get("sp_hit_base") or 0) * (first["stance_ratio"] or 0))
            action = {
                "action_id": action["action_id"], "name": action["name"],
                "action_type": action["action_type"], "target_type": action["target_type"],
                "damage_type": first["element"],
                "toughness_dmg": toughness if isinstance(toughness, str)
                else int(toughness) if float(toughness).is_integer() else toughness,
                "energy_gain": action["energy_gain"], "energy_grant": action["energy_grant"],
            }
            if first["damage_custom_name"]:
                action["damage_custom_name"] = first["damage_custom_name"]
            return action
        if not ctx.damages:
            return action
        hostile_aliases = {"AbilityTargetEntity", "AllEnemy", "AllLightTeam", "SkillTargetEntityList"}
        friendly_aliases = {"AllTeammate", "AllTeamMember", "AllDarkTeam"}
        if target_type in {"self", "ally_single"}:
            friendly_aliases |= {"Caster", "ModifierOwnerEntity"}
        main_aliases = friendly_aliases if target_type in {"self", "ally_single", "ally_aoe"} \
            else hostile_aliases
        main = [d for d in ctx.damages if d["alias"] in main_aliases]
        if not main or any(d["formula"] not in {"ByAttack", "ByMaxHP"} for d in main):
            self._issue(ctx, "DamageByAttackProperty", "Damage", "主动技能缺已注册主目标伤害")
            return action
        if any(d["formula"] != main[0]["formula"] for d in main):
            self._issue(ctx, "DamageByAttackProperty", "Damage", "主目标多段缩放属性不一致")
            return action
        first = main[0]
        scaling_key = "hp" if first["formula"] == "ByMaxHP" else "atk"
        def segment_toughness(record: Dict[str, Any]) -> Any:
            if record["stance_value"] is not None:
                return record["stance_value"] if isinstance(record["stance_value"], str) \
                    else float(record["stance_value"])
            return float(skill.get("sp_hit_base") or 0) * (record["stance_ratio"] or 0)

        def normalized_toughness(value: Any) -> Any:
            return value if isinstance(value, str) else int(value) if float(value).is_integer() else value

        toughness = segment_toughness(first)
        action = {
            "action_id": action["action_id"], "name": action["name"],
            "action_type": action["action_type"], "target_type": action["target_type"],
            "damage_type": first["element"], "scaling": [{scaling_key: first["ratio"]}],
            "toughness_dmg": normalized_toughness(toughness),
            "energy_gain": action["energy_gain"], "energy_grant": action["energy_grant"],
        }
        if first["damage_custom_name"]:
            action["damage_custom_name"] = first["damage_custom_name"]
        if any(record["damage_custom_name"] != first["damage_custom_name"] for record in main):
            self._issue(ctx, "DamageByAttackProperty", "Damage", "主目标多段 CustomName 不一致")
            return action
        if len(main) > 1:
            action["instances"] = len(main)
            if any(d["ratio"] != first["ratio"] or d["stance_ratio"] != first["stance_ratio"]
                   or d["stance_value"] != first["stance_value"] or d["element"] != first["element"]
                   for d in main):
                action["instance_variants"] = []
                for record in main:
                    value = segment_toughness(record)
                    action["instance_variants"].append({
                        "scaling": [{scaling_key: record["ratio"]}],
                        **({"damage_type": record["element"]}
                           if record["element"] != first["element"] else {}),
                        "toughness_dmg": normalized_toughness(value),
                    })
        blast = [d for d in ctx.damages if d["alias"] == "AbilityTargetAdjoinEntity"]
        if blast:
            same_segments = len(blast) in {1, len(main)}
            varying = any(d["ratio"] != blast[0]["ratio"] for d in blast)
            elements_match = all(d["element"] == main[index]["element"]
                                 for index, d in enumerate(blast)) if len(blast) > 1 \
                else blast[0]["element"] == first["element"]
            if not same_segments or not elements_match or (varying and len(blast) != len(main)):
                self._issue(ctx, "DamageByAttackProperty", "Damage", "副目标多段/元素语义未注册")
                return action
            if varying:
                variants = action.get("instance_variants") or [{} for _ in main]
                for index, record in enumerate(blast):
                    variants[index]["scaling_blast"] = [{scaling_key: record["ratio"]}]
                action["instance_variants"] = variants
            elif blast[0]["ratio"] != first["ratio"]:
                action["scaling_blast"] = [{scaling_key: blast[0]["ratio"]}]
        return action

    def compile_skill(self, trigger_key: str) -> Dict[str, Any]:
        """编译 SkillList 的主动技能；``ok`` 仅在全任务树受支持时为真."""
        skill = self.skills.get(trigger_key)
        config_skill = self.config_skills.get(trigger_key)
        config_only = skill is None and config_skill is not None
        if config_only:
            skill = {"skill_id": f"{self.enemy_id}:{trigger_key}",
                     "trigger_key": trigger_key, "param_list": []}
        ctx = _Context(mode="action", skill=skill or {"skill_id": trigger_key})
        if skill is None or config_skill is None:
            self._issue(ctx, trigger_key, "SkillList", "TBGD trigger 与 CharacterConfig 未对齐")
        else:
            entry = config_skill.get("EntryAbility")
            if not entry:
                self._issue(ctx, trigger_key, "SkillList", "缺 EntryAbility")
            else:
                self._compile_ability(str(entry), ctx, trigger_key, ())
            if config_only and any(record["stance_value"] is None for record in ctx.damages):
                self._issue(ctx, trigger_key, "MonsterSkillConfig",
                            "缺 TBGD 行且伤害段未显式给出 StanceValue，不能按零削韧处理")
        action = self._action(ctx, config_skill or {}) if skill is not None else None
        if not ctx.damages:
            ctx.effects = ctx.pre_effects + ctx.effects
            ctx.pre_effects = []
        hooks = self._make_hooks(
            ctx, f"$event.source == $self.actor_id and $event.action_id == '{skill['skill_id']}'",
            event="on_become_target", effects=ctx.pre_effects
        ) if ctx.pre_effects and ctx.damages and skill is not None else []
        hooks.extend(self._make_hooks(
            ctx, f"$event.actor == $self.actor_id and $event.action_id == '{skill['skill_id']}'"
        ) if ctx.effects and skill is not None else [])
        if ctx.hit_effects and skill is not None:
            hooks.extend(self._make_hooks(
                ctx, f"$event.source == $self.actor_id and $event.action_id == '{skill['skill_id']}'",
                event="after_being_hit", effects=ctx.hit_effects))
        hooks.extend(ctx.lifecycle_hooks)
        return {
            "ok": not ctx.unsupported and action is not None,
            "action": action, "hooks": hooks, "summons": ctx.summons,
            "unsupported": ctx.unsupported, "handled": sorted(set(ctx.handled)),
        }

    def _compile_deathrattle(self, callback: Dict[str, Any], ctx: _Context,
                             path: str, stack: Tuple[str, ...]) -> None:
        self._compile_tasks(callback.get("CallbackConfig") or [], ctx, path, stack)

    def compile_passive(self, ability_name: str, skill_id: str) -> Dict[str, Any]:
        """编译被动能力（14_policy.md 被动事件族节）：

        挂载通道：OnAdd → OnStart 任务表编译为 `on_battle_start` 挂载钩（初始阵容）+
        `actor_enter`（wave_index≥1，波次 newcomers）——两触发集按 actor 实例互斥不双挂
        （初始阵容的 actor_enter 在订阅前发射收不到；波次怪的 on_battle_start 在其布场前
        发射 owner 尚不存在天然跳过）。挂载任务走 `_compile_tasks` 全机器——modifier 定义
        与其余回调事件由 `_compile_modifier_lifecycle`/`_PASSIVE_EVENT_MAP` 在施加点消费。
        死亡链回调（OnDeathrattle/OnListenCharacterDie 带旗标）独立子上下文编译为 on_kill
        全局钩（既有口径：$event.target == $self.actor_id）。
        空被动（无 OnAdd/OnStart/回调机制内容——AI 控制壳）空翻译 ok=True。
        """
        skill = next((s for s in self.skills.values() if str(s.get("skill_id")) == str(skill_id)),
                     {"skill_id": str(skill_id)})
        ctx = _Context(mode="event", skill=skill, event="on_battle_start",
                       current_ability=ability_name, passive_owner=True)
        ability = self.abilities.get(ability_name)
        ctx.passive_deathrattle_names = frozenset((ability or {}).get("Modifiers") or {})
        mount_hooks: List[Dict[str, Any]] = []
        deathrattle_hooks: List[Dict[str, Any]] = []
        nothing_to_translate = False
        if ability is None:
            self._issue(ctx, ability_name, "AbilityReference", "被动 Ability 定义缺失")
        else:
            for key in ("OnAdd", "OnStart"):   # 序=OnAdd 先于 OnStart（约定，待实测）
                tasks = ability.get(key) or []
                if tasks:
                    self._compile_tasks(tasks, ctx, f"{ability_name}/{key}", ())
            if ctx.effects:
                mount_hooks.extend(self._make_hooks(ctx, "true", event="on_battle_start"))
                mount_hooks.extend(self._make_hooks(
                    ctx, "$event.actor == $self.actor_id and $event.wave_index >= 1",
                    event="actor_enter"))
            for modifier_name, modifier in (ability.get("Modifiers") or {}).items():
                for index, callback in enumerate(modifier.get("_CallbackList") or []):
                    event = str(callback.get("Event") or "")
                    method_name = EVENT_HANDLERS.get(event)
                    if method_name is None:
                        continue
                    self_death = (event == "OnDeathrattle" or "Deathrattle" in set(
                        modifier.get("BehaviorFlagList") or []))
                    sub = _Context(mode="event", skill=skill, event="on_kill",
                                   current_ability=ability_name, current_modifier=modifier_name)
                    getattr(self, method_name)(callback, sub,
                                               f"{ability_name}/{modifier_name}/{index}", ())
                    for issue in sub.unsupported:
                        self._issue(ctx, issue["path"], issue["node_type"], issue["reason"])
                    if sub.effects:
                        deathrattle_hooks.extend(self._make_hooks(
                            sub, "$event.target == $self.actor_id" if self_death else "true",
                            event="on_kill"))
                    ctx.handled.extend([event, *sub.handled])
                    ctx.summons.extend(sub.summons)
                    ctx.lifecycle_hooks.extend(sub.lifecycle_hooks)
            nothing_to_translate = (not ctx.effects and not mount_hooks
                                    and not deathrattle_hooks and not ctx.lifecycle_hooks
                                    and not any((m or {}).get("_CallbackList")
                                                for m in (ability.get("Modifiers") or {}).values()))
        hooks = [*mount_hooks, *deathrattle_hooks, *ctx.lifecycle_hooks]
        return {"ok": not ctx.unsupported and (bool(hooks) or nothing_to_translate),
                "action": None, "hooks": hooks,
                "summons": ctx.summons, "unsupported": ctx.unsupported,
                "handled": sorted(set(ctx.handled))}

    def _ability_dynamic_hashes(self, name: str, seen: Optional[set] = None) -> set:
        """收集 Ability 及其嵌套引用的动态哈希，用于被动→SkillParam 结构绑定."""
        seen = set() if seen is None else seen
        if name in seen or name not in self.abilities:
            return set()
        seen.add(name)
        hashes: set = set()

        def walk(value: Any) -> None:
            if isinstance(value, dict):
                expr = value.get("PostfixExpr") or {}
                hashes.update(int(h) for h in expr.get("DynamicHashes") or [])
                node_type = str(value.get("$type") or "")
                if node_type in {"RPG.GameCore.TriggerAbility", "RPG.GameCore.TurnInsertAbility"}:
                    raw = value.get("AbilityName")
                    child = raw.get("Value") if isinstance(raw, dict) else raw
                    if child:
                        hashes.update(self._ability_dynamic_hashes(str(child), seen))
                for child in value.values():
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)

        walk(self.abilities[name])
        return hashes

    def _passive_trigger(self, ability_name: str) -> Optional[str]:
        for config_skill in self.config.get("SkillList") or []:
            if (config_skill.get("EntryAbility") == ability_name
                    and config_skill.get("Name") in self.skills
                    and _is_passive_row(config_skill)):
                return str(config_skill["Name"])
        floats = ((self.config.get("DynamicValues") or {}).get("Floats") or {})
        triggers = set()
        for raw_hash in self._ability_dynamic_hashes(ability_name):
            info = (floats.get(str(raw_hash)) or {}).get("ReadInfo") or {}
            trigger = str(info.get("TriggerKey") or "")
            if info.get("Type") == "SkillParam" and trigger.startswith(("Passive", "SkillP")):
                triggers.add(trigger)
        return triggers.pop() if len(triggers) == 1 else None

    @staticmethod
    def _has_supported_event(ability: Dict[str, Any]) -> bool:
        for modifier in (ability.get("Modifiers") or {}).values():
            if any(callback.get("Event") in EVENT_HANDLERS
                   for callback in modifier.get("_CallbackList") or []):
                return True
        return False

    def compile_enemy(self) -> Dict[str, Any]:
        """编译整只敌人的主动与已注册被动，并给出完整覆盖审计."""
        actions: List[Dict[str, Any]] = []
        hooks: List[Dict[str, Any]] = []
        summons: List[Dict[str, Any]] = []
        unsupported: List[Dict[str, str]] = []
        handled: set = set()
        deferred: List[str] = []
        results: Dict[str, Any] = {}
        if not self.config:
            return {
                "ok": False, "actions": [], "hooks": [], "summons": [],
                "unsupported": [{
                    "owner": self.enemy_id, "path": "JsonConfig",
                    "node_type": "CharacterConfig", "reason": "CharacterConfig 缺失",
                }],
                "deferred": [], "handled": [], "skill_results": {},
            }

        def absorb(owner: str, result: Dict[str, Any]) -> None:
            results[owner] = result
            if result.get("action"):
                actions.append(result["action"])
            hooks.extend(result.get("hooks") or [])
            summons.extend(result.get("summons") or [])
            handled.update(result.get("handled") or [])
            unsupported.extend({"owner": owner, **issue}
                               for issue in result.get("unsupported") or [])

        for trigger in self.skills:
            if trigger not in self.config_skills:
                if (trigger in self.skill_param_triggers
                        or trigger not in self.config_ai_references):
                    continue
                unsupported.append({
                    "owner": trigger, "path": trigger, "node_type": "SkillList",
                    "reason": "TBGD trigger 在 CharacterConfig 中不存在",
                })
        for trigger, config_skill in self.config_skills.items():
            if _is_passive_row(config_skill):
                continue
            if trigger not in self.skills:
                ability = self.abilities.get(str(config_skill.get("EntryAbility") or ""))
                tasks = list((ability or {}).get("OnAdd") or [])
                tasks.extend((ability or {}).get("OnStart") or [])
                if (ability is not None
                        and set(ability) <= {"Name", "TargetInfo", "OnAdd", "OnStart"}
                        and self._presentation_only(tasks)):
                    continue
                absorb(trigger, self.compile_skill(trigger))
                continue
            absorb(trigger, self.compile_skill(trigger))

        passive_candidates = {
            str(skill.get("EntryAbility"))
            for skill in self.config.get("SkillList") or []
            if _is_passive_row(skill) and skill.get("EntryAbility")
        }
        passive_candidates.update(
            str(name) for name in self.config.get("AbilityList") or []
            if self._has_supported_event(self.abilities.get(str(name)) or {}))
        for ability_name in sorted(passive_candidates):
            if _is_camera_ability(ability_name):
                continue
            if ability_name.startswith("Monster_Common_"):
                deferred.append(ability_name)
                continue
            ability = self.abilities.get(ability_name)
            if ability is None:
                unsupported.append({"owner": ability_name, "path": ability_name,
                                    "node_type": "AbilityReference",
                                    "reason": "被动 Ability 定义缺失"})
                continue
            # 被动事件族已开编译通道（compile_passive 挂载通道 + _PASSIVE_EVENT_MAP）——
            # 全部 SkillList 绑定的被动进编译，无载体事件在编译内逐条显式拒收。
            trigger = self._passive_trigger(ability_name)
            if trigger is None or trigger not in self.skills:
                # TBGD 无对应 Passive 技能行的主流形态（570/1087）——SkillList 行直连
                # 回退：以行 Name 合成 skill 上下文（无 param_list，SkillParam 依赖内容
                # 按既有未知哈希口径诚实拒；modifier id 按合成 skill_id 确定性生成）。
                rows = [s for s in self.config.get("SkillList") or []
                        if s.get("EntryAbility") == ability_name and _is_passive_row(s)]
                if len(rows) == 1:
                    absorb(ability_name, self.compile_passive(
                        ability_name, f"{self.enemy_id}_{rows[0].get('Name')}"))
                    continue
                unsupported.append({"owner": ability_name, "path": ability_name,
                                    "node_type": "PassiveBinding",
                                    "reason": "无法由 EntryAbility/SkillParam/SkillList 行唯一绑定被动技能"})
                continue
            absorb(ability_name, self.compile_passive(
                ability_name, str(self.skills[trigger]["skill_id"])))
        return {
            "ok": not unsupported and bool(actions or hooks),
            "actions": actions, "hooks": hooks,
            "summons": list({spec["summon_id"]: spec for spec in summons}.values()),
            "unsupported": unsupported, "deferred": sorted(deferred),
            "handled": sorted(handled), "skill_results": results,
        }
