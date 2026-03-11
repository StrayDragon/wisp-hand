# 安装与依赖

## 支持环境

`wisp-hand` 当前只支持下面这类环境：

- Linux
- Wayland 会话
- Hyprland compositor
- Python `3.14+`（如果你使用 `pip` 或虚拟环境安装）
- `uv`（推荐，用于 `uvx` / `uv tool install` / `uv add`）

运行时通常要求 `HYPRLAND_INSTANCE_SIGNATURE` 和 `WAYLAND_DISPLAY` 可用。

## 必需二进制

以下命令需要能在 `PATH` 中找到：

- `hyprctl`
  - 读取显示器、工作区、窗口、光标等桌面拓扑
- `grim`
  - 执行截图
- `wtype`
  - 执行键盘与指针输入

如果缺少这些依赖，`wisp_hand.doctor` 会直接给出阻塞原因。

## 可选组件

- `slurp`
  - 手动框选 region 时有用
- `ollama`
  - 需要启用本地视觉能力时使用
- `jq`
  - 方便格式化 `doctor --json` 输出
- `node` / `npx`
  - 需要使用 MCP Inspector 时使用
- `just`
  - 仓库里提供了快捷命令，但不是运行时必需

## 安装方式

### 直接临时运行

适合先确认环境是否可用：

```bash
uvx wisp-hand doctor --json | jq .
```

### 安装为本地 CLI

推荐：

```bash
uv tool install wisp-hand
```

安装后可直接使用：

```bash
wisp-hand doctor --json
wisp-hand mcp --config ~/.config/wisp-hand/config.toml
```

### 安装到 Python 环境

如果你要把它作为项目依赖或在已有虚拟环境里使用：

```bash
uv add wisp-hand
```

或：

```bash
pip install wisp-hand
```

## 安装后自检

推荐先做一次环境探测：

```bash
uvx wisp-hand doctor --json | jq .
```

检查重点：

- `runtime_supported` 是否为 `true`
- `dependencies` 中必需二进制是否都可用
- `issues` 是否为空

## 配置文件位置

默认配置文件路径：

```text
~/.config/wisp-hand/config.toml
```

也可以通过下面方式覆盖：

- 环境变量 `WISP_HAND_CONFIG`
- CLI 参数 `--config`

示例配置见：

- [示例配置](https://github.com/StrayDragon/wisp-hand/blob/main/docs/example_config.toml)

## 下一步

- 想快速启动服务：看 [快速开始](getting-started.md)
- 想了解 Godot 使用方式：看 [Godot 场景](scenarios/godot.md)
