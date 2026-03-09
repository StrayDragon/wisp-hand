## Context

foundation change 已经固定了 session、scope、错误与审计契约，但当前系统仍然无法读取 Hyprland 拓扑，也没有 screenshot artifact 可供后续链路复用。按照 roadmap，observe 必须先于 input 落地，这样后续所有副作用能力都建立在已验证的坐标与截图路径上。

本 change 是整个 MVP 的只读阶段。它负责证明 Hyprland-first 的读路径可行，同时把 topology 与 capture 的共享数据结构定下来。

## Goals / Non-Goals

**Goals:**

- 通过 `hyprctl` 建立稳定的 Hyprland topology 读取路径。
- 建立 cursor 查询与 scope-relative 坐标输出。
- 建立多目标截图与 capture artifact store。
- 固定 observe 结果和 capture 元数据的共享结构。

**Non-Goals:**

- 不实现 pointer 或 keyboard 输入。
- 不实现 wait、diff、batch 或 vision。
- 不为非 Hyprland compositor 设计兼容适配层。

## Decisions

### 1. 拓扑读取直接建立在 Hyprland 官方能力上

只读取 `hyprctl -j` 与相关 IPC 暴露的 monitors、workspaces、active window、clients、cursor 信息，不为其他桌面抽象第二套模型。这样后续 scope 与坐标计算只服务于 Hyprland。

### 2. Observe 结果统一归一化为共享 topology model

无论底层命令如何返回数据，进入 runtime 后都转换为统一的 topology model，至少包括：

- monitor 几何信息
- workspace 与 monitor 关联
- window 几何信息与焦点状态
- cursor 绝对坐标

下游 change 不再直接解析 `hyprctl` 原始 JSON。

### 3. Capture 结果全部进入 artifact store

截图不直接以内联图片作为唯一返回形式。所有截图都先进入 artifact store，再根据 `inline` 参数决定是否附带 `inline_base64`。这样后续 batch、diff、vision 都可以通过 `capture_id` 复用同一张图。

### 4. Capture 元数据必须携带可逆坐标上下文

截图引擎不仅返回图片，还返回目标类型、原始边界、scope 关联和 downscale 元数据。后续任何需要从图像坐标回推桌面坐标的 change 都使用这份上下文，而不是自己再猜。

### 5. 只读链路与副作用链路保持严格分层

本 change 内所有工具都必须保持无副作用。输入、安全策略和 emergency stop 留到下一个 change，避免 observe 阶段同时承担行为验证和状态治理。

## Risks / Trade-offs

- `hyprctl` 与窗口几何状态之间可能存在短暂不一致 -> 通过统一 topology snapshot 与时间戳降低读取漂移。
- `grim` 截图与 scope/window 边界裁剪可能出现像素偏差 -> 需要在本 change 内建立多显示器与裁剪精度测试。
- 全部截图都写入 artifact store 会增加磁盘占用 -> 通过 TTL 与清理策略控制体积，而不是牺牲可复用性。
