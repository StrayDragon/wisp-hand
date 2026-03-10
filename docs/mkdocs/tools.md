# 工具参考（MCP tools）

所有工具都在 `wisp_hand.*` 命名空间下。下面按功能域给出说明与最小示例。

提示：输入类工具需要 `session_id` 且 session 必须 `armed=true`。

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

### `wisp_hand.desktop.get_topology`

返回 Hyprland 的 monitors/workspaces/active window 等信息，用于：

- 选择 window/monitor selector
- 提供坐标映射上下文（mixed-scale）

注意：该输出可能较大；在 agent 循环中建议低频调用，尽量用 `capture + diff` 作为主观察链路。

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

输出：`capture_id`、尺寸、artifact 路径与 metadata。

### `wisp_hand.capture.diff`

输入：`left_capture_id`, `right_capture_id`  
输出：像素级 diff 摘要（`changed/change_ratio/changed_pixels/...`）。

## 批处理与等待

### `wisp_hand.batch.run`

把多步动作串行放到一次调用里，减少往返与 token。

支持 step `type`：

- `move/click/drag/scroll/type/press/wait/capture`

### `wisp_hand.wait`

在 session 上下文内等待固定毫秒数（用于 UI 过渡）。

## 可选本地视觉（Ollama）

### `wisp_hand.vision.describe`

输入：`capture_id` 或 `inline_image` 二选一，支持自定义 prompt。

### `wisp_hand.vision.locate`

输入：`capture_id`, `target`  
输出：候选框（image 坐标 + 尽可能换算后的 scope 坐标），用于辅助点击定位。

## Scoped 输入

- 指针：`wisp_hand.pointer.move/click/drag/scroll`
- 键盘：`wisp_hand.keyboard.type/press`

输入工具的共同点：

- session 必须 `armed=true`
- 组合键会经过策略过滤（危险快捷键会被拒绝）

