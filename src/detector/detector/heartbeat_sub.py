import rclpy
from rclpy.node import Node
from std_msgs.msg import String


class HeartbeatSub(Node):
    def __init__(self):
        super().__init__('heartbeat_sub')
        self.subscription = self.create_subscription(
            String, 'heartbeat', self.on_message, 10)

    def on_message(self, msg):
        self.get_logger().info(f'received: "{msg.data}"')


def main():
    rclpy.init()
    node = HeartbeatSub()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
