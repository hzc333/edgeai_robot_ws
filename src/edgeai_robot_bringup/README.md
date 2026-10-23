# edgeai_robot_bringup

P1负责的机器人启动包：多机器人仿真启动、每台机器人的软件栈启动，以及速度安全看门狗`safety_watchdog`。

| 项目 | 内容 |
|---|---|
| 负责人 | P1（hzc333） |
| 已完成 | 多机器人仿真启动；`safety_watchdog`（ADR-0003）及其测试；`robot_stack.launch.py`（看门狗 + 可选Nav2），2026-10-24验证 |
| 部分完成 | `robot_agent`：RobotState、阶段确认、`execute_navigation_goal`已实现并通过模拟Nav2测试；**尚未接入`robot_stack.launch.py`，也未在真实Nav2仿真中验收**；`execute_rescue_task`属于计划3-04 |
| 未实现 | 实机启动 |

## 1. 文件清单

| 文件 | 作用 |
|---|---|
| `edgeai_robot_bringup/safety_watchdog.py` | 看门狗节点，入口`ros2 run edgeai_robot_bringup safety_watchdog`；门控逻辑是纯函数`decide()`，便于测试 |
| `edgeai_robot_bringup/robot_agent.py` | 机器人代理节点，入口`ros2 run edgeai_robot_bringup robot_agent`：10 Hz发布`state`、2 Hz发布`phase_ack`，提供`execute_navigation_goal`（内部调用Nav2 `navigate_to_pose`，到达后检查目标自身容差，不满足时再逼近一次；结束时取消Nav2并等待里程计确认停车，超时则报告`CODE_COMMAND_TIMEOUT`）。Nav2错误码104～106映射为BLOCKED，其余为FAILED；碰撞监视器持续停车超过5 s也判BLOCKED |
| `test/test_robot_agent.py` | 代理测试：纯逻辑（模式优先级、错误码映射、容差和协方差判定）和使用模拟Nav2/TF/里程计/AMCL的18项行为测试 |
| `launch/robot_stack.launch.py` | 在`/robot_N`命名空间启动一台机器人的软件栈：看门狗，以及`nav_mode`不为`none`时的Nav2；按运行模式解析参数 |
| `launch/sim_multi_robot.launch.py` | 启动Gazebo世界、1～4台仿真机器人以及各自的软件栈，可选RViz |
| `test/test_safety_watchdog.py` | 看门狗测试：纯逻辑测试和ROS通信测试（见第5节） |
| `test/test_copyright.py`、`test_flake8.py`、`test_pep257.py` | 版权头、代码风格和文档字符串检查 |
| `config/.gitkeep` | 占位，将来放机器人代理的参数 |
| `edgeai_robot_bringup/__init__.py` | Python包入口 |
| `setup.py`、`setup.cfg`、`package.xml`、`resource/` | `ament_python`包配置；`launch/*.py`和`config/*.yaml`安装到包共享目录 |

## 2. safety_watchdog

`/robot_N/cmd_vel`的**唯一发布者**（ADR-0003）。以固定频率重发最新的速度输入；只要任一门控条件成立，就输出零速度。

### 2.1 话题

| 话题（相对命名空间） | 类型 | 方向 | QoS | 说明 |
|---|---|---|---|---|
| `cmd_vel_safe_in` | `geometry_msgs/Twist` | 订阅 | Reliable，深度10 | 自动输入，来自Nav2碰撞监视器 |
| `cmd_vel_manual` | `geometry_msgs/Twist` | 订阅 | Reliable，深度10 | 手动输入，只在`run_mode=development`时生效，生效时优先于自动输入 |
| `/competition/state` | `CompetitionState` | 订阅 | `control_state`（Reliable，Transient Local，深度1） | 阶段和边缘心跳 |
| `/competition/estop` | `EmergencyStop` | 订阅 | 同上 | 急停 |
| `cmd_vel` | `geometry_msgs/Twist` | 发布 | Reliable，深度10 | 底盘速度，`publish_rate_hz`频率 |
| `/diagnostics` | `diagnostic_msgs/DiagnosticArray` | 发布 | 默认 | 1 Hz；状态名`robot_N/safety_watchdog`；门控关闭时为WARN，消息中列出原因 |

只使用`Twist`的`linear.x`和`angular.z`，其他分量一律输出0。

### 2.2 门控规则

| 条件 | 诊断原因 |
|---|---|
| 尚未收到`CompetitionState` | `waiting_for_competition_state` |
| 阶段不是TASK1、TASK2A、TASK2B | `phase_<名称>`，如`phase_frozen` |
| 急停生效（只认`generation`比已收到最大值更大的消息） | `estop` |
| 超过`edge_timeout_s`没有新的`CompetitionState` | `edge_connection_lost` |
| 超过`input_timeout_s`没有速度输入 | `input_timeout`（正常现象，不算故障） |

`require_competition_state:=false`时不检查前两项和边缘心跳，但急停照常生效。

速度超过上限时，线速度和角速度**按同一比例**缩小，保持转弯曲率，例如(0.3 m/s, 0.3 rad/s)在上限(0.15, 0.30)下变为(0.15, 0.15)。

### 2.3 参数

