# Session 与 Scope

Wisp Hand 的核心安全边界是 session。所有有副作用的输入（鼠标/键盘）必须在一个 session 中执行，并且该 session 必须绑定一个明确的 scope（作用域）。

## Session 的关键字段

`wisp_hand.session.open` 返回的 session 至少包含：

- `session_id`：后续所有工具调用都要带上
- `scope`：作用域类型与目标
- `armed`：是否允许输入类工具产生副作用
- `dry_run`：是否只“演练”而不执行真实输入
- `expires_at`：过期时间（TTL）

默认行为是 safe-by-default：

- `armed=false`：你必须显式把 session arm 起来才能输入
- `dry_run` 可用于先验证坐标映射是否正确（尤其在多显示器+缩放场景）

## Scope 类型

`scope_type` 支持：

- `desktop`：整个虚拟桌面
- `monitor`：某个显示器（通过 selector 匹配 name/id/description 等）
- `window`：某个窗口（通过 selector 匹配 address/class/title/pid/workspace 等）
- `region`：一个明确矩形 `{x,y,width,height}`
- `window-follow-region`：窗口内的一个子 region（窗口移动时 region 也随之移动）

### selector 是怎么匹配的

对 `monitor/window`，`scope_target` 是一个 selector，服务端会把它与 Hyprland payload 中一组候选字段做等值匹配（例如 monitor 的 `name/id/description`，window 的 `address/class/title/pid/workspace`）。

实践建议：

- 如果你要稳定绑定一个窗口，优先使用 `address`（会话内最稳定），其次用 `class + title` 组合判断
- 如果你只是“当前前台窗口”，可以先切到目标应用，再读取一次 `active_window`（见工具参考）

## 坐标系约定

- 对外输入坐标统一使用 Hyprland 的 layout/logical px
- session 内输入坐标是 scope-relative：也就是 `(x, y)` 相对于 scope 左上角

截图返回的是 image px（实际渲染像素）。在缩放显示器下 image px 与 layout px 不同，这是正常的；Wisp Hand 会在拓扑与 capture metadata 中提供映射上下文，供上游 agent 做换算或校验。

