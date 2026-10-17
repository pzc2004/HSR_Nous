"""账号快照与适配器测试（离线，不接真 API——假 client 注入 `client._make_client`）.

覆盖 docs/integrations.md §1.6 口径 + 防腐层漂移闸：
- 未配置 → None，不抛异常
- 成功响应 → 解析出全粒度结构（遗器主/副词条、叠影、星魂明细、技能等级、面板、忆灵）
- genshin 抛错 → 静默 None
- adapter 查无模板 → member=None（不脑补）
- adapter 产出形状对拍 build_compiler 词表（_MEMBER_KEYS/_AFFIX_FIELD）——schema 改动当场红
"""
from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

from hsr_nous.account import fetch_account_snapshot
from hsr_nous.account.models import (
    AccountCharacter,
    AccountLightCone,
    AccountRelic,
    RelicStat,
)
from hsr_nous.adapters.account_adapter import account_character_to_member


@pytest.fixture(autouse=True)
def _pin_legacy_transport(monkeypatch):
    """本文件钉解析层（假 client 说 genshin 协议）——传输选择由
    tests/test_account_transport.py 钉，互不越界。"""
    from hsr_nous.account import transport
    monkeypatch.setattr(transport, "available", lambda: False)


# ----------------------------------------------------------------- 假 genshin 端


def _fake_prop(name: str, value: str, times: int = 1):
    """genshin DetailRelicProperty / StarRailCharacterProperty 的鸭子型."""
    return SimpleNamespace(info=SimpleNamespace(name=name), value=value, times=times)


def _fake_panel_prop(name: str, final: str):
    return SimpleNamespace(info=SimpleNamespace(name=name), final=final)


class _FakeClient:
    """鸭子型 genshin.Client：uid 已解析 + 详情/日课/忘却三接口."""

    uid = 80000001

    async def get_starrail_characters(self, uid=None, *, lang=None):
        char = SimpleNamespace(
            id=1308, name="黄泉", level=80, rank=2,
            element="Thunder", path="Nihility",
            ranks=(SimpleNamespace(name="星魂一", is_unlocked=True),
                   SimpleNamespace(name="星魂三", is_unlocked=False)),
            skills=(SimpleNamespace(point_id="130801", level=6),
                    SimpleNamespace(point_id="130803", level=10)),
            equip=SimpleNamespace(id=23024, name="行于流逝的岸", level=80, rank=1, rarity=5),
            relics=(SimpleNamespace(
                id=61011, name="先驱头", pos=1, level=15, rarity=5,
                main_property=_fake_prop("HPDelta", "705.0"),
                properties=(_fake_prop("AttackAddedRatio", "10.4%", times=2),
                            _fake_prop("CriticalChanceBase", "5.8%", times=2)),
            ),),
            ornaments=(),
            properties=(_fake_panel_prop("攻击力", "3200.0"),
                        _fake_panel_prop("暴击率", "55.2%")),
            memosprite=None,
        )
        return SimpleNamespace(avatar_list=(char,))

    async def get_starrail_notes(self, uid=None):
        return SimpleNamespace(current_stamina=240)

    async def get_starrail_challenge(self, uid=None):
        return SimpleNamespace(has_data=True, season=31, name="忘却之庭·其三十一",
                               total_stars=36, max_floor=12, total_battles=18)


class _BoomClient(_FakeClient):
    async def get_starrail_characters(self, uid=None, *, lang=None):
        raise RuntimeError("端点漂移")


# ----------------------------------------------------------------- client 层


def test_unconfigured_returns_none(monkeypatch):
    """未配置（无凭证 → _make_client 为 None）→ fetch 返回 None 且不抛."""
    monkeypatch.setattr("hsr_nous.account.client._make_client", lambda: None)
    assert fetch_account_snapshot() is None


