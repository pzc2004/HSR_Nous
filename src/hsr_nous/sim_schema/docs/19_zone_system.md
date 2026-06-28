## 19. 场地系统 (Zone System)

> **实现说明**：本文档按 Pydantic v2 类型描述目标 schema。当前代码仍使用 `@dataclass`，Pydantic 迁移是独立 PR（见 `designs/0001-mechanics-scan-redesign.md` §3.11）。文档是前瞻性定义，代码会后续对齐。

### 19.1 设计目标

建模“actor 部署一个持续 N 回合的区域效果”。场地内目标可享受 modifier、触发额外效果、改变伤害结算。

典型用例：
- Phainon 终结技部署 "Ruinous Irontomb"
- Cyrene 部署 "Bloom, Elysium of Beyond"
- 爻光 战技 部署 结界
- Silver Wolf LV.999 部署 "God Mode Zone"

### 19.2 Zone 字段

```python
class Zone(BaseModel):
    zone_id: str
    owner_actor_id: str
    area_shape: Literal["single_target", "all_enemies", "all_allies", "self", "battlefield"]
    duration: int
    on_turn_start: list[str] = []
    on_enter: list[str] = []
    on_damage_deal: list[str] = []
    scoped_modifiers: list[str] = []
    in_zone_filter: str | None = None
    duration_decrement_trigger: Literal["on_turn_start", "on_turn_end", "on_cycle_end"] = "on_turn_start"
```

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `zone_id` | string | 必填 | 场地唯一 ID |
| `owner_actor_id` | `actor_id` | 必填 | 部署者 |
| `area_shape` | enum | 必填 | 作用范围：`single_target` / `all_enemies` / `all_allies` / `self` / `battlefield` |
| `duration` | int | 必填 | 持续回合数；`0` = 永久 |
| `on_turn_start` | `List[effect_id]` | `[]` | 每回合开始时触发的效果 |
| `on_enter` | `List[effect_id]` | `[]` | 目标进入场地时触发的效果 |
| `on_damage_deal` | `List[effect_id]` | `[]` | 场地内造成伤害时触发的效果 |
| `scoped_modifiers` | `List[modifier_id]` | `[]` | 仅在场地内生效的 modifier |
| `in_zone_filter` | expression? | `None` | 目标过滤表达式（谁算“在场地内”） |
| `duration_decrement_trigger` | enum | `"on_turn_start"` | 持续时间扣减时机：`on_turn_start` / `on_turn_end` / `on_cycle_end` |

### 19.3 新增 effect_type

#### `deploy_zone`

```yaml
effect_type: "deploy_zone"
zone_id: "ruinous_irontomb"
area_shape: "battlefield"
duration: 3
on_turn_start:
  - "effect_ruinous_irontomb_tick"
on_damage_deal:
  - "effect_ruinous_irontomb_bonus"
scoped_modifiers:
  - "MOD_RUINOUS_IRONTOMB_BUFF"
```

#### `dismiss_zone`

```yaml
effect_type: "dismiss_zone"
zone_id: "ruinous_irontomb"
```

### 19.4 Target 过滤扩展

表达式中可使用：
- `in_zone(zone_id)` — 判断目标是否在指定 zone 内
- `zone_owner()` — 返回 zone 的拥有者

```yaml
# 仅对处于某 zone 内的敌人造成伤害
target:
  type: "filter"
  condition: "in_zone('yao_zone')"
```

### 19.5 应用案例（待定型）

| 角色 | Zone ID | 效果 |
|------|---------|------|
| Phainon | `ruinous_irontomb` | 终结技部署，战场级效果 |
| Cyrene | `bloom_elysium` | 忆灵相关区域 |
| 爻光 | `zone_team_elation_buff` | 结界，全队欢愉加成 |
| Silver Wolf LV.999 | `god_mode_zone` | 神模式区域 |

### 19.6 TBD

- Zone 拥有者死亡时的行为：立即消失 / 持续到时长结束 / 转移给队友（§5 #4）。
- 多 zone 嵌套是否允许（§5 #11）。
- `in_zone_filter` 的完整语法与默认规则。

---
