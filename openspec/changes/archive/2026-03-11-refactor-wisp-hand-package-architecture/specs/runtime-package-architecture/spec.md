# runtime-package-architecture Specification

## Purpose
定义 `src/wisp_hand/` 的目标包结构与模块边界要求，使 Wisp Hand 在保持既有 CLI/MCP 契约稳定的前提下，拥有可扩展、可测试、适合并行开发的内部架构。

## ADDED Requirements

### Requirement: 源码包必须按能力域与 shared/infra 重组

Wisp Hand 仓库 MUST 将 `src/wisp_hand/` 从顶层平铺结构升级为按能力域组织的包结构，并显式区分应用装配、协议层、领域能力、共享类型与基础设施模块。完成后的源码树 MUST 至少包含 `app`、`protocol`、`session`、`desktop`、`capture`、`input`、`vision`、`batch`、`capabilities`、`coordinates`、`shared`、`infra` 等职责明确的子包，而不是继续把主要实现集中在顶层大文件中。

#### Scenario: 顶层平铺结构被新的子包结构替代

- **WHEN** 开发者检查重构完成后的 `src/wisp_hand/`
- **THEN** 主要实现 MUST 位于职责明确的子包中
- **AND THEN** 原先承载核心能力实现的顶层平铺模块 MUST 不再作为长期实现入口继续存在

### Requirement: Runtime 必须收缩为装配层而不是能力聚合层

Wisp Hand 的 runtime 入口 MUST 负责依赖装配与 service 组合，而不是直接承载 session、desktop、capture、input、vision、batch 等能力的完整实现逻辑。

#### Scenario: Runtime 通过服务组合提供能力

- **WHEN** 开发者检查 runtime 入口的职责
- **THEN** runtime MUST 以组合多个领域 service 的方式构建系统
- **AND THEN** 新增或调整单项能力时，不需要继续把核心实现追加到单一超大 runtime 文件中

### Requirement: MCP 协议细节必须与领域实现隔离

Wisp Hand MUST 将 FastMCP server 创建、tool 注册、task-augmented execution 与 MCP resource 注册收敛到协议层模块；领域 service MUST 不直接依赖 FastMCP 请求上下文或协议注册细节。

#### Scenario: 协议层与领域层边界清晰

- **WHEN** 开发者检查 MCP tool 注册与执行逻辑
- **THEN** 相关实现 MUST 位于 `protocol` 子包中
- **AND THEN** 领域 service MUST 只暴露领域结果与结构化错误，而不是直接操作 MCP 协议对象

### Requirement: 领域模型必须按子域归属而不是集中在单一 models 文件

Wisp Hand MUST 将结果模型、TypedDict、dataclass 与输出 schema 按子域归属拆分到对应包中，并把跨域共享类型限制在 `shared` 下；仓库 MUST NOT 继续以单一 `wisp_hand.models` 作为多子域模型汇总入口。

#### Scenario: 模型修改不会集中冲突到单一文件

- **WHEN** 开发者为 `capture`、`input` 或 `vision` 任一子域新增或调整模型
- **THEN** 相关修改 MUST 收敛在对应子域包或 `shared` 包
- **AND THEN** 仓库中 MUST 不存在继续承担多子域模型汇总职责的单一中心模型文件

### Requirement: 外部接口在重构后必须保持行为稳定

在完成包结构重构后，Wisp Hand MUST 继续保留现有 CLI 命令、MCP tool 名称、参数语义、structured output/error 契约与 Hyprland-first 运行边界；本 change MUST NOT 借重构引入新的外部 capability 或破坏既有工具行为。

#### Scenario: 既有 CLI 与 MCP 契约保持不变

- **WHEN** 客户端或测试在重构后继续调用现有 CLI 命令与 MCP tools
- **THEN** 返回的能力面、参数契约与关键错误语义 MUST 与重构前保持一致

### Requirement: 内部模块升级必须直接切换到新路径

Wisp Hand MUST 直接迁移到新的内部包路径与目录组织，不得为了过渡而保留旧模块路径的兼容垫片、转发模块或双轨实现。

#### Scenario: 仓库只保留新结构作为唯一真相

- **WHEN** 开发者检查重构完成后的代码库
- **THEN** 旧顶层模块路径 MUST 已被移除或彻底迁出实现路径
- **AND THEN** 仓库 MUST 只保留新包结构作为后续开发基线

### Requirement: 测试组织必须能够按子域与协议层独立演进

Wisp Hand MUST 让测试可以按领域 service 与协议集成分层组织，既保留覆盖 CLI/MCP 外部行为的集成测试，也允许按 `session`、`desktop`、`capture`、`input`、`vision`、`batch` 等子域独立验证行为。

#### Scenario: 测试可同时覆盖服务级与协议级验收

- **WHEN** 开发者检查重构后的测试组织与验收路径
- **THEN** 仓库 MUST 同时具备验证 service 级行为的测试入口与验证 CLI/MCP 外部接口稳定性的集成测试入口
