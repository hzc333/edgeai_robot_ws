# P3 视觉感知：单机器人目标检测（Phase 3）

本目录实现相机光学坐标系下的 ArUco 检测/位姿估计、RGB-D 深度校验、
反投影和刚体坐标变换，以及单机器人 ROS 2 检测节点。节点只发布原始
`TargetObservation`，不查询 TF、不做多机器人融合或生成救援区。

## 文件

- `edgeai_target_perception/__init__.py`：独立算法包入口。
- `edgeai_target_perception/aruco_core.py`：配置适配、ArUco 检测、IPPE 候选筛选、RGB-D 一致性和二义性诊断。
- `edgeai_target_perception/geometry.py`：深度单位转换、带畸变的像素反投影、刚体变换及 M→T 转换。
- `edgeai_target_perception/target_detector.py`：ROS 2 单机器人节点及观察消息转换。
- `launch/target_detector.launch.py`：在 `robot_N` 命名空间启动节点。
- `test/`：几何与 ROS 消息转换合成测试。

## 依赖与测试

项目标准环境使用 OpenCV 4.12、NumPy、PyYAML、ROS 2 Jazzy 和 `cv_bridge`。
算法要求 `cv2.aruco.ArucoDetector`；配置入口复用 `edgeai_common.config` 的统一解析，
比赛模式继续执行 official 参数门禁。本包不引入新依赖、不更改 Pixi 配置或共享消息。

从仓库根目录在现有 Pixi 环境构建并测试：

```bash
pixi run colcon build --packages-up-to edgeai_target_perception --symlink-install
pixi run colcon test --packages-select edgeai_target_perception
```

启动单机器人节点（topic 按 `robot_id` 解析为机器人前缀路径）：

```bash
ros2 launch edgeai_target_perception target_detector.launch.py \
  robot_id:=robot_1 run_mode:=development use_depth:=false
```

输入为 `camera/image`、`camera/camera_info` 和可选的 `camera/depth_image`；
输出为 `target_observations`，比赛状态从全局 `/competition/state` 读取。
启用深度可设置 `use_depth:=true`。16UC1 深度按 ROS 约定解释为毫米，32FC1 按米解释；
深度帧必须属于同一光学坐标系、尺寸匹配，时间戳差不得超过 `depth_sync_tolerance_s`
（默认 0.05 秒）。深度暂缺或过期时以纯 PnP 继续，但歧义位姿不会发布。

## 使用

把 `src/edgeai_target_perception` 和 `src/edgeai_common` 加入 `PYTHONPATH`。

```python
from edgeai_target_perception.aruco_core import ArucoCore

core = ArucoCore.from_repository_config('development', config_dir='config')
# image: uint8 灰度或 BGR；K: 3x3 内参；D: OpenCV 畸变系数或 None。
results = core.detect(image, K, D)
for result in results:
    if result.valid:
        print(result.identity.target_id, result.rvec, result.tvec,
              result.reprojection_error_px)
    else:
        print(result.marker_id, result.rejection_reason)
```

也可用 `from_resolved_parameters(parameters)` 消费公共解析器结果；不重复实现 official/development
回退。competition 保留公共解析器的全部官方参数门禁。正式官方参数尚未公布时不能静默回退。

算法入口 `estimate_pose(marker_id, corners, K, D)` 支持直接测试已知角点。
角点遵守 `docs/marker_and_rescue_geometry.md`：TL/TR/BR/BL，对应
`(-L/2,+L/2,0)`、`(+L/2,+L/2,0)`、`(+L/2,-L/2,0)`、`(-L/2,-L/2,0)`。
物理尺寸是黑框外沿边长（米）。用 `SOLVEPNP_IPPE_SQUARE` 求候选解，要求所有角点在
相机前方，按重投影 RMS 最小选解。`rvec/tvec` 表示 M→相机光学帧，满足
`p_camera = Rodrigues(rvec) @ p_marker + tvec`，不进行 M→T 或 map 变换。

重投影误差定义为四角点二维欧氏残差的 RMS，单位像素。
可显式传入 `max_reprojection_error_px` 拒绝高误差解；现有配置没有该阈值，默认仅计算，
不擅自写入比赛参数。`ambiguity` diagnostics 比较正深度 IPPE 候选的重投影误差间距和姿态差异；
默认 1 px 内标记为 ambiguous，但诊断本身不拒绝位姿，且可由构造参数调整。未知 ID
返回 `unknown_marker_id`，identity/位姿为空，valid=false。
调用者必须检查 valid，不能仅凭有 tvec 就接受结果。PnP 失败、退化角点、无正深度解均返回
拒绝原因；无检测返回空列表；非法输入或配置抛出 ValueError。

