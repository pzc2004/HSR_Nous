## 19. 场地系统 (Zone System)

> **实现说明**：本文档按 Pydantic v2 类型描述目标 schema。当前代码仍使用 `@dataclass`，Pydantic 迁移尚未完成。文档是前瞻性定义，代码会后续对齐。

### 19.1 设计目标

建模“actor 部署一个持续 N 回合的区域效果”。场地内目标可享受 modifier、触发额外效果、改变伤害结算。

典型用例：
- Phainon 终结技部署 "Ruinous Irontomb"
- Cyrene 部署 "Bloom, Elysium of Beyond"
- 爻光 战技 部署 结界
- Silver Wolf LV.999 部署 "God Mode Zone"

### 19.1.1 本章定位：整体糖化（决策卡 #20）

**VM 不认识 zone**——结界在绑定/编译期展开为既有原语：**界外伪 actor + membership marker + hook**（与召唤物同族，复用 `summon` 原语）：

| zone 概念 | desugar（展开目标） |
|-----------|---------------------|
| 结界本体 | **界外伪 actor**（`av: false`、敌我皆不可选中、固定速度）——携带全部 zone hooks |
| 成员资格 | **membership marker modifier**（成员物化双时点：deploy 时对 area_shape 批量挂标 + `actor_enter` 给新入场者补挂——波次新敌自动入结界） |
| `in_zone()` / `in_zone_filter` | `has_modifier($it, marker)` 及 marker 施加 condition——成员资格口径 = marker 存续**唯一** |
| `zone_owner()` | `$modifier.source` |
| `scoped_modifiers` | 目标 modifier 挂 `active_when: has_modifier(marker)`（`04_modifier.md` §4.14 现成） |
| `on_turn_start` / `on_damage_deal` | 伪 actor 上的 trigger/hook（总线既有） |
| `on_enter`（进入沿） | marker `on_apply` 内联（物化即沿，无第二口径） |
| `duration_decrement_trigger` 三时机 | `04_modifier.md` §4.14 时长锚点映射（挂伪 actor） |
| `deploy_zone` / `dismiss_zone` | spawn 伪 actor + 批量挂标 / 批量 remove marker + dismiss 伪 actor |
| 多 zone 嵌套 | 多 marker 共存，优先序 = hook 注册序（`23_event_hook_system.md` §23.11） |

**owner 死亡行为（默认值钉死）**：owner 离场**不连带**——marker 按自身独立时长持续；需要连带解散的结界由模板显式 `actor_exit` hook 表达（§19.6 原 TBD 就此裁决）。

### 19.2 Zone 字段

```python
class Zone(BaseModel):
    zone_id: str
    owner_actor_id: str
    area_shape: Literal["single_target", "all_enemies", "all_allies", "self", "battlefield"]
    duration: int
    on_turn_start: list[Effect] = []      # 每回合开始时触发的效果
    on_enter: list[Effect] = []           # 目标进入场地时触发的效果
    on_damage_deal: list[Effect] = []     # 场地内造成伤害时触发的效果
    scoped_modifiers: list[modifier_id] = []
    in_zone_filter: str | None = None
    duration_decrement_trigger: Literal["on_turn_start", "on_turn_end", "on_cycle_end"] = "on_turn_start"
```

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `zone_id` | string | 必填 | 场地唯一 ID |
| `owner_actor_id` | `actor_id` | 必填 | 部署者 |
| `area_shape` | enum | 必填 | 作用范围：`single_target` / `all_enemies` / `all_allies` / `self` / `battlefield` |
| `duration` | int | 必填 | 持续回合数；`0` = 永久 |
| `on_turn_start` | `List[Effect]` | `[]` | 每回合开始时触发的效果（内联 effect 对象） |
| `on_enter` | `List[Effect]` | `[]` | 目标进入场地时触发的效果（内联 effect 对象） |
| `on_damage_deal` | `List[Effect]` | `[]` | 场地内造成伤害时触发的效果（内联 effect 对象） |
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
  - effect_type: "deal_damage"
    target: "all_enemies"
    amount: "$self.atk * 0.5"
    damage_type: "physical"
on_damage_deal:
  - effect_type: "apply_modifier"
    target: "self"                    # 示例：给场地拥有者加 buff；实际也可指向 $event.source
    modifier:
      modifier_id: "MOD_RUINOUS_IRONTOMB_BUFF"
      modifier_type: "buff"
      stat: "all_dmg_bonus"
      flat_bonus: 0.2
      duration: 2
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

- Zone 拥有者死亡时的行为：立即消失 / 持续到时长结束 / 转移给队友（TBD）。
- 多 zone 嵌套是否允许（TBD）。
- `in_zone_filter` 的完整语法与默认规则。

---
