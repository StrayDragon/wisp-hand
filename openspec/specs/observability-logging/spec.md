# observability-logging Specification

## Purpose
定义 Wisp Hand 的运行日志(operational logs)事件模型与输出策略: 结构化(JSONL)与人类友好(console)并存, 且在 `stdio` transport 下保证 stdout 不被日志污染, 便于外部 agent/client 聚合检索与本地排障.

## Requirements

### Requirement: 运行日志输出必须可配置为结构化或人类友好模式

Wisp Hand MUST 允许用户通过运行时配置选择运行日志的输出格式与输出目标, 至少支持:

- `json`: 面向日志聚合/检索的 JSON Lines 输出
- `rich`: 面向交互式排障的人类友好控制台输出
- `plain`: 最小回退文本输出

并且 MUST 允许分别启用/禁用 console 输出与文件输出.

#### Scenario: 选择 json 模式输出到文件

- **WHEN** 用户将日志配置为 `format=json` 且启用文件输出
- **THEN** 服务 MUST 以 JSON Lines 写入运行日志文件, 且每行都能被 JSON 解析

#### Scenario: 选择 rich 模式输出到控制台

- **WHEN** 用户将日志配置为 `format=rich` 且启用 console 输出
- **THEN** 服务 MUST 在控制台输出人类友好的日志渲染结果, 并包含日志级别与事件名

### Requirement: stdio transport 下必须保证 stdout 零日志污染

当 `server.transport=stdio` 时, 服务的日志输出 MUST 不写入 stdout; 若启用 console 输出, MUST 写入 stderr 或文件.

#### Scenario: stdio 模式下控制台日志写入 stderr

- **WHEN** 服务以 `stdio` transport 运行且启用了 console 日志
- **THEN** 服务 MUST 把日志写入 stderr(或文件), 且 stdout 只包含 MCP 协议数据

### Requirement: 结构化日志必须包含稳定字段与关键关联维度

当运行日志配置为 `format=json` 时, 每条日志事件 MUST 至少包含:

- `timestamp`
- `level`
- `event`
- `component`

并在与 tool call 相关的事件中包含可用于关联的字段(若可用):

- `tool_name`
- `session_id`
- `batch_id`
- `step_index`
- `latency_ms`
- `status` (ok/error/denied)
- `error.code` (当失败/拒绝时)

#### Scenario: tool call 成功事件包含关联字段

- **WHEN** 客户端调用任意工具且执行成功
- **THEN** 服务 MUST 记录一条包含 `tool_name`, `status=ok` 与 `latency_ms` 的结构化日志事件

#### Scenario: tool call 拒绝事件包含错误码

- **WHEN** 某个工具调用被策略或状态拒绝
- **THEN** 服务 MUST 记录一条包含 `status=denied` 与 `error.code` 的结构化日志事件

### Requirement: 敏感字段必须默认脱敏或截断

运行日志与审计日志 MUST 对潜在敏感内容执行默认脱敏或截断策略, 至少覆盖:

- `hand.keyboard.type` 的输入文本
- vision 的 `inline_image` 或其他大体积二进制字段

并且 MUST 提供配置开关, 使用户在明确知情的本地调试场景可以放开(默认关闭).

#### Scenario: 默认不记录键盘输入原文

- **WHEN** 客户端调用 `hand.keyboard.type` 且输入包含敏感文本
- **THEN** 日志 MUST 不包含原始输入文本, 只包含长度/hash 或摘要等非敏感信息

#### Scenario: 默认不记录内联图像原始 base64

- **WHEN** 客户端调用 vision 工具并提供 `inline_image`
- **THEN** 日志 MUST 不包含原始 base64 图像内容

