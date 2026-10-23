# Copyright 2026 EdgeAI Robotics Challenge Team
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Start the Gazebo world and one or more simulated robots (ADR-0002).

Usage: ros2 launch edgeai_robot_bringup sim_multi_robot.launch.py robots:=robot_1,robot_2
"""

import os

from ament_index_python.packages import get_package_share_directory
from edgeai_common.config import find_config_dir, load_yaml
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, OpaqueFunction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def _launch_setup(context, *args, **kwargs):
    robots = [r.strip() for r in LaunchConfiguration('robots').perform(context).split(',')
              if r.strip()]
    if not robots or len(set(robots)) != len(robots):
        raise RuntimeError(f'robots must be a non-empty list without duplicates: {robots}')
    config_dir = find_config_dir(LaunchConfiguration('config_dir').perform(context) or None)
    spawn_poses = load_yaml(config_dir / 'sim' / 'robots.yaml')['robots']

    description = get_package_share_directory('edgeai_robot_description')
    actions = [IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(description, 'launch', 'sim_world.launch.py')),
        launch_arguments={
            'world': LaunchConfiguration('world').perform(context),
            'headless': LaunchConfiguration('headless').perform(context),
        }.items(),
    )]
    for robot_id in robots:
        if robot_id not in spawn_poses:
            raise RuntimeError(f'{robot_id} has no spawn pose in {config_dir}/sim/robots.yaml')
        pose = spawn_poses[robot_id]
        actions.append(IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                os.path.join(description, 'launch', 'sim_robot.launch.py')),
            launch_arguments={
                'robot_id': robot_id,
                'x': str(pose['x']),
                'y': str(pose['y']),
                'yaw': str(pose['yaw']),
            }.items(),
        ))

    if LaunchConfiguration('rviz').perform(context).lower() in ('true', '1'):
        rviz_file = 'realistic_robot.rviz' if len(robots) == 1 else 'multi_robot.rviz'
        actions.append(Node(
            package='rviz2',
            executable='rviz2',
            name='rviz2',
            arguments=['-d', os.path.join(description, 'rviz', rviz_file)],
            parameters=[{'use_sim_time': True}],
        ))
    return actions


def generate_launch_description():
    default_world = os.path.join(
        get_package_share_directory('edgeai_robot_description'), 'worlds', 'empty.sdf')
    return LaunchDescription([
        DeclareLaunchArgument('robots', default_value='robot_1,robot_2',
                              description='Comma-separated robot IDs to spawn'),
        DeclareLaunchArgument('config_dir', default_value=os.environ.get('EDGEAI_CONFIG_DIR', ''),
                              description='Repository config directory (default: search)'),
        DeclareLaunchArgument('world', default_value=default_world),
        DeclareLaunchArgument('headless', default_value='false'),
        DeclareLaunchArgument('rviz', default_value='false'),
        OpaqueFunction(function=_launch_setup),
    ])
