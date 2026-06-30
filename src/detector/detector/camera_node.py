import cv2
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from cv_bridge import CvBridge


class CameraNode(Node):
    """Reads frames from a source (video file path or camera index) and
    publishes them to /camera/image_raw.

    The source is controlled by the `source` parameter so switching from a
    test video file to a real USB camera on the Pi is a parameter change,
    not a code change:
      - a file path  -> reads the video file (looped)
      - an integer string like "0" -> opens camera device 0
    """

    def __init__(self):
        super().__init__('camera_node')

        # Parameters
        self.declare_parameter('source', '')
        self.declare_parameter('fps', 30.0)
        self.declare_parameter('loop', True)
        self.declare_parameter('frame_id', 'camera')

        source = self.get_parameter('source').get_parameter_value().string_value
        self.fps = self.get_parameter('fps').get_parameter_value().double_value
        self.loop = self.get_parameter('loop').get_parameter_value().bool_value
        self.frame_id = \
            self.get_parameter('frame_id').get_parameter_value().string_value

        if not source:
            self.get_logger().error(
                "Parameter 'source' is empty. Pass a video file path or a "
                "camera index, e.g. -p source:=/path/to/clip.mp4 or "
                "-p source:=0")
            raise SystemExit(1)

        # A purely-numeric source is treated as a camera device index.
        self.source = int(source) if source.isdigit() else source
        self.is_camera = isinstance(self.source, int)

        self.bridge = CvBridge()
        self.publisher = self.create_publisher(Image, '/camera/image_raw', 10)

        self.cap = self._open_capture()
        if not self.cap.isOpened():
            self.get_logger().error(f'Failed to open source: {self.source!r}')
            raise SystemExit(1)

        self.get_logger().info(
            f'Publishing frames from {self.source!r} '
            f'(camera={self.is_camera}, loop={self.loop}) at {self.fps} fps '
            f'on /camera/image_raw')

        self.timer = self.create_timer(1.0 / self.fps, self.tick)

    def _open_capture(self):
        return cv2.VideoCapture(self.source)

    def tick(self):
        ok, frame = self.cap.read()
        if not ok:
            # End of a video file: rewind and keep streaming.
            if not self.is_camera and self.loop:
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ok, frame = self.cap.read()
            if not ok:
                self.get_logger().warning('No frame read from source')
                return

        msg = self.bridge.cv2_to_imgmsg(frame, encoding='bgr8')
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = self.frame_id
        self.publisher.publish(msg)

    def destroy_node(self):
        if getattr(self, 'cap', None) is not None:
            self.cap.release()
        super().destroy_node()


def main():
    rclpy.init()
    node = CameraNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
