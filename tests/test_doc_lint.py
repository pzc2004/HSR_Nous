"""文档 lint：把 sim_schema/docs 全部章节当代码做机械全量检查（T4 工具箱）.

17 闸（全量、机械、无语义判断；闸 9 拆两个测试函数，共 18 个测试）：
1. **表达式闸**：文档中所有表达式字符串必须过 `ast` 白名单解析
2. **effect_type 闸**：用法必须命中声明清单（05 + 17/19/23 章）
3. **触发器闸**：trigger / hook 事件名必须命中 §4.8 + §23.4 清单
4. **公式闸**：01_formula 顶层 formula 表达式的标识符必须有 parameters 定义
5. **命名残留闸**：已退役标识符必须 0 命中（清单配置在下方 RESIDUE，
   豁免"修改记录/废弃/迁移"等历史语境行）
6. **镜像闸**：登记的同名公式跨文件必须逐字相等（归一化后，清单在 MIRRORS）
7. **公式↔表格闸**：伤害类型的公式乘区 = 02 生效表行 = §1.9 矩阵列（归一化集合）
8. **引用闸**：文档间 §X.Y 引用必须解析到真实章节（否定语境"非 §…"豁免）
9. **算术闸**：a) 遗器副词条三档对 relic_sub_affixes 原始数据；
   b) EHR 断点表按 01_base_stats 自家公式重算
10. **索引闸**：docs/README 与 sim_schema/README 的索引清单 ↔ 磁盘文件双向一致
11. **边界闸**：AGENTS.md 模块边界表 ↔ BOUNDARY_ALLOWED 配置 ↔ 实际 import 三向一致
12. **同步闸**：README `<!-- module-boundaries -->` 标记区 == AGENTS.md 边界表
13. **rulebook 镜像闸**：rulebook.yaml ↔ 01_formula.md 的公式/乘区表达式逐字一致
   （双向；rulebook 全部表达式过白名单解析；break_effects 逐元素字段级镜像）
14. **词表闸**：§22.4 函数表标"已实现"集 == expression.py 白名单
   （EFFECT_FUNCTIONS ∪ FORMULA_FUNCTIONS），标"未实现"集与白名单不交
15. **terminology 乘区键闸**：terminology.yaml"伤害乘区"键 ⊆ rulebook zones ∪ 公式标识符
16. **事件契约闸**：§23.4 事件表"状态"列 ↔ `sim/bus.py` DEFAULT_CONTRACT
   （已登记集 == 契约 − §4.8 生命周期表；未登记集与契约不交；
   契约每个键必须在 §23.4 已登记行或 §4.8 表登记——bus.py 是唯一事实来源）
17. **遗器词条镜像闸**：rulebook.yaml relic_affixes 段逐值 == pipeline 词条数据重算
   （calc_relic_main/sub_affix_values），键集与编译器 _AFFIX_FIELD 词表互锁
"""

import re
from pathlib import Path

import pytest

from hsr_nous.sim_schema.expression import ExpressionError, parse
import ast as _ast

DOCS = Path(__file__).parent.parent / "src" / "hsr_nous" / "sim_schema" / "docs"
ROOT = Path(__file__).parent.parent

EXPR_KEYS = re.compile(
    r"^\s*(?:-\s*)?(amount|condition|expression|flat_bonus|scaling_from_source|"
    r"threshold|max_bonus|step|per_step_bonus|duration|hit_condition|delay_condition|"
    r"target_filter|in_zone_filter|active_when)\s*:\s*(.+?)\s*$"
)
ASSIGN_DASH = re.compile(r"^\s*-\s*self\.\w+\s*=\s*(.+)$")
ASSIGN_PLAIN = re.compile(r"^\s+self\.\w+\s*=\s*(.+)$")
IF_LINE = re.compile(r"^\s*-\s*if\s+(.+?):\s*$")
EFFECT_TYPE_LINE = re.compile(r'effect_type:\s*"([^"]+)"')
TRIGGER_LINE = re.compile(r'^\s*(?:-\s*)?trigger:\s*"([^"]+)"', re.M)
EVENT_LINE = re.compile(r'^\s*-\s*event:\s*"([^"]+)"', re.M)
TABLE_ROW = re.compile(r"^\|\s*`?(\w[\w ]*?)`?\s*\|", re.M)


def _unquote(s: str) -> str:
    """剥掉 YAML 风格引号与行尾注释；支持 \\" 与 '' 转义."""
    s = s.strip()
    if s.startswith('"'):
        out, i = [], 1
        while i < len(s):
            ch = s[i]
            if ch == "\\" and i + 1 < len(s):
                nxt = s[i + 1]
                out.append('"' if nxt == '"' else ("\\" if nxt == "\\" else ch + nxt))
                i += 2
                continue
            if ch == '"':
                return "".join(out)
            out.append(ch)
            i += 1
        return "".join(out)
    if s.startswith("'"):
        end = s.find("'", 1)
        if end > 0:
            return s[1:end].replace("''", "'")
        return s[1:]
    # 未加引号：剥行尾注释
    return re.sub(r"\s+#.*$", "", s).strip()


def _skip_line(line: str) -> bool:
    st = line.strip()
    return (not st) or st.startswith("#") or st.startswith("```")


def _yaml_blocks(text: str):
    blocks, cur, in_block = [], [], False
    for line in text.splitlines():
        if line.strip().startswith("```"):
            if in_block:
                blocks.append("\n".join(cur))
                cur = []
            in_block = not in_block
            continue
        if in_block:
            cur.append(line)
    return blocks


def _collect_block_scalars(lines, i, base_indent):
    out = []
    for j in range(i + 1, len(lines)):
        ln = lines[j]
        if not ln.strip():
            out.append("")
            continue
        indent = len(ln) - len(ln.lstrip())
        if indent > base_indent:
            out.append(ln.strip())
        else:
            break
    return "\n".join(out).strip()


def _each_expression_value():
    """产出 (文件, 行号, 表达式字符串) —— YAML 键 / 块标量 / variable_bindings 条件与 RHS."""
    for md in sorted(DOCS.glob("*.md")):
        text = md.read_text(encoding="utf-8")
        for block in _yaml_blocks(text):
            lines = block.splitlines()
            for i, line in enumerate(lines):
                if _skip_line(line):
                    continue
                m = ASSIGN_DASH.match(line) or ASSIGN_PLAIN.match(line)
                if m:
                    yield md.name, i + 1, _unquote(m.group(1))
                    continue
                m = IF_LINE.match(line)
                if m:
                    yield md.name, i + 1, _unquote(m.group(1))
                    continue
                m = EXPR_KEYS.match(line)
                if m:
                    val = m.group(2)
                    if val in ("|", ">"):
                        indent = len(line) - len(line.lstrip())
                        val = _collect_block_scalars(lines, i, indent)
                        if not val:
                            continue
                    else:
                        val = _unquote(val)
                    if val:
                        yield md.name, i + 1, val


