# edgeai_robot_navigation

P1负责的导航包：每台机器人的Nav2和AMCL配置与启动，以及开发用的地图服务器。

| 项目 | 内容 |
|---|---|
| 负责人 | P1（hzc333） |
| 已完成 | 单机器人和双机器人在已知地图上导航（2026-10-24仿真验证） |
| 未实现 | `localization`节点和`/robot_N/relocalize`服务（P1计划3-02）；目前初始位姿需手动发布、导航需手动激活 |

## 1. 文件清单

| 文件 | 作用 |
|---|---|
| `config/nav2_sim.yaml` | 一台机器人的Nav2和AMCL参数模板，含占位符`<ROBOT>`、`<MAX_LINEAR>`、`<MAX_ANGULAR>` |
| `launch/nav_robot.launch.py` | 在`/robot_N`命名空间启动Nav2（可选AMCL），生成该机器人的参数文件 |
| `launch/dev_map_server.launch.py` | **仅开发**：在全局`/map`上发布已保存的地图。比赛中`/map`由P2的`map_manager`提供 |
| `edgeai_robot_navigation/__init__.py` | Python包入口，目前没有节点 |
| `test/test_copyright.py`、`test_flake8.py`、`test_pep257.py` | 版权头、代码风格和文档字符串检查 |
| `setup.py`、`setup.cfg`、`package.xml`、`resource/` | `ament_python`包配置；`launch/*.py`和`config/*.yaml`安装到包共享目录 |

## 2. nav_robot.launch.py

```bash
ros2 launch edgeai_robot_navigation nav_robot.launch.py robot_id:=robot_1 mode:=amcl
```

一般不单独启动，而是通过`edgeai_robot_bringup`的`robot_stack.launch.py nav_mode:=amcl`（或`sim_multi_robot.launch.py nav_mode:=amcl`）启动。

| 参数 | 默认值 | 说明 |
|---|---|---|
| `robot_id` | `robot_1` | 命名空间和帧前缀 |
| `mode` | `amcl` | `amcl`：用AMCL在共享`/map`上定位（Task 2）；`slam`：不启动AMCL，由SLAM提供`map -> robot_N/odom`（Task 1） |
| `run_mode` | `development` | 用于解析速度上限 |
| `config_dir` | 搜索 | 仓库根目录`config/` |
| `use_sim_time` | `true` | 实机设为`false` |
| `params_file` | 包内`config/nav2_sim.yaml` | 参数模板 |
| `autostart_navigation` | `auto` | `auto`：`slam`模式自动激活，`amcl`模式**不自动激活**（见2.2节）；也可设为`true`/`false` |
| `autostart_localization` | `true` | 立即激活AMCL；`localization`节点完成后改为由它管理 |

### 2.1 启动内容

在`/robot_N`命名空间中启动：`controller_server`、`smoother_server`、`planner_server`、`behavior_server`、`velocity_smoother`、`collision_monitor`、`bt_navigator`和`lifecycle_manager_navigation`；`mode:=amcl`时另外启动`amcl`和`lifecycle_manager_localization`。

关键约定：

- **不把`/tf`重映射到命名空间内**（与Nav2自带的`navigation_launch.py`不同），所有机器人共用全局`/tf`，帧名带`robot_N/`前缀（ADR-0002）。
- **参数文件以机器人ID为根键**。ROS 2按完整节点名匹配参数文件中的键，`/robot_1/controller_server`的参数必须写在`robot_1: controller_server:`下，否则节点会**静默使用默认参数**。启动文件读取模板、替换占位符、套上根键后写到临时目录。
- **速度链**：控制器 → `cmd_vel_nav` → 平滑器 → `cmd_vel_smoothed` → 碰撞监视器 → `cmd_vel_safe_in` → `safety_watchdog` → `/robot_N/cmd_vel`（ADR-0003）。Nav2的任何节点都不直接发布`/robot_N/cmd_vel`。
- **速度上限**：`<MAX_LINEAR>`、`<MAX_ANGULAR>`取自按运行模式解析的`motion.max_linear_speed_mps`和`motion.max_angular_speed_radps`，与看门狗一致。

### 2.2 启动顺序：先定位，再激活导航

Nav2激活时，代价地图必须拿到`map -> robot_N/base_footprint`。拿不到时会在超时后失败，生命周期管理器会**永久放弃**启动。AMCL模式下，这个变换要等机器人收到初始位姿后才有，所以默认不自动激活导航。正确顺序：

```bash
# 1. 设置初始位姿（以后由relocalize服务完成）
ros2 topic pub --once /robot_1/initialpose geometry_msgs/msg/PoseWithCovarianceStamped \
  "{header: {frame_id: map}, pose: {pose: {orientation: {w: 1.0}}, covariance: [0.01,0,0,0,0,0, 0,0.01,0,0,0,0, 0,0,0,0,0,0, 0,0,0,0,0,0, 0,0,0,0,0,0, 0,0,0,0,0,0.01]}}"
# 2. 激活导航
ros2 service call /robot_1/lifecycle_manager_navigation/manage_nodes \
  nav2_msgs/srv/ManageLifecycleNodes "{command: 0}"
```

计划3-02的`localization`节点会在`relocalize`成功后自动执行第2步。

## 3. 主要参数（`config/nav2_sim.yaml`）

以Pixi环境中Nav2 1.3.10的默认参数为基础，只保留本项目用到的节点。

