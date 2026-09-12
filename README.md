# ros-dev-loop

A ROS 2 (Jazzy) development-loop workspace. The `detector` package is a
motion-detector pipeline (camera node + detector node) exercised on a laptop
VM before deploying to a Raspberry Pi.

## Package: `detector` (ament_python)

| Node             | Description                                                        | Run command                          |
| ---------------- | ------------------------------------------------------------------ | ------------------------------------ |
| `camera_node`    | Reads frames from `source` and publishes `/camera/image_raw`.      | `ros2 run detector camera_node --ros-args -p source:=/path/to/clip.mp4` |
| `detector_node`  | Differences frames from `/camera/image_raw`, publishes `/detector/motion` (`std_msgs/Bool`). | `ros2 run detector detector_node` |
| `image_transport republish` | Not part of this package — the standalone ROS tool that republishes `/camera/image_raw` as JPEG on `/camera/image_raw/compressed`. Requires `ros-jazzy-compressed-image-transport`. | see launch file below |

### Camera / detector notes

- `camera_node` `source` parameter selects the frame source without code changes:
  - a file path (e.g. `/path/to/clip.mp4`) reads a video file (looped by default),
  - a numeric string (e.g. `0`) opens that camera device index.
  - other params: `fps` (default 30), `loop` (default true), `frame_id` (default `camera`).
- `detector_node` params: `diff_threshold` (default 25), `motion_min_pixels` (default 500).

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
