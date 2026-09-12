"""测试共享构造件（tests/_builders.py）——引擎/战斗环境唯一事实源.

背景：65+ 测试文件各自手写 `_engine/_build/_make` 构造器（测试屎山起点——Encounter
构造签名一改全库一起炸）。本件收敛三个最常用形态；迁移纪律：一次换一批（≤6 文件），
换完跑回归再下一批，绝不一口气全换。

三个件：
- `make_actor` / `make_dummy`：单位小工厂（StatBlock 关键字透传）
- `engine_vs_dummy`：单英雄（+可选队友）对 N 假人——hook DSL/NS/资源/生存测试的主力形态
- `basic_action`：单发普攻工厂（scaling/toughness 可调）
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.policy_api import ScriptedPolicy
from hsr_nous.sim_schema.action import Action
from hsr_nous.sim_schema.actor import Actor, StatBlock
from hsr_nous.sim_schema.encounter import Encounter, TerminationConfig

_DUMMY_WEAKNESS = "fire"


def make_actor(actor_id: str, name: str = "测试员", **stats: Any) -> Actor:
    """我方单位工厂（StatBlock 键透传——hp/atk/spd/max_energy/crit_rate/crit_dmg…）。"""
    base = {"hp": 5000, "atk": 2000, "spd": 200, "max_energy": 100}
    base.update(stats)
    return Actor(actor_id=actor_id, name=name, level=80, stats=StatBlock(**base))


def make_dummy(actor_id: str = "e1", name: str = "假人", *,
               weakness: Sequence[str] = (_DUMMY_WEAKNESS,), **stats: Any) -> Actor:
    """敌方假人工厂（默认血牛+满韧——伤害对轴的沙包；要挨打测试传正常 hp）。"""
    base = {"hp": 1e9, "spd": 100, "max_toughness": 9999}
    base.update(stats)
    return Actor(actor_id=actor_id, name=name, actor_type="monster", level=80,
                 stats=StatBlock(**base, weakness=list(weakness)))


def basic_action(action_id: str = "b", *, scaling: float = 1.0,
                 damage_type: str = _DUMMY_WEAKNESS, toughness_dmg: int = 0,
                 action_type: str = "basic", target_type: str = "single") -> Action:
    """单发普攻工厂（默认 100% ATK 单体火——假人弱点匹配）。"""
    return Action(action_id=action_id, name="普攻", action_type=action_type,
                  target_type=target_type, damage_type=damage_type,
                  scaling=[{"atk": scaling}], toughness_dmg=toughness_dmg)


def engine_vs_dummy(*, hero: Optional[Actor] = None,
                    allies: Sequence[Actor] = (),
                    enemies: Sequence[Actor] = (),
                    actions: Optional[Dict[str, List[Action]]] = None,
                    policy: Optional[ScriptedPolicy] = None,
                    mode: str = MODE_EXPECTED,
                    initial_energy_ratio: float = 0.0,
                    initial_sp: Optional[int] = None,
                    seed: Optional[int] = None,
                    max_av: float = 50.0) -> CombatEngine:
    """单英雄（+可选队友）对 N 假人的引擎（setup 完成态）.

    缺省：hero=测试员（5k/2k/200/100）、1 个火弱假人、hero 一把普攻。
    `actions` 键=actor_id 覆盖默认行动表；`max_av` = fixed_av 终止（默认 50 小局）。
    """
    hero = hero or make_actor("hero")
    foes = list(enemies) or [make_dummy()]
    acts = {"hero": [basic_action()]}
    if actions:
        acts.update(actions)
    enc = Encounter(encounter_id="t", name="t", actors=[hero, *allies, *foes],
                    termination=TerminationConfig(mode="fixed_av", max_action_value=max_av))
    kwargs: Dict[str, Any] = {}
    if initial_sp is not None:
        kwargs["initial_sp"] = initial_sp
    if seed is not None:
        kwargs["seed"] = seed
    eng = CombatEngine(enc, actions_by_actor=acts, policy=policy or ScriptedPolicy(),
                       mode=mode, initial_energy_ratio=initial_energy_ratio, **kwargs)
    eng.setup()
    return eng
