# 工具参考（MCP tools）

所有工具都在 `wisp_hand.*` 命名空间下。下面按功能域给出说明与最小示例。

提示：输入类工具需要 `session_id` 且 session 必须 `armed=true`。

注意：为了极致节省 token，所有 tool 的返回遵循：

- `structuredContent` 是权威结构化结果（主 agent 应优先消费它）
- `content` 默认只返回极短文本（成功 `ok`，失败 `code: message`）
- 截图等重内容通过 MCP Resources 按需读取（不依赖本地 `path`）

## 发现与基础

### `wisp_hand.capabilities`

返回当前环境能力与缺失依赖，用于接入前探测。

### `wisp_hand.session.open`

创建一个绑定 scope 的 session。

最小参数：

- `scope_type`: `desktop|monitor|window|region|window-follow-region`
- `scope_target`: 与 scope_type 对应（例如 window selector 或 region 对象）

常用参数：

- `armed`: 是否允许输入产生副作用（默认 false）
- `dry_run`: 是否只演练（默认取配置）
- `ttl_seconds`: 自定义 TTL

### `wisp_hand.session.close`

关闭 session。

## 只读观察

### `wisp_hand.desktop.get_active_window`

返回当前 active window 的最小 selector + 几何字段集合：

- `address/class/title/workspace/monitor/at/size`

用于：快速拿到 Godot（或游戏窗口）的 selector，而不需要拉取全量 topology。

### `wisp_hand.desktop.get_monitors`

返回 monitors 的最小几何与 mixed-scale 映射上下文：

- `layout_bounds/physical_size/scale/pixel_ratio`

用于：多显示器 + 缩放场景下的坐标诊断与 scope 设计。

### `wisp_hand.desktop.list_windows`

按需枚举窗口列表（带 `limit`）。

- `limit<=0` 会返回 `invalid_parameters`
- 返回的每个窗口对象包含 `address/class/title/workspace/monitor/at/size`

### `wisp_hand.desktop.get_topology`

返回 Hyprland 的 monitors/workspaces/active window 等信息，用于：

- 选择 window/monitor selector
- 提供坐标映射上下文（mixed-scale）

参数：

- `detail`: `summary|full|raw`（默认 `summary`）
  - `summary`: token-efficient（不返回 `windows` 列表，且避免执行 `hyprctl -j clients`）
  - `full`: 返回精简的 `windows` 列表（用于自动化/几何计算）
  - `raw`: 在 `full` 基础上额外返回 `raw`（包含 Hyprland 原始 JSON，用于排障）

注意：即使有 `summary`，也不建议高频轮询；在 agent 循环中尽量用 `capture + diff` 作为主观察链路。

### `wisp_hand.cursor.get_position`

输入：`session_id`  
输出：桌面绝对坐标 `x/y` + scope 相对坐标 `scope_x/scope_y`。

## 截图与对比

### `wisp_hand.capture.screen`

输入：

- `session_id`
- `target`: `scope|desktop|monitor|window|region`（默认 `scope`）

可选：

- `inline`: 是否内联返回 base64（默认 false，推荐保持 false）
- `with_cursor`
- `downscale`

输出（默认）：

- `capture_id/width/height/mime_type/created_at`
- `image_uri`：`wisp-hand://captures/{capture_id}.png`
- `metadata_uri`：`wisp-hand://captures/{capture_id}.json`

默认不返回本地 `path`，也不返回 `inline_base64`。如需内联图片，显式 `inline=true`。

通过 MCP `resources/read` 拉取内容：

- `wisp-hand://captures/{capture_id}.png`（`image/png`）
- `wisp-hand://captures/{capture_id}.json`（`application/json`）

### `wisp_hand.capture.diff`

输入：`left_capture_id`, `right_capture_id`  
输出：像素级 diff 摘要（`changed/change_ratio/changed_pixels/...`）。

## 批处理与等待

### `wisp_hand.batch.run`

把多步动作串行放到一次调用里，减少往返与 token。

参数：

- `return_mode`: `summary|full`（默认 `summary`）
  - `summary`：逐步输出默认裁剪，`capture` 步骤至少返回 `capture_id`（通常还会带 `image_uri/metadata_uri`）
  - `full`：逐步输出保持详细结果（用于排障/调试）

支持 step `type`：

- `move/click/drag/scroll/type/press/wait/capture`

### `wisp_hand.wait`

在 session 上下文内等待固定毫秒数（用于 UI 过渡）。

## 可选本地视觉（Ollama）

### `wisp_hand.vision.describe`

输入：`capture_id` 或 `inline_image` 二选一，支持自定义 prompt。

### `wisp_hand.vision.locate`

输入：`capture_id`, `target`

参数：

- `limit`（默认 3）：限制返回候选数量
- `space`（默认 `scope`）：`scope|image|both`

输出：

- `space=scope`：只返回 `candidates_scope`
- `space=image`：只返回 `candidates_image`
- `space=both`：同时返回两套候选

## Scoped 输入

- 指针：`wisp_hand.pointer.move/click/drag/scroll`
- 键盘：`wisp_hand.keyboard.type/press`

输入工具的共同点：

- session 必须 `armed=true`
- 组合键会经过策略过滤（危险快捷键会被拒绝）
