## ADDED Requirements

### Requirement: 服务必须提供可回溯的坐标映射后端选择结果

Wisp Hand 服务 MUST 基于运行时环境生成一个“坐标映射结果”, 用于把 **layout/logical px** 与 **image px** 联系起来, 并向客户端暴露后端来源与置信度, 以便在 mixed-scale 多显示器下稳定驱动 capture/input/vision.

该结果 MUST 至少包含:

- `backend`: 当前采用的坐标后端标识符
- `confidence`: 后端对当前映射的置信度(0-1 或等价分级)
- `topology_fingerprint`: 用于缓存失效判断的拓扑指纹
- `monitors[*].name`
- `monitors[*].layout_bounds` (layout px)
- `monitors[*].physical_size` (physical px)
- `monitors[*].scale`
- `monitors[*].pixel_ratio` (image px / layout px, 允许 x/y 分离)
- `desktop_layout_bounds` (layout px)

#### Scenario: mixed-scale 下返回每个 monitor 的 pixel_ratio

- **WHEN** Hyprland 会话包含任意 `scale != 1.0` 的 monitor
- **THEN** 服务 MUST 在坐标映射结果中返回该 monitor 的 `pixel_ratio` 且其值与截图像素比例一致

### Requirement: 坐标后端必须支持自动选择与强制覆盖

服务 MUST 通过运行时配置允许选择坐标后端模式, 至少支持:

- `auto`: 自动选择最合适后端
- `hyprctl-infer`: 仅基于 `hyprctl` 信息推断
- `grim-probe`: 通过 `grim` 进行被动探针校准
- `active-pointer-probe`: 主动 pointer 校准(必须显式确认, 默认不可用)

当用户强制选择某个后端且后端不可用时, 服务 MUST 明确失败(配置错误或 `capability_unavailable`), 而不是静默回退到其他后端.

#### Scenario: 强制后端不可用时明确失败

- **WHEN** 用户配置 `coordinates.mode="grim-probe"` 但 `grim` 不可用
- **THEN** 服务 MUST 明确失败并指出缺失依赖, 而不是静默回退为推断模式

### Requirement: 坐标映射结果必须可缓存且可失效

当启用缓存时, 服务 MUST 将坐标映射结果持久化到 `state_dir` 下并在拓扑未变化时复用; 当 `topology_fingerprint` 变化时 MUST 失效并重新生成.

#### Scenario: 拓扑未变化时复用缓存结果

- **WHEN** 服务多次启动且 Hyprland monitor 拓扑未变化
- **THEN** 服务 MUST 复用缓存的坐标映射结果, 且 `backend/confidence/monitors.layout_bounds` 一致