def _expr_errors():
    errors = []
    for fname, lineno, expr in _each_expression_value():
        # 文档定义的 amount 关键字形式（22_syntax_reference §22.5），非表达式
        if expr == "all" or expr.startswith("ratio:"):
            continue
        # 类型注解行（如 `str | None = None` / `List[effect_id] = []`），非表达式
        if " = " in expr and "==" not in expr:
            continue
        try:
            parse(expr, layer="formula")
        except ExpressionError as e:
            errors.append(f"{fname}:{lineno}: {expr!r} → {e}")
    return errors


def test_all_expressions_parse():
    errors = _expr_errors()
    assert not errors, f"{len(errors)} 个表达式无法解析：\n" + "\n".join(errors[:20])


# ---------------------------------------------------------------------------


def _effect_type_inventory():
    inventory = set()
    for name in {"05_effects.md", "17_actor_state.md", "19_zone_system.md",
                 "23_event_hook_system.md", "12_summon.md"}:
        text = (DOCS / name).read_text(encoding="utf-8")
        for block in _yaml_blocks(text):
            inventory.update(EFFECT_TYPE_LINE.findall(block))
    return inventory


def test_effect_type_usage_in_inventory():
    inventory = _effect_type_inventory()
    bad = []
    for md in sorted(DOCS.glob("*.md")):
        for block in _yaml_blocks(md.read_text(encoding="utf-8")):
            for t in EFFECT_TYPE_LINE.findall(block):
                if t not in inventory:
                    bad.append(f"{md.name}: effect_type {t!r} 未在声明清单中")
    assert not bad, "\n".join(sorted(set(bad)))


def _trigger_inventory():
    inv = set()
    text = (DOCS / "04_modifier.md").read_text(encoding="utf-8")
    sec = text[text.index("### 4.8"):text.index("### 4.9")]
    for m in TABLE_ROW.finditer(sec):
        inv.add(m.group(1).strip())
    text23 = (DOCS / "23_event_hook_system.md").read_text(encoding="utf-8")
    sec23 = text23[text23.index("### 23.4"):text23.index("### 23.5")]
    for m in TABLE_ROW.finditer(sec23):
        inv.add(m.group(1).strip())
    return inv


def test_trigger_usage_in_inventory():
    inv = _trigger_inventory()
    bad = []
    for md in sorted(DOCS.glob("*.md")):
        for block in _yaml_blocks(md.read_text(encoding="utf-8")):
            for t in TRIGGER_LINE.findall(block):
                if t not in inv:
                    bad.append(f"{md.name}: trigger {t!r} 未在清单")
            for e in EVENT_LINE.findall(block):
                if e not in inv:
                    bad.append(f"{md.name}: event {e!r} 未在清单")
    assert not bad, "\n".join(sorted(set(bad)))


def test_formula_identifiers_defined():
    """01_formula：**顶层** formula expression（缩进 4）的标识符必须出现在
    全文任何 parameters 的 `- name:` 定义中（跨 formula 共享）。"""
    text = (DOCS / "01_formula.md").read_text(encoding="utf-8")
    bad = []
    params = set(re.findall(r'^\s*-?\s*name:\s*"?(\w+)"?', text, flags=re.M))  # 全文共享池
    for block in _yaml_blocks(text):
        lines = block.splitlines()
        for i, line in enumerate(lines):
            m = re.match(r"^    expression:\s*(.+)$", line)
            if not m:
                continue
            val = m.group(1)
            if val in ("|", ">"):
                val = _collect_block_scalars(lines, i, 4)
            else:
                val = _unquote(val)
            if not val:
                continue
            try:
                prepared = parse(val, layer="formula")
            except ExpressionError as e:
                bad.append(f"顶层 expression 解析失败: {val!r} → {e}")
                continue
            call_names = {
                n.func.id for n in _ast.walk(prepared.tree)
                if isinstance(n, _ast.Call) and isinstance(n.func, _ast.Name)
            }
            # parameters 是乘区声明位；scaling 系数表项与运行时裸属性不属乘区，豁免
            BASE_STATS = {"hp", "atk", "def", "defense", "spd", "max_hp", "max_def", "energy",
                          "max_energy", "shield", "toughness", "max_toughness"}
            RAW_STAT_EXEMPT = BASE_STATS | {"heal_bonus", "shield_bonus", "incoming_heal",
                                            "flat_heal", "flat_shield"}
            for node in _ast.walk(prepared.tree):
                if (isinstance(node, _ast.Name)
                        and node.id not in params
                        and node.id not in call_names
                        and not node.id.endswith("_scaling")
                        and node.id not in RAW_STAT_EXEMPT):
                    bad.append(f"标识符 {node.id!r} 未在任何 parameters 定义: {val!r}")
    assert not bad, "\n".join(sorted(set(bad)))


# ===========================================================================
# 闸5 · 命名残留：退役标识符必须 0 命中（配置驱动）
# ===========================================================================

MECHANICS = Path(__file__).parent.parent / "docs" / "mechanics"

# (模式, 作用域: None=全部文档 或 文件名集合)
RESIDUE = [
    (r"\bsuper_break_mod_multi\b", None),
    (r"\bsuperBreakModMulti\b", None),
    (r"\bextraSuperBreakModifier\b", None),
    (r"\bdot_tick_coefficient\b", None),
    (r"\bdotTickCoefficientMulti\b", None),
    (r"\bdmgMitigationMulti\b", None),
    (r"\bdmg_mitigation_multi\b", None),
    (r"\bon_being_hit\b", None),
    (r"\bon_take_damage\b", None),
    (r"\bon_aha_instant_end\b", None),
    (r"\bon_shield_apply\b", None),
    (r"\bon_hp_change\b", None),
    (r"\bon_energy_full\b", None),
    (r"\bon_death\b", None),
    (r"\bon_target_dead\b", None),
    (r"\bon_energy_threshold\b", None),
    (r"\bon_holding_resource\b", None),
    (r"\bability_multi\b(?!plier)", None),
    (r"\babilityMulti\b(?!plier)", None),
    (r"\bdivergent_universe\b", None),
    (r"\b超击破独立增伤\b", None),
    (r"\bspecialMulti\b", None),
    (r"\bmemps_heal\w*\b", None),
    (r"\bconsume_team_hp_pct\b", None),
    (r"\bweaken_multi\b(?![\w\s]*[✓✓])", {"x_no_file_never_matches"}),  # 占位：weaken 合法，不查
]

