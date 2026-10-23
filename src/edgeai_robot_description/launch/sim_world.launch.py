"""Start the Gazebo world once and bridge the simulation clock.

Robots are added separately with sim_robot.launch.py (ADR-0002).
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, OpaqueFunction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def _launch_setup(context, *args, **kwargs):
    world = LaunchConfiguration('world').perform(context)
    headless = LaunchConfiguration('headless').perform(context).lower() in ('true', '1')

    # -s runs the server only (no GUI), used for CI and remote machines.
    gz_args = f'-r {"-s " if headless else ""}{world}'
    gazebo = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(
            get_package_share_directory('ros_gz_sim'), 'launch', 'gz_sim.launch.py')),
        launch_arguments={'gz_args': gz_args}.items(),
    )

    # The clock is global and must be bridged exactly once.
    clock_bridge = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        name='clock_bridge',
        output='screen',
        arguments=['/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock'],
    )
    return [gazebo, clock_bridge]


def generate_launch_description():
    default_world = os.path.join(
        get_package_share_directory('edgeai_robot_description'), 'worlds', 'empty.sdf')
    return LaunchDescription([
        DeclareLaunchArgument('world', default_value=default_world,
                              description='Gazebo world file'),
        DeclareLaunchArgument('headless', default_value='false',
                              description='Run the Gazebo server without the GUI'),
        OpaqueFunction(function=_launch_setup),
    ])
