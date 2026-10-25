# edgeai_robot_navigation

P1负责的导航包：每台机器人的Nav2和AMCL配置与启动、提供`/robot_N/relocalize`服务的`localization`节点，以及开发用的地图服务器。

| 项目 | 内容 |
|---|---|
| 负责人 | P1（hzc333） |
| 已完成 | 单机器人和双机器人在已知地图上导航（2026-10-24）；`localization`节点和`relocalize`服务（计划3-02，2026-10-25仿真验收） |
| 已完成（续） | SLAM到AMCL交接的P1侧（计划3-03，2026-10-25仿真演练） |
| 未完成 | 不移动时的全局定位基本无法收敛（如实报告失败）；交接需与P2的`map_manager`联调 |

## 1. 文件清单

| 文件 | 作用 |
|---|---|
| `config/nav2_sim.yaml` | 一台机器人的Nav2和AMCL参数模板，含占位符`<ROBOT>`、`<MAX_LINEAR>`、`<MAX_ANGULAR>`、`<BT_DIR>` |
| `config/navigate_to_pose_edgeai.xml` | `bt_navigator`使用的行为树：Nav2 1.3.10默认树的副本，外层重试从6次减到2次，去掉恢复中的原地旋转（Spin），等待改为2 s。目的是让不可达目标尽快失败，并避免靠墙旋转触发碰撞监视器 |
| `launch/nav_robot.launch.py` | 在`/robot_N`命名空间启动Nav2（可选AMCL），生成该机器人的参数文件 |
| `launch/dev_map_server.launch.py` | **仅开发**：在全局`/map`上发布已保存的地图。比赛中`/map`由P2的`map_manager`提供 |
| `edgeai_robot_navigation/localization.py` | `localization`节点，入口`ros2 run edgeai_robot_navigation localization`，见第3节 |
| `edgeai_robot_navigation/__init__.py` | Python包入口 |
| `test/test_localization.py` | `localization`测试：收敛判定、激光与地图匹配度计算，以及使用模拟AMCL和生命周期管理器的服务行为测试 |
| `test/test_copyright.py`、`test_flake8.py`、`test_pep257.py` | 版权头、代码风格和文档字符串检查 |
| `setup.py`、`setup.cfg`、`package.xml`、`resource/` | `ament_python`包配置；`launch/*.py`、`config/*.yaml`和`config/*.xml`安装到包共享目录 |

## 2. nav_robot.launch.py

```bash
ros2 launch edgeai_robot_navigation nav_robot.launch.py robot_id:=robot_1 mode:=amcl
```

一般不单独启动，而是通过`edgeai_robot_bringup`的`robot_stack.launch.py nav_mode:=amcl`（或`sim_multi_robot.launch.py nav_mode:=amcl`）启动。

| 参数 | 默认值 | 说明 |
|---|---|---|
| `robot_id` | `robot_1` | 命名空间和帧前缀 |
| `mode` | `amcl` | `amcl`：用AMCL在共享`/map`上定位（Task 2）；`slam`：由SLAM提供`map -> robot_N/odom`（Task 1），导航自动激活，AMCL和`localization`节点同时启动但保持未激活，供交接使用 |
| `run_mode` | `development` | 用于解析速度上限 |
| `config_dir` | 搜索 | 仓库根目录`config/` |
| `use_sim_time` | `true` | 实机设为`false` |
| `params_file` | 包内`config/nav2_sim.yaml` | 参数模板 |
| `autostart_navigation` | `auto` | `auto`：`slam`模式自动激活，`amcl`模式**不自动激活**（见2.2节）；也可设为`true`/`false` |
| `autostart_localization` | `false` | `false`：AMCL由`localization`节点在第一次`relocalize`时启动。`slam`模式下设为`true`会导致SLAM和AMCL同时发布`map -> odom`，启动直接报错 |
| `require_competition_state` | `true` | 传给`localization`节点；只有development允许`false`（不检查`run_id`和地图版本） |