# 行级豁免：历史/迁移/废弃声明行（blockquote 内延续豁免）
_EXEMPT_LINE = re.compile(r"修改记录|已废弃|废弃|作废|（原 ?\w|原 .*已|迁移|历史")


def _doc_files():
    for md in sorted(DOCS.glob("*.md")):
        yield md
    for md in sorted(MECHANICS.glob("*.md")):
        yield md


def _strip_changelog(text: str) -> str:
    idx = text.find("## 修改记录")
    return text if idx < 0 else text[:idx]


def test_no_naming_residue():
    bad = []
    for md in _doc_files():
        text = _strip_changelog(md.read_text(encoding="utf-8"))
        exempt_quote = False  # blockquote 内的豁免延续
        for ln, line in enumerate(text.splitlines(), 1):
            if line.lstrip().startswith(">"):
                if exempt_quote or _EXEMPT_LINE.search(line):
                    exempt_quote = True
                    continue
            else:
                exempt_quote = False
            if _EXEMPT_LINE.search(line):
                continue
            for pat, scope in RESIDUE:
                if scope is not None and md.name not in scope:
                    continue
                if re.search(pat, line):
                    bad.append(f"{md.name}:{ln}: 残留 {pat}")
    assert not bad, "\n".join(sorted(set(bad)))


# ===========================================================================
# 闸8 · § 引用完整性：§X.Y 必须解析到真实章节（修改记录豁免）
# ===========================================================================

_HEADING_NUM = re.compile(r"^#{1,6}\s+(\d+(?:\.\d+)*)\.?[\s　]")
_REF = re.compile(r"§(\d+(?:\.\d+)*)")
_MD_NAME = re.compile(r"`?(\d{2}_\w+\.md|game_rules\.md|\d{2}\w*\.md)`?")


def _section_index(path: Path):
    idx = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        m = _HEADING_NUM.match(line)
        if m:
            idx.add(m.group(1).rstrip("."))
    return idx


def _ref_ok(ref: str, idx: set) -> bool:
    if ref in idx:
        return True
    for h in idx:
        if h.startswith(ref + ".") or ref.startswith(h + "."):
            return True
    return False


def test_section_reference_integrity():
    idx_cache = {}
    def idx_of(path: Path):
        if path not in idx_cache:
            idx_cache[path] = _section_index(path)
        return idx_cache[path]

    def resolve_named(name: str):
        """文件名解析：xx_*.md 精确名 或 mechanics 0N 简写."""
        p = DOCS / name
        if p.exists():
            return p
        p = MECHANICS / name
        if p.exists():
            return p
        m = re.fullmatch(r"0?(\d)", name)
        if m:
            for cand in MECHANICS.glob(f"0{m.group(1)}_*.md"):
                return cand
        return None

    bad = []
    for md in _doc_files():
        text = _strip_changelog(md.read_text(encoding="utf-8"))
        last_named = None  # 最近出现的 .md 文件名（跨行生效）
        for ln, line in enumerate(text.splitlines(), 1):
            if _EXEMPT_LINE.search(line):
                continue
            # 按位置顺序处理：文件名匹配与 § 引用交错推进
            events = [(m.start(), "name", m.group(1)) for m in _MD_NAME.finditer(line)]
            for mm in re.finditer(r"mechanics 0(\d)\b", line):
                cands = list(MECHANICS.glob(f"0{mm.group(1)}_*.md"))
                if cands:
                    events.append((mm.start(), "name", cands[0].name))
            events += [(m.start(), "ref", m.group(1)) for m in _REF.finditer(line)]
            for pos, kind, val in sorted(events):
                if kind == "name":
                    p = resolve_named(val)
                    if p:
                        last_named = p
                    continue
                # 否定语境（非/无 §X.Y）不是引用
                if re.search(r"[非无]", line[max(0, pos - 12):pos]):
                    continue
                if _ref_ok(val, idx_of(md)):
                    continue
                target = last_named if last_named else md
                if not _ref_ok(val, idx_of(target)):
                    bad.append(f"{md.name}:{ln}: §{val} 在 {target.name} 无对应章节")
    assert not bad, "\n".join(sorted(set(bad)))


# ===========================================================================
# 闸6 · 镜像一致：登记的同名公式跨文件必须逐字相等（归一化后）
# ===========================================================================

def _formula_expr(text: str, key: str) -> str:
    """在 yaml 块里找 `  <key>:` 下的 expression（单行或块标量）。"""
    pat = re.compile(rf"^\s*{re.escape(key)}:\s*$")
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if not pat.match(line):
            continue
        for j in range(i + 1, len(lines)):
            m = re.match(r"^\s*expression:\s*(.+)$", lines[j])
            if m:
                val = m.group(1)
                if val in ("|", ">"):
                    indent = len(lines[j]) - len(lines[j].lstrip())
                    val = _collect_block_scalars(lines, j, indent)
                else:
                    val = _unquote(val)
                return re.sub(r"\s+", " ", val).strip()
            if lines[j].strip() and not lines[j].startswith(" "):
                break
    return ""


MIRRORS = [
    ("elation_damage", "01_formula.md", "21_elation.md"),
]


def test_mirror_expressions_identical():
    bad = []
    texts = {n: (DOCS / n).read_text(encoding="utf-8") for n in
             {"01_formula.md", "21_elation.md"}}
    for key, fa, fb in MIRRORS:
        ea, eb = _formula_expr(texts[fa], key), _formula_expr(texts[fb], key)
        if ea != eb:
            bad.append(f"{key}: {fa} 与 {fb} 不一致\n  A: {ea}\n  B: {eb}")
    assert not bad, "\n\n".join(bad)


# ===========================================================================
# 闸13 · rulebook 镜像：rulebook.yaml ↔ 01_formula.md 公式/乘区逐字一致（归一化后）
# ===========================================================================

RULEBOOK = ROOT / "src" / "hsr_nous" / "sim_schema" / "rulebook.yaml"


