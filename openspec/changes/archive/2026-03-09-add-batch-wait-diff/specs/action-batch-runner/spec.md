## ADDED Requirements

### Requirement: 批处理必须在单一 session 与 scope 中顺序执行

Wisp Hand 服务 MUST 通过 `hand.batch.run` 在单一 `session_id` 下顺序执行一组步骤，并保证所有步骤共享同一 session scope 与安全状态。

#### Scenario: 三步动作顺序成功执行

- **WHEN** 客户端提交包含 `move`、`click`、`capture` 三个步骤的 batch
- **THEN** 服务按提交顺序执行三步，并返回逐步结果列表

#### Scenario: Batch 中的每个步骤都继承同一 session

- **WHEN** 客户端提交 batch 且未为单个步骤单独指定 session
- **THEN** 服务 MUST 使用 batch 级 `session_id` 解析所有步骤，而不是允许步骤绕过当前 session scope

### Requirement: 批处理必须支持 fail-fast 与逐步结果

`hand.batch.run` MUST 支持 `stop_on_error`，并在返回结果中包含每一步的执行状态、输出或错误信息。

#### Scenario: Fail-fast 在首个失败步骤停止

- **WHEN** 客户端提交 `stop_on_error=true` 的 batch，且第二步执行失败
- **THEN** 服务停止执行后续步骤，并在结果中明确标记失败步骤与未执行步骤

#### Scenario: 非 fail-fast batch 继续执行

- **WHEN** 客户端提交 `stop_on_error=false` 的 batch，且某一步失败
- **THEN** 服务继续执行后续步骤，并在结果中分别标记每一步的成功或失败状态

### Requirement: Batch 步骤类型必须受现有工具面约束

`hand.batch.run` 的步骤类型 MUST 只允许复用已定义的 `move`、`click`、`drag`、`scroll`、`type`、`press`、`wait` 与 `capture` 动作，而不是引入绕过现有校验的隐藏步骤。

#### Scenario: 非法步骤类型被拒绝

- **WHEN** 客户端在 batch 中提交未被支持的步骤类型
- **THEN** 服务 MUST 返回结构化参数错误并拒绝该 batch
