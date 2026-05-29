## 12. 输入验证 (Validator)

验证器检查 Encounter 配置的合法性，防止非法输入导致模拟器异常。

### 使用方式

```python
from hsr_nous.sim_schema import validate_encounter, Encounter, Actor

encounter = Encounter(
    encounter_id="E_001",
    name="测试关卡",
    actors=[
        Actor(actor_id="1001", name="三月七", actor_type="character", level=80),
    ],
)

result = validate_encounter(encounter)
if result.valid:
    print("验证通过")
else:
    for error in result.errors:
        print(f"ERROR: {error.path} - {error.message}")
    for warning in result.warnings:
        print(f"WARNING: {warning.path} - {warning.message}")
```

### 验证规则

| 类别 | 规则 | 严重程度 |
|------|------|---------|
| 角色数量 | 上限 4 个 | error |
| 敌人数量 | 每波次上限 10 个 | error |
| 波次数 | 上限 10 个 | error |
| 轮次 AV | 首轮/后续 AV >= 1 | error |
| 最大轮次数 | 上限 99 | error |
| 等级 | 1-90 | error |
| 速度 | 必须 > 0 | error |
| 能量 | 当前 <= 上限 | error |
| 韧性 | 当前 <= 上限 | error |
| 暴击率 | 建议 0-1 | warning |
| 战技点 | current <= max | error |
| actor_type | character/monster/summon | error |
| modifier_type | buff/debuff/dot/shield/heal/control | error |

---

