# 排障

## 1. `doctor --json` 显示 `status=blocked`

优先执行：

```bash
uvx wisp-hand-mcp doctor --json | jq .
```

常见阻塞原因：

- `unsupported_environment`：
  - 需要在 Hyprland/Wayland 会话下运行（`HYPRLAND_INSTANCE_SIGNATURE` 必须存在）。
- `dependency_missing`：
  - 缺少依赖二进制（观察需要 `hyprctl`，截图需要 `grim`，输入需要 `wtype`）。
- `invalid_config`：
  - 配置 TOML 语法错误或字段不合法，按错误信息修正。
- `Path is not writable`：
  - `paths.*` 指向的父目录不可写，修改到可写路径或调整权限。

## 2. stdio transport 下“协议卡住/输出异常”

- stdio transport 的协议数据走 stdout，日志必须走 stderr。
- 本项目默认将 console 日志输出到 stderr；如果你自定义 logging，请确保不要把日志写到 stdout。

## 3. 输入类工具被拒绝（`session_not_armed` / `policy_denied`）

- `wisp_hand.pointer.*` / `wisp_hand.keyboard.*` 需要 session `armed=true`。
- 部分危险快捷键会被策略拒绝（例如 `ctrl+alt+delete`），这是预期行为。

## 4. 多显示器/缩放导致 click 偏移

先运行坐标诊断脚本获取当前坐标后端与置信度：

```bash
uv run python examples/attempts/diagnose_coordinates.py --capture-check
```

如果需要更强校验（会移动鼠标，需显式确认）：

```bash
uv run python examples/attempts/diagnose_coordinates.py \
  --active-probe \
  --confirm-active-probe \
  --active-probe-region "x,y,w,h"
```

## 5. capture artifact 找不到 / diff 报错 `capability_unavailable`

- capture artifacts 受 retention 策略影响，会按时间/容量清理。
- 如果需要更长期保存，调大 `[retention.captures]` 的限制或将 `capture_dir` 指向更大磁盘。

