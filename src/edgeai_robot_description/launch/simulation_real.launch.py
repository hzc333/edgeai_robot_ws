"""Single-robot simulation entry point kept for compatibility.

Starts the world and robot_1 at the original spawn pose. The robot runs in the
/robot_1 namespace with robot_1/ frame prefixes (ADR-0002). For several robots
use edgeai_robot_bringup sim_multi_robot.launch.py.
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration


def generate_launch_description():
    launch_dir = os.path.join(get_package_share_directory('edgeai_robot_description'), 'launch')
    return LaunchDescription([
        DeclareLaunchArgument('headless', default_value='false'),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(os.path.join(launch_dir, 'sim_world.launch.py')),
            launch_arguments={'headless': LaunchConfiguration('headless')}.items(),
        ),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(os.path.join(launch_dir, 'sim_robot.launch.py')),
            launch_arguments={'robot_id': 'robot_1', 'x': '-1.5', 'y': '-1.5',
                              'yaw': '0.0'}.items(),
        ),
    ])
