# ros-dev-loop

A ROS 2 (Jazzy) development-loop workspace. The `detector` package is a
vision pipeline (camera node + motion detector + on-device object detector)
exercised on a laptop VM before deploying to a Raspberry Pi.

## Package: `detector` (ament_python)

| Node             | Description                                                        | Run command                          |
| ---------------- | ------------------------------------------------------------------ | ------------------------------------ |
| `camera_node`    | Reads frames from `source` and publishes `/camera/image_raw`.      | `ros2 run detector camera_node --ros-args -p source:=/path/to/clip.mp4` |
| `detector_node`  | Differences frames from `/camera/image_raw`, publishes `/detector/motion` (`std_msgs/Bool`). | `ros2 run detector detector_node` |
| `object_detector_node` | Runs a YOLOv8n ONNX model (CPU, via ONNX Runtime) on `/camera/image_raw`, publishes `/detector/objects` (`vision_msgs/Detection2DArray`) and an annotated copy on `/detector/objects/annotated`. | `ros2 run detector object_detector_node` |
| `image_transport republish` | Not part of this package — the standalone ROS tool. Two instances run via the launch file: one republishes `/camera/image_raw` as JPEG on `/camera/image_raw/compressed` (opt-in, `compressed:=true`), the other always republishes `/detector/objects/annotated` as JPEG on `/detector/objects/annotated/compressed` (always on — the annotated stream is specifically for remote/Foxglove viewing over LAN). Requires `ros-jazzy-compressed-image-transport`. | see launch file below |

### Camera / detector notes

- `camera_node` `source` parameter selects the frame source without code changes:
  - a file path (e.g. `/path/to/clip.mp4`) reads a video file (looped by default),
  - a numeric string (e.g. `0`) opens that camera device index.
  - other params: `fps` (default 30), `loop` (default true), `frame_id` (default `camera`).
- `detector_node` params: `diff_threshold` (default 25), `motion_min_pixels` (default 500).

### Object detection (P2)

`object_detector_node` runs YOLOv8n (COCO-pretrained, no custom training)
exported to ONNX, on CPU via ONNX Runtime. Params:

- `resolution` (320 or 640, default 320) — selects `models/yolov8n_<resolution>.onnx`.
- `conf_threshold` (default 0.5), `iou_threshold` (default 0.45).
- `classes` (default `['person']`) — filters detections to these COCO class
  names post-inference; the model itself always scores all 80 classes, so
  this is a free filter, not a retrain. Pass an empty list for all classes.

The node logs `fps` / `avg_inference_latency_ms` / `peak_rss_mb` every 30
frames — that's the on-device cost this phase is measuring.

**Dependencies not covered by `python3-opencv`-style apt/rosdep keys:**
`onnxruntime` has no apt package providing its Python bindings on this
platform (only a `ros-jazzy-onnxruntime-vendor` C++ package, which doesn't
help a Python node) — install it with:

```bash
pip install --break-system-packages onnxruntime
```

`vision_msgs` (for `Detection2DArray`) **does** have an apt package:

```bash
sudo apt install ros-jazzy-vision-msgs
```

The `.onnx` model files are committed directly into
`src/detector/models/` — exported once on a dev machine with
`scripts/export_model.py` (needs `ultralytics`, which pulls in PyTorch; run
it in a throwaway venv, never installed on the Pi):

```bash
python3 -m venv .venv-export
source .venv-export/bin/activate
pip install ultralytics onnx
python3 scripts/export_model.py
```

The Pi only ever needs `onnxruntime` + the committed `.onnx` files — it
never needs `ultralytics`/PyTorch.

### Snapshot capture (P3)

`object_detector_node` also serves `/detector/take_snapshot`
(`std_srvs/srv/Trigger`, no request fields) — on call, it freezes the most
recently processed frame + its detections to disk as a JPEG plus a JSON
metadata sidecar (`snapshot_dir` param, default `~/vision_stand_snapshots`).
The sidecar records the code version (git SHA), the model file's sha256 (not
just its filename), the ONNX Runtime version, thresholds, and the detection
result — this is deliberately more than an ad-hoc shape, since the point is
a later reproducibility check against exactly this metadata.

Two ways to trigger it, both work over the LAN the same way Foxglove's live
view already does:

- **Foxglove:** add a "Call Service" panel pointed at `/detector/take_snapshot`
  (empty request `{}`) — `foxglove_bridge`'s default capabilities already
  include `services`, so no extra bridge config is needed.
- **Terminal (scriptable fallback):**
  ```bash
  ros2 service call /detector/take_snapshot std_srvs/srv/Trigger {}
  ```

This staging artifact isn't itself a `LeRobotDataset` — that gets built
laptop-side (see `scripts/build_lerobot_dataset.py`), since the real
`lerobot` package is heavy enough (HF `datasets`, video encoding) that it
follows the same never-on-the-Pi rule as `ultralytics` above.

## Build and run from scratch

```bash
# 1. Clone and enter the workspace
git clone <your-repo-url> ros-dev-loop
cd ros-dev-loop

# 2. Source the workspace environment (ROS 2 Jazzy + project env vars,
#    e.g. ROS_DOMAIN_ID — do this on every machine: VM, Pi, any reimage)
source scripts/env.sh

# 3. Build with colcon
colcon build

# 4. Source the local overlay (do this in every new shell)
source install/setup.bash

# 4a. Known colcon-core issue on this workspace: the generated
#     install/detector/share/detector/package.dsv only registers the
#     PYTHONPATH hook, not AMENT_PREFIX_PATH, so `ros2 run`/`ros2 launch`
#     can't find the `detector` package after step 4 alone. Reproduces on
#     a clean rebuild, independent of --merge-install, and survived a
#     colcon-core 0.20.1 -> 0.21.2 upgrade, so it isn't just a stale
#     package problem. Work around it until root-caused:
export AMENT_PREFIX_PATH="$(pwd)/install/detector:$AMENT_PREFIX_PATH"

# 5. Run the pipeline
ros2 launch detector pipeline.launch.py
```

### Launch file

`src/detector/launch/pipeline.launch.py` starts `camera_node` + `detector_node`
together instead of running each by hand:

```bash
# Defaults: source=test_clip.mp4, fps=30, compressed=false
ros2 launch detector pipeline.launch.py

# Real camera, and also publish the JPEG-compressed topic
ros2 launch detector pipeline.launch.py source:=0 compressed:=true
```

## Deployment

`scripts/deploy.sh` is a commented-out draft template for pushing the workspace
to a Raspberry Pi. The Pi is not set up yet, so the script is intentionally not
runnable: fill in the Pi host/user/path placeholders and uncomment the steps
once the target is known.
