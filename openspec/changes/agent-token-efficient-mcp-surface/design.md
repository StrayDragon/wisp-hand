## Context

Wisp Hand 已完成 foundation/observe/scoped input/batch-wait-diff/vision/task-augmented 等链路，但作为主 agent 的高频 MCP 工具面使用时，默认返回仍偏“人类可读/诊断友好”，不够 token-efficient：

- 关键浪费：tool result `content.text` 中重复携带完整 JSON（pretty + sort + indent），会被 host 直接喂给 LLM，导致 token 成本成倍增长。
- capture/topology/batch/vision 等能力的默认返回包含对 agent 不必要的信息（例如本地 `path`、raw payload、候选过多、步骤 output 级联等），易污染上下文。
- Godot 场景的理想闭环是：获取 active window selector → 打开 window scope session → capture →（vision locate 可选）→ 输入 → wait → capture/diff。该闭环并不需要频繁拉取全量 topology/clients 列表。

本 change 的定位是在 `M6 hardening/beta-ready` 阶段，把 MCP surface 改造为“默认极致省 token、按需展开”的形态，并把重内容交给 MCP Resources。

## Goals / Non-Goals

**Goals:**

- 默认 tool 返回做到极致 token-efficient：`structuredContent` 为权威完整结构化结果；`content` 默认仅返回极短文本。
- capture artifacts 默认通过 MCP Resources 暴露（png + metadata），tool 结果只返回 `capture_id + 最小元信息 + resource URI`。
- 新增更小的 observe primitives（active window/monitors/list windows），减少 `desktop.get_topology` 的高频依赖。
- batch/vision 默认返回 summary 输出，并提供显式 full/detail 开关。
- 以 Godot 场景为基准提供可验证的闭环示例与回归测试，避免未来回退到“默认大返回”。

**Non-Goals:**

- 不做旧行为兼容（不保留 pretty JSON content、不保留 capture 默认返回 path）。
- 不实现内置 agent loop。
- 不引入跨桌面环境/跨 compositor 兼容层。
- 不把大内容（raw payload、base64 image、窗口全量列表等）默认回传；仅在显式请求时返回。

## Decisions

### Decision 1: 将 `CallToolResult.content` 收敛为极短文本

选择将成功返回统一为 `ok`，失败返回为 `code: message`（不带 details），完整结构化结果放在 `structuredContent`。

原因：

- `content` 是许多 host 默认喂给 LLM 的字段；把完整 JSON 放进 `content` 会导致 token 成倍浪费。
- `structuredContent` 已足以承载结构化消费与 UI 展示（Inspector/host 可直接读取）。

替代方案：

- 保留 content 的完整 JSON，但压缩/不缩进：仍是重复传输，且仍会污染 LLM 上下文。
- 用配置开关在调试时开启大 content：增加分支与测试矩阵；本 change 以默认极致省为目标，排障应通过 `detail=raw/full` 与日志/资源读取完成。

### Decision 2: 截图/元数据通过 MCP Resources 模板 URI 暴露

使用 FastMCP `@resource` 注册模板资源，例如：

- `wisp-hand://captures/{capture_id}.png`
- `wisp-hand://captures/{capture_id}.json`

原因：

- png/base64 是重内容，必须从 tool result 中剥离。
- Resources 允许按需读取，且对 host 更通用（不要求共享本地路径语义）。

关键实现边界：

- 资源读取 MUST 严格限制在 capture store 内，禁止任意路径读取（防止 path traversal / 信息泄露）。
- 不提供“列出全部 captures”的资源列表（避免 token 爆炸），只提供模板读取。

### Decision 3: 新增 observe primitives，减少 topology 依赖

新增：

- `wisp_hand.desktop.get_active_window`
- `wisp_hand.desktop.get_monitors`
- `wisp_hand.desktop.list_windows(limit=...)`

原因：

- Godot 场景主要需要 active window 的 selector/几何，以及 monitors 的几何与坐标映射。
- `desktop.get_topology(detail=full/raw)` 仍保留用于诊断，但不作为默认高频工具。

### Decision 4: batch/vision 增加明确的“默认省”开关

- `batch.run(return_mode=summary|full)`：默认 summary，避免每步输出级联大对象。
- `vision.locate(limit, space=scope|image|both)`：默认 limit=3 且仅 scope 坐标；需要 VLM/排障时才返回更多。

## Risks / Trade-offs

- [Host 不消费 structuredContent] → 这是 breaking；通过文档明确要求主 agent/host 以 structuredContent 为主；如需兼容需单独 change 讨论（本仓库默认不做兼容垫片）。
- [Resources 支持差异] → 若某些 host 对 `resources/read` 支持不足，提供显式 `detail=full` 回退以返回本地 path 或 inline（默认关闭）。
- [调试可读性下降] → `content` 不再包含完整 JSON；排障依赖 structuredContent、日志与 `detail=raw`/资源读取。
- [安全风险] 资源读取若实现不当可能泄漏文件 → 只允许读取 capture_id 对应文件，且 capture_id 必须满足 UUID 格式并存在于 capture store。

## Migration Plan

1. 先引入统一 result 包装（content 极短）与对应回归测试，确保 token 不再被重复 JSON 放大。
2. 引入 capture resources：注册模板资源并修改 `capture.screen` 默认返回；更新 tests/examples/docs。
3. 引入 observe primitives：实现新工具并更新 Godot 场景文档，让示例从 topology 迁移到 active_window/monitors。
4. 引入 batch/vision 的 summary 默认输出与显式 full 开关；补齐测试矩阵。

## Open Questions

- `detail=full` 的回退形态是否需要返回本地 `path` 或 `inline_base64`（仅用于某些 host/VLM 无法 resources/read 的场景），以及回退参数的命名（`detail` vs `inline` vs `include_path`）。

