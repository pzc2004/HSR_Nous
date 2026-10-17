# HSR_Nous 外部集成指南

本文档列出 HSR_Nous 与外部服务/库的所有集成方式，包括：**Mihoyo 账号 API**、**YOLO 屏幕识别**、**自动战斗**。每一节都列出风险、配置步骤、测试方法。

## 通用守则

- **所有 Python 包安装必须用 `uv`**（`uv pip install ...`）。**禁止** `pip install` 或 `conda`。
- **所有密钥不应进 git**——`.env` 已被 `.gitignore` 排除，仅提交 `.env.example`。
- **模块边界严格遵守 AGENTS.md**——新模块（如 `account/`、`screen/`、`pilot/`）遵循 `pipeline/` 模式：零内部 import。

---

## 1. Mihoyo 账号 API（HoYoLAB / 米游社）

> 传输层：自 2026-10-15 起由 [genshin.py](https://github.com/seriaati/genshin.py)（ashleney 创立、seriaati 维护，月更）承担——DS 签名/端点轮换/数据模型全部由其负责，本项目只保留凭证管理与领域模型（`account/` 纯数据）+ 防腐翻译（`adapters/account_adapter.py`）。**记录类接口的 HTTP 传输自 2026-10-17 起经 curl_cffi（Chrome 指纹档）**——风控按 TLS/HTTP2 指纹甄别脚本（`account/transport.py` 头注实证链），端点/DS/模型仍复用 genshin.py 单一来源；缺 curl-cffi 的旧环境自动回退 genshin 原生 aiohttp 路径。

### 1.1 风险声明

**HoYoLAB API 是非官方协议**，HoYoverse 随时可能轮换端点或下架。

| 风险项 | 说明 |
|---|---|
| 账号封禁 | 自动化调用违反 ToS，理论上可能封号 |
| 端点轮换 | 公开 API 端点可能随时失效，本项目无法保证长期可用 |
| 字段漂移 | JSON 结构可能变化，代码需容忍字段缺失 |
| 风控（Geetest 10035） | 记录类接口（角色/开拓力/忘却之庭）返回极验验证码错误 → 模块静默 None（见 §1.8） |

**推荐做法**：
- 仅使用本项目用作"配装/配队建议"参考，不要用于自动化游戏行为
- 用 [keyring](https://pypi.org/project/keyring/) 保管 ltuid/ltoken，**不要** 硬编码到 .env
- 项目仅读取公开可查数据，**绝不写入**米游社

### 1.2 获取 ltuid / ltoken

1. 浏览器登录 [HoYoLAB](https://www.hoyolab.com/) 或 [米游社](https://www.miyoushe.com/)
2. F12 → Network → 任意请求 → 查看 Cookie
3. 找到 `ltuid`（数字）和 `ltoken`（长字符串）

### 1.3 配置方式（推荐 keyring）

```python
import keyring

keyring.set_password("hsr_nous", "HSR_NOUS_HOYO_LTUID", "你的ltuid")
keyring.set_password("hsr_nous", "HSR_NOUS_HOYO_LTOKEN", "你的ltoken")
keyring.set_password("hsr_nous", "HSR_NOUS_HOYO_SERVER", "cn_gf01")  # 或 os_asia / os_euro / os_america
```

### 1.4 配置方式（fallback .env）

复制 `.env.example` 为 `.env` 并填入：

```env
HSR_NOUS_HOYO_LTUID=12345678
HSR_NOUS_HOYO_LTOKEN=abc123...
HSR_NOUS_HOYO_SERVER=cn_gf01
```

`account` 模块会**自动加载仓库根 `.env`**（`hsr_nous.common.env` 手写解析，标准库 only；
不覆盖已存在的环境变量；keyring 优先），调用方不需要先 `load_dotenv`。
设备身份缺省**自动签发并永久复用**（首次拉取经米哈游 getFp 端点签发，存
`~/.config/hsr_nous/device_identity.json`，login 与拉取共用同一身份）；
`HSR_NOUS_HOYO_DEVICE_ID` / `HSR_NOUS_HOYO_DEVICE_FP` 仅作风控排查覆写（§1.8）。

### 1.5 验证

```bash
uv run python -c "
from hsr_nous.account import fetch_account_snapshot
snap = fetch_account_snapshot()
print(f'UID: {snap.uid}')
print(f'开拓力: {snap.trailblaze_power}')
print(f'角色数: {len(snap.characters)}')
"
```

预期输出（未配置时为 None）：
```
UID: 12345678
开拓力: 240
角色数: 12
```

### 1.6 测试

```bash
uv run pytest tests/test_account_snapshot.py -v
```

覆盖（离线，假 client 注入 `_make_client` 接缝，不接真 API）：
- 未配置 → 返回 None（不抛异常）
- 成功响应 → 解析出全粒度结构（遗器主/副词条、光锥叠影、星魂明细、技能等级、面板、忆灵标记）
- genshin 侧异常 → 静默返回 None
- `account_adapter.account_character_to_member` → build.yaml 成员字典；模板缺失 → None（不脑补）；产出形状对拍编译器词表（`_MEMBER_KEYS`/`_AFFIX_FIELD` 漂移闸）
- 设备身份（`tests/test_account_device.py`）：getFp 签发幂等不重复、env 覆写优先
  不发网络、拒签降级不抛、login/client 共用身份接线、风控失败 warning 留痕

### 1.7 模块结构

```
src/hsr_nous/account/
├── __init__.py     # 公开 API（fetch_account_snapshot）
├── client.py       # genshin.py 传输层封装、凭证读取（keyring→env）、uid 解析
├── device.py       # 设备身份（device_id 生成 + getFp 签发 + 持久化复用——风控信任链，§1.8）
└── models.py       # AccountCharacter / AccountRelic / AccountLightCone / MoCRecord / AccountSnapshot
                    # （纯领域模型——API 原始词条名原样保留，不认识 sim_schema）

src/hsr_nous/adapters/account_adapter.py
                     # AccountCharacter → build.yaml 成员字典（防腐层：唯一认识
                     # 账号模型 × 编译器 _MEMBER_KEYS 两侧的翻译官）
```

### 1.8 风控与 Geetest（retcode 10035）

症状：`get_starrail_characters` / `get_starrail_notes` / `get_starrail_challenge` 抛
`genshin.errors.GeetestError: [10035] Geetest triggered during the battle chronicle API request`；
而 `get_game_accounts`（账号列表）正常——说明凭证有效，只是米哈游对**记录类接口**触发了极验风控。

诱因（按常见程度）：新设备/新 IP（校园网、机房 IP 更敏感）、请求频率、设备指纹缺失或变化。

现役默认防线（2026-10-17 落地，两道）：
1. **自动设备身份**——`account/device.py` 在首次拉取时生成稳定 device_id + 经米哈游
   getFp 端点签发 device_fp，一次签发、永久复用（风控对稳定指纹随使用收敛；频繁换
   指纹是诱因之一——旧版 login 每次扫码现造随机身份，现已收编为 login/client 共用
   同一身份）。身份存 `~/.config/hsr_nous/device_identity.json`。
2. **Chrome 指纹传输**——记录类接口走 curl_cffi（`account/transport.py`），TLS/HTTP2
   指纹与真 Chrome 一致。变量排除实证：设备指纹/cookie 完备度/UA 伪装全部无效后，
   指纹维度由本件接管；它解决不了的只剩 IP 维度（第 1 条）。

处理顺序（成本从低到高）：

0. **确认自动设备身份已生成**——`cat ~/.config/hsr_nous/device_identity.json`；缺文件就跑
   一次 §1.5 验证命令（自动触发签发）。若日志反复出现「getFp 拒签（code=500）：内部错误」，
   是**服务端对签发请求的门控**（同 payload 形状时好时坏——2026-10-17 同机 13 次请求仅
   1 次放行，不可复现；payload 本身照抄 genshin.py 现行形状）——按第 1 条换网络/等时段
   后再试。身份在、仍触发 10035 → 才往下走。
1. **换网络/等一段时间重试**——风控按 IP/时段收敛，切手机热点、隔几小时再试最常见有效。
2. **覆写可信旧设备标识**——`.env` 填 `HSR_NOUS_HOYO_DEVICE_ID` / `HSR_NOUS_HOYO_DEVICE_FP`
   （浏览器 cookie 里的 `_MHYUUID` / `DEVICEFP`，或旧机器上正常时的值）——覆写自动身份，
   client 透传给 genshin.py。
3. **浏览器先正常访问记录页**——用同一浏览器（已登录）打开米游社战绩页，若弹极验手动通过再试程序；
   有时会刷新凭证/降低风控等级。
4. **扫码重新登录**——`python -m hsr_nous.account.login` 重新取凭证（新设备仍可能被风控）。
5. 不建议自动化解极验（成本高、维护差，且属于绕过风控行为）。

genshin.py 现状（1.7.31）：只有 `GeetestError` 抛出（`genshin/constants.py` 的 `GEETEST_RETCODES`），
**没有**内置求解器/回调。失败时 `fetch_account_snapshot()` 按模块纪律返回 None，不重试、不抛异常——
实时拉取不可用时，配装流程回退手动 `build.yaml`；或走 §1.9 展柜快照（公开面，无风控）。

### 1.9 角色展柜快照（mihomo.me 公共聚合——风控降级替代源）

记录接口撞风控时的公开面：`fetch_showcase_snapshot(uid)` 按游戏 UID 拉取**角色展柜**
数据（api.mihomo.me 聚合，与微信小程序同源——玩家游戏内主动公开，无需登录、不经
米游社风控）。实现与词表映射在 `account/showcase.py`，产出与记录接口**同一
AccountSnapshot 形状**，消费方无感。

```python
from hsr_nous.account import fetch_showcase_snapshot
snap = fetch_showcase_snapshot("163476104")   # 游戏 UID（非米游社账号 id）
```

与记录接口快照的差异（消费方须知情）：

| 项 | 记录接口 | 展柜 |
|---|---|---|
| 角色覆盖 | 全账号 | 仅展柜（游戏上限 8 个，可关闭公开 → None） |
| 遗器/光锥/行迹 | 全粒度 | 同粒度（主/副词条、叠影、技能等级都在） |
| 星魂 | 已解锁名列表 | 仅数量（`unlocked_eidolons` 恒空） |
| 开拓力/忘却之庭 | 有 | 无（快照字段 0/空） |
| 忆灵标记 | 有 | 恒 False |
| 依赖 | 凭证+设备身份+传输指纹 | 仅 UID（第三方服务可用性） |

---

## 2. YOLO 屏幕识别（详见 `docs/screen_setup.md`）

> 框架已落地（`src/hsr_nous/screen/`：ONNX 检测器 + 状态解析；RT-DETR-r18 权重待训练）。

- 默认 backbone：**RT-DETR-r18**（Apache-2.0）
- 显式**不依赖** ultralytics（AGPL-3.0 默认）
- 仅做检测（人物/敌人/轮次），不主动点击

---

## 3. 自动战斗执行层（详见 `docs/autopilot_safety.md`）

> 已落地（`src/hsr_nous/pilot/`）。**默认关闭**。

- 环境变量 `HSR_NOUS_ALLOW_AUTOPILOT=1` 才启用
- 启动时打印 ToS 摘录 + 必须键入 `I ACCEPT`
- 强警告：违反 HoYoverse ToS 可能封号

---

## 4. 调试技巧

### 4.1 查看 LLM 是否被调用

```python
import os
os.environ["OPENAI_API_KEY"] = "sk-..."
os.environ["OPENAI_API_BASE"] = "https://your-proxy/v1"  # 可选

from hsr_nous.api.orchestrator import Orchestrator
Orchestrator().run("为黄泉推荐最优遗器")
```

### 4.2 离线调试（不需要 API key）

```bash
uv run pytest tests/test_agents_mocked.py -v
```

测试通过 mock LLM 验证 5-Agent 编排逻辑。

### 4.3 检查仿真器是否调用

> **已退役（2026-10-12）**：`simulate_battle` / `compare_configs` 旧 demo 通道
> （`adapters/encounter_adapter` 启发式编造数值）已删除——两工具壳保留
> （agents 层 SIM_TOOLS 注册不断链）但恒返回退役说明，agents 按 prompt 约定
> 降级纯数据查询。正规仿真通道：`data/library/**` DSL 模板 → `sim.compile`
> → `CombatEngine`（web 调试台 / 打标 DAG 均为生产面）。