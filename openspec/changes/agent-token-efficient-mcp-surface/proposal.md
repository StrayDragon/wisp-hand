## Why

Wisp Hand 将作为主 agent 的高频 MCP 工具面使用，但当前返回形态仍存在明显 token 浪费与上下文污染风险（尤其是 tool result `content.text` 里重复塞入完整 JSON 结果、以及截图/窗口/诊断类字段默认返回过多）。在 Godot 场景中，agent 的主循环应以“最小观察 + 必要输入 + 最小验证”为中心，默认返回必须做到极致精简。

因此需要一次面向 agent 的 MCP surface 重构：默认只返回必要信息，重内容通过 MCP Resources 按需读取，并提供更小的 observe primitives，减少全量拓扑与大列表的使用。

## What Changes

- **BREAKING**：统一 tool 返回策略：`structuredContent` 作为权威完整结构化结果；默认 `content` 仅返回极短文本（例如 `ok` 或 `code: message`），不再把完整结果以 pretty JSON 复制到 `content.text`。
- **BREAKING**：截图与 artifact 输出默认走 MCP Resources：`wisp_hand.capture.screen` 默认不再返回本地 `path`/内联 base64，改为返回 `capture_id + 最小元信息 + 可读取的 resource URI`（png + metadata）；仅在显式请求时返回更详细/更大内容。
- 新增更小的 observe primitives（以 Godot 场景为导向），减少 `desktop.get_topology` 的高频依赖：
  - `wisp_hand.desktop.get_active_window`
  - `wisp_hand.desktop.get_monitors`
  - `wisp_hand.desktop.list_windows`（支持 limit，默认精简）
- `wisp_hand.batch.run` 新增 `return_mode=summary|full`（默认 summary），批处理默认只返回每步最小必要输出，避免级联大对象。
- `wisp_hand.vision.locate` 新增 `limit` 与坐标输出选择（默认只返回 scope 坐标），在需要 VLM/排障时才返回更多候选与 image 坐标。
- 明确非目标：
  - 不实现内置 agent loop。
  - 不引入跨桌面环境/跨 compositor 兼容层（仍 Hyprland-first）。
  - 不在默认路径返回 raw payload、窗口全量列表、本地路径或内联图像等大字段；均需显式请求。
- 依赖链位置：属于 roadmap 的 `M6 hardening/beta-ready`（在已具备 observe/capture/input/batch/vision/task-augmented 的基础上，进一步将 MCP surface 打磨为高频 agent 友好、token 极致节省的形态）。

## Capabilities

### New Capabilities
- `mcp-token-efficient-surface`: 定义 token-efficient 的 tool result 约定（content 极短、structuredContent 为权威）、artifact 通过 MCP Resources 暴露的契约，以及面向 Godot 场景的最小 observe 工具集。

### Modified Capabilities
- `screen-capture-artifacts`: capture 默认返回从 `path/inline` 为主升级为 `resources` 为主，并明确 detail/full 才返回大字段。
- `hyprland-topology-observe`: 新增更小的 observe primitives（active window/monitors/list windows），并保持 mixed-scale 坐标映射上下文可复用。
- `action-batch-runner`: 增加 `return_mode` 并定义 summary 默认返回边界。
- `ollama-vision-assist`: `vision.locate` 增加 `limit/space` 并定义默认最省输出。

## Impact

- 影响所有 MCP tools 的 `CallToolResult.content` 行为（breaking）：外部 host/agent 必须以 `structuredContent` 为主进行结构化消费。
- 影响 `wisp_hand.capture.screen` 的默认返回字段与下游消费方式：从“读取本地 path 或 base64”迁移为“通过 MCP Resources 按需 read”。
- 增加新的 `wisp_hand.desktop.*` 只读工具，减少 `desktop.get_topology` 的调用频率与 token 压力。
- 影响 tests、examples 与文档：需要全面升级为新默认行为（不做旧写法兼容）。