| 节点 | 参数 | 值 | 说明 |
|---|---|---|---|
| 全部 | 机器人参考帧 | `robot_N/base_footprint` | 驱动轮轴中点（ADR-0002） |
| 两个代价地图 | `footprint` | `[[0.115, 0.175], [0.115, -0.175], [-0.315, -0.175], [-0.315, 0.175]]` | 机器人大部分在轴后方，原地旋转时后角扫过半径约0.36 m |
| | 膨胀半径 / 代价衰减 | 0.35 m / 3.0 | |
| 局部代价地图 | 尺寸 / 分辨率 | 3 m × 3 m滚动窗口 / 0.05 m | 障碍层使用`/robot_N/scan` |
| 全局代价地图 | 静态层`map_topic` | `/map`（绝对名） | 默认的相对名会变成`/robot_N/map` |
| | `track_unknown_space` | `true` | |
| `controller_server` | 控制器 | Regulated Pure Pursuit | 差速、低速、小场地 |
| | 期望线速度 / 原地转向角速度 | `<MAX_LINEAR>` / `<MAX_ANGULAR>` | 开发值0.15 m/s / 0.30 rad/s |
| | 前视距离 | 0.4 m（0.25～0.6） | |
| | 先原地转向 | 是，偏差超过0.785 rad时 | 不允许倒车 |
| | 目标容差 | xy 0.05 m，yaw 0.25 rad | 必须小于任何请求的容差（救援到达0.08 m）：Nav2进入容差后即停止，重复发送同一目标不会再移动。每个目标自己的容差由`robot_agent`检查 |
| | 无进展判定 | 10 s内移动不足0.10 m | |
| `planner_server` | 规划器 | NavFn，`allow_unknown: true`，容差0.25 m | Task 1需要穿越未知区域规划 |
| `behavior_server` | 恢复行为 | spin、backup、drive_on_heading、wait | 最大转速`<MAX_ANGULAR>` |
| `velocity_smoother` | 速度范围 | `[-0.05, <MAX_LINEAR>]` m/s，±`<MAX_ANGULAR>` rad/s | 加速度±0.5 m/s²、±1.0 rad/s² |
| `collision_monitor` | 停车区 | 足迹外扩0.05 m | 数据源`/robot_N/scan`，`min_height: 0.05`（LiDAR高0.155 m，默认0.15会丢掉大部分点） |
| | 减速区 | 足迹外扩0.20 m，速度减半 | |
| `amcl` | 帧和话题 | `map`、`robot_N/odom`、`robot_N/base_footprint`、`/robot_N/scan`、`/map` | |
| | 粒子数 / 激光量程 | 500～2000 / 0.15～12 m | |
| | `set_initial_pose` | `false` | 初始位姿只通过`initialpose`（以后是`relocalize`）给出 |

## 4. dev_map_server.launch.py

```bash
ros2 launch edgeai_robot_navigation dev_map_server.launch.py map:=/path/to/map.yaml
```

默认地图是`edgeai_robot_description`的`maps/edgeai_arena.yaml`。这张地图的`map`坐标系原点在robot_1的出生点：世界坐标 = map坐标 + (-1.5, -1.5)，所以robot_1在map中的初始位姿是(0, 0, 0)，robot_2是(0, 0.7, 0)。

## 5. 验证

```bash
pixi run test      # 目前本包只有代码风格检查
```

运行验证（无界面Gazebo，2026-10-24）：

```bash
ros2 launch edgeai_robot_bringup sim_multi_robot.launch.py robots:=robot_1 headless:=true \
  require_competition_state:=false nav_mode:=amcl
ros2 launch edgeai_robot_navigation dev_map_server.launch.py
# 按2.2节设置初始位姿并激活导航，然后用NavigateToPose动作发送目标：
ros2 action send_goal /robot_1/navigate_to_pose nav2_msgs/action/NavigateToPose \
  "{pose: {header: {frame_id: map}, pose: {position: {x: 3.3, y: 3.3}, orientation: {w: 1.0}}}}"
```

| 测试 | 结果 |
|---|---|
| 单机器人连续10个目标（四角、窄处、障碍物旁、需要掉头的点） | Nav2全部成功（10/10），每个16～30 s；与Gazebo真实位置的最终误差0.02～0.16 m，9个在0.15 m以内 |
| 两台机器人同时导航到不同角落 | 两台都成功，误差约0.10 m，共69 s |
| 测试前后`/robot_N/cmd_vel`的发布者 | 始终只有1个（看门狗） |

最终误差包括目标检查器允许的0.10 m和AMCL定位误差。

## 6. 已知限制

- `relocalize`服务和`localization`节点尚未实现：初始位姿要手动发布，AMCL模式下导航要手动激活（2.2节）。
- 两台机器人交会时，控制器出现过几次“controller patience exceeded”和“failed to make progress”，都由恢复行为自动处理，目标最终成功。双机器人协调和参数调整留到P1计划阶段3。
- 每个目标的精确容差、失败和取消后确认零速度由`edgeai_robot_bringup`的`robot_agent`实现。
- 上表10个目标的测试是在目标容差为0.10 m时做的；收紧到0.05 m后，通过`robot_agent`的精确目标测试成功（见bringup README）。
- AMCL报告的协方差在行驶中持续变宽（约0.31 m），可能是运动噪声参数偏大，待阶段3调参。
- 参数只针对仿真；实机参数等实机接入时再定（计划阶段5）。
