# state-wait-and-diff Specification

## Purpose
定义固定时长等待与 capture diff 的确定性观察契约，为上层 agent / client 提供稳定化与状态比较能力。
## Requirements
### Requirement: 服务必须支持固定时长等待

Wisp Hand 服务 MUST 通过 `hand.wait` 提供固定时长等待能力，并允许 `hand.batch.run` 复用同一等待语义。

#### Scenario: 显式等待到达指定时长

- **WHEN** 客户端调用 `hand.wait` 并提供 `duration_ms`
- **THEN** 服务在等待指定时长后返回成功结果

#### Scenario: Batch 内等待步骤复用同一语义

- **WHEN** 客户端在 batch 中插入 `wait` 步骤
- **THEN** 服务 MUST 按与 `hand.wait` 相同的语义执行等待

### Requirement: 服务必须支持 capture diff

Wisp Hand 服务 MUST 通过 `hand.capture.diff` 基于两个 `capture_id` 做像素级差异比较，并返回 `changed`、`change_ratio` 与确定性 `summary`。

#### Scenario: 两张截图存在明显差异

- **WHEN** 客户端对两张不同状态的截图调用 `hand.capture.diff`
- **THEN** 服务返回 `changed=true`、正的 `change_ratio` 与可复现的差异摘要

#### Scenario: 缺失 capture 时 diff 被拒绝

- **WHEN** 客户端调用 `hand.capture.diff` 但任一 `capture_id` 不存在
- **THEN** 服务 MUST 返回结构化的 capture 查询错误