### 2.1 启动内容

在`/robot_N`命名空间中启动：`controller_server`、`smoother_server`、`planner_server`、`behavior_server`、`velocity_smoother`、`collision_monitor`、`bt_navigator`、`lifecycle_manager_navigation`、`amcl`、`lifecycle_manager_localization`和`localization`（起点位姿取自解析后的`localization.start_poses`）。两种模式下AMCL都在第一次`relocalize`时才激活。

关键约定：

- **不把`/tf`重映射到命名空间内**（与Nav2自带的`navigation_launch.py`不同），所有机器人共用全局`/tf`，帧名带`robot_N/`前缀（ADR-0002）。
- **参数文件以机器人ID为根键**。ROS 2按完整节点名匹配参数文件中的键，`/robot_1/controller_server`的参数必须写在`robot_1: controller_server:`下，否则节点会**静默使用默认参数**。启动文件读取模板、替换占位符、套上根键后写到临时目录。
- **速度链**：控制器 → `cmd_vel_nav` → 平滑器 → `cmd_vel_smoothed` → 碰撞监视器 → `cmd_vel_safe_in` → `safety_watchdog` → `/robot_N/cmd_vel`（ADR-0003）。Nav2的任何节点都不直接发布`/robot_N/cmd_vel`。
- **速度上限**：`<MAX_LINEAR>`、`<MAX_ANGULAR>`取自按运行模式解析的`motion.max_linear_speed_mps`和`motion.max_angular_speed_radps`，与看门狗一致。

### 2.2 启动顺序：先定位，再激活导航

Nav2激活时，代价地图必须拿到`map -> robot_N/base_footprint`，拿不到会超时失败，生命周期管理器会**永久放弃**启动。AMCL模式下这个变换要等机器人被定位后才有，所以AMCL和导航都不自动激活，而是由`localization`节点在第一次`relocalize`成功后依次启动：

```bash
ros2 service call /robot_1/relocalize edgeai_robot_interfaces/srv/Relocalize \
  "{run_id: run-sim, map_id: map-sim, map_revision: 1, mode: 2, start_pose_id: task1_start}"
```

`run_id`和地图版本必须与当前`/competition/state`一致；`require_competition_state:=false`（仅开发）时不检查。

## 3. localization节点与relocalize服务

提供`/robot_N/relocalize`（`Relocalize`服务，计划3-02），管理本机器人AMCL的生命周期，并在第一次成功后启动导航。调用方应为P2的`system_manager`；**是否允许操作员给位姿提示由调用方检查，本节点不检查**。

### 3.1 流程

1. 检查`run_id`、`map_id`、`map_revision`与最新`CompetitionState`一致（刚启动时最多等2 s接收比赛状态）；同一时刻只处理一个请求。
2. AMCL未激活时，通过`lifecycle_manager_localization/manage_nodes`启动。
3. 按模式给AMCL初始条件：

| 模式 | 做法 |
|---|---|
| `MODE_KNOWN_START_POSE`（2） | 从`localization.start_poses[start_pose_id]`取位姿，以默认协方差（标准差0.10 m / 0.10 rad）发布到`initialpose`，再调用10次`request_nomotion_update`。**前提**：`map`坐标系与场地坐标系一致 |
| `MODE_POSE_HINT`（3） | 使用请求中的`pose_hint`（必须在`map`中）；协方差全为0时用默认值；再调用10次`request_nomotion_update` |
| `MODE_GLOBAL`（1） | 调用`reinitialize_global_localization`，再调用30次`request_nomotion_update`；机器人不移动 |