RGB-D 调用可传入 `depth_image`、`depth_scale_m` 和 `depth_tolerance_m`。深度图必须已与彩色图
配准且尺寸一致；提供深度图时必须显式提供尺度（例如 uint16 毫米深度用 `0.001`，浮点米深度用 `1.0`），
因为仓库当前没有规定传感器深度编码。
零、负值和非有限样本转换为 NaN；单位转换结果以米表示。PnP 候选在 Marker 内部的九个位置
采样局部有效深度，至少三个位置可用时计算深度误差中位数，超容差候选被拒绝；没有足够有效
采样返回 `depth_unavailable`，没有一致候选返回 `depth_inconsistent`。深度只用于已配准图像，
不执行时间同步或重配准。

`back_project_pixels` 将像素及米制深度反投影到 `camera_optical_frame`，畸变使用 OpenCV 的
`undistortPoints`。`RigidTransform` 提供右手刚体变换、逆和组合；组合 `A.compose(B)` 先应用
B 再应用 A。`marker_to_target_pose` 按几何协议右乘固定 `R_M_T`，并保持 Marker 中心平移不变。

ROS 节点验证图像和 CameraInfo 的 frame 为 `robot_N/camera_optical_frame`，拒绝无效标定、
不匹配分辨率和不支持的图像编码。仅当 `/competition/state` 在 3 秒内更新、含非空 `run_id`，
且处于 Task 1/Task 2A/Task 2B 非冻结、非急停阶段时发布。消息 Header 使用 RGB 图像的时间戳
和光学 frame；位姿为 Marker→相机光学帧，四元数由 Rodrigues 旋转生成。
未知 Marker ID、PnP 失败、深度不一致和二义性结果不发布。confidence 是由重投影 RMS 导出的
启发式分数，不是校准概率；没有经过测量验证的协方差时，消息以高对角协方差表示不确定性。

## 验证范围与限制

测试覆盖已知位姿合成图像、不同距离/倾角、轻微模糊、普通/协同/未知 ID、畸变参数、
重投影误差、双解选择、负深度/角点穿越相机平面、空图像和错误输入。
合成图像测试容差为距离的 2.5%、姿态 0.12 rad、重投影 1 px，只用于回归，非比赛验收标准。

输入图像必须与标定分辨率一致；RGB 输入应先转 BGR/灰度，鱼眼模型不属于此入口。
平面 PnP 存在二义性，最小重投影误差不能保证真实解；二义性诊断不等于概率置信度，
本阶段不输出未经标定的置信度或协方差。尚无真实相机数据集、遮挡/强模糊性能证明、
时间同步或深度与图像配准验证。
本阶段不修改现有 ROS 消息、Schema、配置或几何协议。

Phase 1 和 Phase 2 的合成单元测试应在项目 Linux Pixi 环境中运行；不增加依赖。

## 单机器人 Gazebo 集成测试

集成 fixture 位于 `test/fixtures/aruco_test_world.sdf`，不会改动正式竞赛世界。
Marker 是 DICT_4X4_50、ID 1，黑框外沿边长 0.15 m；模型用黑白几何格和白色底板构造，
外侧留有 quiet zone。生成的 PNG 是参考图像，不依赖 Gazebo 的纹理渲染。
它位于 robot_1 相机前方约 0.9 m，
正面法线朝向相机并绕竖直轴偏转约 0.4 rad。位姿按 robot_1 出生位置及 xacro 中
`camera_link`/`camera_optical_frame` 变换计算，而不是将 Gazebo 世界轴误认为相机光学轴。

在仓库根目录用已有 Pixi 环境构建并生成模型和 PNG 参考图：

```bash
pixi run colcon build --packages-up-to edgeai_robot_bringup edgeai_robot_description edgeai_target_perception --symlink-install
pixi run python src/edgeai_target_perception/test/fixtures/generate_aruco_marker.py
```

**终端 A：** 启动独立测试世界及 robot_1。`GZ_SIM_RESOURCE_PATH` 让 Gazebo 找到 Marker
模型。该命令不运行 `start_sim.sh`，因此不启动正式世界、RViz 或 robot stack。

