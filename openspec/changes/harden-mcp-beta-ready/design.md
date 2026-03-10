## Context

到 `add-ollama-vision-assist` 为止，Wisp Hand 已经具备完整的 Hyprland-first MVP 能力面：基础 runtime、只读 observe、scope 内输入、batch/wait/diff、可选 vision 都已经存在，且本地测试通过。当前缺口不在“再加一个工具”，而在“让外部 agent / client 可以稳定安装、启动、发现、诊断并长期运行”。

现在的运行面仍有几个 beta 阻塞项：

- `wisp-hand` CLI 只有直接启动入口，没有在连接前完成配置、依赖、写路径与 transport 预检的标准路径。
- `wisp_hand.capabilities`（原 `hand.capabilities`）只能返回基础依赖矩阵，缺少版本、运行实例、transport、保留策略与写路径状态等接入方真正需要的运行元数据。
- audit、runtime log 与 capture artifact 会持续增长，但当前没有明确的 retention 与清理边界。
- session 在进程重启后天然失效，但客户端缺少稳定的实例识别字段来判断“是拿错了 session，还是 runtime 已经重启”。
- README / 配置模板 / smoke test / troubleshooting 还不足以支撑“安装后无需手工猜测依赖”的 beta 交付标准。
- MCP tool 调用目前只能“同步返回结果”，对于 batch、vision、真实环境输入等长耗时调用，缺少标准的 task-augmented 执行与轮询/取消路径，外部接入容易卡死或超时。

这个 change 位于现有 MVP change 链之后，对上游只承接 M1-M5 已交付的工具面，不改写它们的功能边界；对下游则为 beta 发布与后续 v1.1 maintenance change 提供稳定的外部接入基线。项目定位保持不变：Wisp Hand 是给外部 agent 提供能力的 MCP server，不内置 agent loop。

## Goals / Non-Goals

**Goals:**

- 建立统一的 runtime discovery / preflight 契约，让外部接入方在连接前和连接后都能拿到稳定、机器可读的运行信息。
- 为每个运行中的 Wisp Hand 进程引入显式 `runtime_instance_id`，让重启、长会话失效与运维排障可被外部客户端识别。
- 为 audit、runtime log 与 capture artifact 引入明确的 retention 和清理策略，避免 beta 运行期间状态目录无限膨胀。
- 为长耗时 tool 调用接入 MCP task-augmented execution：支持以 task 方式调用 `tools/call`，并提供 `tasks/get` / `tasks/result` / `tasks/list` / `tasks/cancel` 的标准轮询与取消能力。
- 收敛 tool 命名空间：统一使用 `wisp_hand.*` 前缀，确保在多 server 环境下清晰且不易冲突。
- 补齐 Python-first 的安装/启动说明、配置模板、stdio/网络 transport smoke test 与 troubleshooting 文档，使外部 agent / client 可以直接接入。

**Non-Goals:**

- 不新增任何 observe / input / batch / vision 桌面动作原语。
- 不实现内置 agent loop、任务规划器或自动重试编排。
- 不做 X11、GNOME、KDE 或通用 Wayland 兼容层，仍然只对齐 Hyprland-first。
- 不为了平滑过渡保留旧配置路径、旧字段别名、旧 tool 前缀或双轨 discovery 接口；直接升级到新的运行契约。

## Decisions

### 1. 采用“连接前 doctor + 连接后 capabilities”的双入口 discovery

本 change 会引入一个共享的 runtime discovery report 生成层，并暴露两个入口：

- `wisp-hand doctor --json`：用于连接前预检，覆盖配置加载、transport 选择、依赖探测、关键路径可写性、启用能力与阻塞项。
- `wisp_hand.capabilities`：用于已连接客户端获取 live runtime 视角，在基础能力矩阵之上追加版本、`runtime_instance_id`、`started_at`、transport、保留策略摘要与其他运行元数据。

这样可以让“是否可启动”和“当前这个已启动实例是谁”分别有稳定入口，同时避免 CLI 与 MCP tool 各自维护一套不同的探测逻辑。

备选方案是只扩展 `wisp_hand.capabilities`。放弃原因是外部客户端在握手前就需要知道依赖和配置是否可用，仅靠 MCP tool 无法覆盖连接前自检。

### 2. `runtime_instance_id` 作为进程级主标识传播到所有关键工件

每次 runtime 启动都生成新的 `runtime_instance_id` 与 `started_at`。这两个字段会进入：

- `wisp_hand.capabilities`
- `wisp_hand.session.open` 返回结果
- audit 记录
- capture metadata
- 与当前实例相关的结构化错误上下文

这样外部客户端可以缓存当前实例标识，在 session 失效、capture 被清理或服务被重启后快速判断根因，而不是把所有失败都当成同一种 `not_found`。

备选方案是使用 PID 或持久化计数器。放弃原因是 PID 不具备稳定的跨环境语义，而持久化计数器会引入额外锁与状态文件复杂度，超出当前 change 价值。

### 3. retention 按工件类型拆分治理，而不是继续依赖单一无限增长文件

这个 change 不把“清理”留给外部 shell 脚本或宿主机 logrotate，而是在 runtime 内显式治理：

- capture artifact：按年龄与总字节预算清理，删除时必须保证图片与 metadata 成对移除。
- audit / runtime log：按大小滚动并限制保留份数，保证活动文件始终可追加且体积可控。

清理在启动时执行一次，在新 capture 或新日志写入后按需增量执行。保留策略摘要会进入 discovery 输出，方便接入方知道 artifact 的可用窗口不是无限期的。

备选方案是继续使用单一 `audit.jsonl` 和 `runtime.log` 不设上限，或完全依赖外部系统清理。放弃原因是这会把 beta 发布的可运维性前提转嫁给宿主机环境，与“安装后可直接接入”的目标冲突。

