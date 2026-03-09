## 1. Hyprland 读取链路

- [x] 1.1 实现 Hyprland topology adapter，统一读取 monitors、workspaces、active window、windows 与 cursor 信息
- [x] 1.2 将 `hand.desktop.get_topology` 与 `hand.cursor.get_position` 接到 foundation 的 session / error / audit runtime

## 2. 截图与 Artifact Store

- [x] 2.1 实现 `desktop`、`monitor`、`window`、`region`、`scope` 五类截图目标的边界解析与截图执行
- [x] 2.2 实现 capture artifact store、元数据记录、`capture_id` 分配与 inline 返回逻辑
- [x] 2.3 为 capture 元数据加入目标边界、scope 关联与 downscale 上下文字段

## 3. 验证

- [x] 3.1 为拓扑读取、cursor relative 坐标、多显示器截图与依赖缺失路径编写测试
- [x] 3.2 验证 artifact store 可复用 capture、元数据完整且裁剪精度符合 scope 预期
