## MODIFIED Requirements

### Requirement: 截图结果必须进入 artifact store 并附带标准元数据

每次截图 MUST 写入 capture artifact store，并返回至少包含 `capture_id`、`width`、`height`、`mime_type` 与 `created_at` 的标准元数据。

为了保证 token-efficient，默认情况下（未显式请求更多细节）：

- 返回 MUST NOT 包含本地 `path`
- 返回 MUST NOT 包含 `inline_base64`
- 返回 MUST 提供可读取的 capture 资源 URI（png + metadata），以便客户端通过 MCP Resources 按需读取

当客户端显式请求内联图像时（例如 `inline=true`）：

- 服务 MUST 返回 `inline_base64`
- 同时仍 MUST 返回 `capture_id` 与标准元数据

#### Scenario: 默认返回资源 URI（不返回 path/inline）

- **WHEN** 客户端以默认参数调用 `wisp_hand.capture.screen`
- **THEN** 服务返回 `capture_id/width/height/mime_type/created_at` 与 png+metadata 的 resource URI，并且 MUST NOT 返回 `path` 或 `inline_base64`

#### Scenario: 显式请求内联图像

- **WHEN** 客户端以 `inline=true` 调用 `wisp_hand.capture.screen`
- **THEN** 服务返回 `inline_base64`，并仍保留 `capture_id/width/height/mime_type/created_at` 与 png+metadata 的 resource URI