4. 等待`amcl_pose`的x、y标准差 ≤ 0.10 m且航向标准差 ≤ 0.10 rad，并**连续保持1 s**。
5. **激光与地图匹配度检查**：用估计位姿把当前激光的有效落点（6 m以内）投到`/map`，统计落在占据栅格2格（0.1 m）以内的比例，低于0.6则失败。原因：给错提示时，AMCL可能在错误位置收敛且协方差很小，只看协方差无法发现。
6. 成功后，若导航未激活则通过`lifecycle_manager_navigation/manage_nodes`启动。
7. 失败返回`success=false`、`reason.code=RELOCALIZATION_FAILED`（104）或`CONFIGURATION_INVALID`（901），**绝不在未收敛或不匹配时报告成功**。

每次结果都发布到`/diagnostics`（状态名`robot_N/localization`，失败为ERROR，并以1 Hz重发）；`robot_agent`据此在`RobotState.faults`中报告`CODE_RELOCALIZATION_FAILED`（107）。

### 3.2 SLAM到AMCL的交接（计划3-03）

Task 1以`nav_mode:=slam`运行：SLAM发布`map -> robot_N/odom`，导航已激活，AMCL未激活。交接时按ADR-0002附录的顺序：

1. P2切到`HANDOVER`，看门狗让机器人停车。
2. P2记录SLAM给出的最后位姿（`RobotState.pose`或TF `map -> robot_N/base_footprint`）。
3. P2保存地图、停止SLAM，并由`map_manager`在`/map`上发布冻结地图。
4. P2以`MODE_POSE_HINT`和第2步的位姿调用`/robot_N/relocalize`；本节点启动AMCL并确认收敛和匹配。
5. 之后`map -> robot_N/odom`只由AMCL发布；`robot_agent`在收到`amcl_pose`后自动改用AMCL协方差判断是否定位。

### 3.3 参数

| 参数 | 默认值 | 说明 |
|---|---|---|
| `robot_id`、`run_mode`、`config_dir`、`require_competition_state` | — | 同其他节点 |
| `start_poses_yaml` | `{}` | 起点表（YAML），由启动文件从解析后的参数填入 |
| `convergence_max_xy_std_m`、`convergence_max_yaw_std_rad` | 0.10、0.10 | 收敛判据 |
| `convergence_hold_s` | 1.0 | 收敛需连续保持的时间[s] |
| `default_hint_xy_std_m`、`default_hint_yaw_std_rad` | 0.10、0.10 | 起点或提示未给协方差时使用 |
| `hint_nomotion_updates`、`global_nomotion_updates` | 10、30 | 原地更新次数 |
| `nomotion_update_rate_hz` | 5.0 | 原地更新频率 |
| `scan_match_min_ratio` | 0.6 | 匹配度下限 |
| `scan_match_radius_cells`、`scan_match_max_range_m` | 2、6.0 | 匹配半径（格）和使用的最大距离[m] |
| `activate_navigation` | `true` | 成功后启动导航 |

请求的`timeout`为0时，使用`interface_runtime.yaml`的`timeouts_s.relocalize_default`（30 s）。

## 4. 主要参数（`config/nav2_sim.yaml`）

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
| | 无进展判定 | `PoseProgressChecker`：10 s内移动不足0.10 m**且**转动不足0.3 rad | 默认的`SimpleProgressChecker`只看位移，低速原地转向会被误判为无进展 |
| `bt_navigator` | 行为树 | `<BT_DIR>/navigate_to_pose_edgeai.xml` | `<BT_DIR>`由启动文件替换为本包共享目录下的`config` |
| `planner_server` | 规划器 | NavFn，`allow_unknown: true`，容差0.25 m | Task 1需要穿越未知区域规划 |
| `behavior_server` | 恢复行为 | spin、backup、drive_on_heading、wait | 最大转速`<MAX_ANGULAR>` |
| `velocity_smoother` | 速度范围 | `[-0.05, <MAX_LINEAR>]` m/s，±`<MAX_ANGULAR>` rad/s | 加速度±0.5 m/s²、±1.0 rad/s² |
| `collision_monitor` | 停车区 | 足迹外扩0.05 m | 数据源`/robot_N/scan`，`min_height: 0.05`（LiDAR高0.155 m，默认0.15会丢掉大部分点） |
| | 减速区 | 足迹外扩0.20 m，速度减半 | |
| `amcl` | 帧和话题 | `map`、`robot_N/odom`、`robot_N/base_footprint`、`/robot_N/scan`、`/map` | |
| | 粒子数 / 激光量程 | 500～2000 / 0.15～12 m | |
| | 运动噪声`alpha1`～`alpha4` / `alpha5` | 0.05 / 0.2 | 默认0.2时行驶中标准差涨到约0.31 m；仿真里程计误差小，0.05时峰值约0.19 m，真实误差不变（约0.09 m）。实机需按里程计质量重调 |
| | `set_initial_pose` | `false` | 初始位姿只通过`relocalize`给出 |

