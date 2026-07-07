# ros-dev-loop

A ROS 2 (Jazzy) development-loop workspace. The `detector` package is a small
test bench: a motion-detector pipeline (camera node + detector node) plus a few
heartbeat nodes used to exercise the build/run loop before deploying to a
Raspberry Pi.

## Package: `detector` (ament_python)

| Node             | Description                                                        | Run command                          |
| ---------------- | ------------------------------------------------------------------ | ------------------------------------ |
| `heartbeat`      | Timer-only node that logs `live, tick N` once per second.          | `ros2 run detector heartbeat`        |
| `heartbeat_pub`  | Publishes a `std_msgs/String` on `heartbeat` once per second.      | `ros2 run detector heartbeat_pub`    |
| `heartbeat_sub`  | Subscribes to `heartbeat` and logs each received message.          | `ros2 run detector heartbeat_sub`    |
| `camera_node`    | Reads frames from `source` and publishes `/camera/image_raw`.      | `ros2 run detector camera_node --ros-args -p source:=/path/to/clip.mp4` |
| `detector_node`  | Differences frames from `/camera/image_raw`, publishes `/detector/motion` (`std_msgs/Bool`). | `ros2 run detector detector_node` |

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

# 2. Source the ROS 2 Jazzy environment
source /opt/ros/jazzy/setup.bash

# 3. Build with colcon
colcon build

# 4. Source the local overlay (do this in every new shell)
source install/setup.bash

# 5. Run a node
ros2 run detector heartbeat
```

### Run the camera + detector pipeline

In two terminals (source `install/setup.bash` in each):

```bash
# Terminal 1 — publish frames from a video file
ros2 run detector camera_node --ros-args -p source:=/path/to/clip.mp4

# Terminal 2 — detect motion and publish /detector/motion
ros2 run detector detector_node
```

## Deployment

`scripts/deploy.sh` is a commented-out draft template for pushing the workspace
to a Raspberry Pi. The Pi is not set up yet, so the script is intentionally not
runnable: fill in the Pi host/user/path placeholders and uncomment the steps
once the target is known.
