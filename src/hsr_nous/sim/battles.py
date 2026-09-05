"""战斗配置库（battle library）：`data/battles/` 下一局一个 YAML——web 大厅与 CLI 选择器共用.

- 单文件自包含：``{name, description, build_yaml, stage_yaml}``，build/stage 内嵌为
  YAML 字符串（不存路径引用，配置文件可整体搬走）
- 目录 gitignored、脚本自建；目录为空（含首次使用）时自动物化三个内置演示配置
  （本文件常量，不入 git）——删光即"恢复出厂"
- preview = 从内嵌 YAML 解析出的队伍角色名/敌人名列表；模板引用（character_template /
  enemy_template）按模板根解析显示名，解析不到回退引用串——preview 永不因数据缺失拖垮列表；
  特殊充能角色（残梦/飞黄/火种/新蕊族）在角色名后标注（判定见 `_special_charge_label`）
- `template_doc` / `build_team_member` 同时是 web 端 unit_sheet 聚合端点的取数件
- `battle_catalog` / `assemble_form` 是大厅表单编辑器的取数与组装件（表单 → build/stage
  YAML 唯一事实源，前端高级模式的 YAML 预览也靠它，杜绝双份组装逻辑漂移）
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml

from hsr_nous.sim_schema.templates import DEFAULT_TEMPLATE_ROOTS

#: 配置库目录（相对 CWD，与 DEFAULT_TEMPLATE_ROOTS 同约定；测试 monkeypatch 此常量）
BATTLES_DIR = Path("data/battles")

#: 附加模板根（有序，查找时优先于 DEFAULT_TEMPLATE_ROOTS，逐实体独立 first-hit-wins——
#: 同 id 双根都有 → 附加根生效；附加根缺失的 id → 回落默认根）。生产恒空表；
#: web 调试台 --templates 注入（如 tests/fixtures/templates 人工全机制锚模板压生成骨架），
#: 相对 CWD 与 DEFAULT_TEMPLATE_ROOTS 同约定；测试 monkeypatch 此常量
EXTRA_TEMPLATE_ROOTS: List[str] = []

#: 模板来源词表（provenance，中性命名——优先根本质是"用户给的根"，当前恰好是 fixtures
#: 人工锚模板；默认根 = data/sim_templates 生成器产地）：web 徽章/清单标记共用
TEMPLATE_SOURCE_ANCHOR = "anchor"        # 附加根命中
TEMPLATE_SOURCE_GENERATED = "generated"  # 默认根命中

#: 配置名禁用字符（路径分隔符 + Windows 非法字符 + 引号/尖括号——名字同时上文件名、
#: HTML 卡片与 JS 调用串，收口一处）
_NAME_FORBIDDEN = frozenset('\\/:*?"<>|')
_NAME_MAX = 64

#: 演示局公共策略：能量满开大 → 战技点富余放战技 → 默认普攻
_DEMO_POLICY = {
    "name": "default",
    "action_rules": [
        {"condition": "energy >= max_energy", "action": "ultimate", "priority": 90},
        {"condition": "skill_points > 2", "action": "skill", "priority": 50},
        {"condition": "true", "action": "basic", "priority": 0},
    ],
    "target_rules": [],
    "parameters": {},
}


def _demo_enemy(actor_id: str, name: str, spd: float, weakness: List[str],
                toughness: float = 60) -> Dict[str, Any]:
    return {"actor_id": actor_id, "name": name, "level": 80, "hp": 1_000_000_000,
            "spd": spd, "weakness": weakness, "max_toughness": toughness}


#: 三个内置演示配置（dict 形态常量，物化时 dump 成内嵌 YAML 字符串）：
#: ① 真角色模板三人局 ② 白板单角色局 ③ 白厄变身链局
_DEMOS: List[Dict[str, Any]] = [
    {
        "name": "demo_黄泉队",
        "description": "真角色模板局：黄泉+缇宝+砂金（1308/1403/1304）对三只造物",
        "build": {"team": [
            {"character_template": "1308", "level": 80},
            {"character_template": "1403", "level": 80},
            {"character_template": "1304", "level": 80},
        ], "policy": _DEMO_POLICY},
        "stage": {"stage_id": "demo_trio", "enemies": [
            _demo_enemy("enemy1", "炎华造物", 90, ["fire"]),
            _demo_enemy("enemy2", "霜晶造物", 110, ["lightning", "ice"], 30),
            _demo_enemy("enemy3", "虚数卒", 130, ["imaginary"], 90),
        ], "termination": {"mode": "fixed_av", "max_action_value": 300}},
    },
    {
        "name": "demo_停云白板",
        "description": "白板单角色局：停云（1202，无光锥遗器）对木桩假人",
        "build": {"team": [
            {"character_template": "1202", "level": 80},
        ], "policy": {  # 单人局放战技只会给自己刷 buff（零伤害），白板局普攻到底
            "name": "default",
            "action_rules": [
                {"condition": "energy >= max_energy", "action": "ultimate", "priority": 90},
                {"condition": "true", "action": "basic", "priority": 0},
            ],
            "target_rules": [],
            "parameters": {},
        }},
        "stage": {"stage_id": "demo_dummy", "enemies": [
            _demo_enemy("enemy", "假人", 100, ["lightning"]),
        ], "termination": {"mode": "fixed_av", "max_action_value": 300}},
    },
    {
        "name": "demo_白厄",
        "description": "白厄（1408）变身链演示：对单精英怪",
        "build": {"team": [
            {"character_template": "1408", "level": 80},
        ], "policy": {
            "name": "phainon_default",
            "action_rules": [
                {"condition": "energy >= max_energy", "action": "ultimate", "priority": 90},
                {"condition": "not in_state", "action": "skill", "priority": 50},
                {"condition": "true", "action": "basic", "priority": 0},
            ],
            "target_rules": [],
            "parameters": {},
        }},
        "stage": {"stage_id": "demo_elite", "enemies": [
            _demo_enemy("enemy", "精英假人", 100, ["physical"], 240),
        ], "termination": {"mode": "fixed_av", "max_action_value": 300}},
    },
    {
        "name": "demo_白厄队",
        "description": "白厄+刻律德菈+星期日+丹恒•腾荒（1408/1412/1313/1414）："
                        "队友技目标指向白厄叠火种；三只低伤沙包（血池打不完）——"
                        "群攻/扩散/弹射/被击火种全测得到",
        "build": {"team": [
            {"character_template": "1408", "level": 80},
            {"character_template": "1412", "level": 80},
            {"character_template": "1313", "level": 80},
            {"character_template": "1414", "level": 80},
        ], "policy": {
            "name": "phainon_team",
            "action_rules": [
                {"condition": "energy >= max_energy", "action": "ultimate", "priority": 90},
                {"condition": "skill_points > 2", "action": "skill", "priority": 50},
                {"condition": "true", "action": "basic", "priority": 0},
            ],
            "target_rules": [
                # 定位白厄（highest_atk 按基础攻击会误选星期日——见排障记录）
                {"condition": "true",
                 "selector": {"type": "has_modifier", "modifier_id": "TRACE_1408103"}},
            ],
            "parameters": {},
        }},
        "stage": {"stage_id": "demo_elite_long", "enemies": [
            {"enemy_template": "sandbag", "actor_id": "enemy1", "name": "精英假人·壹"},
            {"enemy_template": "sandbag", "actor_id": "enemy2", "name": "精英假人·贰"},
            {"enemy_template": "sandbag", "actor_id": "enemy3", "name": "精英假人·叁"},
        ], "termination": {"mode": "kill_target"}},
    },
]


def _check_name(name: str) -> str:
    """配置名卫生校验：去空白、非空、无禁用字符、长度上限（合法名原样返回）。"""
    name = name.strip()
    if not name:
        raise ValueError("配置名不能为空")
    if name in (".", "..") or len(name) > _NAME_MAX or any(c in _NAME_FORBIDDEN for c in name):
        raise ValueError(f"非法配置名 {name!r}（不可含 {' '.join(sorted(_NAME_FORBIDDEN))}，≤{_NAME_MAX} 字符）")
    return name


def _path(name: str) -> Path:
    return BATTLES_DIR / f"{name}.yaml"


def _write(name: str, description: str, build_yaml: str, stage_yaml: str) -> None:
    record = {"name": name, "description": description,
              "build_yaml": build_yaml, "stage_yaml": stage_yaml}
    _path(name).write_text(yaml.safe_dump(record, allow_unicode=True, sort_keys=False),
                           encoding="utf-8")


def _seed_if_empty() -> None:
    """目录为空（含不存在）→ 物化内置演示配置；已有任一 .yaml 则不动（用户删除单个不复活）。"""
    BATTLES_DIR.mkdir(parents=True, exist_ok=True)
    if any(BATTLES_DIR.glob("*.yaml")):
        return
    for demo in _DEMOS:
        _write(demo["name"], demo["description"],
               yaml.safe_dump({"build": demo["build"]}, allow_unicode=True, sort_keys=False),
               yaml.safe_dump({"stage": demo["stage"]}, allow_unicode=True, sort_keys=False))


def template_roots() -> Tuple[str, ...]:
    """当前模板根查找链：附加根在前（优先）+ 默认根在后——web 启动时同链透传编译层。"""
    return (*EXTRA_TEMPLATE_ROOTS, *DEFAULT_TEMPLATE_ROOTS)


def set_extra_template_roots(roots: "List[str] | Tuple[str, ...]") -> None:
    """设置附加模板根（覆盖式，空表=恢复缺省只查默认根；web --templates 注入入口）。"""
    EXTRA_TEMPLATE_ROOTS[:] = [str(r) for r in roots]


def template_hit(kind: str, ref: str) -> "Tuple[Path, str] | None":
    """模板查找带 provenance：命中 → (文件路径, 来源)；找不到 → None。

    查找序同 `template_roots()`（附加根整体优先于默认根）——附加根命中来源
    TEMPLATE_SOURCE_ANCHOR，默认根命中 TEMPLATE_SOURCE_GENERATED。
    """
    for source, roots in ((TEMPLATE_SOURCE_ANCHOR, EXTRA_TEMPLATE_ROOTS),
                          (TEMPLATE_SOURCE_GENERATED, DEFAULT_TEMPLATE_ROOTS)):
        for root in roots:
            for f in sorted(Path(root).glob(f"{kind}/{ref}_*.yaml")):
                return f, source
    return None


def _template_file(kind: str, ref: str) -> "Path | None":
    """按序在模板根查找链各根下找 {kind}/<ref>_*.yaml（首个命中根生效）；找不到返回 None。"""
    hit = template_hit(kind, ref)
    return hit[0] if hit is not None else None


def template_doc(kind: str, ref: str) -> "Dict[str, Any] | None":
    """模板引用 → 解析后的模板 dict（characters/light_cones/relics/enemies）；找不到/坏文件 → None。"""
    f = _template_file(kind, ref)
    if f is None:
        return None
    try:
        doc = yaml.safe_load(f.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return None
    return doc if isinstance(doc, dict) else None


def description_doc(actor_id: str) -> "Dict[str, Any] | None":
    """呈现层旁车（descriptions/{actor_id}.json，template_generator 产物）→ dict；
    找不到/坏文件 → None（web 调试台 desc/能量名显示回落，契约见 adapters README）。"""
    for root in template_roots():
        f = Path(root) / "descriptions" / f"{actor_id}.json"
        if f.is_file():
            try:
                doc = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return None
            return doc if isinstance(doc, dict) else None
    return None


def build_team_member(build_yaml: str, actor_id: str) -> "Dict[str, Any] | None":
    """build YAML 文本中该 actor 的 member 配置（模板成员 actor_id==模板 id；inline 按 actor_id 匹配）。"""
    try:
        build = yaml.safe_load(build_yaml) or {}
    except yaml.YAMLError:
        return None
    for m in (build.get("build", build).get("team") or []):
        if isinstance(m, dict) and str(m.get("actor_id") or m.get("character_template") or "") == actor_id:
            return m
    return None


#: 特殊充能阈值：正常角色 max_energy ≥ 60（模板分布实测 60~480），低于即层数/特殊资源
#: 顶替能量槽（残梦 9 / 飞黄·火种 12 / 昔涟 24 / 遐蝶 0）
_SPECIAL_CHARGE_ENERGY_CEIL = 60.0

_SPECIAL_NOTE_RE = re.compile(r"特殊充能角色（(.+?)类）")


def _special_charge_label(doc: Dict[str, Any]) -> "str | None":
    """角色模板 dict → 特殊充能标注（None=普通能量角色）。

    判定优先级：DSL `energy_name` 字段（随实体走的唯一事实源，2026-09-05 owner 裁定）
    > 模板注释显式声明（"特殊充能角色（X类）"）> max_energy 异常阈值（<60 通称
    "特殊充能"——阈值只定族不定名，名字须 DSL/注释佐证，不许脑补）。
    """
    if doc.get("energy_name"):
        return str(doc["energy_name"])
    for note in doc.get("trace_notes") or []:
        m = _SPECIAL_NOTE_RE.search(str(note))
        if m:
            return m.group(1)
    me = (doc.get("base_stats") or {}).get("max_energy")
    if me is not None and float(me) < _SPECIAL_CHARGE_ENERGY_CEIL:
        return "特殊充能"
    return None


def _member_name(member: Dict[str, Any]) -> str:
    ref = member.get("character_template")
    if ref is not None and str(ref) != "inline":
        ref = str(ref)
        doc = template_doc("characters", ref)
        f = _template_file("characters", ref)
        if doc is not None or f is not None:
            name = str((doc or {}).get("name") or (f.stem[len(ref) + 1:] if f else "") or ref)
            label = _special_charge_label(doc) if doc else None
            return f"{name}·{label}" if label else name
    if member.get("name"):
        return str(member["name"])
    if ref is not None:
        return str(ref)
    return str(member.get("actor_id", "?"))


def _enemy_name(spec: Dict[str, Any]) -> str:
    if spec.get("name"):
        return str(spec["name"])
    if spec.get("enemy_template") is not None:
        ref = str(spec["enemy_template"])
        doc = template_doc("enemies", ref)
        if doc is not None:
            return str(doc.get("name") or ref)
        f = _template_file("enemies", ref)
        return f.stem[len(ref) + 1:] if f is not None else ref
    return str(spec.get("actor_id", "?"))


def preview_names(build_yaml: str, stage_yaml: str) -> Tuple[List[str], List[str]]:
    """从内嵌 YAML 文本解析预览名单：(队伍角色名列表, 敌人名列表)。坏 YAML → 空列表。"""
    try:
        build = yaml.safe_load(build_yaml) or {}
    except yaml.YAMLError:
        build = {}
    try:
        stage = yaml.safe_load(stage_yaml) or {}
    except yaml.YAMLError:
        stage = {}
    team = [_member_name(m) for m in (build.get("build", build).get("team") or [])
            if isinstance(m, dict)]
    stage_obj = stage.get("stage", stage)
    enemy_specs = [e for e in (stage_obj.get("enemies") or []) if isinstance(e, dict)]
    for wave in stage_obj.get("waves") or []:
        enemy_specs.extend(e for e in (wave.get("enemies") or []) if isinstance(e, dict))
    return team, [_enemy_name(e) for e in enemy_specs]


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def list_battles() -> List[Dict[str, Any]]:
    """列出库内全部配置：{name, description, team_preview, stage_preview}（按文件名排序）。"""
    _seed_if_empty()
    out: List[Dict[str, Any]] = []
    for f in sorted(BATTLES_DIR.glob("*.yaml")):
        try:
            data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
            team, stage = preview_names(str(data.get("build_yaml", "")),
                                        str(data.get("stage_yaml", "")))
        except yaml.YAMLError:
            continue  # 手改坏的文件不进列表，不拖垮大厅
        out.append({
            "name": str(data.get("name") or f.stem),
            "description": str(data.get("description", "")),
            "team_preview": team,
            "stage_preview": stage,
        })
    return out


def load_battle(name: str) -> Tuple[str, str]:
    """按名取配置 → (build_yaml, stage_yaml)；不存在抛 KeyError。"""
    _seed_if_empty()
    path = _path(_check_name(name))
    if not path.exists():
        raise KeyError(f"找不到战斗配置 {name!r}（{BATTLES_DIR} 下无此文件）")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return str(data.get("build_yaml", "")), str(data.get("stage_yaml", ""))


def save_battle(name: str, description: str, build_yaml: str, stage_yaml: str) -> None:
    """保存（同名覆盖）。两段 YAML 须可解析且顶层含 build/stage 键——早失败胜于开不了局。"""
    BATTLES_DIR.mkdir(parents=True, exist_ok=True)
    name = _check_name(name)
    for label, text, key in (("build_yaml", build_yaml, "build"),
                             ("stage_yaml", stage_yaml, "stage")):
        try:
            doc = yaml.safe_load(text)
        except yaml.YAMLError as e:
            raise ValueError(f"{label} 不是合法 YAML：{e}") from e
        if not isinstance(doc, dict) or key not in doc:
            raise ValueError(f"{label} 顶层须含 {key!r} 键")
    _write(name, description, build_yaml, stage_yaml)


def delete_battle(name: str) -> None:
    """按名删除；不存在抛 KeyError。"""
    path = _path(_check_name(name))
    if not path.exists():
        raise KeyError(f"找不到战斗配置 {name!r}")
    path.unlink()


# ---------------------------------------------------------------------------
# 表单编辑器取数（catalog）与组装（form → YAML）
# ---------------------------------------------------------------------------

#: 敌人清单数据源（hakushin 主：zh 名 + 弱点；theBowja 遗留源补遗——两者 id 空间相同，
#: 均与 sim_templates/enemies 文件名同构；测试 monkeypatch 这两个常量）
MONSTER_JSON = Path("data/stages/hakushin/monster.json")
ENEMIES_JSON = Path("data/enemies/enemies.json")

#: 数据文件英文属性名 → DSL 属性键
_ELEMENT_KEY = {"Physical": "physical", "Fire": "fire", "Ice": "ice", "Thunder": "thunder",
                "Wind": "wind", "Quantum": "quantum", "Imaginary": "imaginary"}


def _load_json_dict(path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def battle_catalog() -> Dict[str, List[Dict[str, Any]]]:
    """表单编辑器四张清单（数据文件缺失/坏 → 该清单优雅降级为空表，不炸大厅）。

    - characters：characters 模板（id + 中文名 + 特殊充能标注 + 来源 source，标注判定同 preview）
    - light_cones：光锥模板（id + 名 + 星级）
    - relic_sets：遗器套装模板（id + 名 + 部位类型 cavern(四件)/planar(位面) + 2pc/4pc 简述）
    - enemies：monster.json 为主、enemies.json 补名/弱点；只保留**模板可引用**的 id
      （选了编译不过的 id 不进清单——无模板 id 是死选项）

    清单跨查找链各根合并（同 id 附加根压制、缺位 id 回落默认根——与 _template_file 同序的
    逐实体 first-hit-wins，避免 --templates 启动后表单只剩附加根那几份模板）。
    """
    characters = []
    seen_chars: set = set()
    # 分组迭代（附加根 → 默认根）：source 即大厅角色行来源标记（"anchor"/"generated"）
    for source, roots in ((TEMPLATE_SOURCE_ANCHOR, EXTRA_TEMPLATE_ROOTS),
                          (TEMPLATE_SOURCE_GENERATED, DEFAULT_TEMPLATE_ROOTS)):
        for root in roots:
            for f in sorted(Path(root).glob("characters/*.yaml")):
                ref = f.stem.split("_", 1)[0]
                if ref in seen_chars:
                    continue  # 同 id 附加根已收
                seen_chars.add(ref)
                doc = template_doc("characters", ref) or {}
                characters.append({
                    "id": str(doc.get("actor_id") or ref),
                    "name": str(doc.get("name") or f.stem.split("_", 1)[-1] or ref),
                    "charge": _special_charge_label(doc) if doc else None,
                    "source": source,
                })
    light_cones = []
    relic_sets = []
    seen_lc: set = set()
    seen_rs: set = set()
    for root in template_roots():
        for f in sorted(Path(root).glob("light_cones/*.yaml")):
            ref = f.stem.split("_", 1)[0]
            if ref in seen_lc:
                continue
            seen_lc.add(ref)
            doc = template_doc("light_cones", ref) or {}
            light_cones.append({"id": ref, "name": str(doc.get("name") or f.stem.split("_", 1)[-1]),
                                "rarity": doc.get("rarity")})
        for f in sorted(Path(root).glob("relics/*.yaml")):
            ref = f.stem.split("_", 1)[0]
            if ref in seen_rs:
                continue
            seen_rs.add(ref)
            doc = template_doc("relics", ref) or {}
            set4 = doc.get("set_4pc") or {}
            relic_sets.append({
                "id": ref,
                "name": str(doc.get("name") or f.stem.split("_", 1)[-1]),
                "kind": "cavern" if set4 else "planar",  # 四件套（隧洞）/ 两件套（位面）
                "desc_2pc": str((doc.get("set_2pc") or {}).get("desc", "")),
                "desc_4pc": str(set4.get("desc", "")) if set4 else "",
            })
    monsters = _load_json_dict(MONSTER_JSON)
    legacy = _load_json_dict(ENEMIES_JSON)
    enemies = []
    for eid in sorted(set(monsters) | set(legacy)):
        if _template_file("enemies", eid) is None:
            continue  # 无敌人模板 = 选了也编译不过，不进清单
        m, g = monsters.get(eid) or {}, legacy.get(eid) or {}
        weak = m.get("weak") or g.get("ElementalWeaknesses") or []
        enemies.append({
            "id": eid,
            "name": str(m.get("zh") or g.get("Name") or eid),
            "weakness": [_ELEMENT_KEY[w] for w in weak if w in _ELEMENT_KEY],
            "rank": str(m.get("rank") or ""),
        })
    return {"characters": characters, "light_cones": light_cones,
            "relic_sets": relic_sets, "enemies": enemies}


#: 表单策略默认值（编辑器预填 + 空 rules 兜底）：能量满开大 → 点富余放战技 → 普攻
_DEFAULT_POLICY_RULES: List[Dict[str, Any]] = [
    {"condition": "energy >= max_energy", "action": "ultimate", "priority": 90},
    {"condition": "skill_points > 2", "action": "skill", "priority": 50},
    {"condition": "true", "action": "basic", "priority": 0},
]

_FORM_ACTIONS = frozenset({"basic", "skill", "ultimate"})

#: 遗器默认主词条策略（简化配装：只选套装不逐件配词条，主词条给通用输出向合理默认）：
#: 头=hp / 手=atk（游戏固定）；衣=crit_rate / 脚=spd / 绳=atk_pct（通用输出向）；
#: 球=<角色属性>_dmg（取角色模板首个 damage_type，读不到回退 atk_pct）。
#: cavern（四件套）出头/手/衣/脚四件；planar（位面套）出球/绳两件。副词条一律空表。
_RELIC_MAIN_DEFAULT = {"head": "hp", "hand": "atk", "body": "crit_rate",
                       "feet": "spd", "sphere": "", "rope": "atk_pct"}


def _char_element(char_ref: str) -> "str | None":
    """角色模板首个伤害属性（遗器球位默认主词条用）；读不到 → None。"""
    doc = template_doc("characters", char_ref) or {}
    for a in doc.get("actions") or []:
        if isinstance(a, dict) and a.get("damage_type"):
            return str(a["damage_type"])
    return None


def _default_relics(set_ref: str, char_ref: str) -> Dict[str, Dict[str, Any]]:
    """套装引用 → 默认部件表（主词条策略见 _RELIC_MAIN_DEFAULT 注释）。"""
    doc = template_doc("relics", set_ref)
    if doc is None:
        raise ValueError(f"遗器套装 {set_ref!r} 无模板（data/sim_templates/relics/{set_ref}_*.yaml）")
    slots = ("head", "hand", "body", "feet") if doc.get("set_4pc") else ("sphere", "rope")
    elem = _char_element(char_ref)
    sphere_main = f"{elem}_dmg" if elem else "atk_pct"
    return {slot: {"set_id": set_ref,
                   "main": sphere_main if slot == "sphere" else _RELIC_MAIN_DEFAULT[slot],
                   "subs": {}}
            for slot in slots}


def _form_enemies(form: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """怪物表单 → (wave1 enemies, waves 附加波)。库选=enemy_template 引用（同 id 复选
    会撞模板 actor_id，组装期炸）；自定义=inline（actor_id 按全局序号 e1..eN 发）。"""
    if str(form.get("enemies_mode", "library")) == "custom":
        rows = form.get("custom_enemies") or []
        if not rows:
            raise ValueError("自定义怪物至少 1 只")
        by_wave: Dict[int, List[Dict[str, Any]]] = {}
        counter = 0
        for i, r in enumerate(rows):
            name = str(r.get("name") or "").strip()
            if not name:
                raise ValueError(f"自定义怪物第 {i + 1} 行缺名字")
            counter += 1
            spec = {"actor_id": f"e{counter}", "name": name,
                    "level": int(r.get("level", 80) or 80),
                    "hp": float(r.get("hp", 1_000_000) or 1_000_000),
                    "spd": float(r.get("spd", 100) or 100),
                    "max_toughness": float(r.get("toughness", 60) or 0),
                    "weakness": [w for w in (r.get("weakness") or []) if w in _ELEMENT_KEY.values()]}
            by_wave.setdefault(int(r.get("wave", 1) or 1), []).append(spec)
    else:
        picks = form.get("library_enemies") or []
        if not picks:
            raise ValueError("从库选择怪物至少 1 只")
        ids = [str(p.get("enemy") or "") for p in picks]
        if any(not i for i in ids):
            raise ValueError("存在未选怪物的行")
        dup = sorted({i for i in ids if ids.count(i) > 1})
        if dup:
            raise ValueError(f"同一敌人不可复选（模板 actor_id 会撞）：{dup}——"
                             "需要复数同种怪请用「自定义」")
        by_wave = {}
        for p in picks:
            spec: Dict[str, Any] = {"enemy_template": str(p["enemy"]),
                                    "level": int(p.get("level", 80) or 80)}
            by_wave.setdefault(int(p.get("wave", 1) or 1), []).append(spec)
    wave1 = by_wave.pop(1, [])
    waves = [{"wave_index": w, "enemies": by_wave[w]} for w in sorted(by_wave)]
    if not wave1 and not waves:
        raise ValueError("怪物至少 1 只")
    return wave1, waves


def assemble_form(form: Dict[str, Any]) -> Tuple[str, str]:
    """表单 dict → (build_yaml, stage_yaml)。非法输入抛 ValueError（中文原因，前端 toast）。

    组装规则：配队行 → character_template 引用（等级/星魂/光锥模板+叠影1/遗器默认件，
    见 _default_relics 策略）；policy = action_rules 行直通（条件过表达式白名单预检）；
    怪物两模式见 _form_enemies；终止条件 wipe（杀光即停）= fixed_av 999999
    （全灭判停是引擎模式无关第一分支，大 AV 预算等价"只有杀光才停"）。
    """
    from hsr_nous.sim_schema.expression import ExpressionError, parse

    team_rows = form.get("team") or []
    if not team_rows:
        raise ValueError("配队至少 1 人")
    if len(team_rows) > 4:
        raise ValueError("配队至多 4 人")
    team: List[Dict[str, Any]] = []
    for i, row in enumerate(team_rows):
        ref = str(row.get("character") or "").strip()
        if not ref:
            raise ValueError(f"配队第 {i + 1} 行未选角色")
        if _template_file("characters", ref) is None:
            raise ValueError(f"角色 {ref!r} 无模板（data/sim_templates/characters/{ref}_*.yaml）")
        member: Dict[str, Any] = {"character_template": ref,
                                  "level": int(row.get("level", 80) or 80)}
        eidolon = int(row.get("eidolon", 0) or 0)
        if eidolon:
            member["eidolon"] = min(max(eidolon, 0), 6)
        lc = str(row.get("light_cone") or "").strip()
        if lc:
            member["light_cone_template"] = lc
            member["light_cone"] = {"level": 80, "superimposition": 1}
        rs = str(row.get("relic_set") or "").strip()
        if rs:
            member["relics"] = _default_relics(rs, ref)
        team.append(member)
    rules = form.get("policy_rules") or _DEFAULT_POLICY_RULES
    action_rules = []
    for i, r in enumerate(rules):
        cond = str(r.get("condition") or "").strip()
        action = str(r.get("action") or "").strip()
        if not cond or action not in _FORM_ACTIONS:
            raise ValueError(f"策略第 {i + 1} 行缺条件或行动非法（行动限 basic/skill/ultimate）")
        try:
            parse(cond)
        except ExpressionError as e:
            raise ValueError(f"策略第 {i + 1} 行条件表达式非法：{e}") from e
        action_rules.append({"condition": cond, "action": action,
                             "priority": int(r.get("priority", 0) or 0)})
    if not any(r["condition"] == "true" for r in action_rules):
        action_rules.append({"condition": "true", "action": "basic", "priority": 0})
    build = {"build": {"team": team,
                       "policy": {"name": "form_default", "action_rules": action_rules,
                                  "target_rules": [], "parameters": {}}}}
    wave1, waves = _form_enemies(form)
    term = form.get("termination") or {}
    if str(term.get("mode")) == "wipe":
        termination: Dict[str, Any] = {"mode": "fixed_av", "max_action_value": 999999}
    else:
        termination = {"mode": "fixed_av",
                       "max_action_value": int(term.get("max_action_value", 1500) or 1500)}
    stage: Dict[str, Any] = {"stage": {"stage_id": "form_custom", "enemies": wave1,
                                       "termination": termination}}
    if waves:
        stage["stage"]["waves"] = waves
    return (yaml.safe_dump(build, allow_unicode=True, sort_keys=False),
            yaml.safe_dump(stage, allow_unicode=True, sort_keys=False))
