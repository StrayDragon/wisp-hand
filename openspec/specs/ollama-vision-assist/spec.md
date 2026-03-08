# ollama-vision-assist Specification

## Purpose
定义本地 Ollama 视觉辅助契约，为外部 agent / client 提供显式 describe / locate 能力，而不把视觉推理嵌入隐式执行链路。
## Requirements
### Requirement: Vision 工具必须可以显式启用或关闭

Wisp Hand 服务 MUST 支持 `disabled` 与 `assist` 两种 vision 运行模式；当 vision 未启用或 provider 不可用时，所有视觉工具都必须明确返回 `capability_unavailable`。

#### Scenario: Vision 关闭时拒绝调用

- **WHEN** 客户端在 `vision.mode=disabled` 时调用任意视觉工具
- **THEN** 服务 MUST 返回 `capability_unavailable`

#### Scenario: Provider 不可用时拒绝调用

- **WHEN** 客户端启用了 vision，但 Ollama provider 不可达或配置不完整
- **THEN** 服务 MUST 返回 `capability_unavailable` 并附带不可用原因

### Requirement: 服务必须支持图像描述能力

Wisp Hand 服务 MUST 通过 `hand.vision.describe` 支持基于 `capture_id` 或 `inline_image` 的图像描述，并返回 `model`、`answer` 与 `latency_ms`。

#### Scenario: 基于 capture 描述图像

- **WHEN** 客户端提供有效 `capture_id` 调用 `hand.vision.describe`
- **THEN** 服务读取对应 capture，调用 Ollama，并返回 `model`、`answer` 与 `latency_ms`

#### Scenario: 基于内联图像描述图像

- **WHEN** 客户端提供 `inline_image` 调用 `hand.vision.describe`
- **THEN** 服务使用内联图像作为输入完成描述，而不要求先存在 capture artifact

### Requirement: 服务必须支持目标定位能力

Wisp Hand 服务 MUST 通过 `hand.vision.locate` 基于 `capture_id` 与文本目标返回候选区域列表，每个候选至少包含 `x`、`y`、`width`、`height`、`confidence` 与 `reason`。

#### Scenario: 定位返回候选区域

- **WHEN** 客户端对有效 `capture_id` 调用 `hand.vision.locate` 并提供文本目标
- **THEN** 服务返回一个或多个候选区域，每个候选都包含位置、尺寸、置信度与解释原因

### Requirement: Vision 链路必须受配置与审计约束

视觉调用 MUST 受模型名、`base_url`、请求超时、最大图像尺寸、最大 token 与并发限制约束，并把输入来源、模型与延迟写入审计记录。

#### Scenario: 超大图像会先预处理再发送

- **WHEN** 输入图像超过配置的最大边长
- **THEN** 服务先按配置下采样，再调用 Ollama provider

#### Scenario: 视觉调用生成审计记录

- **WHEN** 任意视觉工具成功或失败
- **THEN** 服务 MUST 记录输入来源、provider、模型、延迟与结果状态