```bash
cd /home/xiaomin/projects/edgeai_robot_ws
pixi shell
source install/setup.bash
export EDGEAI_CONFIG_DIR="$PWD/config"
export GZ_SIM_RESOURCE_PATH="$PWD/src/edgeai_target_perception/test/fixtures${GZ_SIM_RESOURCE_PATH:+:$GZ_SIM_RESOURCE_PATH}"
export ROS_DOMAIN_ID=67
export ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
ros2 launch edgeai_robot_bringup sim_multi_robot.launch.py \
  robots:=robot_1 \
  world:="$PWD/src/edgeai_target_perception/test/fixtures/aruco_test_world.sdf" \
  headless:=true rviz:=false stack:=false config_dir:="$PWD/config"
```

**终端 B：** 持续发布临时 Task 1 状态，使用与 detector `control_state` 订阅匹配的可靠、
Transient Local QoS。持续发布满足 3 秒状态新鲜度限制：

```bash
cd /home/xiaomin/projects/edgeai_robot_ws
pixi shell
source install/setup.bash
export ROS_DOMAIN_ID=67
export ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
ros2 topic pub -r 1 --qos-reliability reliable --qos-durability transient_local \
  /competition/state edgeai_robot_interfaces/msg/CompetitionState \
  "{run_id: 'run-p3-gazebo-test', phase: 1, frozen: false, estop_active: false}"
```

**终端 C：** 先检查真实 ROS 图像、标定、深度和时钟，然后启动 detector：

```bash
cd /home/xiaomin/projects/edgeai_robot_ws
pixi shell
source install/setup.bash
export EDGEAI_CONFIG_DIR="$PWD/config"
export ROS_DOMAIN_ID=67
export ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
ros2 topic echo /clock --once
ros2 topic echo /robot_1/camera/image --once --field header.frame_id --qos-profile sensor_data
ros2 topic echo /robot_1/camera/image --once --field encoding --qos-profile sensor_data
ros2 topic echo /robot_1/camera/camera_info --once --field header.frame_id --qos-profile sensor_data
ros2 topic echo /robot_1/camera/camera_info --once --field k --qos-profile sensor_data
ros2 topic echo /robot_1/camera/depth_image --once --field encoding --qos-profile sensor_data
ros2 run tf2_ros tf2_echo robot_1/camera_link robot_1/camera_optical_frame
ros2 launch edgeai_target_perception target_detector.launch.py \
  robot_id:=robot_1 run_mode:=development config_dir:="$PWD/config" use_depth:=true
```

**终端 D：** 等待观察消息：

```bash
cd /home/xiaomin/projects/edgeai_robot_ws
pixi shell
source install/setup.bash
export ROS_DOMAIN_ID=67
export ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
ros2 topic echo /robot_1/target_observations \
  edgeai_robot_interfaces/msg/TargetObservation --once --timeout 30 \
  --qos-reliability best_effort
```

验收字段：`marker_id=1`、`target_id=T1`、`robot_id=robot_1`、
`run_id=run-p3-gazebo-test`，frame 为 `robot_1/camera_optical_frame`，Header stamp 与触发
该检测的 RGB 图像时间戳相同。核对 RGB 和深度的 frame/尺寸/时间戳及 depth encoding；
深度同步误差应不超过默认 0.05 秒。测试后在各终端 Ctrl+C 停止模拟器、detector 和状态发布。

### WSL2 实测结果

- Gazebo Harmonic 8.10.0 成功加载独立 `aruco_test` 世界并生成 robot_1；ROS `/clock`、
  RGB、CameraInfo、深度和 TF 均有数据。
- RGB 为 `640x480 rgb8`，深度为 `640x480 32FC1`；相机图像、深度和 CameraInfo 的 frame
  均为 `robot_1/camera_optical_frame`。
- `camera_link` 到 `camera_optical_frame` 的静态变换可查到；平移为零，RPY 约为
  `(-1.571, 0, -1.571)`。
- 开启深度模式时收到有效观察：`marker_id=1`、`target_id=T1`、`robot_id=robot_1`、
  `run_id=run-p3-gazebo-test`。观察 Header stamp 与对应 RGB、深度及 CameraInfo stamp
  完全相同，光学 frame 正确；PnP 深度约 `0.897 m`。
- 深度路径通过，本次无需 RGB-only 对照。Gazebo 日志仍出现 `/dev/dri` EGL 权限警告，
  但本次传感器渲染和端到端检测成功；硬件加速状态未单独确认。

若深度模式没有观察，先看 detector 是否报告 `depth_inconsistent`、无效深度或时间同步问题，
随后以 `use_depth:=false` 重启 detector 重测纯 RGB PnP。不要为通过测试而更改 PnP 歧义或深度
拒绝阈值。若 RGB-only 仍未发布，检查 Gazebo 是否找到 Marker 模型、Marker 是否在图像中可见，以及
日志中的 unknown ID、PnP 或 ambiguity 诊断。
