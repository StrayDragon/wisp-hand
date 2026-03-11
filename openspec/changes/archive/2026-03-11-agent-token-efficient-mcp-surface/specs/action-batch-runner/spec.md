## MODIFIED Requirements

### Requirement: 批处理必须支持 fail-fast 与逐步结果

`wisp_hand.batch.run` MUST 支持 `stop_on_error`，并在返回结果中包含每一步的执行状态、输出或错误信息。

此外，为了保证 token-efficient，`wisp_hand.batch.run` MUST 支持 `return_mode=summary|full`，且默认行为 MUST 等价于 `return_mode=summary`：

- `return_mode=summary`：每步结果 MUST 只返回最小必要字段；对于 `capture` 步骤，输出 MUST 至少包含 `capture_id`；对于失败步骤，错误 MUST 至少包含 `code` 与 `message`。
- `return_mode=full`：允许返回更详细的步骤输出（例如复用对应 tool 的完整结构化结果）。

#### Scenario: Fail-fast 在首个失败步骤停止

- **WHEN** 客户端提交 `stop_on_error=true` 的 batch，且第二步执行失败
- **THEN** 服务停止执行后续步骤，并在结果中明确标记失败步骤与未执行步骤

#### Scenario: 非 fail-fast batch 继续执行

- **WHEN** 客户端提交 `stop_on_error=false` 的 batch，且某一步失败
- **THEN** 服务继续执行后续步骤，并在结果中分别标记每一步的成功或失败状态

#### Scenario: 默认 return_mode=summary 返回最小逐步输出

- **WHEN** 客户端调用 `wisp_hand.batch.run` 且不提供 `return_mode`
- **THEN** 服务返回的逐步结果 MUST 为 summary 级别，且 `capture` 步骤输出至少包含 `capture_id`

#### Scenario: return_mode=full 返回详细逐步输出

- **WHEN** 客户端调用 `wisp_hand.batch.run(return_mode=full)`
- **THEN** 服务返回的逐步结果包含比 summary 更详细的输出（例如包含完整 capture 元信息）

