## Context

observe change 已经把 topology、cursor 与 capture 建好，系统现在具备可靠的只读上下文。下一步是把副作用能力接上，但如果只交付 pointer/keyboard 而不同时交付 arming、dry-run 与 emergency stop，MVP 的安全边界会直接失效。

因此本 change 把输入执行和安全治理绑定为同一个交付单元。只有这两层一起成立，scope-first 与 safe-by-default 才不是口号。

## Goals / Non-Goals

**Goals:**

- 提供 scope 内 pointer / keyboard 输入工具。
- 固定 scope-relative 坐标到桌面绝对坐标的映射链路。
- 让所有副作用动作统一经过 armed、dry-run、policy 与审计护栏。
- 为后续 batch 和视觉辅助点击提供稳定输入面。

**Non-Goals:**

- 不实现 batch orchestration、wait 或 capture diff。
- 不实现视觉模型推理或 locate-to-click 组合闭环。
- 不为非 Hyprland 路径设计兼容输入后端。

## Decisions

### 1. 输入工具只接受 session 语义，不重复传 scope

所有输入工具都以 `session_id` 为唯一上下文入口，从 session 中读取标准化 scope 和安全状态，不再接受一套独立的临时 scope 参数。这样可以避免一次调用里出现“session scope”和“请求参数 scope”相互冲突。

### 2. 安全护栏按固定顺序执行

输入前的判定顺序固定为：

1. session 查询
2. armed 校验
3. dry-run 标记
4. emergency stop
5. rate limit / policy deny
6. scope 边界校验
7. 输入 dispatch
8. 审计落盘

这样每次拒绝都有唯一的责任层，不会出现相同请求在不同顺序下得到不同错误。

### 3. Pointer 与 keyboard 共用一套输入调度与审计模型

虽然 pointer 与 keyboard 的底层实现可能不同，但它们在运行时上共享：

- session 解析
- 安全护栏
- 结果模型
- 审计字段

后续 batch change 只需要组合这套公共输入面，而不需要再区分不同动作族的调用协议。

### 4. 风险较高的动作由策略层统一拒绝

例如危险快捷键、高频连点、越界拖拽等动作，不在具体 tool 内写分散的特殊判断，而是由统一策略层产出 `policy_denied`。这样未来若要加入更细粒度确认机制，也只需要扩展策略层。

## Risks / Trade-offs

- 输入后端是 Wayland/Hyprland 最不稳定的部分 -> 通过先固定公共输入协议，再替换底层 dispatch 实现，降低返工面。
- Dry-run 需要在“看起来执行了”和“实际不 dispatch”之间取得平衡 -> 通过统一模拟结果与审计字段保持可预测性。
- Emergency stop 会引入全局锁存状态 -> 需要在实现中明确复位方式和并发访问语义，避免误锁死。
