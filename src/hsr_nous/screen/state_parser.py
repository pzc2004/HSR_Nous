"""状态解析：把 ScreenSnapshot → sim_schema.Encounter 草案.

Phase 4 实现简单启发式：
- 把每条 Detection 的 label 映射到 sim_schema 字段
- text 字段（如 OCR 结果）若包含已知角色名 → 关联到 character

不做精确 OCR（依赖 PaddleOCR，详见 docs/screen_setup.md 后续接入）。
"""
from __future__ import annotations

from typing import List, Optional, Tuple

from hsr_nous.adapters.character_adapter import (
    adapt_character_by_name,
    make_dummy_enemy,
)
from hsr_nous.sim_schema.action import Action
from hsr_nous.sim_schema.actor import Actor
from hsr_nous.sim_schema.encounter import Encounter, TerminationConfig
from hsr_nous.sim_schema.policy import Policy

from hsr_nous.screen.models import Detection, ScreenSnapshot


def parse_state(snapshot: ScreenSnapshot) -> dict:
    """从 ScreenSnapshot 解析出结构化状态信息.

    Returns:
        dict: {
            "characters": List[str],      # 检测到的角色名
            "enemies": int,                # 敌人数量
            "cycle": Optional[int],        # 当前轮次（None 表示未读到）
            "buffs": List[str],            # 检测到的 buff 图标
        }
    """
    chars: List[str] = []
    enemies = 0
    cycle: Optional[int] = None
    buffs: List[str] = []

    for det in snapshot.detections:
        if det.label == "character_portrait" and det.text:
            chars.append(det.text)
        elif det.label == "enemy":
            enemies += 1
        elif det.label == "cycle_counter" and det.text:
            # 期望格式 "12/15 轮次" 或 "12"
            try:
                cycle = int(det.text.split("/")[0].strip())
            except (ValueError, IndexError):
                pass
        elif det.label in ("buff_icon", "debuff_icon") and det.text:
            buffs.append(det.text)

    return {"characters": chars, "enemies": enemies, "cycle": cycle, "buffs": buffs}


def snapshot_to_encounter(
    snapshot: ScreenSnapshot,
    *,
    level: int = 80,
    max_av: int = 1500,
    lang: str = "en",
) -> Tuple[Encounter, dict]:
    """把 ScreenSnapshot 直接组装成 sim_schema.Encounter.

    检测到的角色名 → adapt_character_by_name；未检测到的角色用 stub Actor。
    敌人：基于 `enemies` 计数生成 dummy enemies。

    Returns:
        (Encounter, parsed_state_dict)
    """
    parsed = parse_state(snapshot)

    char_actors: List[Actor] = []
    actions_by_actor = {}
    for name in parsed["characters"]:
        actor = adapt_character_by_name(name, level=level, lang=lang)
        if actor is None:
            actor = Actor(actor_id=name, name=name, actor_type="character", level=level)
        char_actors.append(actor)
        # 自动添加 dummy basic action（保证 Engine 不跳过）
        actions_by_actor[actor.actor_id] = [
            Action(
                action_id=f"dummy_{actor.actor_id}",
                name="普攻",
                action_type="basic",
                target_type="single",
                scaling=[{"atk": 0.5}],
            )
        ]

    # 敌人
    n_enemies = max(parsed["enemies"], 1)  # 至少 1 个
    enemy_actors = [
        make_dummy_enemy(name=f"Enemy{i+1}", hp=200000.0, atk=800.0, def_=600.0, toughness=80.0)
        for i in range(n_enemies)
    ]

    policy = Policy(
        name="screen-default",
        action_rules=[
            {
                "condition": "energy >= ULT_THRESHOLD",
                "action": "ultimate",
                "priority": 100,
            },
            {"condition": "true", "action": "skill", "priority": 50},
            {"condition": "true", "action": "basic", "priority": 0},
        ],
        parameters={"ULT_THRESHOLD": 100},
        target_rules=[{"condition": "true", "selector": "primary_target", "priority": 0}],
    )

    enc = Encounter(
        encounter_id=f"screen_{snapshot.timestamp:.0f}",
        name=f"ScreenSnapshot@{snapshot.timestamp:.0f}",
        actors=char_actors + enemy_actors,
        policy=policy,
        termination=TerminationConfig(
            mode="fixed_av",
            max_action_value=max_av,
            max_turns=200,
        ),
    )
    return enc, parsed