def _doc_zone_exprs(text: str) -> dict:
    """01_formula parameters 形态：`- name: X` 后随（更深缩进的）`expression:`（同名取首见，重复名须同式）."""
    out = {}
    lines = text.splitlines()
    for i, line in enumerate(lines):
        m = re.match(r'^(\s*)-\s*name:\s*"?(\w+)"?\s*$', line)
        if not m:
            continue
        base = len(m.group(1))
        for j in range(i + 1, len(lines)):
            ln = lines[j]
            stripped = ln.strip()
            if not stripped:
                break  # 空行 = parameters 条目结束（不跨条目/跨块扫描）
            indent = len(ln) - len(ln.lstrip())
            if indent <= base and not stripped.startswith("#"):
                break  # 缩进回退 = 离开本条目（含下一个 - name:）
            e = re.match(r"^\s*expression:\s*(.+)$", ln)
            if e and indent > base:
                val = e.group(1)
                if val in ("|", ">"):
                    val = _collect_block_scalars(lines, j, indent)
                else:
                    val = _unquote(val)
                name = m.group(2)
                val = re.sub(r"\s+", " ", val).strip()
                if name in out and out[name] != val:
                    out[name] = f"!!重复名不同式!! {out[name]} vs {val}"
                else:
                    out[name] = val
                break
    return out


def _doc_break_effects(text: str) -> dict:
    """01_formula §1.4 的 break_effects YAML 块（```yaml 围栏内首个含 break_effects: 的块）."""
    import yaml
    for m in re.finditer(r"```yaml\n(.*?)```", text, re.S):
        if "break_effects:" not in m.group(1):
            continue
        data = yaml.safe_load(m.group(1))
        if isinstance(data, dict) and isinstance(data.get("break_effects"), dict):
            return data["break_effects"]
    return {}


def _doc_break_scaling_table(text: str) -> dict:
    """01_formula §1.7 属性击破倍率表：中文属性 → 倍率浮点（200% → 2.0）."""
    sec = text[text.index("### 1.7"):]
    end = sec.find("### 1.8")
    if end >= 0:
        sec = sec[:end]
    out = {}
    for m in re.finditer(r"^\|\s*(物理|火|风|冰|雷|量子|虚数)\s*\|\s*([\d.]+)%\s*\|", sec, re.M):
        out[m.group(1)] = float(m.group(2)) / 100
    return out


def test_rulebook_mirrors_01_formula():
    """rulebook（可执行唯一来源）与 01_formula（文档镜像）双向逐字一致 +
    rulebook 全部表达式过白名单解析（formula 层）."""
    import yaml
    rb = yaml.safe_load(RULEBOOK.read_text(encoding="utf-8"))
    doc = (DOCS / "01_formula.md").read_text(encoding="utf-8")
    bad = []
    # 顶层公式：rulebook formulas 每键 ↔ 01_formula 同名 expression
    for key, entry in rb["formulas"].items():
        rb_expr = re.sub(r"\s+", " ", str(entry["expression"])).strip()
        doc_expr = _formula_expr(doc, key)
        if not doc_expr:
            bad.append(f"formula {key!r}: 01_formula.md 无同名 expression")
        elif rb_expr != doc_expr:
            bad.append(f"formula {key!r} 不一致:\n  rulebook: {rb_expr}\n  01_formula: {doc_expr}")
    # 乘区：双向逐名一致
    doc_zones = _doc_zone_exprs(doc)
    rb_zones = {k: re.sub(r"\s+", " ", str(v)).strip() for k, v in rb["zones"].items()}
    for name in sorted(set(rb_zones) | set(doc_zones)):
        if name not in rb_zones:
            bad.append(f"乘区 {name!r}: 01_formula 有而 rulebook 缺")
        elif name not in doc_zones:
            bad.append(f"乘区 {name!r}: rulebook 有而 01_formula 缺")
        elif rb_zones[name] != doc_zones[name]:
            bad.append(f"乘区 {name!r} 不一致:\n  rulebook: {rb_zones[name]}\n  01_formula: {doc_zones[name]}")
    # 表达式本身必须过白名单（formula 层）——rulebook 是引擎直接消费的数据
    for label, exprs in (("formula", {k: v["expression"] for k, v in rb["formulas"].items()}),
                         ("zone", rb["zones"])):
        for name, expr in exprs.items():
            try:
                parse(str(expr), layer="formula")
            except ExpressionError as e:
                bad.append(f"rulebook {label} {name!r} 解析失败: {e}")
    # break_effects：rulebook 引擎表 ↔ 01_formula §1.4 镜像（逐元素字段级）
    EL_ZH = {"physical": "物理", "fire": "火", "ice": "冰", "thunder": "雷",
             "wind": "风", "quantum": "量子", "imaginary": "虚数"}
    doc_be = _doc_break_effects(doc)
    scaling_tbl = _doc_break_scaling_table(doc)
    for el, entry in rb["break_effects"].items():
        d = doc_be.get(el)
        if not d:
            bad.append(f"break_effects {el!r}: 01_formula §1.4 缺")
            continue
        dot_ratio = entry.get("dot_ratio")
        if dot_ratio and el != "quantum":  # 真 DoT（fire/thunder/wind）：倍率 ↔ effect_multiplier；持续 ↔ duration
            # quantum 豁免：rulebook dot 字段供引擎"纠缠近似为 2 回合 DoT"消费，
            # spec 侧模型是 §1.4 damage 表达式（控制类，duration 1）——两模型差异在案，不在本闸镜像范围
            if d.get("effect_multiplier") != dot_ratio:
                bad.append(f"break_effects {el!r} dot_ratio {dot_ratio} ≠ "
                           f"01_formula effect_multiplier {d.get('effect_multiplier')}")
            if d.get("duration") != entry.get("dot_duration"):
                bad.append(f"break_effects {el!r} dot_duration {entry.get('dot_duration')} ≠ "
                           f"01_formula duration {d.get('duration')}")
        if entry.get("control"):  # 控制类（ice/quantum/imaginary）：control_duration ↔ duration
            if d.get("duration") != entry.get("control_duration"):
                bad.append(f"break_effects {el!r} control_duration {entry.get('control_duration')} ≠ "
                           f"01_formula duration {d.get('duration')}")
        if el == "physical" and d.get("duration") != entry.get("dot_duration"):
            bad.append(f"break_effects physical dot_duration {entry.get('dot_duration')} ≠ "
                       f"01_formula duration {d.get('duration')}")
        zh = EL_ZH.get(el)  # 击破瞬间倍率 ↔ §1.7 属性倍率表
        if zh and scaling_tbl.get(zh) is not None and scaling_tbl[zh] != entry.get("scaling"):
            bad.append(f"break_effects {el!r} scaling {entry.get('scaling')} ≠ §1.7 {scaling_tbl[zh]}")
    assert not bad, "\n\n".join(bad)


