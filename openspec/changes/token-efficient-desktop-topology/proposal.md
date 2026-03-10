## Why

`wisp_hand.desktop.get_topology` 当前默认返回近似“原样”的 Hyprland 全量快照（尤其是 `hyprctl -j clients` 的窗口列表与 monitors 的大字段），在 agent 循环中会被高频调用，导致不必要的 token 消耗、序列化/传输开销与端到端延迟；而大多数调用其实只需要“当前显示器/活动窗口几何与坐标映射上下文”。

因此需要把拓扑观察能力从“默认全量”升级为“默认精简、按需展开”，让外部 agent/client 以最小代价获得稳定、可复用的几何上下文，并在需要排障时仍可请求全量或 raw 细节。

## What Changes

- **BREAKING**：`wisp_hand.desktop.get_topology` 增加 `detail` 参数并调整默认行为：
  - 默认 `detail=summary`：返回稳定的“拓扑摘要”（精简 monitors/workspaces/active_window 等字段），不再默认返回 `windows` 全量列表，不包含 monitors 的大体积字段（如 `availableModes`）。
  - `detail=full`：返回包含 `windows` 列表的“可用全量”（窗口字段为稳定的精简集合，面向自动化与几何计算；仍避免明显无用的大字段）。
  - `detail=raw`：用于排障/诊断，额外返回 Hyprland 原始 payload（可显式要求，默认不返回）。
- `wisp_hand.desktop.get_topology(detail=summary)` 路径下服务端 MUST 避免执行不必要的重查询（例如默认不运行 `hyprctl -j clients`），以降低延迟并减少 CPU/IO 压力。
- 在 summary/full 两种模式下，返回 MUST 保留后续 scoped capture/input/vision 需要的坐标映射上下文（例如 `coordinate_backend`、`desktop_layout_bounds` 与每个 monitor 的 `layout_bounds/physical_size/scale/pixel_ratio`），确保 mixed-scale 多显示器下可复用。
- 明确非目标：
  - 不引入跨桌面环境/跨 compositor 兼容层（仍 Hyprland-first）。
  - 不在本 change 内新增“UI 语义识别/控件树”等高层抽象（保持 deterministic-first）。
  - 不为旧行为提供兼容垫片；旧的默认全量行为通过 `detail=full/raw` 显式获取。
- 依赖链位置：属于 `M6 hardening` 的“token/latency 治理”补强，作为后续更深的 MCP 集成（长耗时任务、多轮观察）和外部 agent 稳定接入的基础。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `hyprland-topology-observe`: 将 `wisp_hand.desktop.get_topology` 从“默认全量快照”升级为“默认摘要 + 按需展开（full/raw）”，并明确不同 detail 的稳定输出边界与错误语义。

## Impact

- 影响 MCP tool：`wisp_hand.desktop.get_topology` 的入参与默认返回形态（属于破坏性变更），并要求 server/runtime/hyprland adapter 做按需查询与响应裁剪。
- 影响 tests 与 examples：需要新增针对 `detail=summary/full/raw` 的回归用例，并更新任何依赖旧拓扑结构的脚本/文档。
- 影响外部接入：外部 agent/client 将获得更小、更稳定的默认观察输出，减少 token 成本并降低“拓扑拉全量导致的上下文污染”风险。

