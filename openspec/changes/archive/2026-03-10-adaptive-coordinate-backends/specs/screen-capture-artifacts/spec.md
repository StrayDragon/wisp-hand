## MODIFIED Requirements

### Requirement: 截图元数据必须保留坐标映射上下文

capture 元数据 MUST 保留目标类型、原始几何边界与 downscale 上下文, 并且 MUST 明确提供 **image px** 与 **layout/logical px** 的映射字段, 以便后续 input、diff 与 vision 链路把图像坐标稳定映射回桌面或 scope 坐标.

返回与落盘的 capture 元数据 MUST 至少包含:

- `source_bounds`: 截图几何边界, 坐标系为 layout/logical px
- `width`/`height`: 输出 PNG 图像尺寸, 坐标系为 image px
- `source_coordinate_space = "layout_px"`
- `image_coordinate_space = "image_px"`
- `pixel_ratio_x` 与 `pixel_ratio_y` (image px / layout px, 必须考虑 downscale)
- `downscale` (若请求)

若该 capture 的 `source_bounds` 跨越多个 monitor 且存在不同的 `pixel_ratio`, 服务 MUST 明确标记该 capture 的映射为非单一比例(例如 `mapping.kind="multi-monitor"`), 并避免伪造单一 `pixel_ratio` 导致误点击.

#### Scenario: Downscale 截图仍可回溯原始边界

- **WHEN** 客户端请求 downscale 后的截图
- **THEN** 返回的 capture 元数据仍包含 `source_bounds` 与可用于回溯映射的 `pixel_ratio_x/y` 与 `downscale`

