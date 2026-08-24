"""sim_schema/expression.py 的单元测试.

覆盖：算术/布尔/三元/命名空间/白名单函数/RNG 注入/拒绝项/trace 树。
文档 golden 用例来自 `22_syntax_reference.md`。
"""

import random

import pytest

from hsr_nous.sim_schema.expression import (
    ExpressionError,
    evaluate,
    parse,
)


def ev(source, context=None, layer="effect", rng=None, functions=None):
    return evaluate(parse(source, layer=layer), context or {}, rng=rng, functions=functions).value


# ---------------------------------------------------------------------------
# 算术与比较
# ---------------------------------------------------------------------------


def test_arithmetic_precedence():
    assert ev("1 + 2 * 3 - 4 / 2") == 5.0


def test_floor_div_mod_pow():
    assert ev("7 // 2") == 3
    assert ev("7 % 2") == 1
    assert ev("2 ** 3") == 8


def test_unary_minus_and_not():
    assert ev("-5 + 3") == -2
    assert ev("not 0") is True


def test_chained_comparison():
    assert ev("0 < 3 < 5") is True
    assert ev("0 < 3 < 2") is False


def test_bool_short_circuit():
    # 短路时不应访问未定义变量
    assert ev("true_var or undefined_var", {"true_var": True}) is True
    assert ev("false_var and undefined_var", {"false_var": False}) is False


def test_plain_names_from_context():
    assert ev("target_toughness > 0 ? 0.9 : 1.0", {"target_toughness": 30}) == 0.9
    assert ev("target_toughness > 0 ? 0.9 : 1.0", {"target_toughness": 0}) == 1.0


# ---------------------------------------------------------------------------
# C 三元转换
# ---------------------------------------------------------------------------


def test_ternary_basic():
    assert ev("1 > 0 ? 10 : 20") == 10
    assert ev("1 < 0 ? 10 : 20") == 20


def test_ternary_nested():
    assert ev("1 > 0 ? (2 > 1 ? 'a' : 'b') : 'c'") == "a"


def test_ternary_with_operators_and_funcs():
    assert ev("(random() < crit_rate) ? (1 + crit_dmg) : 1.0", {"crit_rate": 1.0, "crit_dmg": 0.5}, layer="formula", rng=random.Random(1)) == 1.5


def test_ternary_missing_colon_rejected():
    with pytest.raises(ExpressionError):
        parse("1 > 0 ? 10")


def test_ternary_multiple_q_rejected():
    with pytest.raises(ExpressionError):
        parse("1 > 0 ? 10 ? 20 : 30 : 40")


# ---------------------------------------------------------------------------
# 布尔运算符与命名空间（DSL 语法 → Python）
# ---------------------------------------------------------------------------


def test_dsl_boolean_operators():
    assert ev("$resource.punchline > 100 && !$target.broken",
              {"resource": {"punchline": 150}, "target": {"broken": False}}) is True
    assert ev("$resource.punchline > 100 || $target.broken",
              {"resource": {"punchline": 50}, "target": {"broken": True}}) is True


def test_namespaces():
    ctx = {
        "self": {"max_hp": 6000, "heal_pct": 0.5},
        "resource": {"punchline": 120},
        "event": {"amount": 30},
        "target": {"hp": 800, "max_hp": 1000},
        "build": {"eidolon": 6, "skill_levels": {"skill": 10}},
        "prev": {"amount": 100},
        "last": {"actual_amount": 25},
        "team": {"taunt": [1, 2, 3]},
    }
    assert ev("$self.max_hp * $self.heal_pct + 200", ctx) == 3200.0
    assert ev("$event.amount - $last.actual_amount", ctx) == 5
    assert ev("$target.hp / $target.max_hp < 0.5", ctx) is False
    assert ev("$build.eidolon >= 6", ctx) is True
    assert ev("$prev.amount * 0.8", ctx) == 80.0
    assert ev("sum($team.taunt)", ctx) == 6


def test_attribute_on_objects():
    class Obj:
        pass

    o = Obj()
    o.stats = {"atk": 2000}
    assert ev("$self.stats.atk * 2", {"self": o}) == 4000


def test_subscript():
    ctx = {"build": {"skill_levels": {"basic": 2}}, "basic_scaling": [0.5, 0.6, 0.7]}
    assert ev("basic_scaling[$build.skill_levels.basic - 1]", ctx) == 0.6


