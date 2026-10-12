"""extract_caveats 提取规则闸钉：空账/完成陈述不误提，真挂账不误杀.

`scripts/extract_caveats.py` 的 `_classify` 是 caveats 机读键质量的唯一漏斗——
三类病灶曾入库（「待收：无（…）」前缀挂账正文空账被 default 兜底误放、
「已收编——…」完成陈述误标 pending、「无待收段」空账声明误标 pending），
本文件钉死修复后的规则形态，防回潮。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from extract_caveats import _classify  # noqa: E402


class TestEmptyAndCompletedGates:
    """空账/完成陈述闸（无论通道，先于 default 兜底）."""

    @pytest.mark.parametrize("text", [
        "无（纯类型桶增伤，dmg_basic_dmg_boost/dmg_skill_dmg_boost 引擎消费端在案）",
        "无（heal_self ratio=施放者有效生命上限×比例，与官方同口径）",
    ])
    def test_explicit_empty(self, text):
        """「无（…）」显式空账——注释通道 default=pending 也不得误放."""
        assert _classify(text, "pending") is None

    @pytest.mark.parametrize("text", [
        "「造成的击破伤害无视目标#3[i]%的防御力」已收编——scoped def_pen 逐目标无视防御通道（116 幽锁 4pc 族 2026-09-16 落地）",
        "「每层【流光】使终结技伤害无视目标#2[i]%防御」已收编——scoped def_pen + hit_stat_exprs 按层现值",
    ])
    def test_completed_statement(self, text):
        """「…已收编——…」完成陈述（无挂账标记词）不得误标 pending."""
        assert _classify(text, "pending") is None

    def test_no_pending_declarations(self):
        """「无待收段」空账声明不得误标 pending（「待收」标记词的空账用法）."""
        text = "set_2pc 已由 stat_effects dmg_imaginary 0.1 承载（验收批在案，e2e 对轴通过——无待收段）。"
        assert _classify(text, "pending") is None


class TestLiveEntriesUnharmed:
    """真挂账不误杀."""

    def test_plain_pending(self):
        assert _classify("战技驱散与伤害结算先后、同目标多 buff 选取优先级待实测", "pending") == "pending"

    def test_approx_family(self):
        assert _classify("按常驻闩承载近似建模，方向已知有偏", "pending") == "approx"

    def test_notes_channel_pending(self):
        """notes 通道（default=None）真挂账照常提取."""
        assert _classify("终结技 100% 基础概率按必挂处理（命中公式待实测终审）", None) == "pending"

    def test_mixed_completed_and_live_conservative(self):
        """「已收编——但 X 待实测」混合句：与既定「拿不准宁可不进」方针一致，
        保守不提取（核销语境按子句一刀切是既有行为，不在本闸扩写）."""
        assert _classify("「每层【流光】无视防御」已收编——但 AoE 回能次数待实测", "pending") is None
