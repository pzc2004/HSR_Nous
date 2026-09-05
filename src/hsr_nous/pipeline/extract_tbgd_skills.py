#!/usr/bin/env python3
"""从上游技能配置仓库提取角色技能的机制数值（战技点耗产/基础回能/削韧）.

数据来源: 见 URL / URL_LD 常量（公开镜像仓，跟随现网版本更新）
- 文件: AvatarSkillConfig.json + AvatarSkillConfigLD.json（全技能 × 全等级，
  含强化/变身/派生/联动形态独立条目；LD=联动角色分库，同 schema）
- 该配置是各 wiki（米游社/BWIKI/Fandom）战技点数据的上游——wiki 为二手转录

数据模型（2026-09-05 四点校准钉死：刃/流萤/遐蝶/火花）：
- `BPNeed` = 战技点**消耗**：≥0 = 耗 N 点（1=常规战技，2=饮月2段强化普攻/Archer 战技，
  3=饮月3段）；**-1 或字段缺失 = 无耗**（普攻/终结技/免费技如遐蝶阿兰——免费技
  两种写法都存在：遐蝶 -1、阿兰字段缺失）
- `BPAdd` = 战技点**产出**：1 = 产 1 点（普攻类）；**字段缺失 = 不产**（刃强化普攻/
  青雀/银狼999/白厄变身普攻 全部 None——2026-09-05 全字段 dump 时发现，此前误判
  "产点无字段靠引擎规则"）
- `SPBase` = 基础**回能**（普攻 20/战技 30/终结技 5；强化形态逐技能值：刃强化普攻 30/
  火花强化普攻 40/饮月强化普攻 35~40）；字段缺失 = 不回能（流萤变身形态/遐蝶族）
- `ShowStanceList` = 削韧（原始单位，÷3 = 游戏 UI/米游社显示值）——削韧主源是 fandom
  （owner 裁定 2026-09-05），此处仅作交叉校验附带
- 各等级 BPNeed/BPAdd/SPBase/ShowStance 不变（全库验证 0 反例），取 Level 1 为代表

红线：只入库 StarRailRes 在册角色（花名册已过 redline 版本对齐）——上游数据混未上线
内容（如 1513），按角色前缀过滤剔除，拦截计数进报告。
"""

import argparse
import json
import sys
import time
import urllib.request
from collections import Counter
from pathlib import Path

URL = ("https://gitlab.com/Dimbreath/turnbasedgamedata/-/raw/main/"
       "ExcelOutput/AvatarSkillConfig.json")
URL_LD = ("https://gitlab.com/Dimbreath/turnbasedgamedata/-/raw/main/"
          "ExcelOutput/AvatarSkillConfigLD.json")  # 联动角色分库（同 schema）
UA = {"User-Agent": "HSR_Nous/0.1 (TurnBasedGameData extractor)"}


def char_id_of(skill_id: str) -> str:
    """技能 ID → 角色 ID：6 位取前 4（150110→1501）；7 位忆灵/派生取 1..5（1140701→1407）."""
    return skill_id[1:5] if len(skill_id) == 7 else skill_id[:4]


def _download(url: str, cache: Path, refresh: bool) -> bytes:
    if cache.exists() and not refresh:
        return cache.read_bytes()
    print(f"下载 {url} ...")
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=180) as resp:
        raw = resp.read()
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(raw)
    print(f"缓存到 {cache}（{len(raw)} 字节）")
    return raw


def main() -> int:
    ap = argparse.ArgumentParser(description="TurnBasedGameData 技能机制数值提取（战技点耗产/回能/削韧）")
    ap.add_argument("--data-dir", default="data", help="数据目录（默认 data）")
    ap.add_argument("--refresh", action="store_true", help="忽略缓存重新下载")
    ap.add_argument("--file", help="用本地 AvatarSkillConfig.json（离线调试）")
    args = ap.parse_args()

    data_dir = Path(args.data_dir)
    cache_dir = data_dir / "tbgd" / "cache"

    if args.file:
        raws = [Path(args.file).read_bytes()]
    else:
        raws = [_download(URL, cache_dir / "AvatarSkillConfig.json", args.refresh),
                _download(URL_LD, cache_dir / "AvatarSkillConfigLD.json", args.refresh)]
    entries = [e for raw in raws for e in json.loads(raw)]
    print(f"技能条目: {len(entries)}")

    # 红线花名册（已过版本对齐的在册角色）
    srr = json.loads((data_dir / "starrailres" / "index_new" / "cn" / "characters.json")
                     .read_text(encoding="utf-8"))
    live_ids = set(srr.keys())

    skills: dict[str, dict] = {}
    vocab: Counter = Counter()
    blocked_chars: set[str] = set()
    for s in entries:
        if s.get("Level") != 1:
            continue  # 各等级不变（全库验证），取 Lv1 代表
        sid = str(s["SkillID"])
        cid = char_id_of(sid)
        if cid not in live_ids:
            blocked_chars.add(cid)
            continue
        bp = s.get("BPNeed")
        raw_cost = bp["Value"] if isinstance(bp, dict) else None
        vocab[raw_cost] += 1
        ba = s.get("BPAdd")
        raw_gain = ba["Value"] if isinstance(ba, dict) else None
        sb = s.get("SPBase")
        raw_energy = sb["Value"] if isinstance(sb, dict) else None
        skills[sid] = {
            "char_id": cid,
            "sp_cost": raw_cost if isinstance(raw_cost, int) and raw_cost >= 0 else 0,
            "sp_cost_raw": raw_cost,  # None=字段缺失 / -1=类型默认，provenance 用
            "sp_gain": raw_gain if isinstance(raw_gain, int) else 0,
            "sp_gain_raw": raw_gain,  # None=不产（刃强化普攻族）
            "energy_gen": raw_energy if isinstance(raw_energy, (int, float)) else 0,
            "energy_gen_raw": raw_energy,  # None=不回能（流萤变身/遐蝶族）
            "stance": [x["Value"] for x in s.get("ShowStanceList", [])],
            "max_level": s.get("MaxLevel"),
        }
    print(f"入库技能: {len(skills)}（BPNeed 词表: {dict(sorted(vocab.items(), key=lambda x: str(x[0])))}）")

    covered = {v["char_id"] for v in skills.values()}
    gap = sorted(live_ids - covered)
    out = {
        "_meta": {
            "source": "上游技能配置仓库（见提取脚本 URL 常量）",
            "url": URL, "url_ld": URL_LD,
            "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "skill_count": len(skills),
            "semantics": ("sp_cost: 0=无耗(-1/字段缺失), N=耗N点；sp_gain: 0=不产(字段缺失), "
                          "1=产1点；energy_gen: 0=不回能(字段缺失), N=基础回能"),
        },
        "skills": skills,
    }
    out_path = data_dir / "tbgd_skill_data.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"写入 {out_path}（{len(skills)} 技能 / {len(covered)} 角色）")

    # ---- 报告（不静默）----
    print(f"-- 红线拦截（未在册角色前缀）{len(blocked_chars)}: {sorted(blocked_chars)}")
    if gap:
        print(f"!! 在册但本文件无技能的角色 {len(gap)}: "
              f"{[(cid, srr[cid]['name']) for cid in gap]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
