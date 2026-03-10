## 1. 收敛配置与边界

- [ ] 1.1 确定运行日志顶层配置表名（`[logging]` vs `[observability]`），并将其加入 `RuntimeConfig` 的 Pydantic schema 与默认值
- [ ] 1.2 明确并落实日志级别字段的归属（迁移 `server.log_level` 为 `logging.level` 并移除旧字段，或定义清晰的优先级与单一真源）
- [ ] 1.3 明确运行日志文件路径与现有 `paths.text_log_file` 的关系（复用/更名/弃用），并同步更新默认路径与文档说明
- [ ] 1.4 确定 “审计 vs 运行日志” 的职责边界与共享关联字段集合（tool/session/scope/batch/step/latency/error.code）

## 2. 引入依赖与日志初始化

- [ ] 2.1 在 `pyproject.toml` 添加 `structlog` 与 `rich` 依赖，并更新 `uv.lock`
- [ ] 2.2 新增日志初始化模块（例如 `wisp_hand/observability.py`）：提供 `init_logging(config: RuntimeConfig)` 统一配置 structlog 事件模型与渲染
- [ ] 2.3 实现可配置 sink：console（默认 stderr）与 file（可选），支持分别启用/禁用并能按 `format=json|rich|plain` 切换渲染
- [ ] 2.4 在 CLI 启动路径（`src/wisp_hand/cli.py`）中最早初始化 logging，确保 runtime 与 FastMCP 都基于同一日志基线工作

## 3. stdio 安全与输出策略

- [ ] 3.1 当 `server.transport=stdio` 时，强制保证 stdout 零日志污染（console handler 必须走 stderr 或 file，即使用户误配）
- [ ] 3.2 约束 Rich 渲染的启用条件（例如非 TTY 自动降级为 plain/json），并在代码与文档中写清规则
- [ ] 3.3 确保日志系统失败不会影响工具语义（写日志异常必须降级处理，避免中断 tool call）

## 4. 结构化事件与上下文绑定

- [ ] 4.1 定义并实现运行日志的稳定字段基线（`timestamp/level/event/component` + tool/session/batch/step/latency/status/error.code）
- [ ] 4.2 将现有 `_AUDIT_CONTEXT` 与 structlog contextvars 绑定打通：进入 `_audit_context` 时自动携带字段，退出时恢复
- [ ] 4.3 实现默认脱敏/截断策略：键盘输入文本与 vision 的 `inline_image` 等大字段不记录原文，只记录长度/hash/摘要等
- [ ] 4.4 建立并落地关键事件命名集合（至少覆盖 tool call 的 ok/error/denied 三类），并确保字段符合规范

## 5. Runtime/Server 接入改造

- [ ] 5.1 重构 `AuditLogger`：保留 `audit.jsonl` 的回放/归因语义，同时将运行日志输出迁移到 structlog 管线（或由 structlog 统一生成）
- [ ] 5.2 在 `WispHandRuntime._run_tool` 中接入结构化日志：成功/拒绝/错误都写事件，并包含 `latency_ms` 与关联字段
- [ ] 5.3 补齐关键子系统事件：依赖探测、session open/close、capture、input dispatch、vision（遵守默认脱敏规则）
- [ ] 5.4 处理 FastMCP/Server 侧日志：确保其输出不会污染 stdout（stdio transport），并尽可能进入同一 sink/格式

## 6. 测试与真实环境 smoke

- [ ] 6.1 新增单元测试：`format=json` 且启用文件输出时，每行均可 JSON 解析且包含 required 字段
- [ ] 6.2 新增单元测试：`transport=stdio` 时 stdout 无日志污染，console 日志写入 stderr 或 file
- [ ] 6.3 新增单元测试：默认脱敏策略生效（`hand.keyboard.type` 文本原文与 `inline_image` base64 不出现在运行日志/审计）
- [ ] 6.4 更新/新增 `examples/attempts` 的 smoke：提供可复现命令生成日志文件并验证 stdio 安全与格式切换

