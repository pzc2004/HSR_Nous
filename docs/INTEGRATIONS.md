# HSR_Nous 外部集成指南

本文档列出 HSR_Nous 与外部服务/库的所有集成方式，包括：**Mihoyo 账号 API**、**YOLO 屏幕识别**、**自动战斗**。每一节都列出风险、配置步骤、测试方法。

## 通用守则

- **所有 Python 包安装必须用 `uv`**（`uv pip install ...`）。**禁止** `pip install` 或 `conda`。
- **所有密钥不应进 git**——`.env` 已被 `.gitignore` 排除，仅提交 `.env.example`。
- **模块边界严格遵守 AGENTS.md**——新模块（如 `account/`、`screen/`、`pilot/`）遵循 `pipeline/` 模式：零内部 import。

---

## 1. Mihoyo 账号 API（HoYoLAB / 米游社）

### 1.1 风险声明

**HoYoLAB API 是非官方协议**，HoYoverse 随时可能轮换端点或下架。

| 风险项 | 说明 |
|---|---|
| 账号封禁 | 自动化调用违反 ToS，理论上可能封号 |
| 端点轮换 | 公开 API 端点可能随时失效，本项目无法保证长期可用 |
| 字段漂移 | JSON 结构可能变化，代码需容忍字段缺失 |

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

### 1.5 验证

```bash
uv run python -c "
from hsr_nous.account import get_account_snapshot
snap = get_account_snapshot()
print(f'UID: {snap.uid}')
print(f'开拓力: {snap.trailblaze_power}')
print(f'角色数: {len(snap.owned_characters)}')
"
```

预期输出（未配置时为空）：
```
UID: 12345678
开拓力: 240
角色数: 12
```

### 1.6 测试

```bash
uv run pytest tests/test_account.py -v
```

覆盖：
- 未配置 → 返回空 / 友好提示
- httpx 成功响应 → 正确解析 OwnedCharacter
- httpx 5xx → 静默返回空（不抛异常）
- account_adapter → 把 OwnedCharacter 转为 Actor

### 1.7 模块结构

```
src/hsr_nous/account/
├── __init__.py     # 公开 API（AccountClient + 函数）
├── client.py       # HTTP 客户端、DS 签名、token 读取
└── models.py       # OwnedCharacter / MoCRecord / AccountSnapshot

src/hsr_nous/adapters/account_adapter.py
                     # OwnedCharacter → Actor（与 character_adapter 平行）

src/hsr_nous/agents/tools/data_tools.py
  + query_my_account  # LangChain 工具，供 Builder/Orchestrator 调用
```

---

## 2. YOLO 屏幕识别（详见 `docs/screen_setup.md`）

> 计划于阶段 4 实施。

- 默认 backbone：**RT-DETR-r18**（Apache-2.0）
- 显式**不依赖** ultralytics（AGPL-3.0 默认）
- 仅做检测（人物/敌人/轮次），不主动点击

---

## 3. 自动战斗执行层（详见 `docs/autopilot_safety.md`）

> 计划于阶段 5 实施。**默认关闭**。

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

```python
from hsr_nous.agents.tools.sim_tools import simulate_battle
print(simulate_battle.invoke({
    "team_config": "Acheron+Sparkle+Ruan Mei+Fu Xuan",
    "relic_set": "雷4",
    "enemy_name": "忘却之庭BOSS",
}))
```

应输出基于 `sim.engine.CombatEngine` 的真实数据（非占位）。