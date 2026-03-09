## Why

`Wisp Hand` 的 MVP 后续会连续落下 observe、input、batch、vision 四段能力链。若先不把 daemon/MCP 入口、session/scope 状态、配置、错误和审计这些公共契约定死，后面的每个 change 都会重复定义边界并互相打架。

这个 change 先把所有后续能力都要依赖的 runtime foundation 固化下来，让后面的提案和实现只关注各自功能，不再争论公共运行时长什么样。

## What Changes

- 建立本地 daemon 与 MCP server 的最小运行骨架，先暴露 `hand.capabilities`、`hand.session.open`、`hand.session.close` 三类基础工具。
- 定义 session 生命周期、scope envelope、`armed` / `dry_run` / TTL 等基础状态，以及关闭、过期、找不到 session 时的统一语义。
- 定义运行时配置格式、结构化错误码、文本日志与 JSONL 审计日志的基础契约。
- 明确本 change 只交付公共运行时，不实现 Hyprland 拓扑读取、截图、输入、副作用批处理或视觉能力。
- 依赖链位置：这是 MVP 的第一个 change，无前置依赖；完成后直接承接 `add-hyprland-observe-capture`，并为后续所有 change 提供公共会话与治理边界。

## Capabilities

### New Capabilities

- `session-runtime`: 定义会话生命周期、scope 绑定、arming/dry-run 状态与基础 MCP 会话工具。
- `runtime-config-and-audit`: 定义配置加载、能力自检、结构化错误与审计日志契约。

### Modified Capabilities

无。

## Impact

- 影响后续所有 MCP tool 的公共输入输出形状。
- 影响运行时配置文件、日志目录、审计目录和 session 存储方式。
- 为 `add-hyprland-observe-capture`、`add-scoped-input-safety`、`add-batch-wait-diff`、`add-ollama-vision-assist` 提供共享基础。