## 5. dev_map_server.launch.py

```bash
ros2 launch edgeai_robot_navigation dev_map_server.launch.py map:=/path/to/map.yaml
```

默认地图是`edgeai_robot_description`的`maps/edgeai_arena_world.yaml`：图像与组织方的`edgeai_arena.yaml`相同，但原点平移后`map`坐标系与Gazebo世界坐标系重合，所以`gz model -m robot_N -p`的结果可以直接与地图坐标比较，场地坐标的起点位姿（如`task1_start` = (-1.5, -1.5, 0)）也可以直接使用。

## 6. 验证

```bash
pixi run test      # 本包：localization测试和代码风格检查
```

`test/test_localization.py`覆盖：收敛判定；激光与地图匹配度能区分正确与错误位姿；已知起点会启动AMCL和导航；未知起点被拒绝；位姿提示缺协方差时用默认值；提示不在`map`中被拒绝；全局定位；不收敛时失败并在`/diagnostics`报告ERROR；激光与地图不匹配时失败；成功后失败再成功节点仍存活；`run_id`和地图版本不一致时被拒绝。

运行验证（无界面Gazebo）：

```bash
ros2 launch edgeai_robot_bringup sim_multi_robot.launch.py robots:=robot_1 headless:=true \
  require_competition_state:=false nav_mode:=amcl
ros2 launch edgeai_robot_navigation dev_map_server.launch.py
ros2 service call /robot_1/relocalize edgeai_robot_interfaces/srv/Relocalize "{mode: 2, start_pose_id: task1_start}"
ros2 action send_goal /robot_1/navigate_to_pose nav2_msgs/action/NavigateToPose \
  "{pose: {header: {frame_id: map}, pose: {position: {x: 1.8, y: 1.8}, orientation: {w: 1.0}}}}"
# 移动机器人后测试重新定位：
gz service -s /world/empty/set_pose --reqtype gz.msgs.Pose --reptype gz.msgs.Boolean --timeout 2000 \
  --req 'name: "robot_1", position: {x: 1.0, y: -0.5, z: 0.01}'
```

导航（2026-10-24，当时目标容差0.10 m、地图为旧坐标系版本）：

| 测试 | 结果 |
|---|---|
| 单机器人连续10个目标（四角、窄处、障碍物旁、需要掉头的点） | Nav2全部成功（10/10），每个16～30 s；与Gazebo真实位置的最终误差0.02～0.16 m，9个在0.15 m以内 |
| 两台机器人同时导航到不同角落 | 两台都成功，误差约0.10 m，共69 s |
| 测试前后`/robot_N/cmd_vel`的发布者 | 始终只有1个（看门狗） |

重新定位（2026-10-25，`require_competition_state:=true`，测试脚本发布比赛状态）：

| 测试 | 结果 |
|---|---|
| 启动后 | `localized=false`，导航未激活 |
| 已知起点`task1_start` | 成功，约6 s，位置误差0.02 m、航向误差0.003 rad，匹配度1.00；导航自动激活，代理报告已定位 |
| 瞬移到3个新位置后，用偏差约0.14 m的位姿提示 | 全部成功，约4 s，位置误差0.04～0.09 m，匹配度0.89～1.00 |
| 瞬移后给出偏差1.0 m的错误提示 | 失败（AMCL不收敛，`RELOCALIZATION_FAILED`），代理报告`CODE_RELOCALIZATION_FAILED` |
| 瞬移后不移动的全局定位 | 失败（不收敛），没有谎报成功 |

