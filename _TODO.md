
• 先给你当前实测结论，再给你需要你亲手操作的部分。

已测结果

- uv run pytest -q 通过，24 passed。
- 真实 Hyprland/Wayland 环境下，只读链路已跑通：
  - wisp_hand.capabilities
  - wisp_hand.session.open/close
  - wisp_hand.desktop.get_topology
  - wisp_hand.cursor.get_position
  - wisp_hand.capture.screen
  - wisp_hand.wait
  - wisp_hand.capture.diff
  - wisp_hand.batch.run
- 安全护栏的真实无副作用验证已跑通：
  - 未 armed 的 pointer 调用会被拒绝
  - dry_run 的 pointer / keyboard 会返回成功结构，但不实际派发
  - 危险快捷键会被 policy_denied
- 当前机器状态：
  - hyprctl/grim/slurp 存在
  - wtype 缺失，所以真实键盘派发现在会报 dependency_missing
  - Ollama API 可达，但本机当前没有视觉模型，只有 qwen3.5:0.8b、bge-m3:567m、qwen2.5-coder:1.5b，所以
    vision 实测被 404 挡住

重要发现

- 在 scale = 1.25 的显示器上，我开了 120x120 的 region session，capture 落盘结果是 150x150。
- 在 scale = 1.0 的显示器上，同样的 120x120 region，capture 结果就是 120x120。
- 这说明当前 capture.py 和 hyprland.py 之间，scope/source_bounds 用的是逻辑坐标，而截图尺寸是物理像素。
这个点会直接影响后续 vision 坐标和 click 坐标的一致性，建议你优先反馈。

你来操作

1. 先复现缩放问题。先看监视器信息：

hyprctl -j monitors | jq '.[] | {name,x,y,width,height,scale,focused}'

2. 把下面脚本里的两个 region 改成你机器上一个 scale != 1 显示器左上角区域，和一个 scale == 1 显示器左上
 角区域，然后运行：

tmpdir=$(mktemp -d)
cat > "$tmpdir/config.toml" <<EOF
[server]
transport = "stdio"

[paths]
state_dir = "./state"
audit_file = "./state/audit.jsonl"
runtime_log_file = "./state/runtime.jsonl"
capture_dir = "./state/captures"
EOF

WISP_TEST_DIR="$tmpdir" uv run python - <<'PY'
import json, os
from pathlib import Path
from wisp_hand.config import load_runtime_config
from wisp_hand.runtime import WispHandRuntime

REGIONS = [
  ("scaled-monitor", {"x": 0, "y": 0, "width": 120, "height": 120}),
  ("scale-1-monitor", {"x": 2048, "y": 0, "width": 120, "height": 120}),
]

tmpdir = Path(os.environ["WISP_TEST_DIR"])
runtime = WispHandRuntime(config=load_runtime_config(tmpdir / "config.toml"))
rows = []

for name, region in REGIONS:
  opened = runtime.open_session(
      scope_type="region",
      scope_target=region,
      armed=False,
      dry_run=False,
      ttl_seconds=60,
  )
  try:
      cap = runtime.capture_screen(
          session_id=opened["session_id"],
          target="scope",
          inline=False,
          with_cursor=False,
      )
      rows.append({
          "name": name,
          "source_bounds": cap["source_bounds"],
          "captured_size": {"width": cap["width"], "height": cap["height"]},
          "path": cap["path"],
      })
  finally:
      runtime.close_session(session_id=opened["session_id"])

print(json.dumps(rows, ensure_ascii=False, indent=2))
PY

3. 如果你愿意做真实 pointer 派发测试，先切到一个空白工作区，确保下面 REGION 覆盖的是绝对安全的空白区域，
 再运行：

tmpdir=$(mktemp -d)
cat > "$tmpdir/config.toml" <<EOF
[server]
transport = "stdio"

[paths]
state_dir = "./state"
audit_file = "./state/audit.jsonl"
runtime_log_file = "./state/runtime.jsonl"
EOF

WISP_TEST_DIR="$tmpdir" uv run python - <<'PY'
import os, time
from pathlib import Path
from wisp_hand.config import load_runtime_config
from wisp_hand.runtime import WispHandRuntime

REGION = {"x": 2048, "y": 0, "width": 300, "height": 200}