# ===========================================================================
# 闸9 · 查表算术：遗器三档 vs 原始数据；断点表按公式重算
# ===========================================================================

RELIC_DATA = Path(__file__).parent.parent / "data" / "starrailres" / "index_new" / "cn" / "relic_sub_affixes.json"


def test_relic_substat_tiers_match_data():
    import json as _json
    if not RELIC_DATA.exists():
        import pytest as _pt
        _pt.skip("本地无 relic_sub_affixes.json")
    raw = _json.loads(RELIC_DATA.read_text(encoding="utf-8"))
    affixes = raw["5"]["affixes"]  # 结构：{rarity: {affixes: {id: {property, base, step}}}}
    data_vals = {a["property"]: (float(a["base"]), float(a["step"])) for a in affixes.values()}
    text = (DOCS / "06_relics.md").read_text(encoding="utf-8")
    entries = re.findall(r"(\w+):\s*\{base:\s*([\d.]+),\s*step:\s*([\d.]+)\}", text)
    assert entries, "06_relics 未找到 relic_sub_stats 表"
    doc_vals = {k: (float(b), float(s)) for k, b, s in entries}

    NAME_MAP = {
        "hp": "HPDelta", "atk": "AttackDelta", "def": "DefenceDelta",
        "hp_pct": "HPAddedRatio", "atk_pct": "AttackAddedRatio",
        "def_pct": "DefenceAddedRatio", "spd": "SpeedDelta",
        "crit_rate": "CriticalChanceBase", "crit_dmg": "CriticalDamageBase",
        "break_effect": "BreakDamageAddedRatioBase",
        "effect_hit": "StatusProbabilityBase", "effect_res": "StatusResistanceBase",
    }
    bad = []
    for k, (b, s) in doc_vals.items():
        prop = NAME_MAP.get(k)
        if prop not in data_vals:
            bad.append(f"{k}: 数据文件无对应 property（{prop}）")
            continue
        db, ds = data_vals[prop]
        if abs(b - db) > max(1e-6, abs(db) * 1e-4) or abs(s - ds) > max(1e-6, abs(ds) * 1e-4):
            bad.append(f"{k}: 文档 base={b} step={s} vs 数据 base={db} step={ds}")
    assert not bad, "\n".join(bad)


def test_ehr_breakpoint_table_recompute():
    text = (MECHANICS / "01_base_stats.md").read_text(encoding="utf-8")
    m = re.search(r"\| 敌人效果抗性 \| 基础概率 60% \| 基础概率 80% \| 基础概率 100% \| 基础概率 120% \|(.*?)\n\n", text, re.S)
    assert m, "断点表未找到"
    rows = re.findall(r"\| (\d+)% \| ([\d.]+)% \| ([\d.]+)% \| ([\d.]+)% \| ([\d.]+)% \|", m.group(1))
    assert len(rows) == 3, f"断点表行数异常: {rows}"
    bad = []
    for res_s, *cells in rows:
        res = int(res_s) / 100
        for p, got_s in zip((0.6, 0.8, 1.0, 1.2), cells):
            expect = (1 / (p * (1 - res)) - 1) * 100
            got = float(got_s)
            if abs(got - expect) > 0.06:
                bad.append(f"res={res_s}% p={p}: 表中 {got}% ≠ 计算 {expect:.1f}%")
    assert not bad, "\n".join(bad)


# ===========================================================================
# 闸17 · 遗器词条镜像：rulebook relic_affixes ↔ pipeline 词条数据重算（逐值精确）
# ===========================================================================

#: DSL 词条 id → StarRailRes property（闸 9a NAME_MAP 的全集：主/副词条共用一份词表）
_AFFIX_ID2PROP = {
    "hp": "HPDelta", "atk": "AttackDelta", "def_": "DefenceDelta",
    "hp_pct": "HPAddedRatio", "atk_pct": "AttackAddedRatio",
    "def_pct": "DefenceAddedRatio", "spd": "SpeedDelta",
    "crit_rate": "CriticalChanceBase", "crit_dmg": "CriticalDamageBase",
    "effect_hit": "StatusProbabilityBase", "effect_res": "StatusResistanceBase",
    "break_effect": "BreakDamageAddedRatioBase", "energy_regen": "SPRatioBase",
    "heal_bonus": "HealRatioBase",
    "physical_dmg": "PhysicalAddedRatio", "fire_dmg": "FireAddedRatio",
    "ice_dmg": "IceAddedRatio", "thunder_dmg": "ThunderAddedRatio",
    "wind_dmg": "WindAddedRatio", "quantum_dmg": "QuantumAddedRatio",
    "imaginary_dmg": "ImaginaryAddedRatio",
}


def test_rulebook_relic_affixes_match_pipeline():
    """rulebook.yaml relic_affixes 段（build 编译期消费的词条数值表）必须逐值 ==
    pipeline StarRailRes 词条数据重算（唯一来源）；键集同时与编译器 _AFFIX_FIELD 词表互锁——
    三处任一漂移在此炸（改数值先跑重算改 rulebook，改词表三处同步）."""
    import yaml as _yaml

    from hsr_nous.pipeline import calc_relic_main_affix_values, calc_relic_sub_affix_values
    from hsr_nous.sim.compile.build_compiler import _AFFIX_FIELD

    rb = _yaml.safe_load(RULEBOOK.read_text(encoding="utf-8")).get("relic_affixes") or {}
    want_main = {k: v for k, p in _AFFIX_ID2PROP.items()
                 if (v := calc_relic_main_affix_values().get(p)) is not None}
    want_sub = {k: v for k, p in _AFFIX_ID2PROP.items()
                if (v := calc_relic_sub_affix_values().get(p)) is not None}
    bad = []
    for kind, want in (("main", want_main), ("sub", want_sub)):
        got = rb.get(kind) or {}
        if set(got) != set(want):
            bad.append(f"relic_affixes.{kind} 键集漂移: rulebook {sorted(got)} != "
                       f"数据重算 {sorted(want)}")
            continue
        for k in want:
            if got[k] != want[k]:
                bad.append(f"relic_affixes.{kind}.{k}: rulebook {got[k]!r} != "
                           f"数据重算 {want[k]!r}（重算改 rulebook）")
    vocab = set(_AFFIX_FIELD)
    tables = set(rb.get("main") or {}) | set(rb.get("sub") or {})
    if vocab != tables:
        bad.append(f"编译器 _AFFIX_FIELD 词表 {sorted(vocab)} != rulebook 词条键集 {sorted(tables)}")
    assert not bad, "\n".join(bad)


