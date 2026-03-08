## 1. 输入工具面与坐标映射

- [x] 1.1 实现 `hand.pointer.move`、`hand.pointer.click`、`hand.pointer.drag`、`hand.pointer.scroll`
- [x] 1.2 实现 `hand.keyboard.type` 与 `hand.keyboard.press`
- [x] 1.3 将所有输入工具接入 session scope 解析与绝对坐标映射

## 2. 安全护栏

- [x] 2.1 实现 `armed` 检查、`dry_run` 语义与统一输入调度结果模型
- [x] 2.2 实现 emergency stop 锁存、动作频率限制与危险动作策略拒绝
- [x] 2.3 为所有输入路径补齐成功、失败、拒绝三类审计记录

## 3. 验证

- [x] 3.1 为 scope 越界、未 armed、dry-run、rate limit、policy deny 路径编写测试
- [x] 3.2 验证 move/click/drag/scroll/type/press 在 scope 内可重复执行且错误码稳定