| 参数 | 默认值 | 单位 | 来源（由`robot_stack.launch.py`传入） |
|---|---|---|---|
| `robot_id` | `robot_1` | — | 启动参数 |
| `run_mode` | `development` | — | 启动参数：`development`/`rehearsal`/`competition` |
| `max_linear_mps` | 0.15 | m/s | 解析后的`motion.max_linear_speed_mps` |
| `max_angular_radps` | 0.30 | rad/s | 解析后的`motion.max_angular_speed_radps` |
| `input_timeout_s` | 0.5 | s | `interface_runtime.yaml`的`timeouts_s.velocity_command` |
| `edge_timeout_s` | 1.0 | s | `timeouts_s.edge_connection` |
| `require_competition_state` | `true` | — | 启动参数；只有`run_mode=development`允许设为`false`，否则节点报错退出 |
| `publish_rate_hz` | 20.0 | Hz | 固定 |
| `config_dir` | 搜索 | — | 用于读取QoS定义 |

节点退出时会再发布一次零速度。

## 3. robot_stack.launch.py

```bash
ros2 launch edgeai_robot_bringup robot_stack.launch.py robot_id:=robot_1 run_mode:=development
```

| 参数 | 默认值 | 说明 |
|---|---|---|
| `robot_id` | `robot_1` | 命名空间 |
| `run_mode` | `development` | 用`edgeai_common.resolve_parameters`解析比赛参数。`competition`模式下官方必需参数仍为`null`时**启动失败**（当前就是这种情况） |
| `config_dir` | 搜索 | 仓库根目录`config/` |
| `use_sim_time` | `true` | 实机设为`false` |
| `require_competition_state` | `true` | 见2.3节 |
| `nav_mode` | `none` | `none`：只启动看门狗；`amcl`或`slam`：同时包含`edgeai_robot_navigation`的`nav_robot.launch.py`（AMCL模式下导航需在定位后激活，见该包README第2.2节） |

## 4. sim_multi_robot.launch.py

```bash
export EDGEAI_CONFIG_DIR=$PWD/config      # start_sim.sh会自动设置
ros2 launch edgeai_robot_bringup sim_multi_robot.launch.py robots:=robot_1,robot_2
ros2 launch edgeai_robot_bringup sim_multi_robot.launch.py robots:=robot_1,robot_2,robot_3,robot_4 headless:=true
```

`./start_sim.sh N`（N为1～4）等价于`robots:=robot_1,...,robot_N rviz:=true run_mode:=development require_competition_state:=false`，因此可以直接用`/robot_N/cmd_vel_manual`手动驾驶。

| 参数 | 默认值 | 说明 |
|---|---|---|
| `robots` | `robot_1,robot_2` | 逗号分隔的机器人ID，不能为空或重复 |
| `config_dir` | 环境变量`EDGEAI_CONFIG_DIR` | 为空时从当前目录向上查找`config/` |
| `world` | `edgeai_robot_description`的`worlds/empty.sdf` | 世界文件 |
| `headless` | `false` | 只运行Gazebo服务器 |
| `rviz` | `false` | 1台用`realistic_robot.rviz`，多台用`multi_robot.rviz` |
| `stack` | `true` | 为每台机器人包含`robot_stack.launch.py` |
| `run_mode` | `development` | 传给每台机器人的软件栈 |
| `require_competition_state` | `true` | 同上 |
| `nav_mode` | `none` | 同上，作用于每台机器人 |

工作过程：读取`config/sim/robots.yaml`的出生位姿 → 包含一次`sim_world.launch.py` → 每台机器人包含`sim_robot.launch.py`和（`stack:=true`时）`robot_stack.launch.py`。`robots.yaml`中没有某台机器人的位姿时启动报错退出。每台机器人的话题和坐标系见`edgeai_robot_description`的README。

## 5. 验证

```bash
pixi run test     # 或只测本包：colcon test --packages-select edgeai_robot_bringup
```

`test/test_safety_watchdog.py`覆盖：

- 纯逻辑：各门控条件（无比赛状态、FROZEN/HANDOVER/ESTOP阶段、急停、边缘失联、输入超时）都输出零速度；不要求比赛状态时急停仍生效；手动输入只在允许时生效且优先；按比例限幅保持曲率。
- ROS通信（P1计划2-04）：`cmd_vel`只有一个发布者；输入停止、急停、阶段切到FROZEN、心跳停止时1 s内输出零速度；旧`generation`的急停释放被忽略、新的释放后恢复；超速被按比例限幅；非开发模式忽略手动输入；非开发模式下禁止关闭比赛状态要求。

2026-10-24仿真实测（无界面Gazebo，robot_1）：

| 情况 | 结果 |
|---|---|
| `require_competition_state:=false`，手动指令0.3 m/s持续2 s | 被限到0.15 m/s，移动约0.22 m；停止发送后1 s内停车，之后仅移动约2 mm |
| `require_competition_state:=true`，无比赛状态 | 不移动 |
| 两种情况下`/robot_1/cmd_vel`的发布者 | 1个（看门狗） |
| `run_mode:=competition` | 启动失败，提示`aruco.dictionary`等官方参数未设置 |

## 6. 已知限制

- 目前只有仿真启动；实机启动等组织方技术教程后实现（P1计划阶段5）。
- 机器人ID只能是`robot_1`～`robot_4`。
- `robot_agent`尚未实现；P2、P4请先使用`edgeai_system_tests`中的`mock_robot_agent`。
- 在P2的阶段管理器完成前，需要运动的开发测试只能用`run_mode:=development require_competition_state:=false`，或自行发布`/competition/state`。
