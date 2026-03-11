## Context

`Wisp Hand` 当前已经具备完整的 MVP 级运行时能力链：session、topology observe、capture、scoped input、batch/wait/diff、vision assist，以及 discovery / audit / retention / task-augmented execution 等 hardening 能力。外部 CLI 与 MCP 契约已经形成稳定基线，但内部包结构仍保留了 MVP 早期的顶层平铺形态。

当前主要问题集中在三个文件：

- `runtime.py` 同时承担应用装配、session 管理、desktop 查询、capture、input、vision、batch、审计上下文等职责，已经成为超大聚合点。
- `server.py` 同时承担 FastMCP 注册、structured output 转换、task-augmented execution 与 resource registration，协议细节与业务编排耦合。
- `models.py` 同时容纳 TypedDict、dataclass、Pydantic 输出模型与多个子域返回结构，导致跨能力修改时高频冲突。

与之相对，`coordinates/` 已经表现出更清晰的子域边界，这说明项目的自然演进方向不是继续扩大顶层文件，而是按能力域收敛。

这个 change 位于现有 MVP change 链之后，承接 `M6 hardening / beta-ready` 的稳定化成果，服务于下一轮 capability 扩展。上游接口边界是：

- 继续保留现有 CLI 入口与 MCP tool surface
- 继续保留 Hyprland-first、scope-first、safe-by-default、local-first 原则

下游接口边界是：

- 后续 capability 直接基于新的包结构继续迭代
- 新功能不得再把实现集中回 `runtime.py` 或顶层平铺模块

当前结构：

```text
src/wisp_hand/
  __init__.py
  __main__.py
  audit.py
  capabilities.py
  capture.py
  cli.py
  command.py
  config.py
  discovery.py
  errors.py
  hyprland.py
  input_backend.py
  mcp_app.py
  models.py
  observability.py
  policy.py
  resources.py
  runtime.py
  scope.py
  server.py
  session.py
  tooling.py
  vision.py
  coordinates/
```

目标结构：

```text
src/wisp_hand/
  __init__.py
  __main__.py
  cli.py
  tooling.py
  app/
    bootstrap.py
    runtime.py
  protocol/
    mcp_server.py
    tool_registry.py
    task_execution.py
    resources.py
  session/
    models.py
    store.py
    service.py
  desktop/
    models.py
    service.py
    hyprland_adapter.py
    scope.py
  capture/
    models.py
    store.py
    diff.py
    service.py
  input/
    models.py
    backend.py
    policy.py
    service.py
  vision/
    models.py
    provider.py
    service.py
  capabilities/
    service.py
  batch/
    models.py
    service.py
  coordinates/
    ...
  shared/
    types.py
    errors.py
  infra/
    audit.py
    command.py
    config.py
    discovery.py
    observability.py
```

## Goals / Non-Goals

**Goals:**

- 把 `src/wisp_hand/` 重构为“能力域优先 + shared/infra 下沉”的长期结构。
- 让 `runtime.py` 退化为应用装配层，由显式 service 负责能力实现。
- 把 MCP/FastMCP 细节限制在 `protocol/` 内，避免协议层污染领域实现。
- 把模型定义拆回各子域，减少跨能力开发冲突。
- 在不改变 CLI/MCP 契约的前提下，提升可测试性与并行开发效率。
- 明确包级依赖方向，防止重构后再次回到顶层大文件聚合。

**Non-Goals:**

- 不新增新 tool、新 transport、新视觉能力或新桌面后端。
- 不改变现有 tool 名称、参数、structured output 或错误码语义。
- 不引入旧模块路径兼容层、转发模块、双轨实现或阶段性过渡架构。
- 不重写 `coordinates/` 子域的核心逻辑，只做边界对齐。
- 不在本 change 内扩展 ROADMAP 的后续里程碑内容。

## Decisions

### Decision: 顶层结构采用“能力域优先 + shared/infra 下沉”

选择该结构是因为项目的主要扩展轴是 capability，而不是通用 CRUD 服务。按能力域组织可以让新增 `capture`、`input`、`vision` 等改动收敛到单一子包，明显优于纯 `api/services/adapters/models/infra` 技术分层。

备选方案：

- 保持顶层平铺，仅继续拆大文件：改动小，但无法解决跨域边界和并行开发冲突。
- 纯技术分层：依赖方向更“理论化”，但开发者在新增一个能力时需要频繁跨目录跳转，不符合当前项目的自然使用方式。
- 纯能力域：语义直观，但通用错误、配置、日志、命令执行等基础设施容易重复，因此仍需要 `shared/infra` 承接。

