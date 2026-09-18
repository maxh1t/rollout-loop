# rollout-loop

A rollout loop for shipping versioned software to a fleet of networked
Raspberry Pis: bump a version, push, and each device pulls and swaps to it
on its own. Rollback is just as simple: one edit, one push.

The example workload it ships is a small ROS 2 (Jazzy) vision pipeline:
camera capture, motion detection, and on-device object detection (YOLOv8n,
CPU via ONNX Runtime). The running version is overlaid directly on the live
annotated video feed, so a deploy or rollback is visible on camera, not just
in logs. Tested end-to-end on a Raspberry Pi 5 with a USB webcam.

## The example app

| Node                   | What it does                                                                        |
|------------------------|-------------------------------------------------------------------------------------|
| `camera_node`          | Reads a video file or camera and publishes frames.                                  |
| `detector_node`        | Frame-differencing motion detector.                                                 |
| `object_detector_node` | Runs YOLOv8n on each frame and publishes detections plus an annotated video stream. |

## Quickstart

```bash
git clone <repo-url> rollout-loop && cd rollout-loop
source scripts/env.sh
colcon build
source install/setup.bash
ros2 launch detector pipeline.launch.py
```

By default this runs against the bundled `test_clip.mp4`. To use a real
camera instead:

```bash
ros2 launch detector pipeline.launch.py source:=0
```

## The rollout loop

The stack ships as a versioned container image, built by CI and pulled by
each device on its own:

1. Bump the version in `src/detector/package.xml` and `src/detector/setup.py`,
   and point a device at it in `deploy/rollout.json`.
2. Commit and push. CI builds the image and publishes it to GHCR.
3. The device polls `rollout.json` every minute and updates itself.

Rolling back is the same: point `rollout.json` at an older, already-published
version and push. To bring up a new device, run
`scripts/provision_device.sh <ssh-host> <device-id> <service>`.

## License

MIT, see `src/detector/LICENSE`.
