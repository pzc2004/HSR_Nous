# 权限管理与反伪造规范（当前实现 vs 目标态）

> **文档定位**：本章是权限契约，不是权限模块的实现公告。当前仓库没有独立的 permissions 包，也没有统一的 OS/进程级 Agent 沙箱。下文把“当前已实现的证据与完整性约束”和“目标态必须实现的权限控制”分开描述，禁止把目标态当成已落地能力。

## 1. 威胁模型

研究后端必须假设 Agent 会主动或无意地优化“看起来可信”的表面结果，而不只是出现普通程序错误。

| 威胁 | 具体形式 | 当前控制 | 目标态补充 |
|---|---|---|---|
| 伪造/篡改结果 | 手写均值、CI、claim status、report、artifact hash | `ClaimValidator` 从原始 artifact 重算并拒绝不一致；report 发布前再次验证 | 外部工具入口也必须执行同一路径，不能只靠调用方自觉 |
| 选择性报道 | 删失败 run、只报有利 seed/网页、隐藏负向结果和 caveats | 固定 cohort、全量 run 和失败清单、ComparisonSet 复核 | 保留完整 query/result set、执行历史和矛盾来源 |
| 绕过 `submit_claim` | 直接 publish run/claim/report、让分析脚本数字进入 Claim | 内部 Python 的正常路径是 runner → validator → composer | 对不可信 Agent 只开放一个外部提交通道，禁止旁路发布 |
| 越权读写 | 修改 canonical、artifact、其他 trial、其他调查状态或权限策略 | canonical 只读、路径防逃逸、不可覆盖和 revision/history 前缀检查 | 按角色和资源配置读写 ACL；权限策略只能由人变更 |
| Bash/Python/Docker 逃逸 | `os.system`、`subprocess`、`ctypes`、任意脚本、Docker socket | 研究执行没有提供这些作为合法研究通道 | 默认完全禁用；未来如确需探索脚本，必须使用独立受限运行时 |
| 凭证外泄 | 读取 `.env`、keyring、HMAC key、CI token，并写入 query/log/artifact | 研究 artifact 不应包含凭证；敏感文件访问受工具环境限制 | 秘密统一由可信服务管理，Agent 永远得不到密钥内容 |
| 联网 prompt injection | 网页指示执行命令、换 seed、删除证据、泄露秘密或伪造结论 | 社区资料不作为结论性统计输入 | 默认断网；白名单、SSRF 防护、内容只作先验，注入文本不得执行 |
| 反复重试刷结论 | 换 seed、换 holdout、重复搜索直到出现 accepted | 协议 seed 固定；相同内容幂等，篡改后形成 rejected/stale | 限制查询与重试预算，保留全部尝试，禁止以重搜替代验证 |

## 2. 信任角色

| 角色 | 信任假设与允许职责 | 不能做什么 |
|---|---|---|
| 不可信 Agent | 只能提出 ResearchContract、读取被授权的证据和调用外部 `submit_claim` | 不得直接写 canonical/artifact/claim/report，不得提供结论数字、改变协议或选择样本 |
| 可信 runner | 校验 contract 和 patch，物化 variant，调用 CombatEngine，保留全部 raw run | 不得自行决定统计结论、删除失败样本或改写既有世界线 |
| 可信 validator | 重新读取 spec/result/run/variant，重算比较、CI、claim 和当前指纹 | 不得信任 Agent 提供的 metrics、摘要、结论句或分析脚本输出 |
| ArtifactStore | 提供 canonical bytes、内容哈希、原子发布、只读、路径和读取完整性校验 | 不是自主决策者，也不是同用户恶意进程的强安全边界 |
| WebSearchPolicy / 用户授权者 | 管理联网开关、白名单、查询预算、密钥与权限策略版本 | 不得把网页文本提升为模拟证据或让秘密进入 query |

关键边界：**只读权限 + SHA-256 只是防误改和检测篡改的护栏**。同一用户下的恶意进程仍可 chmod、替换文件、伪造数据或调用其他通道；只有独立重算、受限入口和必要时的来源认证才能补足，不能把文件哈希描述为强安全沙箱。

## 3. 资源权限矩阵

