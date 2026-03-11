# 场景：让 AI 观察与操作 Godot

目标：接入 Wisp Hand MCP 后，让外部 AI 能够查看 Godot 编辑器、点击运行项目、并用截图/diff 做最小行为验证。

Wisp Hand 不负责“如何操作 Godot 才正确”的规划，它只提供可验证、可追踪的基础动作原语。推荐把 Godot 场景拆成下面的闭环：

1. 找到 Godot 窗口（或游戏窗口）的 selector
2. 在 window scope 内截图观察
3. 在明确 `armed=true` 的 session 内执行输入
4. 用 `capture.diff` 判断动作是否生效

## 0) Preflight

```bash
uvx wisp-hand-mcp doctor --json | jq .
```

确保：

- `hyprland_detected=true`
- `capture_available=true`
- `input_available=true`

## 1) 获取 Godot 窗口 selector

推荐做法：

1. 手动把 Godot 切到前台（确保它是 active window）
2. 调用 `wisp_hand.desktop.get_active_window`，读取 `address/class/title`
3. 用其中一个作为后续 `scope_target`

实践建议：

- 优先使用 `address`（通常最稳定）
- 如果你需要跨启动定位窗口，可用 `class + title` 做匹配，但要接受 title 变化的可能
- 只有在诊断/排障时才用 `wisp_hand.desktop.get_topology(detail=full|raw)`（它更重，不建议高频调用）

## 2) 打开 window scope session（先 dry-run）

先用 `dry_run=true` 校验坐标映射与点击位置（尤其多显示器 + 缩放）：

工具调用（示意）：

- `wisp_hand.session.open`
  - `scope_type`: `window`
  - `scope_target`: `<address 或其他 selector>`
  - `armed`: `true`
  - `dry_run`: `true`

然后：

- `wisp_hand.capture.screen(target="scope")` 获取一张 scope 截图

如果你发现 click 会偏移，先看 [坐标与缩放](../concepts/coordinates.md) 的诊断流程。

必要时可以先调用 `wisp_hand.desktop.get_monitors` 获取 mixed-scale 映射上下文，用于解释多显示器 + 缩放导致的坐标差异。

## 3) 定位并点击 “Run/Play”

有两种路线：

### 路线 A：无视觉（手工坐标）

你可以先在截图上确定按钮位置（scope-relative layout px），然后让 AI 调 `pointer.click(x,y)`。

### 路线 B：本地视觉辅助（推荐）

如果启用了 Ollama 视觉：

1. `capture.screen` 拿到 `capture_id`
2. `vision.locate(capture_id, target="Run button")` 得到候选框
3. 取候选框中心点作为点击坐标（scope-relative）

注意：视觉只给候选，最终输入仍要走 scope + policy。

如果你的外部 AI 需要“看见截图内容”但不想依赖本地路径：

- 从 `capture.screen` 的 `image_uri` / `metadata_uri` 得到资源 URI
- 用 MCP `resources/read` 读取 png 与 metadata（按需拉取，避免默认把大内容塞进 tool result）

## 4) 等待并做截图验证

最小验证建议用 `capture.diff`：

1. 动作前 `capture.screen`（记为 A）
2. 点击运行
3. `wait(duration_ms=...)`（例如 300~1500ms，取决于你的机器）
4. 动作后 `capture.screen`（记为 B）
5. `capture.diff(A, B)`：若 `changed=true` 且 `change_ratio` 超过你设置的阈值，则认为 UI 有变化

如果你想把“动作 + 等待 + 截图”变成一次调用，使用 `wisp_hand.batch.run`：

- steps: `click -> wait -> capture`
- 默认 `return_mode=summary` 会裁剪逐步输出；排障时可用 `return_mode=full`

## 5) 游戏窗口（新窗口/全屏）怎么处理

很多项目运行后会出现新的游戏窗口，或者 Godot 进入全屏。

处理方式：

1. 再次读取 `active_window`（切到游戏窗口后）
2. 用新的 selector 打开新的 window scope session
3. 后续验证与输入都在新的 session 内进行

## 6) 推荐的 agent 调用策略（token/延迟）

- `desktop.get_active_window/get_monitors/list_windows` 优先用于“选择 scope/窗口”，避免高频拉全量 topology。
- `desktop.get_topology` 不要高频轮询：它是诊断工具（必要时再用 `detail=full/raw`）。
- 高频状态判断优先用：`capture.screen` + `capture.diff`（更稳定、可验证、也更契合 GUI 回归）。
- 需要减少往返时，用：`batch.run` 把多步动作串起来。
