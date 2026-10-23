# EdgeAI 机器人工作空间

这是一个面向Gazebo中真实差速驱动机器人的ROS 2工作空间，提供RViz可视化、LiDAR、RGB-D相机以及基于SLAM Toolbox的建图功能。

## 比赛系统前期准备

本仓库现已加入五人比赛项目的初版共享工程协议。请从[`docs/README.md`](docs/README.md)开始阅读，其中包含：

- 目标系统架构、命名空间、TF树、ROS 2端点、QoS、状态机、安全协议和持久化文件格式；
- P1～P5的详细职责、负责边界、模块交接和验收标准；
- 分阶段集成计划和关键依赖链；
- ROS包/节点布局、首版Task 1策略、Mock及测试计划；
- 比赛规则草案中的假设、冲突以及尚未确定的官方参数清单。

共享ROS 2消息、服务和动作定义位于`src/edgeai_robot_interfaces`。Task 1和Task 2B的机器可读格式位于`schemas/`；`config/competition_parameters.yaml`则将尚未确认的官方参数与仅用于测试的开发默认值严格分开。

这些新增内容完成的是接口定义和前期准备，并不表示自主探索、ArUco感知、Nav2、多机器人救援或本地LLM执行已经实现。

## 运行环境

- Ubuntu 24.04（x86-64）。
- Gazebo Harmonic。
- 首选由**Pixi**管理的ROS 2 Jazzy，使用`pixi.toml`中配置的RoboStack Jazzy和conda-forge软件源。
- 也支持安装在`/opt/ros/jazzy`中的系统ROS 2 Jazzy；系统依赖安装脚本为`tools/install_system_ros_deps.sh`。
- 系统具有能够运行Gazebo和RViz的图形桌面。

项目清单和锁文件定义了**唯一的标准环境**。感知开发、团队联调、里程碑验收和比赛机器必须使用Pixi。系统ROS只用于非感知模块的本地开发：Ubuntu 24.04自带OpenCV 4.6，与Pixi固定的OpenCV 4.12系列不同，ArUco接口和检测行为也不同，因此系统ROS下的感知结果不能作为验收证据。

Pixi环境包含Nav2完整导航栈、SLAM Toolbox、rosbag2（含MCAP存储）、cv_bridge、OpenCV 4.12及契约校验所需的jsonschema和PyYAML。升级OpenCV或ROS依赖必须经相关负责人审核后执行`pixi lock`并提交更新后的`pixi.lock`。

每台开发机首次准备或依赖更新后，在仓库根目录执行环境检查：

```bash
pixi run build
pixi run check-env
```

使用系统ROS时运行`python3 tools/check_environment.py --allow-system-opencv`，OpenCV不一致会降级为警告，但仍会明确提示。

在Pixi和系统ROS之间切换前，必须先删除`build/`、`install/`和`log/`再重新构建，否则CMake缓存会混用两套环境的路径。

## 安装与构建

```bash
git clone https://github.com/hzc333/edgeai_robot_ws.git
cd edgeai_robot_ws
git remote add upstream https://github.com/dongjw-hit/edgeai_robot_ws.git   # 组织方基线，只读
pixi install --locked
pixi run build
```

常用命令：`pixi run build`（`colcon build --symlink-install`）、`pixi run test`（全部包的测试）、`pixi run validate`（共享契约检查）、`pixi run check-env`（环境一致性检查）。协作流程见[小组GitHub协作流程](docs/team_collaboration.md)。

请在仓库根目录运行这些命令。修改ROS包资源或新增配置文件后，需要重新构建。

使用系统ROS 2 Jazzy时执行：

```bash
./tools/install_system_ros_deps.sh  # 每台机器首次准备时执行
source /opt/ros/jazzy/setup.bash
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
colcon build --symlink-install
```

## 启动仿真

在仓库根目录运行：

```bash
./start_sim.sh        # 1台机器人robot_1
./start_sim.sh 2      # robot_1和robot_2，最多4台
```

该脚本会根据自身位置确定工作空间路径，优先激活Pixi环境；若Pixi不可用，则加载系统ROS 2 Jazzy。随后它加载`install/setup.bash`，导出`EDGEAI_CONFIG_DIR`，启动`edgeai_robot_bringup`的`sim_multi_robot.launch.py`并打开RViz（1台时用`realistic_robot.rviz`，多台时用`multi_robot.rviz`）。运行前必须已完成构建。在脚本所在终端按**Ctrl+C**即可停止整个会话。

