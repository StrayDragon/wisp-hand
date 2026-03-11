## ADDED Requirements

### Requirement: Tool 结果必须以 structuredContent 为权威，content 默认极短

Wisp Hand 服务对所有 `wisp_hand.*` tools 的 `tools/call` 返回 MUST 满足：

- `structuredContent` MUST 存在，并承载该 tool 的完整结构化结果（成功或失败）。
- `content` MUST 默认只包含极短文本，不得再次携带完整 JSON 结果（避免重复传输与 token 放大）。

当 tool 成功时，`content` 的默认文本 MUST 为 `ok`。

当 tool 失败时，`content` 的默认文本 MUST 为 `<code>: <message>` 的简短摘要，且错误细节 MUST 仅在 `structuredContent` 中返回。

#### Scenario: tool 成功时 content 不携带完整 JSON

- **WHEN** 客户端调用任意 `wisp_hand.*` tool 且返回成功
- **THEN** 返回 MUST 包含 `structuredContent`，且 `content` 仅包含极短文本 `ok`，不得把结构化结果 JSON 再次写入 `content.text`

#### Scenario: tool 失败时 content 仅携带简短错误摘要

- **WHEN** 客户端调用任意 `wisp_hand.*` tool 且返回失败
- **THEN** 返回 MUST 包含错误的结构化 `structuredContent`，且 `content` 仅包含 `<code>: <message>` 的简短摘要

### Requirement: 重内容必须通过 MCP Resources 按需读取

当 tool 结果涉及重内容时（至少包括截图 png 与截图 metadata），服务 MUST 通过 MCP Resources 暴露可读取的资源，并在 tool 结果中返回对应资源的 URI（而不是内联 base64 或本地路径）。

服务 MUST 至少暴露以下 capture 资源模板：

- `wisp-hand://captures/{capture_id}.png`
- `wisp-hand://captures/{capture_id}.json`

#### Scenario: capture 默认返回资源 URI

- **WHEN** 客户端以默认参数调用 `wisp_hand.capture.screen`
- **THEN** 返回 MUST 包含 png 与 metadata 的 resource URI，并且 MUST NOT 默认返回本地 `path` 或内联 base64 图像

#### Scenario: 客户端可通过 resources/read 获取 png

- **WHEN** 客户端对 `wisp-hand://captures/{capture_id}.png` 执行 `resources/read`
- **THEN** 服务返回对应 png 的二进制内容（或等价 blob 资源内容），且该内容与 capture artifact store 中的图片一致

#### Scenario: 不存在的 capture 资源被明确拒绝

- **WHEN** 客户端对不存在或已被 retention 清理的 `capture_id` 执行 `resources/read`
- **THEN** 服务 MUST 返回结构化错误（例如 `capability_unavailable`），而不是返回空内容或崩溃