# ===========================================================================
# 闸7 · 公式↔表格：伤害类型的公式乘区 = 生效表行 = §1.9 矩阵列（归一化集合）
# ===========================================================================

def _norm(zone: str) -> str:
    return re.sub(r"[_\s]", "", zone.lower())


CN2KEY = {
    "基础击破伤害": "breakBaseMulti", "韧性系数": "breakBaseMulti",
    "击破特攻": "beMulti", "击破特攻区": "beMulti",
    "超击破基数": "superBreakBaseMulti", "削韧": "superBreakBaseMulti",
    "超击破转换倍率": "superBreakConversionMulti",
    "击破增伤区": "breakDmgBoostMulti", "击破增伤": "breakDmgBoostMulti",
    "超击破增伤区": "superBreakDmgBoostMulti", "超击破增伤": "superBreakDmgBoostMulti",
    "最终伤害": "finalDmgMulti", "防御": "defMulti", "易伤": "vulnMulti",
    "减伤": "dmgRedMulti", "抗性": "resMulti", "韧性减伤": "baseUniversalMulti",
    "增伤": "dmgBoostMulti", "通用增伤": "dmgBoostMulti",
    "独立增伤": "indDmgBoostMulti", "独立易伤": "indVulnMulti",
    "双暴": "critMulti", "暴击": "critMulti", "虚弱": "weakenMulti",
    "等级系数": "levelMultiplier", "技能倍率": "abilityMultiplier",
    "欢愉度": "elationMulti", "笑点": "punchlineMulti", "好活当赏": "punchlineMulti",
    "增笑": "merrymakeMulti", "原始欢愉伤害倍率": "origElationDmgMulti",
    "欢愉增伤区": "elationDmgBoostMulti", "欢愉增伤": "elationDmgBoostMulti",
    "真实伤害": "trueDmgMulti", "效果命中区": "ehrMulti",
    "效果命中": "ehrMulti",
}

_TYPE_ROWS = {
    "直伤": "直伤", "常规持续伤害": "dot", "击破伤害": "break",
    "超击破伤害": "super_break", "真实伤害": "true", "欢愉伤害": "elation",
}
_FORMULA_SEC = {
    "dot": "### 2.12", "break": "### 2.10", "super_break": "### 2.11",
    "true": "### 2.8", "elation": "### 2.14",
}


def _sec_of(text: str, start: str, stops=("\n### ", "\n## ")) -> str:
    i = text.index(start)
    ends = [text.find(s, i + 1) for s in stops if text.find(s, i + 1) > 0]
    return text[i:min(ends)] if ends else text[i:]


def _formula_zones(text: str) -> set:
    zones = set(re.findall(r"\b(\w+Multi(?:plier)?)\b", text))
    return {_norm(z) for z in zones}


def _cell_zones(cell: str) -> set:
    out = set()
    for z in re.findall(r"\b(\w+Multi(?:plier)?)\b", cell):
        out.add(_norm(z))
    plain = re.sub(r"[（(].*?[)）]", "", cell)
    # 长 key 优先匹配并消耗命中片段，防止"增伤"误中"击破增伤/独立增伤"
    for cn in sorted(CN2KEY, key=len, reverse=True):
        if cn in plain:
            out.add(_norm(CN2KEY[cn]))
            plain = plain.replace(cn, " ")
    return out


# 各类型：公式乘区提取方式 + 各自豁免（基数容器：公式/生效表出现但矩阵无行）
_TYPE_EXEMPT = {
    "break": {"breakbasemulti"},
    "super_break": {"superbreakbasemulti", "superbreakconversionmulti"},
    "elation": {"levelmultiplier"},
}


def _first_code_zones(section_text: str) -> set:
    """只取章节内第一个 ```...``` 代码块中的乘区。"""
    m = re.search(r"```\n(.*?)```", section_text, re.S)
    return _formula_zones(m.group(1)) if m else set()


def test_formula_vs_tables():
    text = (MECHANICS / "02_damage_formula.md").read_text(encoding="utf-8")
    # 生效表（02:43-50）
    tbl = _sec_of(text, "| 伤害类型 | 生效乘区 | 不生效乘区 |", ("\n>",))
    table = {}
    for m in re.finditer(r"\| ([^|]+) \| ([^|]+) \| ([^|]+) \|", tbl):
        name = m.group(1).strip()
        for k, v in _TYPE_ROWS.items():
            if name.startswith(k):
                table[v] = _cell_zones(m.group(2))
    # §2.1 主公式乘区（直伤行与 DOT 行的"2.1 常规乘区"由此展开）
    zones21 = _first_code_zones(_sec_of(text, "### 2.1" if "### 2.1" in text else "## 2.1"))
    # 公式乘区：dot/break/super_break 取各节第一个代码块；true/elation 取全节
    formulas = {
        "dot": _first_code_zones(_sec_of(text, _FORMULA_SEC["dot"])),
        "break": _first_code_zones(_sec_of(text, _FORMULA_SEC["break"])),
        "super_break": _first_code_zones(_sec_of(text, _FORMULA_SEC["super_break"])),
        "true": _formula_zones(_sec_of(text, _FORMULA_SEC["true"])),
        "elation": _formula_zones(_sec_of(text, _FORMULA_SEC["elation"])),
        "直伤": zones21,
    }
    # 生效表特殊行展开
    table["dot"] = (zones21 - {_norm("critMulti")}) | {_norm("ehrMulti")}
    table["直伤"] = set(zones21)
    # schema 矩阵
    schema_text = (DOCS / "01_formula.md").read_text(encoding="utf-8")
    mtx = _sec_of(schema_text, "### 1.9")
    cols = [c.strip() for c in re.findall(r"\| 乘区 \| (.+) \|", mtx)[0].split("|")]
    matrix = {c: set() for c in cols}
    for m in re.finditer(r"^\| (\w+) \| (.+)$", mtx, re.M):
        zone = m.group(1)
        marks = [x.strip() for x in m.group(2).split("|")]
        for c, mk in zip(cols, marks):
            if mk == "✓":
                matrix[c].add(_norm(zone))

    bad = []
    for t in ("dot", "break", "super_break", "true", "elation"):
        ex = _TYPE_EXEMPT.get(t, set())
        f = formulas.get(t, set()) - ex
        tb = table.get(t, set()) - ex
        if f != tb:
            bad.append(f"{t}: 生效表多出 {sorted(tb - f)} / 生效表缺 {sorted(f - tb)}")
        col = {"dot": "DOT", "break": "击破", "super_break": "超击破",
               "true": "真实伤害", "elation": "欢愉"}[t]
        mz = matrix.get(col, set()) - ex
        if mz != f:
            bad.append(f"{t} 矩阵: 矩阵多出 {sorted(mz - f)} / 矩阵缺 {sorted(f - mz)}")
    assert not bad, "\n".join(bad)