### 4. 重启与清理场景坚持显式失败，不做隐式恢复

对于已经失效的 session、已被 retention 清理的 capture、或当前实例已重启的场景，服务会返回结构化错误，并在上下文中附带足够的实例与工件信息让客户端决定是否重建 session / recapture。服务不会自动重建 session、偷偷保活旧引用，也不会在后台伪造缺失工件。

这保持了 scope-first 与 deterministic-first：客户端始终知道自己操作的是哪一个 runtime、哪一个 session、哪一个 capture，而不是依赖服务端做带副作用的猜测恢复。

### 5. beta 交付继续走 Python-first 路径，并把 transport 矩阵纳入 smoke gate

本 change 仍然以 Python 包与 `wisp-hand` console script 为标准交付形式，文档同时覆盖 `uv run` / `uvx` / `python -m wisp_hand` 的推荐启动方式。网络 transport 仍只覆盖当前 runtime 已支持的模式，不新增独立 sidecar。

beta smoke gate 至少包含：

- `wisp-hand doctor --json`
- `stdio` 启动与最小 MCP 调用
- 一个网络 transport 的启动与最小 MCP 调用

备选方案是同时引入系统包、容器镜像或 Rust sidecar。放弃原因是当前目标是先把外部 MCP 集成契约打磨稳定；更重的分发形态和 `pyo3` 优化留到后续阶段。

## Risks / Trade-offs

- richer discovery 字段会诱导客户端依赖非核心元数据 → 通过文档明确稳定字段，并保持错误码与关键标识的一致性。
- retention 可能删除客户端仍想复用的 capture → 通过 discovery 暴露保留策略，并在缺失时返回结构化错误而不是静默失败。
- `doctor` 与运行时 discovery 可能出现逻辑漂移 → 通过共享 report builder 与同一套检查函数降低分叉风险。
- 网络 transport smoke test 在 CI 或本地可能更容易受端口/环境波动影响 → 使用临时端口、严格超时与最小握手路径来控制不稳定性。

### 6. 使用 MCP task-augmented execution 处理长耗时 tools/call

本 change 会把 “长耗时 tool call” 的稳定集成方式收敛到 MCP task-augmented execution：

- 客户端在 `tools/call` 的 params 中携带 `task` 元数据（例如 TTL），服务端立即返回 `CreateTaskResult`。
- 客户端随后通过 `tasks/get` 轮询状态，通过 `tasks/result` 获取最终 `CallToolResult`。
- 对于可以被用户中止的场景，客户端可调用 `tasks/cancel` 请求取消；服务端应在可行处尽快停止并把 task 标记为 `cancelled` 或 `failed`（以错误上下文说明取消时机）。

实现策略（可落地）：

- 继续以 FastMCP 作为工具注册与 schema 生成层，但启用底层 lowlevel server 的 experimental tasks 支持（`server.experimental.enable_tasks()`），以获得标准的 `tasks/*` handler 与 capability 宣告。
- 在 server 的 `call_tool` 路径做一次“task-aware 包装”：
  - 当当前请求是 task-augmented（`request_context.experimental.is_task == true`）时，不直接同步执行工具，而是调用 `request_context.experimental.run_task(work)` 创建 task，并在后台执行 `work`。
  - `work` 内部调用既有工具执行逻辑（与同步模式同源），并在关键阶段更新 task 的 `statusMessage`（例如 “running <tool>”, “capture…”, “vision…”, “done”）。
  - 若工具执行抛出结构化错误，`work` 将其转换为 `CallToolResult(isError=true)` 作为 task 结果，以保持外部接入方的一致错误处理方式。

### 7. 收敛 MCP tool 命名空间前缀为 `wisp_hand.*`

当前 `hand.*` 前缀过于通用且语义不清晰；在 beta 交付前应收敛为项目级命名空间，避免多 server 环境下冲突，并提升可读性。该收敛包括：

- 将所有工具从 `hand.*` 重命名为 `wisp_hand.*`（例如 `wisp_hand.capture.screen`）。
- 不保留旧前缀兼容层；文档与示例同步更新为新前缀。
- 对外可见的错误上下文、审计字段、capabilities 中的 `implemented_tools` 列表统一为新前缀。

## Migration Plan

这是一次 beta-ready hardening，会引入 tool 前缀重命名与 tasks 能力增强，但不引入兼容层。迁移方式是：

1. 扩展配置 schema，新增 retention 与 discovery 相关配置，默认值直接对齐 beta 目标。
2. 更新默认配置模板与 README，统一外部接入方的安装/启动路径。
3. 将 MCP tool 前缀从 `hand.*` 全量升级为 `wisp_hand.*`，并同步更新 tests、示例脚本与文档（不保留旧前缀）。
4. 启用 tasks 支持并补齐 “tools/call as task” 的集成与测试，确保长耗时调用具备轮询/取消路径。
5. 为外部客户端文档明确新的 discovery 契约：连接前用 `wisp-hand doctor --json`，连接后用 `wisp_hand.capabilities` 读取 live runtime 元数据。
6. 以 `uv run pytest`、OpenSpec validate 与 transport smoke test 作为发布前校验。

如果实现过程中发现 hardening 变更影响启动稳定性，回滚策略就是回退到上一个发布版本；本 change 不引入不可逆的数据迁移。

## Open Questions

- 当前 beta smoke matrix 中，网络 transport 默认应以 `sse` 还是 `streamable-http` 作为主验证目标，需要在实现时根据 `mcp[cli]` 的实际支持稳定性最终锁定。
- runtime log 是否除了大小滚动外还需要额外的按时间保留策略，如果实现复杂度过高，可以先只对 capture 与 audit 做强约束，再把 runtime log 的细化治理留到后续 maintenance change。
