## Why

当前在缩放显示器(scale != 1.0)与多显示器混合缩放场景下, Wisp Hand 的 capture/input/vision 三条链路存在坐标系与像素系的隐式不一致: 例如同样的 region `120x120` 在 `scale=1.25` 显示器上会产出 `150x150` 的截图像素尺寸, 这会直接导致 vision locate 坐标难以稳定映射到可点击坐标, 并带来 pointer click 偏移风险.

该问题是高频真实桌面环境的常见痛点, 如果不在 MVP hardening 前收敛坐标契约, 后续 MCP 能力集成与长耗时任务执行会反复踩坑且难以定位.

## What Changes

- 引入 **坐标后端(Coordinate Backend)** 子系统, 以单一“规范坐标系”对外输出, 同时内部支持多种后端探测与 fallback:
  - `hyprctl-infer`(被动推断, 快)
  - `grim-probe`(被动探针, 更可靠, 通过截图像素比值反推)
  - `active-pointer-probe`(可选主动校准, 需要显式确认, 最高置信)
- 收敛对外坐标契约: 所有 scope/session/pointer 的坐标统一为 **Hyprland layout/logical px**; 所有截图图像的 `width/height` 统一为 **image px**; 两者之间通过明确的映射字段连接.
- `wisp_hand.desktop.get_topology` 增强: 为每个 monitor 输出规范化的 `layout_bounds` 与 `physical_size`/`scale`, 并返回坐标后端选择结果与置信度, 便于 agent 与排障.
- `wisp_hand.capture.screen` 增强: capture 元数据与返回值补齐可逆映射上下文(例如 `pixel_ratio_x/y`, `source_bounds` 坐标系声明, downscale 影响), 以便把 image px 稳定映射回 scope/layout px.
- **BREAKING**: `wisp_hand.vision.locate` 输出字段收敛为显式坐标系, 避免歧义:
  - 返回 `candidates_scope`(scope/layout px) 作为默认可点击坐标
  - 同时返回 `candidates_image`(image px) 作为调试与高级 fallback
- scoped input 修正: virtual pointer `motion_absolute` 的 extent 计算改为使用规范化的 desktop/layout bounds, 避免在 mixed-scale 多显示器下的归一化漂移.
- 新增诊断与 smoke: 提供可复现脚本验证缩放/多显示器的 capture 比例、vision 坐标回映射、以及(可选)真实 pointer 校准闭环.
- 新增坐标映射缓存: 基于 topology fingerprint 缓存坐标后端输出, 默认复用并在变化时失效, 降低探针开销.

## Capabilities

### New Capabilities
- `coordinate-backends`: 定义坐标后端选择、探针、置信度与缓存, 输出规范化的 monitor/desktop 坐标映射能力.

### Modified Capabilities
- `hyprland-topology-observe`: topology 输出补齐 monitor 的 layout/physical/scale 语义与坐标后端元信息.
- `screen-capture-artifacts`: capture 元数据补齐 image px 与 layout px 之间的映射字段, 并明确 `source_bounds` 的坐标系语义.
- `scoped-input-control`: pointer 输入坐标与 desktop extent 的规范化, 保证 mixed-scale 多显示器下点击不漂移.
- `ollama-vision-assist`: `vision.locate` 返回显式的 scope/layout 坐标候选, 并提供 image px 候选用于调试与 fallback.

## Impact

- 影响核心模块: `hyprland.py`, `capture.py`, `runtime.py`, `input_backend.py`, `vision.py`, `models.py`, `config.py` 以及相关 tests/examples.
- 引入新的运行时配置段(例如 `[coordinates]`), 并新增/调整 smoke 脚本以支持真实环境验证.
- 不新增必须的外部依赖; `grim`/`hyprctl` 已是必需链路, 探针复用现有能力与 Pillow 解析图像尺寸.