### Decision: `app/runtime.py` 只负责装配，不再直接承载能力实现

新的 runtime 负责：

- 创建配置、日志、命令执行、审计等基础依赖
- 组装 `SessionService`、`DesktopService`、`CaptureService`、`InputService`、`VisionService`、`BatchService`、`CapabilitiesService`
- 管理少量跨域上下文，例如 runtime instance identity

新的 runtime 不再直接实现具体能力逻辑。这样可以把行为测试下沉到 service 层，避免任何一项功能改动都触发 `runtime.py` 冲突。

备选方案：

- 保留 `WispHandRuntime` 为“大门面 + 具体逻辑”类：短期改动少，但只会延续当前复杂度。

### Decision: 协议层全部收口到 `protocol/`

`protocol/` 负责：

- FastMCP server 创建与运行
- tool schema 注册与 structured output 绑定
- task-augmented execution
- MCP resources 注册

领域 service 不直接依赖 FastMCP 运行上下文，只返回领域结果或抛出结构化错误。这样做可以把协议集成测试和 service 单测分离，避免测试总是穿透到 MCP 层。

备选方案：

- 继续在 `server.py` 内集中处理：协议细节会继续与业务行为纠缠。

### Decision: 模型按领域归属，跨域通用类型进入 `shared/types.py`

拆分原则：

- 各子域的输入/输出/result model 放入对应 `models.py`
- `JSONValue`、通用 type alias、少量稳定共享结构进入 `shared/types.py`
- `shared/errors.py` 保持统一错误模型
- 不保留旧的 `wisp_hand.models` 汇总入口

这样可以避免后续对 `vision`、`input`、`capture` 的独立演进总是碰撞同一文件。

备选方案：

- 保留中央 `models.py`：实现简单，但继续制造高频冲突。

### Decision: `coordinates/` 保持独立子域，不并入 `desktop/`

`coordinates/` 已经具备较成熟的边界：backend resolution、cache、fingerprint、models、service。它既服务于 observe，也服务于 capture 与 input。将其继续维持为独立子域，比把它吸回 `desktop/` 更稳定。

备选方案：

- 并回 `desktop/`：目录更少，但会模糊其“跨 observe/input/capture 的共享子域”定位。

### Decision: 直接升级内部模块路径，不做兼容垫片

项目约束已经明确：除非用户明确要求兼容，否则直接升级到目标写法。对本 change 来说，这意味着：

- 删除旧顶层模块，而不是保留转发壳
- 测试、导入、装配关系全部一次性迁移到新结构
- 以新目录结构作为唯一长期真相

备选方案：

- 保留旧 import 兼容层：短期迁移顺滑，但会把历史包袱长期留在仓库里，与本次 change 目标冲突。

## Risks / Trade-offs

- [大范围文件迁移会放大分支冲突] → 通过明确的迁移顺序执行：先 shared/infra，后 domain services，再 protocol，最后删除旧模块。
- [重构过程容易意外改变现有工具行为] → 以现有 OpenSpec 覆盖的行为测试作为回归基线，优先保持 CLI/MCP 契约不变。
- [模型拆分后可能出现循环依赖] → 只允许跨域共享类型进入 `shared/types.py`，禁止把领域 service 回引到 `protocol/`。
- [测试同时重组与代码迁移会增加不确定性] → 保留一层 `integration/` 风格端到端测试，先稳住外部接口，再逐步细化 service 级测试。
- [一次性移除旧路径会增加短期修改量] → 接受一次性升级成本，换取后续能力迭代的持续收益。

## Migration Plan

1. 先建立新目录骨架与包级依赖规则，把 `shared/`、`infra/`、`app/`、`protocol/`、各能力域子包放到位。
2. 迁移不带行为变化的基础模块：`errors.py`、`command.py`、`config.py`、`observability.py`、`audit.py`、`discovery.py`。
3. 按能力域拆出 service 与 models：`session`、`desktop`、`capture`、`input`、`vision`、`batch`、`capabilities`。
4. 将 `WispHandRuntime` 收缩为装配层，改为组合各 service，而不是内嵌实现。
5. 将 `server.py` 拆到 `protocol/`，完成 tool registration、task execution、resource registration 的分离。
6. 重组测试目录和测试导入路径，补齐 service 级单测与协议级集成测试。
7. 删除旧顶层模块与旧导入路径，确保仓库只保留新结构。

回滚策略：

- 该 change 在单分支内完成；若中途验证失败，回滚方式是回退整个 change，而不是保留双轨代码。

## Open Questions

- 无阻塞性开放问题。目录命名、迁移边界、兼容策略与验收目标均已确定，可直接进入实现。
