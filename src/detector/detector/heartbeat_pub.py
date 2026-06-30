import rclpy
from rclpy.node import Node
from std_msgs.msg import String


class HeartbeatPub(Node):
    def __init__(self):
        super().__init__('heartbeat_pub')
        self.counter = 0
        self.publisher = self.create_publisher(String, 'heartbeat', 10)
        self.timer = self.create_timer(1.0, self.tick)

    def tick(self):
        self.counter += 1
        msg = String()
        msg.data = f'heartbeat {self.counter}'
        self.publisher.publish(msg)
        self.get_logger().info(f'published: "{msg.data}"')


def main():
    rclpy.init()
    node = HeartbeatPub()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
