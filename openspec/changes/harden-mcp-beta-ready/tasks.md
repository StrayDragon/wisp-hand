## 0. 分发与 CLI（`uvx wisp-hand-mcp`）

- [ ] 0.1 将 Python distribution 名称调整为 `wisp-hand-mcp`，并提供 `wisp-hand-mcp` console script（不保留 `wisp-hand` 旧命令）
- [ ] 0.2 更新 CLI `prog`/帮助文本与文档示例，使 `uvx wisp-hand-mcp` 成为默认分发与使用方式；保留 `python -m wisp_hand` 作为调试入口

## 1. Tool 命名空间收敛（`hand.*` -> `wisp_hand.*`）

- [ ] 1.1 将所有 MCP tools 从 `hand.*` 全量重命名为 `wisp_hand.*`（server 注册名、implemented_tools、文档与示例全部同步）
- [ ] 1.2 更新测试用例中所有 tool name 断言与调用路径，确保 `uv run pytest -q` 通过
- [ ] 1.3 更新 OpenSpec specs（含本 change 与共享 specs）中出现的 `hand.*` 为 `wisp_hand.*`，保持契约一致
- [ ] 1.4 更新审计输出中的 `tool_name` 与相关字段，确保输出面向外部接入方时不再出现旧前缀

## 2. Runtime Discovery 与 Preflight

- [ ] 2.1 提炼共享的 runtime discovery report，统一输出版本、config、transport、依赖、写路径、能力摘要与阻塞问题
- [ ] 2.2 扩展 `wisp-hand-mcp` CLI，新增 `doctor --json` 入口并让启动前预检复用同一套 discovery 检查
- [ ] 2.3 扩展 `wisp_hand.capabilities` 返回 live runtime 元数据，包括 `version`、`runtime_instance_id`、`started_at`、transport 与 retention 摘要
- [ ] 2.4 为 discovery 的 ready / blocked、stdio / 网络 transport 分别编写测试

## 3. MCP Task-Augmented Execution（长耗时 tools/call）

- [ ] 3.1 启用底层 lowlevel server 的 experimental tasks（注册 `tasks/get`、`tasks/result`、`tasks/list`、`tasks/cancel`，并宣告 tasks capability）
- [ ] 3.2 实现 task-aware 的 `tools/call` 路径：当请求携带 `task` 元数据时返回 `CreateTaskResult`，并在后台执行原工具逻辑，最终产出 `CallToolResult`
- [ ] 3.3 在后台执行中写入最小 task 状态信息（`statusMessage`），至少覆盖 started / running tool / done / error
- [ ] 3.4 为 batch/vision 等可长耗时工具补齐“不会卡死”的默认超时与可取消边界（允许 best-effort，不要求抢占式中止）
- [ ] 3.5 新增集成测试：使用 `mcp.client` 以 stdio transport 启动 server，调用 `session.experimental.call_tool_as_task(...)` 并通过 `tasks/get`/`tasks/result` 验证结果与错误路径

## 4. Runtime Instance 与 Retention Hardening

- [ ] 4.1 为 runtime 引入进程级 `runtime_instance_id` / `started_at`，并把它接入 session 返回、audit 记录、capture metadata 与相关错误上下文
- [ ] 4.2 扩展配置 schema，加入 capture、audit、runtime log 的 retention 配置，并定义默认 beta 策略
- [ ] 4.3 实现 capture artifact retention 与启动清理，保证图片和 metadata 成对保留或删除
- [ ] 4.4 实现 audit / runtime log 的有界滚动或清理，保证长期运行下活动日志仍然可写
- [ ] 4.5 为重启后旧 session 识别、capture 被清理后的错误返回、日志/工件清理边界编写测试

## 5. 外部接入交付与验证

- [ ] 5.1 更新 README 与示例配置，明确 Python-first 的安装、`uv run` / `uvx wisp-hand-mcp` / `python -m wisp_hand` 启动方式，以及 `doctor` / `wisp_hand.capabilities` 的推荐接入顺序
- [ ] 5.2 补齐任务模式接入指南：如何以 task 方式调用工具、如何轮询与取消、以及推荐的超时与 pollInterval 策略
- [ ] 5.3 补齐 stdio 与一个网络 transport 的 smoke test / 集成脚本，覆盖最小 MCP 握手、discovery 调用与 task-augmented 调用
- [ ] 5.4 编写 troubleshooting 文档，覆盖配置非法、依赖缺失、写路径不可用、runtime 重启、retention 清理与 task 轮询的常见排障路径
- [ ] 5.5 运行并记录 `uv run pytest -q`、OpenSpec validate 与 smoke test，确认 change 达到 beta-ready 完成定义
