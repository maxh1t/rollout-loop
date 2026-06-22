import rclpy
from rclpy.node import Node


class Heartbeat(Node):
    def __init__(self):
        super().__init__('heartbeat')
        self.counter = 0
        self.timer = self.create_timer(1.0, self.tick)

    def tick(self):
        self.counter += 1
        self.get_logger().info(f'live, tick {self.counter}')


def main():
    rclpy.init()
    node = Heartbeat()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()