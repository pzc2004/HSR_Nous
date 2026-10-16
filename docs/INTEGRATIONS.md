# HSR_Nous 外部集成指南

本文档列出 HSR_Nous 与外部服务/库的集成方式：**Mihoyo 账号 API**。列出风险、配置步骤、测试方法。

## 通用守则

- **所有 Python 包安装必须用 `uv`**（`uv pip install ...`）。**禁止** `pip install` 或 `conda`。
- **所有密钥不应进 git**——`.env` 已被 `.gitignore` 排除，仅提交 `.env.example`。
- **模块边界严格遵守 AGENTS.md**——新模块（如 `account/`）遵循 `pipeline/` 模式：零内部 import。

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

> 直接测试暂缺：原 `tests/test_account.py` 随旧 agents 层移除（2026-10-15），
> 以下为待补覆盖口径——

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
```

---

## 2. 调试技巧

### 2.1 查看 LLM 是否被调用

```bash
bash scripts/annotator.sh ping
```

经 tribios 一次最小 chat，回显端点/模型/key 数（永不回显 key 本体）——换 API 后第一件事。

### 2.2 离线调试（不需要 API key）

```bash
uv run pytest tests/test_ops_annotator_llm.py -v
```

mock 传输层验证 LLM 接线/热更/消息形状，不接真 API。

### 2.3 仿真器调用

正规仿真通道：`data/library/**` DSL 模板 → `sim.compile` → `CombatEngine`
（web 调试台 / 打标 DAG 均为生产面）。旧 encounter_adapter demo 通道已于 2026-10-12 删除。