# ===========================================================================
# 闸10 · 索引一致：README 索引清单 ↔ 磁盘文件（双向）
# ===========================================================================

def _index_entries(readme: Path, link_prefix: str = "") -> set:
    """提取 README 索引中的 NN_xxx.md：有 link_prefix 只认 markdown 链接，
    否则只认目录树行（├──/└──）。"""
    text = readme.read_text(encoding="utf-8")
    if link_prefix:
        return set(re.findall(rf"\({re.escape(link_prefix)}(\d\d_[a-z_0-9]+\.md)\)", text))
    out = set()
    for line in text.splitlines():
        if ("├──" in line or "└──" in line) and ".md" in line:
            m = re.search(r"(\d\d_[a-z_0-9]+\.md)", line)
            if m:
                out.add(m.group(1))
    return out


def test_readme_indexes_match_disk():
    bad = []
    # sim_schema/README.md 章节表 ↔ sim_schema/docs/（只认表格里的 markdown 链接）
    readme_idx = _index_entries(ROOT / "src/hsr_nous/sim_schema/README.md", "docs/")
    disk = {p.name for p in DOCS.glob("??_*.md")}
    for f in sorted(disk - readme_idx):
        bad.append(f"sim_schema/README.md 索引缺 {f}")
    for f in sorted(readme_idx - disk):
        bad.append(f"sim_schema/README.md 索引指向不存在的 {f}")
    # docs/README.md 目录树 ↔ docs/mechanics/
    mech_idx = _index_entries(ROOT / "docs/README.md")
    mech_disk = {p.name for p in (ROOT / "docs/mechanics").glob("??_*.md")}
    for f in sorted(mech_disk - mech_idx):
        bad.append(f"docs/README.md 索引缺 mechanics/{f}")
    for f in sorted(mech_idx - mech_disk):
        bad.append(f"docs/README.md 索引指向不存在的 mechanics/{f}")
    assert not bad, "\n".join(bad)


# ===========================================================================
# 闸11 · 模块边界：AGENTS.md 边界表 ↔ 闸门配置 ↔ 实际 import（三向）
# ===========================================================================

# 与 AGENTS.md「模块边界」表的"允许 import"列一致，改表需同步本配置
BOUNDARY_ALLOWED = {
    "pipeline": set(),
    "raw_schema": set(),
    "sim_schema": set(),
    "adapters": {"pipeline", "raw_schema", "sim_schema", "account"},
    "sim": {"sim_schema"},
    "agents": {"adapters", "sim", "pipeline", "account"},
    "api": {"agents", "adapters", "sim", "pipeline"},
    "account": set(),
    "screen": {"adapters", "sim_schema"},
    "pilot": {"screen"},
}

_IMPORT_RE = re.compile(r"^\s*(?:from|import)\s+hsr_nous\.([a-z_]+)", re.M)


def _actual_edges() -> dict:
    """扫各模块真实 import 的跨模块边。"""
    edges = {}
    for mod in BOUNDARY_ALLOWED:
        mods = set()
        for py in (ROOT / "src/hsr_nous" / mod).rglob("*.py"):
            for m in _IMPORT_RE.finditer(py.read_text(encoding="utf-8")):
                target = m.group(1)
                if target != mod and target in BOUNDARY_ALLOWED:
                    mods.add(target)
        edges[mod] = mods
    return edges


def _agents_md_allowed() -> dict:
    """解析 AGENTS.md 模块边界表的"允许 import"列（反引号模块名）。"""
    text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    table = {}
    for m in re.finditer(r"^\| `([a-z_]+)/` \| ([^|]+) \|", text, re.M):
        mod, cell = m.group(1), m.group(2)
        names = set(re.findall(r"`([a-z_]+)`", cell))
        table[mod] = {n for n in names if n in BOUNDARY_ALLOWED}
    return table


def test_module_boundaries():
    bad = []
    actual = _actual_edges()
    for mod, targets in actual.items():
        over = targets - BOUNDARY_ALLOWED[mod]
        if over:
            bad.append(f"{mod}/ 实际 import 越界: {sorted(over)}（表未允许）")
    parsed = _agents_md_allowed()
    for mod in BOUNDARY_ALLOWED:
        if mod not in parsed:
            bad.append(f"AGENTS.md 边界表缺 {mod}/ 行")
            continue
        if parsed[mod] != BOUNDARY_ALLOWED[mod]:
            bad.append(f"{mod}/ 表格允许 {sorted(parsed[mod])} != 闸门配置 {sorted(BOUNDARY_ALLOWED[mod])}")
    assert not bad, "\n".join(bad)


# ===========================================================================
# 闸12 · 同步闸：README 标记区镜像 == AGENTS.md 源表（归一化后逐字相等）
# ===========================================================================

def _agents_boundary_table() -> list:
    """AGENTS.md「模块边界」节的表格行（| 开头的行，去尾空白）。"""
    text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    sec = text[text.index("## 模块边界"):text.index("**核心原则**")]
    return [ln.rstrip() for ln in sec.splitlines() if ln.startswith("|")]


def _readme_mirror() -> list:
    """README 中 <!-- module-boundaries --> 标记区内的非空行。"""
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    begin = text.index("<!-- module-boundaries -->")
    end = text.index("<!-- /module-boundaries -->")
    return [ln.rstrip() for ln in text[begin:end].splitlines()[1:] if ln.strip()]


def test_boundary_mirror_in_sync():
    src = _agents_boundary_table()
    mirror = _readme_mirror()
    assert src, "AGENTS.md 未找到模块边界表"
    assert mirror, "README 未找到 module-boundaries 标记区"
    assert mirror == src, (
        "README 模块边界表与 AGENTS.md 不一致——改表请改 AGENTS.md，"
        "并把该节表格同步到 README 的 <!-- module-boundaries --> 标记区"
    )


# ===========================================================================
# 闸14 · 词表闸：§22.4 函数表"状态"列 ↔ expression.py 白名单（唯一事实来源）
# ===========================================================================

_FUNC_CALL = re.compile(r"`(\w+)\(")