def test_snapshot_full_granularity(monkeypatch):
    """假 client → 快照解析出全粒度结构化数据."""
    monkeypatch.setattr("hsr_nous.account.client._make_client", lambda: _FakeClient())
    snap = fetch_account_snapshot()
    assert snap is not None
    assert snap.uid == "80000001" and snap.trailblaze_power == 240
    assert len(snap.moc_records) == 1 and snap.moc_records[0].stars == 36

    ch = snap.characters[0]
    assert (ch.id, ch.name, ch.level, ch.eidolon) == ("1308", "黄泉", 80, 2)
    assert ch.unlocked_eidolons == ("星魂一",)
    assert ch.skill_levels == {"130801": 6, "130803": 10}
    assert ch.light_cone is not None and ch.light_cone.superimposition == 1
    assert ch.panel == {"攻击力": 3200.0, "暴击率": pytest.approx(0.552)}
    assert ch.has_memosprite is False

    relic = ch.relics[0]
    assert relic.pos == 1 and relic.level == 15
    assert relic.main is not None and relic.main.name == "HPDelta"
    assert [s.name for s in relic.subs] == ["AttackAddedRatio", "CriticalChanceBase"]
    assert relic.subs[0].times == 2


def test_genshin_error_silent_none(monkeypatch):
    """genshin 侧任何异常 → 静默 None（不抛、不重试）."""
    monkeypatch.setattr("hsr_nous.account.client._make_client", lambda: _BoomClient())
    assert fetch_account_snapshot() is None


# ----------------------------------------------------------------- adapter 层


def _rich_character() -> AccountCharacter:
    return AccountCharacter(
        id="1308", name="黄泉", level=80, eidolon=2,
        skill_levels={"130801": 6, "130802": 10, "130803": 10, "130804": 10},
        light_cone=AccountLightCone(id="23024", name="行于流逝的岸", superimposition=1),
        relics=(AccountRelic(
            id="61011", name="先驱头", pos=1, level=15,
            main=RelicStat("HPDelta", "705.0"),
            subs=(RelicStat("AttackAddedRatio", "10.4%", 2),),
        ),),
    )


def test_adapter_missing_template_returns_none():
    """角色模板不存在 → member=None + dropped 记账（不脑补）."""
    ghost = AccountCharacter(id="9999", name="不存在")
    member, dropped = account_character_to_member(ghost)
    assert member is None and dropped


def test_adapter_member_shape_and_drift_gates():
    """产出形状对拍编译器词表——schema/词表改动当场红（漂移无静默死角）."""
    from hsr_nous.sim.compile.build_compiler import _AFFIX_FIELD, _MEMBER_KEYS

    member, dropped = account_character_to_member(_rich_character())
    assert dropped == []
    assert member is not None
    assert set(member) <= _MEMBER_KEYS, "成员键集超出编译器作者面"
    assert member["character_template"] == "1308"
    assert member["light_cone"] == {"superimposition": 1}

    relics = member["relics"]
    assert set(relics) <= {"head", "hands", "body", "feet", "sphere", "rope"}
    for entry in relics.values():
        assert entry["main"] in _AFFIX_FIELD
        assert set(entry["subs"]) <= set(_AFFIX_FIELD)
        assert all(isinstance(v, int) for v in entry["subs"].values())
    assert relics["head"] == {"main": "hp", "subs": {"atk_pct": 2}}


def test_adapter_dropped_is_loud():
    """词表外词条/未知技能槽 → 进 dropped，不静默吞."""
    ch = _rich_character()
    ch2 = AccountCharacter(
        id=ch.id, name=ch.name, level=ch.level,
        skill_levels={"999999": 9},
        relics=(AccountRelic(id="1", name="x", pos=1, level=15,
                             main=RelicStat("新词条", "1.0"),
                             subs=(RelicStat("新词条", "1.0", 1),)),),
    )
    member, dropped = account_character_to_member(ch2)
    assert member is not None  # 模板在,角色本身存活
    assert "技能点 999999" in dropped and any("新词条" in d for d in dropped)
    assert member["relics"]["head"] == {"subs": {}}  # 词条被摘,槽位仍在


def test_env_autoload_from_repo_root(monkeypatch):
    """仓库根 .env 由 account 模块自动加载（common.env；调用方无需先 load_dotenv）；CI 无 .env 时 skip."""
    from hsr_nous.account import client as account_client
    from hsr_nous.common.paths import repo_root

    if not (repo_root() / ".env").exists():
        pytest.skip(".env 不存在（gitignored，CI 无此文件）")
    for key in ("HSR_NOUS_HOYO_LTUID", "HSR_NOUS_HOYO_LTOKEN", "HSR_NOUS_HOYO_SERVER"):
        monkeypatch.delenv(key, raising=False)
    assert account_client._make_client() is not None, ".env 未被自动加载（凭证不可见）"
    assert os.environ.get("HSR_NOUS_HOYO_SERVER"), "仓库根 .env 未被自动加载"
