# runtime-operations-hardening Specification

## Purpose
定义 runtime 的运维硬化与长期运行治理要求，包括运行实例标识、capture artifacts 留存清理、审计与运行日志有界滚动等，保证外部接入下可诊断、可治理、可持续写入。

## Requirements
### Requirement: 运行实例标识必须贯穿运维工件与重启诊断

Wisp Hand MUST 为每次 runtime 启动生成唯一的 `runtime_instance_id`，并把该标识写入关键运维工件与相关返回上下文，包括 session 创建结果、audit 记录、capture metadata，以及与实例失配有关的结构化错误。

#### Scenario: 同一实例下的工件共享同一标识

- **WHEN** 客户端在同一个运行中的 Wisp Hand 实例上依次打开 session、执行 capture 并查看对应 audit 记录
- **THEN** 这些结果中的 `runtime_instance_id` MUST 一致，以便外部接入方做关联排障

#### Scenario: 重启后旧 session 失效可被明确识别

- **WHEN** 客户端在 runtime 重启后继续使用上一个实例创建的 `session_id`
- **THEN** 服务 MUST 返回结构化错误，并在错误上下文中包含当前 `runtime_instance_id`，使客户端能够判断失败与实例切换有关

### Requirement: capture artifact 必须受显式 retention 治理

Wisp Hand MUST 对 capture artifact 执行显式 retention 策略，并在启动时与新 capture 写入后执行清理。清理过程 MUST 保证图片文件与 metadata 成对存在或成对删除，不得暴露半写入或半删除状态。

#### Scenario: 超出预算时清理最旧 capture

- **WHEN** capture artifact 总体积或保留时长超过配置的 retention 预算
- **THEN** 服务 MUST 清理最旧且超出预算的 capture，直到 store 回到配置范围内

#### Scenario: 已被清理的 capture 会返回结构化缺失错误

- **WHEN** 客户端继续引用一个已被 retention 清理的 `capture_id`
- **THEN** 服务 MUST 返回结构化缺失工件错误，而不是崩溃、挂起或读取到不完整文件

### Requirement: audit 与 runtime log 必须在长期运行中保持有界

Wisp Hand MUST 对 audit 日志与 runtime log 执行有界 retention，使活动日志文件在长期运行和重复调用下仍然可写，并且旧日志按照配置被滚动或清理。

#### Scenario: 活动日志达到上限后仍可继续写入

- **WHEN** audit 日志或 runtime log 达到配置的保留上限
- **THEN** 服务 MUST 对旧日志执行滚动或清理，并继续把新记录写入活动日志文件

#### Scenario: 启动时会先整理超预算日志

- **WHEN** 服务启动时发现已存在的 audit 日志或 runtime log 超出 retention 预算
- **THEN** 服务 MUST 在进入正常服务前先完成必要的整理，使日志目录回到配置范围内

