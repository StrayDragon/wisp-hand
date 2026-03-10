## 1. 统一 Tool Result（content 极短）

- [ ] 1.1 修改 server 统一返回封装：成功时 `content.text="ok"`；失败时 `content.text="<code>: <message>"`；完整结果只放 `structuredContent`
- [ ] 1.2 为 `content.text` 增加回归测试（长度上限断言，例如 `< 64`），防止回归到 pretty JSON

## 2. Capture 改为 MCP Resources（默认不返回 path/inline）

- [ ] 2.1 设计并实现 capture 资源 URI 方案：`wisp-hand://captures/{capture_id}.png` 与 `wisp-hand://captures/{capture_id}.json`
- [ ] 2.2 在 server 注册 FastMCP `@resource` 模板并实现 `resources/read`：读取 png 与 metadata（严格限制只能读取 capture store 内、禁止路径穿越）
- [ ] 2.3 修改 `wisp_hand.capture.screen` 默认 structured 输出：返回 `capture_id/width/height/mime_type/created_at` + resource URI（移除默认 `path` 与 `inline_base64`）
- [ ] 2.4 支持显式 `inline=true`：仅在显式请求时返回 `inline_base64`
- [ ] 2.5 更新测试与 examples：capture 默认不含 `path/inline_base64`；resources/read 能读取 png/json；已被 retention 清理的 capture 读取返回明确错误

## 3. Observe Primitives（Godot 导向）

- [ ] 3.1 新增 `wisp_hand.desktop.get_active_window`：返回最小 selector+几何字段集合（`address/class/title/workspace/monitor/at/size`）
- [ ] 3.2 新增 `wisp_hand.desktop.get_monitors`：返回最小几何+映射字段集合（`layout_bounds/physical_size/scale/pixel_ratio`，不含 `availableModes`）
- [ ] 3.3 新增 `wisp_hand.desktop.list_windows(limit=...)`：按需枚举窗口（默认精简字段，limit<=0 返回 `invalid_parameters`）
- [ ] 3.4 更新 tests：字段白名单断言与 limit 行为断言；非 Hyprland 环境返回 `unsupported_environment`

## 4. Batch 输出瘦身（return_mode）

- [ ] 4.1 为 `wisp_hand.batch.run` 增加 `return_mode=summary|full`（默认 summary）参数与模型
- [ ] 4.2 `return_mode=summary` 下裁剪每步输出：`capture` 步骤至少返回 `capture_id`，其余步骤避免返回大对象；错误至少包含 `code/message`
- [ ] 4.3 `return_mode=full` 保持现有详细输出能力
- [ ] 4.4 更新 tests：默认 summary 的逐步输出边界、full 输出边界与 stop_on_error 行为不回退

## 5. Vision Locate 输出瘦身（limit/space）

- [ ] 5.1 为 `wisp_hand.vision.locate` 增加 `limit`（默认 3）与 `space=scope|image|both`（默认 scope）参数
- [ ] 5.2 默认仅返回 scope 候选；`space=both` 时同时返回两套坐标；非法 space 返回 `invalid_parameters`
- [ ] 5.3 更新 tests：默认候选数量与字段集合；both 模式返回两套候选

## 6. 文档与 Godot 闭环示例

- [ ] 6.1 更新 docs：强调主 agent 以 `structuredContent` 消费、通过 `resources/read` 拉取原图/metadata（不依赖本地 path）
- [ ] 6.2 更新 Godot 场景：优先使用 `get_active_window/get_monitors`，将 `get_topology` 限定为低频诊断
- [ ] 6.3 更新工具参考：补齐新工具与参数（return_mode/limit/space/resource URI）

