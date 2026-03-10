## 1. 接口与模型

- [x] 1.1 更新 [src/wisp_hand/server.py](/home/l8ng/Projects/__straydragon__/wisp-hand/src/wisp_hand/server.py) 的 `wisp_hand.desktop.get_topology` 工具签名: 增加 `detail` 参数, 默认 `summary`, 并对非法值返回 `invalid_parameters`
- [x] 1.2 更新 [src/wisp_hand/models.py](/home/l8ng/Projects/__straydragon__/wisp-hand/src/wisp_hand/models.py) 中的拓扑返回模型, 体现 `detail=summary/full/raw` 的稳定输出边界(含 `raw` 字段仅在 raw 模式返回)

## 2. Hyprland 查询规划

- [x] 2.1 重构 [src/wisp_hand/hyprland.py](/home/l8ng/Projects/__straydragon__/wisp-hand/src/wisp_hand/hyprland.py) 的拓扑查询: 支持按 `detail` 规划子命令, `detail=summary` 时不执行 `hyprctl -j clients`
- [x] 2.2 更新 [src/wisp_hand/runtime.py](/home/l8ng/Projects/__straydragon__/wisp-hand/src/wisp_hand/runtime.py) 的 `get_topology` 实现: 根据 `detail` 调用适配器并构建 `summary/full/raw` 三种视图输出

## 3. 拓扑裁剪与 raw 输出

- [x] 3.1 实现 `detail=summary/full` 的 token-efficient 裁剪规则: `monitors[*]` 不包含 `availableModes` 等大字段; 返回保留 `coordinate_backend/desktop_layout_bounds` 与 `layout_bounds/physical_size/scale/pixel_ratio`
- [x] 3.2 实现 `detail=raw` 输出: 在 `detail=full` 的基础上额外包含 `raw` 字段, 且 `raw` 至少覆盖 Hyprland 原始 `monitors/workspaces/active_workspace/active_window/windows`

## 4. 测试与示例

- [x] 4.1 添加/更新 tests: 验证 `summary` 默认不含 `windows`, `full` 含 `windows`, `raw` 含 `raw`; 非法 `detail` 返回 `invalid_parameters`
- [x] 4.2 添加/更新 tests: 验证 `detail=summary` 路径不执行 `hyprctl -j clients`(通过 mock/spy `CommandRunner`)
- [x] 4.3 更新 repo 内示例脚本(例如 coordinate/诊断脚本)以适配新默认, 对需要全量/排障的路径显式传 `detail=full/raw`

## 5. 文档

- [x] 5.1 更新 README/文档: 说明 `wisp_hand.desktop.get_topology` 的 `detail` 用法, 并给出 token-efficient 默认调用示例与排障用法