下表是目标权限契约。`read` 表示不可信 Agent 的读取范围，`write` 表示唯一合法写入者；实际实现状态另见末节，不能据此认定所有 ACL 已由代码强制执行。

| 资源 | 不可信 Agent read | 唯一合法写入者 |
|---|---|---|
| 仓库源码与测试 | 只读，用于理解和验证 | 经审查的人；通过正常代码评审与测试流程修改 |
| canonical 模板与数据 | 只读，经统一 loader | 经授权的策展人或既有生成器；research runner 不得写入 |
| Agent 自有项目目录 | 仅项目根内的文件，realpath 校验 | Agent 本人，且只产生 exploratory 产物；不得写 canonical/raw artifact/claim/report |
| research_root 的 trial 元数据 | 仅可读取被授权的 trial 元数据 | 可信 runner / ArtifactStore；默认 `Path.home()/HSR_Nous` 或授权 env 根 |
| raw artifact（spec/variant/run/result） | 通过 `EvidenceLink` 和只读接口 | 仅可信 runner；store 原子发布、不可覆盖、同字节幂等 |
| Claim | 只读已验证记录 | 仅可信 ClaimValidator；逻辑 claim_id 与 record ID 分离，不覆盖历史 |
| Report | 只读已验证 JSON | 仅 ReportComposer，且发布前必须再次 validate |
| `.env` / keyring / tokens / HMAC key | 默认不可读、不可写、不可出现在 query 或 artifact 中 | 仅可信秘密管理服务；按 key_id 和 rotation 授权，Agent 永远得不到 key 内容 |
| Docker socket / container daemon | 默认不可访问 | 仅未来可信隔离服务在明确授权时使用，不向 Agent 暴露 socket |
| 网络与网页内容 | 默认关闭；仅经 WebSearchPolicy 返回白名单结果集 | 仅 WebSearchPolicy / 用户授权者开启和配置，不允许任意抓取或联网写入 |

## 4. 执行通道：Bash、Python 与 Docker

### Bash：默认完全禁用

不可信 Agent 不得通过 `bash`、`os.system`、`subprocess`、shell 重定向或后台进程完成研究。合法执行由可信服务内部的结构化 Python API 完成：

- `compile_encounter` 与 `BuildCompiler.load_template`；
- `TrialRunner` 和固定 `paired-v1`；
- `ClaimValidator` 与 `ReportComposer`；
- `ArtifactStore` 的只读证据接口；
- 经授权的 `ExecutionManager` 生命周期方法。

这些 API 是可信服务的内部组件，不表示它们全部直接向 Agent 开放。Agent 只能通过 ResearchContract、外部 `submit_claim`、只读证据接口和被授权的生命周期动作使用这些能力。

### Python：默认禁用；未来探索脚本必须独立隔离

如果未来确实需要 Agent 生成探索性 Python，不能只靠 AST 审核，因为 `os.system`、`subprocess`、`ctypes`、文件描述符和反射都可能绕过表面限制。目标运行时至少必须满足：

- 无网络、无 Docker socket、无凭证环境；
- canonical 与仓库根只读，只有独立临时目录可写；
- 非 root 用户、独立进程/容器、CPU/内存/进程数/文件数/超时限制；
- 输出只能标记为 exploratory，不能直接成为 claim、CI、报告或 accepted 证据；
- 任何结论性数字仍需重新走合法 ResearchContract 和 CombatEngine。

### Docker：默认禁用

Docker 不能被当作“启动即安全”的快捷答案。当前没有容器隔离实现；目标态若要使用，必须由可信服务持有 daemon、镜像和网络策略，Agent 不接触 Docker socket。

## 5. 结果完整性与来源认证三层

### 第一层：canonical bytes + 全 SHA-256（当前已实现）

用于发现意外改写、同 ID 冲突和非 canonical 文件，配合原子发布、只读和路径检查。哈希只能回答“内容是否与某个哈希一致”，**不能证明内容真实、作者可信或数据来自合法模拟器**。隐藏哈希算法没有安全意义；应使用公开、明确的 SHA-256 和 canonical 格式。

### 第二层：原始证据交叉核验（当前已实现）

