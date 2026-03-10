## Context

Wisp Hand 目前的 scope/input/capture/vision 都默认使用 Hyprland/Wayland “桌面坐标”, 但这些坐标在缩放显示器(scale != 1.0)与多显示器 mixed-scale 场景下会出现典型的三类坐标空间:

- **Layout/Logical px**: compositor 的布局坐标(跨显示器拼接后的逻辑坐标), 通常用于窗口/region 的 `x/y/width/height` 与 cursorpos.
- **Physical px**: 显示器 framebuffer 的物理像素尺寸, 在 fractional scaling 下通常与 logical 存在比例关系.
- **Image px**: 截图 PNG 的像素坐标系(由 `grim` 产生), 与 logical 之间存在 `pixel_ratio`(通常等于 monitor scale, 再叠加 downscale)。

当前系统在这些坐标空间之间缺少稳定、显式、可回溯的映射契约:

- capture `source_bounds` 与返回的 `width/height` 并非同一坐标空间, 导致 vision locate 的候选坐标无法直接用于 pointer click.
- virtual pointer 的 `motion_absolute` 需要 `extent` 作为归一化边界, 但 desktop extent 若使用了错误的空间(physical vs logical)会在 mixed-scale 下产生漂移.

本 change 目标是在不引入通用 Wayland 兼容层的前提下(Hyprland-first), 通过一层“坐标后端”把坐标契约收敛为可验证的系统行为, 并提供多后端 fallback 与可观测性输出, 支撑后续 MCP hardening 与长耗时 task-augmented execution.

## Goals / Non-Goals

**Goals:**

- 对外收敛单一规范坐标系: scope/session/pointer 统一为 **layout/logical px**。
- 对外补齐 image px <-> layout px 的稳定映射字段, 使 vision locate 能输出可点击坐标.
- 内部实现可插拔的坐标后端体系, 提供 `auto` 选择与用户强制覆盖, 并输出置信度与诊断信息.
- 修复 mixed-scale 多显示器下 virtual pointer extent 计算的潜在不一致, 降低 click 偏移风险.
- 提供验证/诊断脚本与单元测试, 能在真实桌面环境复现与定位坐标问题.

**Non-Goals:**

- 不做 X11/GNOME/KDE 或通用 Wayland compositors 兼容层.
- 不实现 GUI 校准器或持续后台采样; 坐标探针只在需要时运行并支持缓存.
- 不在 server 启动时默认执行任何有副作用的 pointer 动作; 主动校准必须显式确认.

## Decisions

### 1. 单一规范坐标系 + 显式映射字段

我们选择以 **layout/logical px** 作为对外唯一“动作坐标系”:

- `hand.session.open` 的 scope target (region/monitor/window/desktop) 使用 layout 坐标.
- `hand.pointer.*` 的 `x/y` 解释为 scope 内 layout px.

截图与视觉结果仍然存在 image px, 但必须通过显式字段连接:

```
layout px (scope/source_bounds)  <---- pixel_ratio ---->  image px (png width/height)
```

这避免了“一个字段多语义”的歧义, 也让 agent 可以在必要时自行 fallback.

### 2. 坐标后端(Coordinate Backend)作为独立子系统

新增内部模块(示例命名):

- `wisp_hand/coordinates/`:
  - `CoordinateBackend` 接口: `resolve(topology) -> CoordinateMap`
  - `CoordinateMap`: per-monitor `layout_bounds`, `physical_size`, `scale`, `pixel_ratio`, `confidence`, `source`
  - `auto` 选择器: 按条件与置信度挑选后端, 并允许 `force_backend`
  - `cache`: 基于 topology fingerprint 存盘/读盘

对 runtime 而言, 坐标后端是 “事实来源”, input/capture/vision 均从它读取映射.

### 3. 多后端策略与 fallback

设计上提供三类后端, 以满足“开箱即用 + 可回退 + 可校准”:

- `hyprctl-infer`:
  - 仅使用 `hyprctl -j monitors` 的 `x/y/width/height/scale` 推断 `layout_bounds`
  - 通过“邻接一致性”(monitor x/y 拼接关系)计算置信度
  - 优点: 快, 无额外 IO; 缺点: 在字段语义变化或单显示器时置信度可能不足
- `grim-probe`:
  - 使用 `grim` 做被动探针, 通过截图尺寸计算 `pixel_ratio` 与 physical_size, 从而得到 layout_bounds
  - 优点: 更可靠; 缺点: 启动时有额外截图开销(但可缓存, 且只在需要时触发)
- `active-pointer-probe`:
  - 需要用户显式确认, 在安全 region 内执行一次 pointer move 并回读 `hyprctl cursorpos` 验证 extent 与坐标系一致性
  - 优点: 最高置信; 缺点: 有副作用, 只能作为诊断/校准流程使用

默认 `coordinates.mode="auto"`:

- scale 全为 1.0 且多显示器拼接一致时优先 `hyprctl-infer`
- 发现 fractional scaling 或置信度不足时升级为 `grim-probe`
- 仅在用户显式运行诊断/校准命令或开启配置时才允许 `active-pointer-probe`

### 4. mixed-scale 复杂场景的边界

- 对 scope=region/window/monitor 的 mapping, 我们仅在其完全落入单一 monitor 的情况下保证 `pixel_ratio` 为常量且可逆.
- 若 capture 的 `source_bounds` 跨越多个 monitor 且存在不同 scale, 则:
  - 标记 `mapping.kind="multi-monitor"` 并返回分段映射(如果可行), 或
  - 明确返回 `capability_unavailable` / `unsupported_mapping`(取决于 spec 决策)

本 change 会优先保证“单 monitor 范围内”的确定性, 并把跨 monitor 的精确映射作为后续增强点.

## Risks / Trade-offs

- [计算/取整导致 1px 偏差] → 采用一致的 rounding/clamp 规则, 并在 scope 边界内裁剪.
- [推断失败导致系统性偏移] → `auto` 置信度机制 + 可强制后端 + grim-probe 被动校准路径.
- [grim-probe 开销] → 缓存 + 仅在 scale != 1 或低置信度时触发; 支持手动预热.
- [主动 pointer probe 有副作用] → 默认禁用, 仅诊断命令 + 显式确认 + 仅在用户框选安全区域内执行.

## Migration Plan

- 本 change 引入 **BREAKING** 的 `hand.vision.locate` schema 调整(显式区分 scope/image 坐标). 同步更新 tests 与 examples.
- 在引入新 `[coordinates]` 配置段后, 旧配置不做兼容; 所有内置示例与文档统一升级.

## Open Questions

- `grim` 对 `-g geometry` 与 `-o output` 的坐标语义是否在所有 wlroots/hyprland 版本上稳定一致? 需要用诊断脚本在多机型上确认.
- 对跨 monitor capture 的 mapping, v1 是否直接拒绝以确保确定性, 还是输出分段映射并在 agent 侧处理?