多机器人约定见[ADR-0002](docs/decisions/0002-multi-robot-tf-and-naming.md)：每台机器人的话题位于`/robot_N/`下，坐标系带`robot_N/`前缀，出生位姿在`config/sim/robots.yaml`中。不带图形界面运行（CI或远程机）：

```bash
ros2 launch edgeai_robot_bringup sim_multi_robot.launch.py robots:=robot_1,robot_2 headless:=true
```

单独的启动文件：`edgeai_robot_description`中的`sim_world.launch.py`（世界和`/clock`，只启动一次）和`sim_robot.launch.py`（一台机器人，参数`robot_id`、`x`、`y`、`yaw`）。`simulation_real.launch.py`保留为“世界加robot_1”的兼容入口。

可移植的真实模型启动流程已经测试通过。AMCL定位仍属于本地实验，其启动文件和参数文件没有包含在本仓库中。环境中已安装AMCL依赖并不表示定位或自主导航已经完成。

## 在其他终端中使用ROS命令

每打开一个额外终端，都需要进入克隆后的仓库并激活项目环境：

```bash
cd /path/to/edgeai_robot_ws
pixi shell
source install/setup.bash
```

使用系统ROS时改为：

```bash
cd /path/to/edgeai_robot_ws
source /opt/ros/jazzy/setup.bash
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
source install/setup.bash
```

请将`/path/to/edgeai_robot_ws`替换为实际克隆路径。以下命令均假设已经完成上述设置，并且仿真正在运行。

### 主要话题

下表以`robot_1`为例，其他机器人把前缀换成`robot_N`。

| 话题 | ROS消息类型 | 用途 |
| --- | --- | --- |
| `/robot_1/cmd_vel` | `geometry_msgs/msg/Twist` | 机器人速度指令 |
| `/robot_1/odom` | `nav_msgs/msg/Odometry` | Gazebo差速驱动里程计 |
| `/robot_1/joint_states` | `sensor_msgs/msg/JointState` | 仿真关节状态 |
| `/robot_1/scan` | `sensor_msgs/msg/LaserScan` | LiDAR扫描数据（Best Effort） |
| `/robot_1/imu` | `sensor_msgs/msg/Imu` | IMU（100 Hz） |
| `/robot_1/camera/image` | `sensor_msgs/msg/Image` | RGB图像，帧`robot_1/camera_optical_frame` |
| `/robot_1/camera/depth_image` | `sensor_msgs/msg/Image` | 深度图像 |
| `/robot_1/camera/camera_info` | `sensor_msgs/msg/CameraInfo` | 相机标定信息 |
| `/robot_1/robot_description` | `std_msgs/msg/String` | 机器人模型 |
| `/tf` | `tf2_msgs/msg/TFMessage` | 全局动态TF，包括`robot_1/odom` → `robot_1/base_footprint` |
| `/tf_static` | `tf2_msgs/msg/TFMessage` | 全局静态TF |
| `/clock` | `rosgraph_msgs/msg/Clock` | 仿真时间 |
| `/map` | `nav_msgs/msg/OccupancyGrid` | SLAM Toolbox运行时生成的占据栅格地图 |

单机器人RViz配置使用`robot_1/odom`作为固定坐标系，多机器人配置使用`map`（需要SLAM或定位运行后才有）。查看话题和一条里程计消息：

```bash
ros2 topic list
ros2 topic echo /robot_1/odom --once
```

### 移动与停止

确认机器人前方没有障碍后，发送低速前进指令：

```bash
ros2 topic pub --rate 10 /robot_1/cmd_vel geometry_msgs/msg/Twist \
  '{linear: {x: 0.1}, angular: {z: 0.0}}'
```

按**Ctrl+C**停止发布器，然后必须显式发送零速度指令：

```bash
ros2 topic pub --once /robot_1/cmd_vel geometry_msgs/msg/Twist \
  '{linear: {x: 0.0}, angular: {z: 0.0}}'
```

不能把“停止速度发布器”等同于“机器人已经收到停止命令”。速度安全链（[ADR-0003](docs/decisions/0003-velocity-safety-chain.md)）上线后，`/robot_N/cmd_vel`只由`safety_watchdog`发布，手动控制改为在开发模式下发布到`/robot_N/cmd_vel_manual`。

## 使用SLAM Toolbox建图

保持仿真运行。在另一个已完成环境准备的终端中，从仓库根目录执行：

```bash
ros2 launch slam_toolbox online_async_launch.py \
  slam_params_file:="$PWD/src/edgeai_robot_description/config/slam_toolbox.yaml" \
  use_sim_time:=true
```

