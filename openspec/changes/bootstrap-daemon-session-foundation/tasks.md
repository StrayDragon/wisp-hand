## 1. Runtime 入口与基础工具

- [ ] 1.1 建立 daemon / MCP server 的启动入口与模块边界
- [ ] 1.2 注册 `hand.capabilities`、`hand.session.open`、`hand.session.close` 的基础 tool surface

## 2. Session 与 Scope 模型

- [ ] 2.1 实现 session store、TTL 过期、close/expire 状态机
- [ ] 2.2 定义标准化 scope envelope，并让 session open/close 全部经过统一校验

## 3. 配置、错误与审计

- [ ] 3.1 实现运行时配置加载、默认值合并与非法配置诊断
- [ ] 3.2 定义结构化错误码 taxonomy 与 MCP 错误映射
- [ ] 3.3 实现文本日志与 JSONL 审计日志写入管线

## 4. 验证

- [ ] 4.1 为 capabilities、自检降级、session 生命周期与配置错误编写测试
- [ ] 4.2 验证审计日志字段完整、TTL 过期生效且错误码稳定
