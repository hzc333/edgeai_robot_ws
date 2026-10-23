"""Spawn one simulated robot in its own namespace (ADR-0002).

Requires a running world (sim_world.launch.py). All robot endpoints live under
/<robot_id>/, all robot frames carry the <robot_id>/ prefix, and the robot's
odometry TF is bridged to the global /tf.
"""

import os
import tempfile

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, GroupAction, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node, PushRosNamespace
import xacro
import yaml

ROBOT_ID_FORMAT = ('robot_1', 'robot_2', 'robot_3', 'robot_4')


def bridge_config(robot_id, publish_odom_tf):
    """Return the ros_gz_bridge entries for one robot."""
    ns = f'/{robot_id}'

    def entry(ros_topic, gz_topic, ros_type, gz_type, direction='GZ_TO_ROS'):
        return {
            'ros_topic_name': ros_topic,
            'gz_topic_name': gz_topic,
            'ros_type_name': ros_type,
            'gz_type_name': gz_type,
            'direction': direction,
        }

    entries = [
        entry(f'{ns}/cmd_vel', f'{ns}/cmd_vel', 'geometry_msgs/msg/Twist', 'gz.msgs.Twist',
              'ROS_TO_GZ'),
        entry(f'{ns}/odom', f'{ns}/odom', 'nav_msgs/msg/Odometry', 'gz.msgs.Odometry'),
        entry(f'{ns}/joint_states', f'{ns}/joint_states', 'sensor_msgs/msg/JointState',
              'gz.msgs.Model'),
        entry(f'{ns}/scan', f'{ns}/scan', 'sensor_msgs/msg/LaserScan', 'gz.msgs.LaserScan'),
        entry(f'{ns}/imu', f'{ns}/imu', 'sensor_msgs/msg/Imu', 'gz.msgs.IMU'),
        entry(f'{ns}/camera/image', f'{ns}/camera/image', 'sensor_msgs/msg/Image',
              'gz.msgs.Image'),
        entry(f'{ns}/camera/depth_image', f'{ns}/camera/depth_image', 'sensor_msgs/msg/Image',
              'gz.msgs.Image'),
        entry(f'{ns}/camera/camera_info', f'{ns}/camera/camera_info',
              'sensor_msgs/msg/CameraInfo', 'gz.msgs.CameraInfo'),
        # camera/points is intentionally not bridged: Gazebo fills the cloud in
        # camera_link axes but stamps it with the optical frame (ADR-0002).
    ]
    if publish_odom_tf:
        # DiffDrive publishes <robot_id>/odom -> <robot_id>/base_footprint. Disable
        # this when an EKF owns that transform.
        entries.append(entry('/tf', f'{ns}/tf', 'tf2_msgs/msg/TFMessage', 'gz.msgs.Pose_V'))
    return entries


def _launch_setup(context, *args, **kwargs):
    robot_id = LaunchConfiguration('robot_id').perform(context)
    if robot_id not in ROBOT_ID_FORMAT:
        raise RuntimeError(f'robot_id must be one of {ROBOT_ID_FORMAT}, got {robot_id!r}')
    x = LaunchConfiguration('x').perform(context)
    y = LaunchConfiguration('y').perform(context)
    yaw = LaunchConfiguration('yaw').perform(context)
    publish_odom_tf = LaunchConfiguration('publish_odom_tf').perform(context).lower() in (
        'true', '1')

    share = get_package_share_directory('edgeai_robot_description')
    robot_description = xacro.process_file(
        os.path.join(share, 'urdf', 'edgeai_robot_real.urdf.xacro'),
        mappings={'robot_id': robot_id},
    ).toxml()

    config_dir = tempfile.mkdtemp(prefix=f'edgeai_{robot_id}_bridge_')
    bridge_file = os.path.join(config_dir, 'bridge.yaml')
    with open(bridge_file, 'w', encoding='utf-8') as stream:
        yaml.safe_dump(bridge_config(robot_id, publish_odom_tf), stream, sort_keys=False)

    robot_state_publisher = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        name='robot_state_publisher',
        output='screen',
        parameters=[{
            'robot_description': robot_description,
            'frame_prefix': f'{robot_id}/',
            'use_sim_time': True,
        }],
    )
    spawn = Node(
        package='ros_gz_sim',
        executable='create',
        name='spawn',
        output='screen',
        arguments=['-name', robot_id, '-topic', f'/{robot_id}/robot_description',
                   '-x', x, '-y', y, '-z', '0.01', '-Y', yaw],
    )
    bridge = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        name='ros_gz_bridge',
        output='screen',
        parameters=[{'config_file': bridge_file, 'use_sim_time': True}],
    )
    return [GroupAction([PushRosNamespace(robot_id), robot_state_publisher, spawn, bridge])]


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('robot_id', default_value='robot_1',
                              description='robot_1 .. robot_4'),
        DeclareLaunchArgument('x', default_value='-1.5', description='Spawn x [m]'),
        DeclareLaunchArgument('y', default_value='-1.5', description='Spawn y [m]'),
        DeclareLaunchArgument('yaw', default_value='0.0', description='Spawn yaw [rad]'),
        DeclareLaunchArgument('publish_odom_tf', default_value='true',
                              description='Bridge the DiffDrive odom TF to /tf'),
        OpaqueFunction(function=_launch_setup),
    ])
