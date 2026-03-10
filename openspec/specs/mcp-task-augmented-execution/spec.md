# mcp-task-augmented-execution Specification

## Purpose
定义 MCP Tasks 能力在 Wisp Hand 中的落地要求，使长耗时的 `tools/call` 可以通过 task-augmented 方式异步执行、轮询获取结果并支持取消。

## Requirements
### Requirement: 服务必须支持 tools/call 的 task-augmented 执行与轮询

当客户端在 `tools/call` 请求参数中携带 `task` 元数据时，Wisp Hand MUST 以 task 方式执行该工具调用：

- 服务 MUST 立即返回 `CreateTaskResult`（而不是阻塞等待工具执行完成）。
- 服务 MUST 支持 `tasks/get` 查询 task 状态。
- 服务 MUST 支持 `tasks/result` 获取最终结果，且结果类型 MUST 与原始请求类型一致：对 `tools/call` 来说返回 `CallToolResult`。

#### Scenario: 以 task 方式调用长耗时工具并轮询拿到结果

- **GIVEN** 客户端已连接到 Wisp Hand，并已通过 `wisp_hand.session.open` 获得 `session_id`
- **WHEN** 客户端以 task-augmented 方式调用 `wisp_hand.wait`（例如 `duration_ms=2000`）
- **THEN** 服务 MUST 立即返回 `CreateTaskResult`
- **AND THEN** 客户端通过 `tasks/get` 轮询直到 task 达到终态
- **AND THEN** 客户端通过 `tasks/result` 获得 `CallToolResult`，其 `structuredContent` MUST 与同步调用 `wisp_hand.wait` 的返回结构一致

### Requirement: 服务必须支持 tasks/list 与 tasks/cancel

服务 MUST 支持：

- `tasks/list`：列出当前已存在的 tasks（可分页）
- `tasks/cancel`：取消一个非终态 task

#### Scenario: 取消一个正在执行的工具 task

- **GIVEN** 客户端已创建一个工具 task（例如 `wisp_hand.wait` 的长等待）
- **WHEN** 客户端调用 `tasks/cancel`
- **THEN** 服务 MUST 返回取消后的 task 状态，并使其进入 `cancelled` 终态
- **AND** 对已进入终态的 task，服务 MUST NOT 再将其状态转换为 `completed` 或 `failed`

### Requirement: task 执行期间必须提供最小可诊断状态信息

当工具以 task 方式执行时，服务 MUST 在 task 执行期间更新 `statusMessage`（或等价字段）以便外部接入方诊断当前阶段，至少覆盖：

- started / running tool / done

#### Scenario: task 状态信息可随轮询观察到

- **WHEN** 客户端对一个工作中的 tool task 反复调用 `tasks/get`
- **THEN** 返回的 task MUST 包含非空的 `statusMessage`，且随着阶段推进可变化

