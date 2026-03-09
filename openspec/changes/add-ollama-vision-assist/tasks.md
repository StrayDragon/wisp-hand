## 1. Ollama Provider 与配置

- [ ] 1.1 实现 Ollama HTTP provider、模型配置、超时与并发控制
- [ ] 1.2 将 `vision.mode`、`model`、`base_url`、`max_image_edge`、`max_tokens` 等配置接入 runtime

## 2. Vision 工具

- [ ] 2.1 实现 `hand.vision.describe`，支持 `capture_id` 与 `inline_image`
- [ ] 2.2 实现 `hand.vision.locate`，基于 capture artifact 返回候选区域列表
- [ ] 2.3 实现图像预处理、输入来源校验与 `capability_unavailable` 降级路径

## 3. 验证

- [ ] 3.1 为 disabled / assist 模式、provider 不可用、超时与超大图像预处理编写测试
- [ ] 3.2 验证 describe / locate 的返回结构、审计字段与 capture 复用链路