tmpdir = Path(os.environ["WISP_TEST_DIR"])
runtime = WispHandRuntime(config=load_runtime_config(tmpdir / "config.toml"))
opened = runtime.open_session(
  scope_type="region",
  scope_target=REGION,
  armed=True,
  dry_run=False,
  ttl_seconds=30,
)

try:
  print("3 秒后开始 move/click/scroll，请不要把鼠标移入危险区域")
  time.sleep(3)
  print("move")
  runtime.pointer_move(session_id=opened["session_id"], x=40, y=40)
  time.sleep(1)
  print("click")
  runtime.pointer_click(session_id=opened["session_id"], x=40, y=40, button="left")
  time.sleep(1)
  print("scroll")
  runtime.pointer_scroll(session_id=opened["session_id"], x=40, y=40, delta_y=-120)
  print("done")
finally:
  runtime.close_session(session_id=opened["session_id"])
PY

4. 如果你要测真实键盘派发，先确保 wtype 可用：

command -v wtype

如果没有，再装上它。然后把焦点放到一个空白文本框或临时编辑器里，运行：

tmpdir=$(mktemp -d)
cat > "$tmpdir/config.toml" <<EOF
[server]
transport = "stdio"

[paths]
state_dir = "./state"
audit_file = "./state/audit.jsonl"
runtime_log_file = "./state/runtime.jsonl"
EOF

WISP_TEST_DIR="$tmpdir" uv run python - <<'PY'
import os, time
from pathlib import Path
from wisp_hand.config import load_runtime_config
from wisp_hand.runtime import WispHandRuntime

tmpdir = Path(os.environ["WISP_TEST_DIR"])
runtime = WispHandRuntime(config=load_runtime_config(tmpdir / "config.toml"))
opened = runtime.open_session(
  scope_type="region",
  scope_target={"x": 0, "y": 0, "width": 300, "height": 200},
  armed=True,
  dry_run=False,
  ttl_seconds=30,
)

try:
  print("3 秒后开始输入，请把焦点放到安全文本框")
  time.sleep(3)
  runtime.keyboard_type(session_id=opened["session_id"], text="wisp-hand-smoke")
  print("done")
finally:
  runtime.close_session(session_id=opened["session_id"])
PY

5. 如果你要测 vision，先确保本机 Ollama 里有视觉模型。先看：

curl -sS http://127.0.0.1:11434/api/tags | jq -r '.models[].name'

如果没有视觉模型，先 pull 一个你想用的视觉模型。然后把 VISION_MODEL 改成真实模型名再跑：

tmpdir=$(mktemp -d)
VISION_MODEL="你的视觉模型名"
cat > "$tmpdir/config.toml" <<EOF
[server]
transport = "stdio"

[paths]
state_dir = "./state"
audit_file = "./state/audit.jsonl"
runtime_log_file = "./state/runtime.jsonl"
capture_dir = "./state/captures"

[vision]
mode = "assist"
model = "$VISION_MODEL"
base_url = "http://127.0.0.1:11434"
timeout_seconds = 8
max_image_edge = 512
max_tokens = 128
max_concurrency = 1
EOF

WISP_TEST_DIR="$tmpdir" uv run python - <<'PY'
import json, os
from pathlib import Path
from wisp_hand.config import load_runtime_config
from wisp_hand.runtime import WispHandRuntime

tmpdir = Path(os.environ["WISP_TEST_DIR"])
runtime = WispHandRuntime(config=load_runtime_config(tmpdir / "config.toml"))
opened = runtime.open_session(
  scope_type="region",
  scope_target={"x": 0, "y": 0, "width": 220, "height": 160},
  armed=False,
  dry_run=False,
  ttl_seconds=60,
)

try:
  cap = runtime.capture_screen(session_id=opened["session_id"], target="scope", inline=False,
with_cursor=False)
  desc = runtime.vision_describe(capture_id=cap["capture_id"], prompt="Describe the screenshot
briefly.")
  print(json.dumps(desc, ensure_ascii=False, indent=2))
finally:
  runtime.close_session(session_id=opened["session_id"])
PY

你回我时，优先告诉我这 4 件事

- 缩放显示器上的 source_bounds 和 captured_size 分别是多少。
- 真实 pointer move/click/scroll 是否都成功，是否有坐标漂移。
- 装上 wtype 后，keyboard_type 是否正常。
- vision 用的具体模型名，以及 describe 是成功还是报错。

你回这些结果后，我就能判断先修缩放坐标契约，还是先补真实 input/vision 的收口。