- completed run 的 `observed.seed / total_damage / truncated` 与 run seed 和 `final_save.state` 一致；
- 全量 cohort、run 顺序、parent lineage、failed/truncated 清单和 failure reasons 重新核对；
- variant metadata、build/YAML、config/policy/implementation fingerprint 与 spec 一致；
- ClaimValidator 和 ReportComposer 各自重新执行验证，不能只比较哈希后就接受。

### 第三层：需要时的 HMAC 来源证明（目标态，尚未实现）

当 artifact 需要跨进程或跨服务证明“确实由某个可信 runner 产出”时，可由可信服务附加 HMAC。HMAC key、`key_id`、rotation 和验证策略只能由可信服务管理，Agent 不得读取、生成或替换密钥。HMAC 只证明持有相应密钥的签名者认可该内容，仍不等于游戏机制真实或统计结论正确。

## 6. `submit_claim`：唯一外部提交通道

目标态的外部 Agent 只能通过 `submit_claim` 提交 ResearchContract。当前 Python 内部实现对应的是 `TrialRunner → ClaimValidator → ReportComposer`，**尚不存在一个独立、统一的外部 `submit_claim` 工具 API**。

禁止不可信 Agent 直接 `publish_run` / `publish_claim` / `publish_report`、手写 metrics，或把分析脚本产生的数字放进 Claim。可信 runner 和 store 内部的发布 API 不等同于对 Agent 开放权限。

返回语义：

| 状态 | 外部返回 | 不允许的行为 |
|---|---|---|
| `accepted` | 返回经重算的 JSON 报告、效应、CI、推导和证据链接 | 不得扩展为真实游戏正确、全局最优或实测完成 |
| `inconclusive` | 返回 failed/truncated/样本不足/CI 跨 0 等原因，不输出方向性结论 | 不得换 seed 或删失败后改判 accepted |
| `rejected` | 返回结构化错误：失败阶段、字段、证据身份和原因 | 不得把 variant 效果更差误标为 rejected，不得只返回无结构文本 |
| `stale` | 返回当前指纹与前提不一致的派生视图和原因 | 不改写历史 accepted，不伪造当前有效的 accepted |

## 7. 可信内核的数据源白名单

结论性统计只能来自：

1. CombatEngine 的 observed outcome；
2. `save_state()` 的全精度 `final_save`；
3. setup 前挂接的 StructuredLogger 和 setup 后挂接的 RunRecorder；
4. 经统一 loader 和协议校验后物化的 variant。

网页、社区攻略、Agent 手写数字、解释性分析脚本输出、未经核对的 CSV 或二手摘要都不能成为结论性输入。Agent 若要获得新数字，只能重新构造合法 ResearchContract 并运行模拟器；不能用文字“计算”替代一次真实执行。

## 8. 防选择性报道与反复重试

- 全部协议 run 必须保留，包括 failed、truncated、负向结果和 caveats。
- `ComparisonSet`、dev/holdout seed 和顺序由 `paired-v1` 固定，Agent 不得挑选或替换。
- ExecutionRecord.history、InvestigationState.execution_ids 和 revision 只能追加，不得删除不利尝试。
- 首版只有一个 baseline/variant，不存在通过候选筛选来隐藏其他结果的空间；多候选搜索仍未实现。
- 同一确定性输入重跑应幂等；不同内容不得覆盖旧世界线。重试不能用来规避 rejected 或 stale，也不能用重新搜索网页替代重新验证。

## 9. 联网权限（目标态）

研究后端当前不依赖联网结果作为结论输入。若未来启用 WebSearchPolicy，必须同时满足：

- 默认关闭，按域名/路径白名单和查询预算逐项授权；
- 保存完整 query 与 result set，不得只保留支持假设的摘录；
- 保留矛盾来源和检索失败，社区资料只作先验，不进入 CI 或 accepted 证据；
- 防 SSRF：禁止私网、loopback、链接本地、云元数据地址和未经审查的重定向；
- 网页中的命令、角色设定和 prompt injection 只作为不可信文本，绝不执行；
- `.env`、token、HMAC key、私有路径和用户隐私不得进入 query、日志或 artifact。