仓库配置为`robot_1`建图：使用`/robot_1/scan`、`robot_1/base_footprint`、`robot_1/odom`和`map`，启用建图模式，地图分辨率为0.05米。仿真时间来自桥接后的`/clock`话题。仿真启动脚本不会自动启动SLAM。

SLAM启动后，在RViz中将**Fixed Frame**设置为`map`，并添加一个订阅`/map`的**Map**显示项。让机器人在空旷区域缓慢行驶以收集扫描数据，并适当回到已经观察过的区域。避免机器人长时间接触墙壁或障碍物。

### 保存占据栅格地图

SLAM正在运行且`/map`可用时，在另一个已准备好的终端中，从仓库根目录执行：

```bash
mkdir -p maps
ros2 run nav2_map_server map_saver_cli -f "$PWD/maps/my_map" \
  --ros-args -p use_sim_time:=true
```

该命令会生成`maps/my_map.yaml`及其对应的地图图像。每次需要保留新地图时，请使用新的文件基本名称。这些文件是占据栅格地图导出结果，并不是可用于恢复SLAM建图会话的SLAM Toolbox序列化位姿图。

ROS包中还包含`src/edgeai_robot_description/maps/edgeai_arena.yaml`及对应地图图像。保存`maps/my_map`不会覆盖包内自带地图。

## 与组织方指南的差异（ADR-0002）

本仓库对组织方基线做了两处几何修正，`Initial_Robot_Simulation_and_SLAM_Guide.md`中的部分数值因此不再适用：

- **`base_footprint`位于驱动轮轴中点。**原基线的`base_footprint`在`base_link`正下方，比实际旋转中心靠后0.0875 m，原地旋转约180°会产生约0.18 m的里程计误差。修正后，`lidar_link`相对`base_footprint`约为(0.0125, 0.080, 0.155) m，`camera_link`约为(0.0875, 0, 0.100) m。
- **相机图像使用光学坐标系。**`/camera/image`、`/camera/depth_image`和`/camera/camera_info`的`frame_id`为`camera_optical_frame`（x右、y下、z前）。原基线的零旋转兼容TF已删除。
- **仿真不再桥接`/camera/points`。**Gazebo的RGB-D点云数据使用`camera_link`轴向（x朝前），却以`camera_optical_frame`作为帧名，数据与帧名不一致。需要点云时，请用`depth_image_proc`由深度图和CameraInfo生成。实机RealSense驱动的点云不受影响。

## 已知限制：碰撞时里程计漂移

根据已有运动测试，机器人正常直线行驶时，Gazebo与RViz中的运动保持同步，显式零速度命令也可以让机器人停止。但机器人接触墙壁或障碍物后，Gazebo中的实体运动会停止，而`/odom`可能继续变化，RViz中的机器人也会继续移动。

当前`/odom`来自Gazebo DiffDrive插件。应将其视为估计值，而不是经过碰撞修正的真实位置：机器人受阻或车轮打滑时，车轮运动与实际位移可能不一致。该碰撞漂移问题目前仍未解决。机器人受阻后应立即停止；建图时避免主动撞击障碍物；不要把RViz中的持续移动理解为Gazebo中的真实物理运动。SLAM并不能保证自动修正这一问题。

## 仓库结构

```text
pixi.toml / pixi.lock                 Pixi环境和依赖锁文件
start_sim.sh                          仿真与RViz统一启动入口
tools/install_system_ros_deps.sh     系统ROS 2 Jazzy依赖安装与rosdep初始化
tools/check_environment.py           当前终端环境与标准环境一致性检查
tools/validate_project_contracts.py 接口、Schema、样例和配置契约检查
src/edgeai_robot_description/
  launch/simulation_real.launch.py   真实模型仿真与ROS–Gazebo桥接
  urdf/edgeai_robot_real.urdf.xacro  当前机器人模型
  worlds/empty.sdf                   Gazebo仿真世界
  rviz/realistic_robot.rviz          RViz配置
  config/slam_toolbox.yaml           SLAM建图参数
  maps/                              包内地图资源
src/edgeai_robot_interfaces/         比赛系统共享ROS 2接口
docs/                                架构、职责和集成计划
schemas/                             目标列表及任务计划JSON Schema
examples/interfaces/                 目标与任务格式的有效样例
config/competition_parameters.yaml  官方TBD参数与开发默认值
config/interface_runtime.yaml       统一QoS、频率、超时和身份规则
config/development_scenarios.yaml   开发Marker及固定测试场景
config/team_assignments.yaml         P1～P5人员分配记录
CONTRIBUTING.md                      Git协作、审核与发布流程
```