阶段3调参（2026-10-25，无界面Gazebo，robot_1和robot_2 + 真实Nav2/AMCL，测试脚本扮演边缘节点）：

| 测试 | 调参前 | 调参后 |
|---|---|---|
| A：robot_1行驶约4.7 m到(1.8, 1.8) | AMCL标准差峰值0.31 m | 峰值0.18～0.21 m；成功，真实误差0.09～0.11 m |
| B：目标在障碍物内部（不可达） | 等满60 s超时 | 24～37 s内FAILED（Nav2错误208） |
| C：救援保持中被向前推0.35 m | 掉头时车尾扫进停车区，BLOCKED | 倒车回位，推完后约12 s重新HOLDING，真实误差0.083～0.086 m |
| D：两台机器人路径交叉 | — | 两台都一次成功，真实误差0.056 m和0.082 m，共107 s |
| 全程控制器“patience exceeded”/“failed to make progress” | 4次 | 0次 |

C的修复在`robot_agent`（见`edgeai_robot_bringup`的README 3.3节）。

SLAM到AMCL交接演练（2026-10-25，robot_1，测试脚本代行P2的SLAM启停和地图保存）：

| 步骤 | 结果 |
|---|---|
| Task 1：`nav_mode:=slam` + SLAM Toolbox | 代理报告已定位、导航可用；2个探索目标都成功（真实误差约0.04 m） |
| HANDOVER：记录SLAM位姿、保存地图、停止SLAM、发布冻结地图 | 机器人SAFE停车；确认`slam_toolbox`已不在运行 |
| 用SLAM位姿调用`relocalize`（位姿提示） | 成功，3.4 s，匹配度0.99；**交接前后位姿跳变0.053 m**（P1计划验收标准为 < 0.05 m，略超） |
| 交接后 | AMCL active，代理报告已定位、导航可用 |
| TASK2A导航目标 | 成功，真实误差0.021 m |

## 7. 已知限制

- **不移动时的全局定位基本无法收敛**，近似对称的场地还可能收敛到错误位置。比赛中应优先使用已知起点或位姿提示（需组织方确认是否提供起点位姿，见TBD登记表）。后续可在允许运动的阶段原地旋转辅助收敛。
- 已知起点模式要求`map`坐标系与场地坐标系一致，需要P2在Task 1开始时用起点初始化SLAM。
- 交接前后位姿跳变实测0.053 m，略超P1计划的0.05 m标准；需与P2联调时复测，必要时减小提示协方差或增加原地更新次数。
- **机器人一旦进入碰撞监视器停车区就无法自行脱困**：停车区对所有方向的速度都置零（包括倒车和原地旋转），只能人工移开或由障碍物自己离开。代理在5 s后报告BLOCKED。
- AMCL的真实误差约0.06～0.11 m（阶段3实测），与0.10 m的默认导航容差相当；精确目标的成败主要受定位误差影响。
- 每个目标的精确容差、失败和取消后确认零速度由`edgeai_robot_bringup`的`robot_agent`实现。
- 参数只针对仿真；实机参数等实机接入时再定（计划阶段5）。
- 在`ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST`模式下运行两台以上的完整机器人软件栈时，Cyclone DDS会因参与者数量超过默认上限而报“Failed to find a free participant index”，后启动的节点创建失败。解决：设置`CYCLONEDDS_URI='<CycloneDDS><Domain><Discovery><MaxAutoParticipantIndex>200</MaxAutoParticipantIndex></Discovery></Domain></CycloneDDS>'`。项目默认的`SUBNET`模式不受影响。
