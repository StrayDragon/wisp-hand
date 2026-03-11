## Why

当前 `src/wisp_hand/` 已从 MVP 阶段的单模块扩张演变为平台核心，但顶层结构仍以平铺文件为主，`runtime.py`、`server.py`、`models.py` 承担了过多跨域职责，已经开始阻碍后续能力扩展、测试拆分与多人并行开发。现在进入 M6 hardening 之后、下一轮能力迭代之前，是一次性把包结构升级到长期正确形态的合适窗口。

这个 change 位于现有 MVP change 链之后，前置条件是当前 `session / observe / scoped input / batch / vision / hardening` 相关行为已经作为既有契约固定下来；它的目标不是增加新 MCP 功能，而是在不改变既有工具契约的前提下，重建 `src/wisp_hand/` 的内部模块边界，为后续 capability 扩展和测试演进提供稳定基础。

## What Changes

- 将 `src/wisp_hand/` 从顶层平铺文件重构为“能力域优先 + shared/infra 下沉”的包结构。
- 将现有 `runtime.py` 收缩为应用装配层，拆出 `session / desktop / capture / input / vision / batch / capabilities` 等独立 service。
- 将现有 `server.py` 拆分为 `protocol/` 下的 MCP server、tool registry、task execution、resource registration 等协议层模块。
- 将现有 `models.py` 拆散到各能力域 `models.py` 与 `shared/types.py`，移除单一大杂烩模型入口。
- 保留 `coordinates/` 作为独立子域，并与新的 `desktop/`、`input/` 边界重新对齐。
- 重组测试结构，使 service 级测试和协议级集成测试可以按子域拆分。
- **BREAKING**: Python 内部模块路径与包组织直接升级到新结构，不为旧 import 路径保留兼容垫片或转发模块。

边界与非目标：

- 不新增新的 MCP tool、CLI 命令或运行时 capability。
- 不改变现有 MCP tool 名称、参数语义、structured output/error 契约。
- 不引入 X11、GNOME、KDE 或通用 Wayland 兼容层，继续保持 Hyprland-first。
- 不为了降低迁移成本保留旧架构双轨实现。

完成定义：

- `src/wisp_hand/` 顶层目录完成新包结构重组。
- 各能力域具备清晰的 service / models / adapter 边界，`runtime.py` 和 `server.py` 不再承担超大聚合职责。
- 现有 OpenSpec 覆盖的 runtime 行为通过测试保持稳定。
- 新结构可以支持后续 capability 在单一子包内增量开发，而不必继续集中修改单一大文件。

后续承接：

- 该 change 完成后，后续功能提案应直接基于新的包结构继续演进，而不是在旧顶层平铺结构上追加新模块。

## Capabilities

### New Capabilities
- `runtime-package-architecture`: 定义 `src/wisp_hand/` 的目标包结构、领域服务边界、依赖方向约束与测试组织要求。

### Modified Capabilities

无。

## Impact

- 受影响代码：`src/wisp_hand/` 下的大部分运行时模块，尤其是 `runtime.py`、`server.py`、`models.py`、`hyprland.py`、`capture.py`、`input_backend.py`、`vision.py`、`session.py`、`scope.py`、`config.py`、`observability.py`、`discovery.py`、`audit.py`、`command.py`。
- 受影响测试：`tests/` 下现有 runtime、input、task、observe、vision 等测试需要随新结构重组，但必须保持行为验收不退化。
- 对外接口影响：CLI 与 MCP 接口保持稳定；内部 Python import 路径和模块布局为破坏性升级。
- 依赖与系统影响：不新增外部运行时依赖；主要影响代码组织、依赖注入方式与测试分层。
