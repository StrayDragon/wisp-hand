## Context

当前 `wisp_hand.desktop.get_topology` 直接把 Hyprland 的 monitors/workspaces/activewindow/clients 等 payload 作为一次性大对象返回，并在 runtime 侧额外注入 `coordinate_backend`、`desktop_layout_bounds` 与 monitor 的 layout/physical/pixel_ratio 等字段。该输出在 mixed-scale 多显示器下对后续 scope/capture/input 很有价值，但“默认全量”导致：

- 外部 agent/client 高并发轮询时 token 与带宽浪费严重
- `hyprctl -j clients` 等查询在不需要窗口列表时仍被执行，拉高延迟
- 输出字段过多且多为 Hyprland 内部诊断字段，默认会污染上游 LLM 上下文

本设计把拓扑输出拆成“默认摘要 + 按需展开”，同时保留坐标映射上下文以确保 mixed-scale 下可复用。

## Goals / Non-Goals

**Goals:**

- `wisp_hand.desktop.get_topology` 默认返回 token-efficient 的拓扑摘要（`detail=summary`），覆盖 monitor/workspace/active window 的几何与坐标映射关键字段。
- 支持显式请求更高详细度（`detail=full/raw`），用于需要窗口列表或排障的场景。
- `detail=summary` 路径下避免不必要的 Hyprland 重查询（尤其避免默认 `clients`）。
- 输出结构以“可复用几何/坐标上下文”为中心，减少与 Hyprland 版本/实现细节强耦合字段。

**Non-Goals:**

- 不实现跨 compositor 的 topology 兼容层。
- 不在本 change 内引入窗口语义识别、控件树、OCR 等高层能力。
- 不为旧的“默认全量”行为保留兼容垫片；如需全量由 `detail=full/raw` 显式获取。
- 不在本 change 内引入新的分页/流式拉取协议（如需后续独立 change 处理）。

## Decisions

### Decision: 用 `detail` 枚举控制返回详细度，而不是多个布尔开关

选择 `detail in {summary, full, raw}`：

- `summary` 覆盖 agent 常用的“几何与坐标上下文”最小集合。
- `full` 覆盖需要窗口列表的自动化场景，但仍保持字段精简与稳定。
- `raw` 面向排障，把 Hyprland 原始 payload 放到显式字段中，避免默认污染。

替代方案：

- 多个 `include_*` 布尔参数：灵活但组合爆炸，且更难形成稳定默认与测试矩阵。
- 新增多个工具（例如 `get_topology_summary`/`get_topology_full`）：工具面膨胀，发现成本更高。

### Decision: `summary/full` 返回采用“稳定精简字段集合”，`raw` 才允许透传 Hyprland 原始 payload

`summary/full` 的目标是稳定、紧凑、可用于几何计算，因此只保留：

- monitors: `name/id/focused` + 坐标映射关键字段（`layout_bounds/physical_size/scale/pixel_ratio`）+ 必要几何定位（`x/y/width/height` 或等价）
- workspaces/active_workspace: `id/name/monitor/windows/hasfullscreen` 等可验证字段
- active_window: 可用于 scope/window 的 selector 与几何（`address/class/title/workspace/monitor/at/size` 或归一化 `x/y/width/height`）
- `coordinate_backend` 与 `desktop_layout_bounds`

`raw` 明确作为诊断接口：允许携带 `hyprctl -j *` 的原始输出，以便定位 Hyprland 侧变化或后端差异。

### Decision: Hyprland 查询做“按需子命令规划”

实现上将 `HyprlandAdapter.get_topology()` 拆成可组合子查询（monitors/workspaces/activeworkspace/activewindow/clients），并在 runtime 根据 `detail` 决定是否查询 `clients`：

- `detail=summary`：不查询 `clients`
- `detail=full/raw`：查询 `clients`（raw 额外保留原始 monitors 字段）

替代方案：

- 仍然全量查询但只裁剪返回：能省 token，但省不了延迟；不满足“默认不做无用工作”的目标。

## Risks / Trade-offs

- [Breaking change] 外部调用方依赖旧的默认全量输出会被破坏 → 通过 `detail=full/raw` 提供显式迁移路径，并更新 repo 内 examples/tests。
- [字段选择争议] “哪些字段算必要”在不同 agent 场景下可能不同 → 以“几何/selector/坐标映射”为准绳；对诊断需求引导使用 `detail=raw`，避免把诊断字段带入默认输出。
- [实现风险] runtime 内部工具（capture/input/cursor）也依赖 topology → 内部调用可以继续请求所需子集/全量，不要求复用对外的 summary；增加回归测试覆盖 window scope 与 mixed-scale monitor。
- [Hyprland 变更] Hyprland JSON 字段随版本变化 → `summary/full` 自定义稳定字段集合降低耦合；`raw` 用于排障与兼容追踪。

## Migration Plan

1. 更新 MCP tool schema：`wisp_hand.desktop.get_topology(detail=...)`，默认 `summary`。
2. 更新内部与 examples：需要窗口列表时显式传 `detail=full` 或使用内部 full 查询路径。
3. 增加测试矩阵：`summary` 不包含 `windows`、`full` 包含、`raw` 额外包含 raw payload；并验证 `summary` 路径不会执行 `clients` 查询（通过 mock/spy runner）。
4. 在 README/文档中加入“token-efficient 默认值”与排障用法。

## Open Questions

- `full` 模式下 windows 对象的字段集合是否需要支持后续“分页/limit”扩展（本 change 暂不实现，但需要预留可扩展空间）。

