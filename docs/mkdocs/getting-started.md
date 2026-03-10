# 快速开始

## 前置条件

- 运行在 Hyprland/Wayland 会话中（环境变量 `HYPRLAND_INSTANCE_SIGNATURE` 必须存在）
- 已安装依赖二进制：
  - `hyprctl`（拓扑/窗口/光标）
  - `grim`（截图）
  - `wtype`（键盘/鼠标输入）
  - `slurp`（可选：你手动框选 region 时会用到）

## 1) 连接前自检

推荐先跑一次 preflight：

```bash
uvx wisp-hand-mcp doctor --json | jq .
```

如果 `status=blocked`，优先看 `issues` 里的错误码与缺失依赖。

## 2) 准备配置文件

默认配置路径是 `~/.config/wisp-hand/config.toml`，也可以在启动时用 `--config` 指定。

仓库里有一个示例：

```bash
sed -n '1,200p' docs/example_config.toml
```

## 3) 启动 MCP server

默认是 `stdio` transport（适合被 MCP client/Inspector 以子进程方式拉起）：

```bash
uvx wisp-hand-mcp --config ~/.config/wisp-hand/config.toml
```

开发/调试等价入口：

```bash
uv run wisp-hand-mcp --config ./config.toml
python -m wisp_hand --config ./config.toml
```

## 4) 用 MCP Inspector 验证

仓库自带 `Justfile`：

```bash
just inspector
```

这会执行：

```bash
npx --yes @modelcontextprotocol/inspector -- uv run wisp-hand-mcp --config docs/example_config.toml --transport stdio
```

在 Inspector 中建议先依次调用：

1. `wisp_hand.capabilities`
2. `wisp_hand.session.open`（先 `armed=false`，scope 选一个小的 `region`）
3. `wisp_hand.capture.screen`
4. `wisp_hand.session.close`

## 5) 下一步：Godot 场景

如果你的目标是“让 AI 看 Godot 编辑器，点击运行并用截图验证”，直接看：

- [Godot 场景](scenarios/godot.md)

