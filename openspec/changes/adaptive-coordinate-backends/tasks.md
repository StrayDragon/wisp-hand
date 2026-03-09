## 1. 配置与数据模型

- [ ] 1.1 新增 `[coordinates]` 配置段(Pydantic schema + 默认值): `mode`, `cache_enabled`, `probe_region_size`, `min_confidence` 等
- [ ] 1.2 定义坐标映射数据模型: `CoordinateMap`/`MonitorMap`/`Bounds`/`PixelRatio` 并支持 JSON 序列化
- [ ] 1.3 实现 `topology_fingerprint` 生成与 `state_dir` 下的 cache 读写/失效逻辑

## 2. 坐标后端实现

- [ ] 2.1 实现 `hyprctl-infer` 后端: 基于 monitor `x/y/width/height/scale` 推断 `layout_bounds`, 并计算置信度
- [ ] 2.2 实现 `grim-probe` 后端: 使用 `grim` 被动探针反推 `physical_size` 与 `pixel_ratio`, 并产出 `layout_bounds`
- [ ] 2.3 实现 `auto` 选择器: 依据 scale/置信度选择最合适后端; 支持强制后端且不可用时明确失败
- [ ] 2.4 实现诊断级 `active-pointer-probe` 流程(不默认启用): 通过显式确认 + 用户框选安全 region 做一次 move 并回读 cursorpos 校验 extent

## 3. Runtime/Tool 接入

- [ ] 3.1 在 runtime 初始化阶段生成/加载 `CoordinateMap`, 并记录后端选择与置信度日志事件
- [ ] 3.2 升级 `hand.desktop.get_topology` 输出: 增加 `coordinate_backend`、`desktop_layout_bounds`、`monitors[*].layout_bounds/physical_size/scale/pixel_ratio`
- [ ] 3.3 修复 `desktop_bounds`/monitor bounds 的坐标空间: 统一使用 `layout_bounds` 作为 desktop/layout extent
- [ ] 3.4 修复 virtual pointer `motion_absolute` extent: 使用 `desktop_layout_bounds`(layout px) 作为归一化边界
- [ ] 3.5 升级 `hand.capture.screen` 元数据: 补齐 `source_coordinate_space/image_coordinate_space/pixel_ratio_x/pixel_ratio_y` 并处理跨 monitor 的映射边界
- [ ] 3.6 **BREAKING** 升级 `hand.vision.locate` 输出: 返回 `candidates_scope` + `candidates_image`, 并基于 capture 映射自动换算

## 4. 诊断与示例

- [ ] 4.1 新增 `examples/attempts/diagnose_coordinates.py`(或扩展现有 smoke): 输出坐标后端选择、每个 monitor 的推断/探针结果与比例校验
- [ ] 4.2 补齐“用户需要手动操作”的验证指引: slurp 框选安全区域、运行主动校准、如何判断偏移
- [ ] 4.3 更新 README/ROADMAP 附录或 docs: 给出 mixed-scale 推荐配置与 fallback 方案

## 5. 测试

- [ ] 5.1 单测: `hyprctl-infer` 在 scale=1.25 + 1.0 双屏下能产出正确的 `desktop_layout_bounds`
- [ ] 5.2 单测: capture 元数据包含映射字段且 `pixel_ratio` 与截图尺寸一致
- [ ] 5.3 单测: `hand.vision.locate` 的 `candidates_scope` 不随 scale 漂移(基于合成 capture/metadata 断言换算)
- [ ] 5.4 单测: pointer dispatch 的 extent 使用 layout bounds(避免把 physical width 当 extent)
- [ ] 5.5 真实环境 smoke: 生成 JSON 报告验证缩放比例与 stdout 安全(可选 pointer 校准需显式确认)

