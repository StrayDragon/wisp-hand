# Wisp Hand Roadmap

- Status: Draft
- Date: 2026-03-09
- Target: Hyprland-first computer-use MCP

## 1. Roadmap 原则

1. 先做 Hyprland，不做跨桌面兼容。
2. 先做基础能力稳定，再做智能增强。
3. 先把安全与作用域打牢，再放开更复杂动作。
4. 先低级、可验证工具，再逐步增加组合能力。

## 2. 里程碑总览

### 当前 OpenSpec change 链

- `bootstrap-daemon-session-foundation` 对应 `M1`
- `add-hyprland-observe-capture` 对应 `M2`
- `add-scoped-input-safety` 对应 `M3`
- `add-batch-wait-diff` 对应 `M4`
- `add-ollama-vision-assist` 对应 `M5`
- `M6` 的 hardening / beta-ready 仍保留为下一轮独立提案

### M0: 产品与技术验证

目标：

- 锁定 v1 架构边界
- 确认 Hyprland 可行的截图、拓扑、输入路径

输出：

- OpenSpec MVP change 链
- ROADMAP
- 技术 spike 结论
- 最小依赖清单

完成标志：

- 明确采用 Hyprland-first
- 明确 scope 模型
- 明确 vision 采用 Ollama 可选模式

### M1: Core Foundation

目标：

- 建立服务骨架与核心域模型

范围：

- session model
- scope model
- topology model
- error model
- config loader
- audit logger

输出：

- 可运行的基础 daemon 骨架
- MCP server 骨架
- 配置文件与日志目录约定

验收：

- 服务可启动
- 可读取配置
- 可返回 `capabilities`
- 可创建/销毁 session

### M2: Hyprland Observe MVP

目标：

- 完成只读能力链路

范围：

- monitors/workspaces/windows 查询
- active window 查询
- cursor position 查询
- full/monitor/window/region screenshot
- capture artifact store

输出：

- `hand.desktop.get_topology`
- `hand.cursor.get_position`
- `hand.capture.screen`

验收：

- Hyprland 拓扑信息正确
- 多显示器下截图结果与作用域一致
- 截图 artifact 可复用

### M3: Scoped Input MVP

目标：

- 完成作用域内输入控制

范围：

- pointer move/click/double/right/drag/scroll
- keyboard type/press
- arm/disarm
- dry-run
- scope boundary enforcement
- emergency stop

输出：

- `hand.pointer.*`
- `hand.keyboard.*`
- `hand.session.open/close`

验收：

- 作用域内动作稳定执行
- 越界动作被拒绝
- 未 armed 会话无法产生副作用
- emergency stop 生效

### M4: Batch + Wait + Diff

目标：

- 让 agent 能减少往返，提高闭环可靠性

范围：

- `hand.batch.run`
- `hand.wait`
- `hand.capture.diff`
- before/after capture hooks

输出：

- 批处理动作
- 基础状态等待
- 像素级 diff

验收：

- 三步以上动作可单次调用完成
- 错误时可精确定位失败步骤
- diff 能支撑“界面是否发生变化”的判断

### M5: Ollama Vision Integration

目标：

- 补上本地视觉辅助链路

范围：

- Ollama provider
- image pre-processing
- describe / locate / compare prompts
- timeouts / retries / concurrency control

输出：

- `hand.vision.describe`
- `hand.vision.locate`

验收：

- 在本地 Ollama 存在时可正常工作
- 未启用视觉时工具明确返回不可用
- 单次视觉任务可追踪模型、耗时、输入来源

### M6: Hardening and Beta

目标：

- 提升稳定性、可调试性、交付质量

范围：

- structured logging
- replayable audit trail
- failure recovery
- packaging
- docs
- integration tests

输出：

- Beta 版本
- 安装文档
- 故障排查文档

验收：

- 常见失败场景有明确错误信息
- 可复现实验路径清晰
- 安装后无需手工猜测依赖

## 3. 建议时间规划

在单人开发前提下，建议按 10 到 12 周推进。

### 第 1 周

- M0 完成

### 第 2-3 周

- M1 完成

### 第 4-5 周

- M2 完成

### 第 6-7 周

- M3 完成

### 第 8 周

- M4 完成

### 第 9-10 周

- M5 完成

### 第 11-12 周

- M6 完成并进入 Beta

## 4. 每阶段测试重点

### M1

- 配置加载
- session 生命周期
- scope 序列化
- 错误码一致性

### M2

- 多显示器坐标映射
- region/window capture 裁剪精度
- active window 变化
- artifact store 清理

### M3

- move/click/drag/scroll 稳定性
- 键盘组合键
- scope 越界拒绝
- emergency stop
- dry-run 不落副作用

### M4

- batch fail-fast
- wait 超时
- diff 阈值误报/漏报

### M5

- Ollama 不可用时降级
- 大图缩放
- vision timeout
- 并发请求控制

### M6

- 重启恢复
- 高并发 tool call
- 长时间会话
- 日志与 captures 体积增长

## 5. 关键依赖

v1 建议依赖：

- Hyprland
- `hyprctl`
- `grim`
- `slurp`
- Ollama（可选）

原型阶段可接受的临时依赖：

- `wtype`

## 6. 风险分解与缓解

### 风险 A：输入注入路径不稳定

缓解：

- 在 M0/M1 就完成最小 spike
- 尽早验证 move/click/drag/keyboard 四类动作

### 风险 B：坐标漂移

缓解：

- 强制所有动作走 scope 坐标
- 引入截图坐标与桌面坐标映射测试

### 风险 C：视觉延迟过高

缓解：