def _v224_function_status() -> dict:
    """§22.4 白名单函数表：函数名 → "implemented" / "unimplemented"（同行多函数共享行状态）.

    行分类规则（表格纪律）：含"已实现" → implemented（含"公式层已实现"的混合行——
    该函数确在白名单某层）；否则含"未实现" → unimplemented；两者都无 = 漏标状态。
    """
    text = (DOCS / "22_syntax_reference.md").read_text(encoding="utf-8")
    sec = text[text.index("#### 白名单函数"):text.index("#### 运算符")]
    out = {}
    for line in sec.splitlines():
        if not line.startswith("|"):
            continue
        names = _FUNC_CALL.findall(line)
        if not names:
            continue  # 表头 / 分隔行
        if "已实现" in line:
            status = "implemented"
        elif "未实现" in line:
            status = "unimplemented"
        else:
            status = None
        for n in names:
            out[n] = status
    return out


def test_expression_functions_mirror_22_4():
    """§22.4 函数表标"已实现"的集合必须逐名等于 expression.py 白名单（两层并集），
    标"未实现"的集合与白名单不交——expression.py 是唯一事实来源，防四方再分裂."""
    from hsr_nous.sim_schema.expression import EFFECT_FUNCTIONS, FORMULA_FUNCTIONS

    whitelist = set(EFFECT_FUNCTIONS) | set(FORMULA_FUNCTIONS)
    table = _v224_function_status()
    assert table, "§22.4 未找到白名单函数表"
    bad = []
    missing_status = sorted(n for n, s in table.items() if s is None)
    if missing_status:
        bad.append(f"§22.4 行缺“状态”标注：{missing_status}")
    impl = {n for n, s in table.items() if s == "implemented"}
    if impl != whitelist:
        bad.append(
            f"§22.4 标已实现 {sorted(impl)} != expression.py 白名单 {sorted(whitelist)}"
            f"（多标 {sorted(impl - whitelist)} / 漏标 {sorted(whitelist - impl)}）"
        )
    overlap = {n for n, s in table.items() if s == "unimplemented"} & whitelist
    if overlap:
        bad.append(f"§22.4 标未实现但白名单已实现：{sorted(overlap)}")
    assert not bad, "\n".join(bad)


# ===========================================================================
# 闸15 · terminology 乘区键闸：terminology.yaml"伤害乘区"键 ⊆ rulebook zones ∪ 公式标识符
# ===========================================================================

TERMINOLOGY = ROOT / "terminology.yaml"


def test_terminology_zone_keys_in_rulebook():
    """terminology.yaml 的"伤害乘区"分节键必须命中 rulebook 乘区名或公式表达式标识符——
    乘区键唯一来源 = rulebook.yaml（防 ability_multi → ability_multiplier 类漂移再发）."""
    import yaml

    rb = yaml.safe_load(RULEBOOK.read_text(encoding="utf-8"))
    known = set(rb["zones"])
    for entry in rb["formulas"].values():
        known |= set(re.findall(r"\b[a-z_]\w*\b", str(entry["expression"])))
    text = TERMINOLOGY.read_text(encoding="utf-8")
    m = re.search(r"# ===== 伤害乘区 =====\n(.*?)(?=\n# =====|\Z)", text, re.S)
    assert m, "terminology.yaml 缺'伤害乘区'分节"
    bad = []
    for line in m.group(1).splitlines():
        km = re.match(r"^([a-z_]\w*):", line)
        if km and km.group(1) not in known:
            bad.append(f"乘区键 {km.group(1)!r} 不在 rulebook zones/公式标识符中")
    assert not bad, "\n".join(bad)


# ===========================================================================
# 闸16 · 事件契约闸：§23.4 事件表"状态"列 ↔ sim/bus.py DEFAULT_CONTRACT
# ===========================================================================

_EVENT_ROW = re.compile(r"^\|\s*`(\w+)`\s*\|")


def _v234_event_status() -> dict:
    """§23.4 事件表：事件名 → "registered" / "unregistered"（首列反引号事件名，整行共享状态词）.

    行分类规则（表格纪律，同闸 14 先例）：含"已登记" → registered；否则含"未登记" →
    unregistered；两者都无 = 漏标状态。
    """
    text = (DOCS / "23_event_hook_system.md").read_text(encoding="utf-8")
    sec = text[text.index("### 23.4"):text.index("### 23.5")]
    out = {}
    for line in sec.splitlines():
        m = _EVENT_ROW.match(line)
        if not m:
            continue
        if "已登记" in line:
            status = "registered"
        elif "未登记" in line:
            status = "unregistered"
        else:
            status = None
        out[m.group(1)] = status
    return out


def _v48_lifecycle_events() -> set:
    """04_modifier §4.8 生命周期触发表的事件名（首列反引号）——契约中归该表的事件免进 §23.4."""
    text = (DOCS / "04_modifier.md").read_text(encoding="utf-8")
    sec = text[text.index("### 4.8"):text.index("### 4.9")]
    return {m.group(1) for m in re.finditer(r"^\|\s*`(\w+)`\s*\|", sec, re.M)}


def test_event_contract_mirror_23_4():
    """§23.4 标"已登记"集 == DEFAULT_CONTRACT − §4.8 生命周期表；标"未登记"集与契约不交；
    契约每个键必须在 §23.4 已登记行或 §4.8 表登记——`sim/bus.py` 是唯一事实来源，防再漂
    （模板侧另有编译期闸：hook event 不在契约即炸，见 13_validator §13.2）。"""
    from hsr_nous.sim.bus import DEFAULT_CONTRACT

    contract = set(DEFAULT_CONTRACT)
    table = _v234_event_status()
    lifecycle = _v48_lifecycle_events()
    assert table, "§23.4 未找到事件表"
    bad = []
    missing_status = sorted(n for n, s in table.items() if s is None)
    if missing_status:
        bad.append(f"§23.4 行缺“状态”标注：{missing_status}")
    registered = {n for n, s in table.items() if s == "registered"}
    unregistered = {n for n, s in table.items() if s == "unregistered"}
    expected = contract - lifecycle
    if registered != expected:
        bad.append(
            f"§23.4 标已登记 {sorted(registered)} != 契约−§4.8 {sorted(expected)}"
            f"（多标 {sorted(registered - expected)} / 漏标 {sorted(expected - registered)}）"
        )
    overlap = unregistered & contract
    if overlap:
        bad.append(f"§23.4 标未登记但契约已登记：{sorted(overlap)}")
    uncovered = contract - registered - lifecycle
    if uncovered:
        bad.append(f"契约键在 §23.4 / §4.8 皆未登记：{sorted(uncovered)}")
    assert not bad, "\n".join(bad)