## 10. TOCTOU 与权限策略版本

当前执行链已有以下时间-of-check/time-of-use 控制：

- runner 执行前重新校验 contract、patch、模板和指纹；
- ClaimValidator 在 claim 前重新加载证据、重算统计并比较当前指纹；
- ReportComposer 发布前再次调用 validator；
- 当前指纹与 claim 前提不一致时返回 stale，而不是让旧 accepted 继续生效。

目标态的权限策略本身也必须版本化：记录 policy_version、创建者、创建时间和变更历史。只有人或被明确授权的可信服务能修改策略，Agent 不得提高自身权限、修改白名单或改写授权历史。

## 11. 对抗验收清单

以下是目标态工具层必须全部拒绝的验收项；“当前已有证据”只表示已有对应实现或测试，不表示完整权限系统已经落地。

| 对抗行为 | 目标结果 | 当前已有证据 / 缺口 |
|---|---|---|
| 修改 run/variant/report 后重算哈希 | 必须失败 | 当前读取会检查内容哈希与逻辑身份；篡改语义还会进入 rejected |
| 删除 failed run 或截断样本 | 必须失败 | 当前 result 重建全量 cohort，缺 run 即失败，不能洗成 accepted |
| 伪造 publish_run/claim/report | 必须失败 | 内部校验能识别部分伪造；统一外部 Agent ACL 尚未实现 |
| `os.system` / `subprocess` / `ctypes` / Docker 逃逸 | 必须失败 | 目标态隔离运行时，当前未实现 |
| `..`、symlink、绝对路径逃逸 | 必须失败 | 当前 `_safe_path` 和 ID/组件检查已覆盖 |
| 读取 secret 并外泄到 query/log/artifact | 必须失败 | 目标态秘密管理与脱敏审计；当前无统一 Agent 权限层 |
| 只挑选有利网页或矛盾来源 | 必须失败 | 目标态完整 query/result set 与矛盾来源保留，当前未实现联网策略 |
| 修改 CI、holdout、seed、status 或报告数字 | 必须失败或 stale | 当前独立重算会拒绝；当前指纹不匹配会 stale |
| 重搜/重试直到出现 accepted | 必须失败或保持原状态 | 当前 seed 固定且内容幂等；查询/重试预算尚未实现 |

## 12. 当前实现清单 vs 尚未实现清单

### 当前已实现

- 递归冻结契约、canonical JSON、全 SHA-256、原子发布和只读文件；
- canonical 只读、统一模板 loader、variant/build.json 内容身份与路径防逃逸；
- observed/final_save、全量 cohort、失败/truncated、lineage 和 variant metadata 交叉核验；
- 固定 paired-v1、不可覆盖 trial artifact、独立 ClaimValidator 与 ReportComposer 重算；
- accepted/inconclusive/rejected/stale 的内部语义、历史 claim 不改写和证据下钻；
- ExecutionRecord/InvestigationState 的 history 前缀、revision、取消/恢复/cache/replay；
- `research_permissions` 包：不可变 `CapabilityPolicy`、`ResearchGateway` 和唯一外部 `submit_claim`（contract/trial_id/claim）；
- `ClaimSubmissionResult` 的 accepted/inconclusive/rejected/stale/failed/cancelled/permission_denied 结构化返回；
- 默认 Bash/Python/Docker 拒绝、项目路径/凭证检查及对应 Python 对抗测试（这些是工具层约束，不是 OS 级隔离）；
- `research_web`：DeepSeek Search/Fetch provider、默认关闭的联网开关、域名白名单、预算与 usage 持久化、完整 query/result set、域外结果保留、SSRF/重定向防护和有限退避；这些结果只作外部先验，不进入可信内核或 accepted 推导。

### 尚未实现

- 完整角色 ACL、权限策略版本与人机授权界面；
- OS/进程级 Agent 沙箱与 Bash/Python/Docker 的强制隔离运行时；
- HMAC key、`key_id`、rotation 和跨服务来源证明；
- 统一的 secret 访问控制、完整对抗验收自动化与真实联网验收（当前测试使用 mock transport）。

这些未完成项不得在文档、报告或 API 说明中被表述为已存在的安全保证。