# ---------------------------------------------------------------------------
# 白名单函数
# ---------------------------------------------------------------------------


def test_builtin_functions():
    assert ev("min(3, 5)") == 3
    assert ev("max(3, 5)") == 5
    assert ev("abs(-4)") == 4
    assert ev("round(3.6)") == 4
    assert ev("clamp(15, 0, 10)") == 10
    assert ev("clamp(-5, 0, 10)") == 0
    assert ev("sum([1, 2, 3])") == 6


def test_chance_deterministic_with_seed():
    assert ev("chance(100)", rng=random.Random(42)) is True
    assert ev("chance(0)", rng=random.Random(42)) is False
    # 同一 seed 两次求值可复现（注入式随机源）
    assert ev("chance(50)", rng=random.Random(7)) == ev("chance(50)", rng=random.Random(7))


def test_in_zone_host_function():
    assert ev("in_zone('yao_zone')", functions={"in_zone": lambda z: z == "yao_zone"}) is True
    assert ev("in_zone('yao_zone')", functions={"in_zone": lambda z: False}) is False


def test_lookup_table_formula_layer():
    def lookup_table(name, index):
        return {"base_hp_by_level": [1200, 1300, 1400]}[name][index]

    assert ev('lookup_table("base_hp_by_level", index=$build.level - 1)',
              {"build": {"level": 2}}, layer="formula", functions={"lookup_table": lookup_table}) == 1300


def test_random_only_formula_layer():
    assert ev("random() < 1", layer="formula", rng=random.Random(1)) is True
    with pytest.raises(ExpressionError, match="白名单"):
        parse("random() < 1", layer="effect")


# ---------------------------------------------------------------------------
# 拒绝项（安全红线）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad", [
    "open('x')",                         # 任意内置函数
    "eval('1')",
    "__import__('os')",
    "print(1)",
    "exec('a=1')",
    "'abc'.upper()",                     # 方法调用
    "[x for x in [1]]",                  # 推导式
    "lambda x: x",
    "f'{1}'",
    "(1 if True else 2 if True else 3)", # Python 风格三元（文档只允许 C 风格）
])
def test_rejected_constructs(bad):
    with pytest.raises(ExpressionError):
        parse(bad)


def test_dunder_attribute_rejected():
    with pytest.raises(ExpressionError, match="内部属性"):
        parse("$self.__class__")


def test_unknown_namespace_rejected():
    with pytest.raises(ExpressionError, match="未知命名空间"):
        parse("$foo.bar + 1")


def test_undefined_variable_error_message():
    with pytest.raises(ExpressionError, match="未定义变量 'self'"):
        ev("$self.atk + 1")


def test_missing_attribute_error():
    with pytest.raises(ExpressionError, match="不存在"):
        ev("$self.defense", {"self": {"atk": 1}})


def test_chance_requires_rng():
    with pytest.raises(ExpressionError, match="随机源"):
        ev("chance(50)")


def test_syntax_error():
    with pytest.raises(ExpressionError, match="语法错误"):
        parse("1 +* 2")


def test_slice_rejected():
    with pytest.raises(ExpressionError):
        ev("$self.skills[0:2]", {"self": {"skills": [1, 2, 3]}})


# ---------------------------------------------------------------------------
# 文档 golden 用例（22_syntax_reference.md）
# ---------------------------------------------------------------------------


def test_doc_example_hyacine_damage():
    # 22.11：amount: "$resource.hyacine_cumulative_heal * $self.damage_ratio"
    ctx = {"resource": {"hyacine_cumulative_heal": 5000}, "self": {"damage_ratio": 0.6}}
    assert ev("$resource.hyacine_cumulative_heal * $self.damage_ratio", ctx) == 3000.0


def test_doc_example_condition():
    # 22.4 白名单示例
    assert ev("$self.hp / $self.max_hp < 0.5", {"self": {"hp": 300, "max_hp": 1000}}) is True
    assert ev("$resource.punchline > 100 && !$target.broken",
              {"resource": {"punchline": 120}, "target": {"broken": False}}) is True