- 将 vision 保持为可选链路
- 允许完全关闭
- 加入 downscale 和超时策略

### 风险 D：安全性不足

缓解：

- 默认 disarmed
- 强制 session
- 强制 scope
- 强制审计日志

## 7. v1 发布门槛

只有同时满足以下条件才进入 v1：

1. Hyprland 下核心 MCP 工具稳定可用。
2. 截图、点击、拖拽、输入、滚动在作用域内可重复执行。
3. 安全链路完整，包括 arming、dry-run、emergency stop、日志。
4. 可选 Ollama 视觉能力可正常启停。
5. 文档齐全，外部 agent 可以直接接入。

## 8. v1 后续方向

### v1.1

- overlay
- wait for change
- screenshot compare summary
- window-follow-region

### v1.2

- 更细粒度策略引擎
- 危险快捷键确认
- action replay / debug trace

### v2

- wlroots 泛化
- portal 模式
- 更多视觉模型后端

## 9. 引用与里程碑依据

以下引用于 2026-03-09 核对。ROADMAP 中每个阶段的里程碑都以这些资料为输入边界，而不是凭空拆分。

### 9.1 内部参考

- `RM-INT-01` `wayland-mcp` README 与 MCP 工具实现:
  [source_ref/someaka.wayland-mcp/README.md](source_ref/someaka.wayland-mcp/README.md),
  [source_ref/someaka.wayland-mcp/wayland_mcp/server_mcp.py](source_ref/someaka.wayland-mcp/wayland_mcp/server_mcp.py)
- `RM-INT-02` `ui-act` README 与 agent loop:
  [source_ref/TobiasNorlund.ui-act/README.md](source_ref/TobiasNorlund.ui-act/README.md),
  [source_ref/TobiasNorlund.ui-act/ui_act/src/agent.rs](source_ref/TobiasNorlund.ui-act/ui_act/src/agent.rs)
- `RM-INT-03` `ui-act` 环境抽象:
  [source_ref/TobiasNorlund.ui-act/ui_act/src/env/full_desktop.rs](source_ref/TobiasNorlund.ui-act/ui_act/src/env/full_desktop.rs),
  [source_ref/TobiasNorlund.ui-act/ui_act/src/env/single_window.rs](source_ref/TobiasNorlund.ui-act/ui_act/src/env/single_window.rs)
- `RM-INT-04` `Wayland-automation` README 与底层模块:
  [source_ref/OTAKUWeBer.Wayland-automation/README.md](source_ref/OTAKUWeBer.Wayland-automation/README.md),
  [source_ref/OTAKUWeBer.Wayland-automation/wayland_automation/mouse_controller.py](source_ref/OTAKUWeBer.Wayland-automation/wayland_automation/mouse_controller.py),
  [source_ref/OTAKUWeBer.Wayland-automation/wayland_automation/keyboard_controller.py](source_ref/OTAKUWeBer.Wayland-automation/wayland_automation/keyboard_controller.py),
  [source_ref/OTAKUWeBer.Wayland-automation/wayland_automation/mouse_position.py](source_ref/OTAKUWeBer.Wayland-automation/wayland_automation/mouse_position.py)

### 9.2 外部官方与上游资料

- `RM-EXT-01` Hyprland `hyprctl`:
  https://wiki.hypr.land/Configuring/Using-hyprctl/
- `RM-EXT-02` Hyprland IPC:
  https://wiki.hypr.land/IPC/
- `RM-EXT-03` `grim`:
  https://github.com/emersion/grim
- `RM-EXT-04` `slurp`:
  https://github.com/emersion/slurp
- `RM-EXT-05` wlroots `wlr-virtual-pointer-unstable-v1`:
  https://github.com/swaywm/wlroots/blob/master/protocol/wlr-virtual-pointer-unstable-v1.xml
- `RM-EXT-06` `wtype`:
  https://github.com/atx/wtype
- `RM-EXT-07` XDG Desktop Portal Screenshot:
  https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.Screenshot.html
- `RM-EXT-08` XDG Desktop Portal RemoteDesktop:
  https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.RemoteDesktop.html
- `RM-EXT-09` Ollama API:
  https://docs.ollama.com/api
- `RM-EXT-10` Model Context Protocol:
  https://modelcontextprotocol.io/introduction

### 9.3 里程碑到引用映射

- `M0` 主要验证 `RM-EXT-01` 到 `RM-EXT-09`，并结合 `RM-INT-01` 到 `RM-INT-04` 抽出最小可行路径。
- `M1` 对应 `bootstrap-daemon-session-foundation`，覆盖 session / scope / error / audit / config / MCP foundation，并以 `RM-INT-01`, `RM-INT-02`, `RM-EXT-10` 为接口与服务边界参考。
- `M2` 的 observe 链路主要依赖 `RM-EXT-01`, `RM-EXT-02`, `RM-EXT-03`, `RM-EXT-04`。
- `M3` 的输入链路主要依赖 `RM-EXT-05` 与 `RM-EXT-06`，并由 `RM-INT-03`, `RM-INT-04` 提供工程实现参考。
- `M4` 对应 `add-batch-wait-diff`，主要承接 `RM-INT-01`, `RM-INT-02` 的动作闭环经验，并建立可复用的 batch / wait / diff 编排层。
- `M5` 的视觉辅助链路主要依赖 `RM-EXT-09`，并参考 `RM-INT-01`, `RM-INT-02` 的图像分析使用方式。
- `M6` 的 MCP 集成质量、交付形态与外部可接入性，主要依赖 `RM-EXT-10`，并受本 roadmap 的 v1 发布门槛与后续 hardening change 约束。
