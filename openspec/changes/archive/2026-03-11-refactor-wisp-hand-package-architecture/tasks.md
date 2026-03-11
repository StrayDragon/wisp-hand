## 1. 建立目标包骨架与基础设施归位

- [x] 1.1 在 `src/wisp_hand/` 下创建目标子包骨架：`app`、`protocol`、`session`、`desktop`、`capture`、`input`、`vision`、`batch`、`capabilities`、`shared`、`infra`，并补齐必要的 `__init__.py`
- [x] 1.2 将 `errors.py` 与跨域通用类型拆分到 `shared/errors.py`、`shared/types.py`，清理旧的中心化类型依赖
- [x] 1.3 将 `command.py`、`config.py`、`observability.py`、`audit.py`、`discovery.py` 迁移到 `infra/`，并修正全仓库导入路径
- [x] 1.4 调整 `__init__.py`、`__main__.py`、`cli.py` 的基础导入，使包入口继续可用但内部指向新结构
- [x] 1.5 运行基础测试，确认配置加载、错误结构和 runtime discovery 行为在基础设施迁移后保持稳定

## 2. 按能力域拆分服务与模型

- [x] 2.1 将 session 相关实现拆分为 `session/models.py`、`session/store.py`、`session/service.py`，并让 session 生命周期逻辑脱离旧顶层模块
- [x] 2.2 将 desktop 相关实现拆分为 `desktop/models.py`、`desktop/service.py`、`desktop/hyprland_adapter.py`、`desktop/scope.py`，并与 `coordinates/` 重新对齐
- [x] 2.3 将 capture 相关实现拆分为 `capture/models.py`、`capture/store.py`、`capture/diff.py`、`capture/service.py`
- [x] 2.4 将 input 相关实现拆分为 `input/models.py`、`input/backend.py`、`input/policy.py`、`input/service.py`
- [x] 2.5 将 vision、batch、capabilities 相关实现分别拆分到各自子包的 `models.py` / `service.py` / `provider.py`
- [x] 2.6 删除对旧 `wisp_hand.models` 的新增依赖，并在各子域完成模型归属迁移

## 3. 收缩 runtime 为装配层

- [x] 3.1 在 `app/runtime.py` 中重建 `WispHandRuntime`，使其只负责依赖构建、service 组装与少量跨域上下文管理
- [x] 3.2 将现有 `runtime.py` 中的 session、desktop、capture、input、vision、batch、capabilities 具体逻辑迁移到对应 service，避免继续保留超大聚合实现
- [x] 3.3 明确 service 间依赖方向，只允许通过领域模型、共享类型或显式注入交互，禁止反向依赖 `protocol/`
- [x] 3.4 运行现有 runtime 相关测试，确认 `session`、`capture`、`input`、`vision`、`batch` 的行为与重构前一致

## 4. 将 MCP 协议层拆分到 `protocol/`

- [x] 4.1 将现有 `server.py` 拆分为 `protocol/mcp_server.py`、`protocol/tool_registry.py`、`protocol/task_execution.py`、`protocol/resources.py`
- [x] 4.2 将 tool 注册逻辑改为从领域 service 读取能力，而不是直接依赖旧 runtime 大文件中的具体实现
- [x] 4.3 将 task-augmented execution 和 MCP resources 注册收口到 `protocol/`，确保领域 service 不直接依赖 FastMCP 请求上下文
- [x] 4.4 更新 `cli.py`、`mcp_app.py` 与顶层导出，使服务启动路径与 MCP 入口继续保持可用
- [x] 4.5 运行 task execution 与 server 集成测试，确认 tool 列表、structured output、task cancel/result 行为不变

## 5. 重组测试结构并完成行为回归

- [x] 5.1 将测试按 `session`、`desktop`、`capture`、`input`、`vision`、`batch`、`protocol`、`integration` 重组，避免继续围绕旧顶层大文件组织
- [x] 5.2 为拆分后的 service 层补齐单测，覆盖关键成功路径与拒绝路径
- [x] 5.3 保留并修复 CLI/MCP 端到端测试，确保外部接口契约仍由集成测试兜底
- [x] 5.4 运行完整测试集，确认现有 OpenSpec 覆盖的行为验收全部通过

## 6. 删除旧结构并完成最终验收

- [x] 6.1 删除旧的顶层平铺实现模块与旧内部导入路径，不保留兼容垫片、转发模块或双轨实现
- [x] 6.2 清理仓库中残留的旧结构引用，确保新增开发只能基于新包结构继续演进
- [x] 6.3 验证最终 `src/wisp_hand/` 目录结构与设计文档一致，包含约定的子包边界和职责划分
- [x] 6.4 进行最终验收：CLI 可启动、MCP tool 面保持稳定、现有行为测试通过、代码库只保留新结构作为唯一真相