def test_doc_example_crit_formula():
    # 01_formula.md crit_multi（公式层 + 注入随机源）
    crit_ctx = {"crit_rate": 1.0, "crit_dmg": 0.8}
    assert ev("(random() < crit_rate) ? (1 + crit_dmg) : 1.0", crit_ctx,
              layer="formula", rng=random.Random(0)) == 1.8
    crit_ctx["crit_rate"] = 0.0
    assert ev("(random() < crit_rate) ? (1 + crit_dmg) : 1.0", crit_ctx,
              layer="formula", rng=random.Random(0)) == 1.0


# ---------------------------------------------------------------------------
# Prepared 复用 + trace 树
# ---------------------------------------------------------------------------


def test_parse_once_evaluate_many():
    prepared = parse("$self.atk * 2 + 1")
    assert evaluate(prepared, {"self": {"atk": 100}}).value == 201
    assert evaluate(prepared, {"self": {"atk": 400}}).value == 801


def test_trace_tree():
    outcome = evaluate(parse("$self.max_hp * 0.3 + 200"), {"self": {"max_hp": 6000}})
    assert outcome.value == 2000.0
    t = outcome.trace
    assert t["kind"] == "BinOp" and t["op"] == "Add" and t["value"] == 2000.0
    mul = t["children"][0]
    assert mul["op"] == "Mult" and mul["value"] == 1800.0
    attr = mul["children"][0]
    assert attr["kind"] == "Attribute" and attr["attr"] == "max_hp" and attr["value"] == 6000
    const = t["children"][1]
    assert const == {"kind": "Constant", "value": 200}


def test_reserved_word_def_as_stat():
    # `$self.def`：def 是 Python 关键字，走 .def → ["def"]，dict key 统一为 defense
    assert ev("$self.def * 0.48 + 640", {"self": {"defense": 1000}}) == 1120.0


def test_bare_def_identifier():
    # 护盾公式里的裸 def（def_scaling * def ...）
    assert ev("(def_scaling * def + flat_shield) * 2",
              {"def_scaling": 0.5, "defense": 1000, "flat_shield": 100}) == 1200.0


def test_multiline_expression():
    # expression: | 块标量折行：压平后单行求值
    assert ev("1 +\n2 *\n3") == 7.0


# ---------------------------------------------------------------------------
# 字符串字面量保护（预处理变换不得改写引号内容——审查实测的静默改名）
# ---------------------------------------------------------------------------


def _str_arg(source):
    """求值 has_modifier(...) 并返回第二个参数（字符串字面量）原样值."""
    return ev(source, functions={"has_modifier": lambda target, mid: mid})


def test_string_literal_and_or_untouched():
    # 曾把参数静默改成 "a and b"
    assert _str_arg('has_modifier("x", "a && b")') == "a && b"
    assert _str_arg('has_modifier("x", "a || b")') == "a || b"


def test_string_literal_bang_untouched():
    # 曾把参数静默改成 "x not y"
    assert _str_arg('has_modifier("x", "x!y")') == "x!y"
    assert _str_arg("has_modifier('x', 'x!y')") == "x!y"


def test_string_literal_def_untouched():
    # 曾把参数静默改成 "defense"
    assert _str_arg('has_modifier("x", "def")') == "def"


def test_string_literal_if_not_rejected():
    # 字符串内的 if/else 不触发"Python 风格三元"误杀
    assert _str_arg('has_modifier("x", "if only")') == "if only"
    assert parse('"if only"').tree is not None


def test_string_literal_dollar_untouched():
    # 字符串内的 $ 不报"未知命名空间引用"
    assert _str_arg('has_modifier("x", "a $ b")') == "a $ b"


def test_string_literal_ternary_chars_untouched():
    # 字符串内的 ? : 不参与三元切分
    assert _str_arg('has_modifier("x", "a ? b : c")') == "a ? b : c"


def test_string_literal_operators_outside_still_transform():
    # 回归：非字符串段的 &&/!/def 照常变换
    assert ev('$self.hp > 0 && "a" == "a"', {"self": {"hp": 1}}) is True
    assert ev('!("a" == "b")') is True
    assert ev('$self.def + 1', {"self": {"defense": 10}}) == 11.0


def test_ternary_with_string_branches():
    assert ev('1 > 0 ? "y" : "n"') == "y"
    assert ev('1 < 0 ? "y" : "n"') == "n"


def test_unterminated_string_rejected():
    with pytest.raises(ExpressionError, match="引号未闭合"):
        parse('has_modifier("x, "a"')
