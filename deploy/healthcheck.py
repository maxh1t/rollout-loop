#!/usr/bin/env python3
"""Health signal for the deploy pipeline (MAX-10 / P4).

Run inside the just-started container (`docker exec ... healthcheck.py`) by
the host-side updater right after a version swap. Confirms the pipeline is
actually alive by requiring a few frames on /camera/image_raw within a
timeout.

What this catches: a crashed node, a camera/source that failed to open, ROS
never coming up.
What this deliberately does NOT catch: the detector running and publishing
garbage or wrong detections — frames arriving says nothing about whether the
model output is correct. That gap gets written up alongside the rest of
MAX-10's results, same shape as the reproducibility gap from P3.
"""
import sys

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image

TIMEOUT_S = 10.0
MIN_FRAMES = 3


class HealthCheck(Node):
    def __init__(self):
        super().__init__('health_check')
        self.count = 0
        self.create_subscription(Image, '/camera/image_raw', self._on_frame, 10)

    def _on_frame(self, _msg):
        self.count += 1


def main():
    rclpy.init()
    node = HealthCheck()

    deadline = node.get_clock().now().nanoseconds / 1e9 + TIMEOUT_S
    while node.count < MIN_FRAMES and node.get_clock().now().nanoseconds / 1e9 < deadline:
        rclpy.spin_once(node, timeout_sec=0.5)

    count = node.count
    node.destroy_node()
    rclpy.shutdown()

    if count >= MIN_FRAMES:
        print(f'OK: received {count} frames on /camera/image_raw')
        sys.exit(0)
    else:
        print(f'FAIL: received only {count} frames in {TIMEOUT_S}s')
        sys.exit(1)


if __name__ == '__main__':
    main()
