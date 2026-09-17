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

## Deployment (P4)

The stack is containerized and shipped as a versioned image, not built on
the device. `scripts/deploy.sh` (the earlier rsync-and-`colcon build`-on-Pi
draft) is superseded by this — devices never get a source checkout at all.

### How a commit reaches a device

Versioning works like a `package.json` version bump, not an opaque build
number — CI is deliberately **read-only** against this repo; it never
commits anything back.

1. `src/detector/package.xml`'s `<version>` is the version, human-bumped as
   part of a normal commit — the same commit that changes the code it
   describes. `deploy/rollout.json` (which tag each device, keyed by device
   id, should run) is edited the same way, in the same commit, when you
   want that version to go live on a device: e.g. bump `<version>` to
   `0.2.0` and set `rollout.json["pi5"]` to `"0.2.0"` together.
2. A push to `main` touching `src/**` or the `Dockerfile` triggers
   `.github/workflows/build.yml`, which reads the version straight from
   `package.xml`, builds the image natively on a GitHub-hosted arm64 runner
   (`ubuntu-24.04-arm` — free for this public repo, no QEMU emulation
   needed), and publishes it to `ghcr.io/maxh1t/ros-dev-loop:<version>`.
   CI refuses to publish if that version is already published (the same
   guarantee `npm publish` gives you) — forgetting to bump the version
   fails the build loudly instead of silently overwriting a tag something
   might later be rolled back to.
3. Each device runs its own reconciler (`deploy/updater.py`, via
   `vision-stand-updater.timer`, every 1 minute) that checks
   `rollout.json` on its own and pulls + swaps if it's behind. This is
   pull-only by design — nothing (CI included) ever reaches inbound into a
   device, so an offline device just catches up whenever it next wakes.

For the normal case that's the whole loop: bump the version, point
`rollout.json` at it, push. `scripts/set_version.sh <device-id> <version>`
still exists for the exception, not the everyday path — rolling back to an
already-published version without a new commit, or moving `vm-sim` (the
canary/second-device stand-in, never touched by the steps above) by hand
for a staged-rollout test:
```bash
scripts/set_version.sh <device-id> <version>
```

### Bringing up a new device

```bash
scripts/provision_device.sh <ssh-host> <device-id> <vision-stand.service|vision-stand-sim.service>
```
Installs Docker if missing, copies the small set of host-side files
(`deploy/updater.py`, the systemd units) over SSH, and enables the
always-on services. Use `vision-stand.service` for a device with a real
camera (auto-detects its stable `/dev/v4l/by-id/...` path — see "Camera
hot-plug" below), or `vision-stand-sim.service` for a device with no camera
that reads `test_clip.mp4` instead (used for the canary/second simulated
fleet member, since a single physical device can't demonstrate a staged
rollout on its own).

After provisioning, give the device its first version:
```bash
scripts/set_version.sh <device-id> <version>
ssh <ssh-host> sudo systemctl start vision-stand-updater.service
```

### What runs on a device

Four systemd units, all `Restart=always` and enabled at boot (this also
closes the standing gap from P2/P3 — nothing needed a manual SSH restart
after a reboot anymore):
- `vision-stand.service` — the camera + detector pipeline container.
- `vision-stand-foxglove.service` — `foxglove_bridge`, for remote viewing.
- `vision-stand-updater.timer` / `.service` — the fleet reconciler above.

### Camera hot-plug

`camera_node`'s `source` should be a stable `/dev/v4l/by-id/...` path, not
a raw `/dev/videoN` index — a USB unplug/replug re-enumerates the camera
and can move (or remove) that numeric index, but udev keeps the by-id
symlink pointing at the right device regardless.
`scripts/provision_device.sh` auto-detects this for the real-camera unit.
`vision-stand.service` bind-mounts `/dev` live (`-v /dev:/dev` plus
`--device-cgroup-rule`) instead of a static `--device` snapshot, so the
container sees the change. On the app side, `camera_node` releases and
reopens its capture after 10 consecutive read failures, and its `enabled`
parameter can be toggled live (e.g. from Foxglove's Parameters panel) to
deliberately release/reacquire the device without a restart.

### Health signal

`deploy/healthcheck.py` runs inside the container right after a version
swap (`docker exec`) and requires a few frames on `/camera/image_raw`
within a timeout. It catches a crashed node, a camera that failed to open,
or ROS never coming up — it does **not** catch the detector running and
publishing wrong/garbage results, since frame arrival says nothing about
whether the model output is correct. Same class of gap as P3's
reproducibility check.
