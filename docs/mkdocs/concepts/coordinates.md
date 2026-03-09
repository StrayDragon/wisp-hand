# 坐标与缩放

在 Hyprland + mixed-scale（不同显示器不同 scale）环境中，“输入坐标”和“截图像素”不是同一套单位。Wisp Hand 的策略是：

- 输入：统一使用 Hyprland layout/logical px（scope-relative）
- 截图：得到 image/physical px（实际渲染像素）
- 映射：通过 topology 与 capture metadata 提供 `pixel_ratio` 等上下文字段，把 image px 与 layout px 对齐

## 常见问题：为什么 click 会偏移

常见原因是某个 monitor 的 scale 不为 1.0，或者多显示器的 layout 坐标与物理像素之间存在换算。

解决思路：

1. 优先用 `dry_run=true` 开 session，查看服务端计算出来的 `absolute_position`
2. 在需要时运行坐标诊断脚本，确认当前坐标后端与置信度

## 坐标后端（Coordinate Backends）

Wisp Hand 支持多种坐标后端，并在 `coordinates.mode=auto` 时自动选择：

- `hyprctl-infer`：基于 Hyprland monitors JSON 推断映射（快，但在部分组合下可能不够稳）
- `grim-probe`：通过小区域截图 probe 推断 image px 与 layout px 比例（更稳，成本稍高）
- `active-pointer-probe`：通过主动移动光标并读回位置做强验证（最强，但会产生可见副作用，需要显式确认）

## 诊断脚本

只做 capture 校验（无输入副作用）：

```bash
uv run python examples/attempts/diagnose_coordinates.py --capture-check
```

强验证（会移动鼠标，需要显式确认）：

```bash
uv run python examples/attempts/diagnose_coordinates.py \
  --active-probe \
  --confirm-active-probe \
  --active-probe-region "x,y,w,h"
```

如果你需要让 AI 自动化长期稳定运行，建议在 CI/排障时先把这套诊断跑通，并把 `coordinates.mode` 固定为你验证过的后端。

