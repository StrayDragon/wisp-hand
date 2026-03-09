## ADDED Requirements

### Requirement: 服务必须从统一配置源加载运行参数

Wisp Hand 服务 MUST 从统一的运行时配置文件加载启动参数、目录约定、安全默认值与依赖探测选项，并在配置非法时给出明确诊断。

#### Scenario: 有效配置成功加载

- **WHEN** 服务在启动时读取合法配置文件
- **THEN** 配置值会覆盖默认值并进入后续 runtime 组件

#### Scenario: 非法配置阻止启动

- **WHEN** 服务在启动时读取到缺失必填字段或类型错误的配置
- **THEN** 服务 MUST 以明确的配置错误终止启动，而不是在运行中延迟失败

### Requirement: 所有工具失败都必须返回结构化错误

所有 MCP tool 失败 MUST 返回稳定的结构化错误码与上下文数据，避免让客户端依赖字符串匹配来判断错误原因。

#### Scenario: 找不到 session 时返回稳定错误码

- **WHEN** 客户端对不存在的 `session_id` 调用任何基础工具
- **THEN** 服务返回 `session_not_found` 及相关上下文，而不是只返回自由文本

#### Scenario: 缺少能力时返回稳定错误码

- **WHEN** 某个工具依赖的运行能力不可用
- **THEN** 服务 MUST 返回 `capability_unavailable` 或 `dependency_missing`，并附带具体原因

### Requirement: 所有工具调用都必须进入审计日志

服务 MUST 为每次 tool call 记录文本日志与 JSONL 审计记录，至少包含时间戳、tool 名称、session、scope、执行结果、拒绝原因与延迟。

#### Scenario: 成功调用生成审计记录

- **WHEN** 任意基础工具成功执行
- **THEN** 服务写入一条包含结果与延迟的 JSONL 审计记录

#### Scenario: 被拒绝的调用也会被记录

- **WHEN** 任意基础工具因配置、状态或策略被拒绝
- **THEN** 服务 MUST 记录拒绝原因与相关上下文，而不是只记录成功事件
