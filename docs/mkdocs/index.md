# Wisp Hand MCP

Wisp Hand 是一个面向 Hyprland/Wayland 的 computer-use MCP server 基座：它不是 agent，不做“规划与决策”，只提供可被外部 AI/客户端调用的能力（观察、截图、输入、批处理、可选本地视觉、以及 task-augmented 的长耗时执行）。

## 适合用来做什么

- 让 AI 帮你查看桌面应用的状态（例如 Godot 编辑器、浏览器、终端）
- 用截图 + diff 做 GUI 行为验证与回归（动作前后是否发生变化）
- 在明确 scope 的前提下执行输入（指针/键盘），并记录审计日志

## 关键特性

- Hyprland-first：只支持 Hyprland（不做 GNOME/KDE/通用 Wayland 兼容层）
- Scope-first：所有有副作用的输入必须绑定 session scope
- Safe-by-default：默认 `armed=false`，输入类工具会被拒绝；危险快捷键会被策略拒绝
- Mixed-scale 可用：对外输入坐标统一为 Hyprland layout/logical px，并提供截图 image px 的映射上下文
- 可观测：tool call/audit/capture/diff/latency 都可追踪（并支持 rich/structlog 输出）

## 从这里开始

- [快速开始](getting-started.md)
- [Godot 场景](scenarios/godot.md)
- [工具参考](tools.md)
- [排障](troubleshooting.md)

