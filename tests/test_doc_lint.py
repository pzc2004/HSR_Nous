"""文档 lint：把 sim_schema/docs 的 24 章当代码做机械全量检查（T4 工具箱）.

四闸（全量、机械、无语义判断）：
1. **表达式闸**：文档中所有表达式字符串必须过 `ast` 白名单解析
2. **effect_type 闸**：用法必须命中声明清单（05 + 17/19/23 章）
3. **触发器闸**：trigger / hook 事件名必须命中 §4.8 + §23.4 清单
4. **公式闸**：01_formula 顶层 formula 表达式的标识符必须有 parameters 定义
"""

import re
from pathlib import Path

import pytest

from hsr_nous.sim_schema.expression import ExpressionError, parse
import ast as _ast

DOCS = Path(__file__).parent.parent / "src" / "hsr_nous" / "sim_schema" / "docs"

EXPR_KEYS = re.compile(
    r"^\s*(?:-\s*)?(amount|condition|expression|flat_bonus|scaling_from_source|"
    r"threshold|max_bonus|step|per_step_bonus|duration|hit_condition|delay_condition|"
    r"target_filter|in_zone_filter)\s*:\s*(.+?)\s*$"
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
