from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    source_arg = DeclareLaunchArgument(
        'source', default_value='test_clip.mp4',
        description='camera_node source: video file path or camera device index')
    fps_arg = DeclareLaunchArgument(
        'fps', default_value='30.0', description='camera_node publish rate')
    compressed_arg = DeclareLaunchArgument(
        'compressed', default_value='false',
        description='also run image_transport republish to publish '
                     '/camera/image_raw/compressed')

    camera_node = Node(
        package='detector', executable='camera_node', name='camera_node',
        parameters=[{
            'source': LaunchConfiguration('source'),
            'fps': LaunchConfiguration('fps'),
        }],
    )

    detector_node = Node(
        package='detector', executable='detector_node', name='detector_node',
    )

    republish_node = Node(
        package='image_transport', executable='republish', name='image_republisher',
        arguments=['raw', 'compressed'],
        remappings=[
            ('in', '/camera/image_raw'),
            ('out/compressed', '/camera/image_raw/compressed'),
        ],
        condition=IfCondition(LaunchConfiguration('compressed')),
    )

    return LaunchDescription([
        source_arg, fps_arg, compressed_arg,
        camera_node, detector_node, republish_node,
    ])
