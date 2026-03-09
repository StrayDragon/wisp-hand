## Why

在 foundation 固定了 session、scope、config 和审计契约之后，下一步必须先把只读观察链路打通。没有稳定的 topology、cursor 与 screenshot，后面的输入、安全、batch 和 vision 都没有可靠上下文。

这个 change 专门负责验证 Hyprland-first 读路径，把“能看到什么、坐标怎么对齐、截图如何被复用”一次讲清，并且保持全程无副作用。

## What Changes

- 新增 Hyprland 只读适配层，读取 monitors、workspaces、active workspace、active window、windows 与 cursor position。
- 新增截图引擎与 capture artifact store，支持 `desktop`、`monitor`、`window`、`region`、`scope` 五类目标截图。
- 暴露 `hand.desktop.get_topology`、`hand.cursor.get_position`、`hand.capture.screen` 三类只读工具。
- 定义拓扑坐标、scope 坐标与 capture 元数据之间的映射关系，让后续 input、batch、vision 都复用同一套观察结果。
- 明确本 change 不实现任何 pointer/keyboard 副作用，不实现 wait/diff，也不接入视觉模型。
- 依赖链位置：前置为 `bootstrap-daemon-session-foundation`；完成后直接承接 `add-scoped-input-safety`，并为 `add-batch-wait-diff` 与 `add-ollama-vision-assist` 提供只读输入源。

## Capabilities

### New Capabilities

- `hyprland-topology-observe`: 定义 Hyprland 拓扑、自检后的环境读取和 cursor 查询能力。
- `screen-capture-artifacts`: 定义多目标截图、capture 元数据与 artifact store 契约。

### Modified Capabilities

无。

## Impact

- 引入 `hyprctl`、`grim` 等 Hyprland-first 读能力依赖。
- 影响后续输入与视觉链路共享的坐标映射和 capture 元数据。
- 影响运行时 capture 存储目录、TTL 清理和 inline 返回策略。
