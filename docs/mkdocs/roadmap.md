# Roadmap（摘要）

Wisp Hand 的路线是“先把低级、可验证、可安全治理的能力打牢，再逐步增强组合与智能”。

当前阶段以 OpenSpec change 链为主（见仓库 `openspec/changes/` 与 `docs/ROADMAP.md`），大体顺序是：

1. Foundation：daemon/server 骨架、session/scope/error/config/audit
2. Observe：Hyprland topology/active window/cursor/screenshot + artifact store
3. Scoped Input + Safety：pointer/keyboard、arm/disarm、dry-run、policy、emergency stop
4. Batch/Wait/Diff：减少往返、像素级 diff 做行为验证
5. Vision Assist：可选本地 Ollama 的 describe/locate
6. Hardening/Beta：日志/诊断/体积治理、对外集成契约与发布

更完整的版本在：

- `docs/ROADMAP.md`

