## 1. Runtime Discovery 与 Preflight

- [ ] 1.1 提炼共享的 runtime discovery report，统一输出版本、config、transport、依赖、写路径、能力摘要与阻塞问题
- [ ] 1.2 扩展 `wisp-hand` CLI，新增 `doctor --json` 入口并让启动前预检复用同一套 discovery 检查
- [ ] 1.3 扩展 `hand.capabilities` 返回 live runtime 元数据，包括 `runtime_instance_id`、`started_at`、transport 与 retention 摘要
- [ ] 1.4 为 discovery 的 ready / blocked、stdio / 网络 transport 分别编写测试

## 2. Runtime Instance 与 Retention Hardening

- [ ] 2.1 为 runtime 引入进程级 `runtime_instance_id` / `started_at`，并把它接入 session 返回、audit 记录、capture metadata 与相关错误上下文
- [ ] 2.2 扩展配置 schema，加入 capture、audit、runtime log 的 retention 配置，并定义默认 beta 策略
- [ ] 2.3 实现 capture artifact retention 与启动清理，保证图片和 metadata 成对保留或删除
- [ ] 2.4 实现 audit / runtime log 的有界滚动或清理，保证长期运行下活动日志仍然可写
- [ ] 2.5 为重启后旧 session 识别、capture 被清理后的错误返回、日志/工件清理边界编写测试

## 3. 外部接入交付与验证

- [ ] 3.1 更新 README 与示例配置，明确 Python-first 的安装、`uv run` / `uvx` / `python -m wisp_hand` 启动方式，以及 `doctor` / `hand.capabilities` 的推荐接入顺序
- [ ] 3.2 补齐 stdio 与一个网络 transport 的 smoke test / 集成脚本，覆盖最小 MCP 握手与 discovery 调用
- [ ] 3.3 编写 troubleshooting 文档，覆盖配置非法、依赖缺失、写路径不可用、runtime 重启与 retention 清理后的常见排障路径
- [ ] 3.4 运行并记录 `uv run pytest -q`、OpenSpec validate 与 smoke test，确认 change 达到 beta-ready 完成定义
