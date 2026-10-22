#!/usr/bin/env bash
set -euo pipefail

sudo apt-get update
sudo apt-get install -y \
  ros-jazzy-joint-state-publisher \
  ros-jazzy-xacro \
  ros-jazzy-ros-gz \
  ros-jazzy-slam-toolbox \
  ros-jazzy-navigation2 \
  ros-jazzy-nav2-bringup \
  ros-jazzy-rmw-cyclonedds-cpp \
  ros-jazzy-tf2-tools \
  ros-jazzy-rosbag2 \
  ros-jazzy-rosbag2-storage-mcap \
  ros-jazzy-cv-bridge \
  python3-jsonschema \
  python3-yaml \
  ros-dev-tools

if [[ ! -f /etc/ros/rosdep/sources.list.d/20-default.list ]]; then
  sudo rosdep init
fi
rosdep update

printf '\nROS 2项目依赖与rosdep初始化已完成。\n'
printf '注意：Ubuntu 24.04自带OpenCV 4.6，与Pixi固定的版本不同，ArUco接口也不同。\n'
printf '系统ROS只用于非感知模块的本地开发；感知开发、联调和验收必须使用Pixi环境。\n'
read -r -p '按Enter关闭此窗口……'
