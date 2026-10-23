# edgeai_robot_bringup

P1负责的机器人启动包：多机器人启动入口，以及将来的`safety_watchdog`和`robot_agent`。

| 项目 | 内容 |
|---|---|
| 负责人 | P1（hzc333） |
| 已完成 | 多机器人仿真启动（`sim_multi_robot.launch.py`），2026-10-23验证 |
| 未实现 | `safety_watchdog`（ADR-0003）、`robot_agent`（RobotState、阶段确认、两个动作服务器）、实机启动 |

## 1. 文件清单

| 文件 | 作用 |
|---|---|
| `launch/sim_multi_robot.launch.py` | 启动Gazebo世界和1～4台仿真机器人，可选打开RViz |
| `edgeai_robot_bringup/__init__.py` | Python包入口，目前没有节点 |
| `config/.gitkeep` | 占位，将来放看门狗和代理的参数文件 |
| `test/test_copyright.py`、`test_flake8.py`、`test_pep257.py` | 版权头、代码风格和文档字符串检查 |
| `setup.py`、`setup.cfg`、`package.xml`、`resource/` | `ament_python`包配置；`launch/*.py`和`config/*.yaml`会安装到包共享目录 |

## 2. sim_multi_robot.launch.py

```bash
export EDGEAI_CONFIG_DIR=$PWD/config      # start_sim.sh会自动设置
ros2 launch edgeai_robot_bringup sim_multi_robot.launch.py robots:=robot_1,robot_2
ros2 launch edgeai_robot_bringup sim_multi_robot.launch.py robots:=robot_1,robot_2,robot_3,robot_4 headless:=true
```

`./start_sim.sh N`（N为1～4）等价于`robots:=robot_1,...,robot_N rviz:=true`。

| 参数 | 默认值 | 说明 |
|---|---|---|
| `robots` | `robot_1,robot_2` | 逗号分隔的机器人ID，不能为空或重复 |
| `config_dir` | 环境变量`EDGEAI_CONFIG_DIR` | 仓库根目录`config/`；为空时从当前目录向上查找 |
| `world` | `edgeai_robot_description`的`worlds/empty.sdf` | 世界文件 |
| `headless` | `false` | 只运行Gazebo服务器，无图形界面 |
| `rviz` | `false` | 打开RViz：1台机器人用`realistic_robot.rviz`，多台用`multi_robot.rviz` |

工作过程：

1. 用`edgeai_common.config.find_config_dir`找到`config/`，读取`config/sim/robots.yaml`中的出生位姿。
2. 包含一次`edgeai_robot_description/sim_world.launch.py`（世界和`/clock`）。
3. 对每台机器人包含一次`edgeai_robot_description/sim_robot.launch.py`。
4. `robots.yaml`中没有某台机器人的位姿时，启动报错退出。

每台机器人的话题、坐标系和桥接见`edgeai_robot_description`的README第4节。

## 3. 验证

```bash
colcon test --packages-select edgeai_robot_bringup && colcon test-result --verbose
```

运行验证步骤见`edgeai_robot_description` README第6节。2026-10-23实测：两台机器人话题和TF无冲突，只驱动robot_2时robot_1不动；四台机器人同时运行时实时速率0.98。

## 4. 计划中的内容

按`docs/decisions/0003-velocity-safety-chain.md`和P1执行计划阶段2实现：

| 节点 | 职责 |
|---|---|
| `safety_watchdog` | `/robot_N/cmd_vel`的唯一发布者，20 Hz；按阶段、急停`generation`、边缘心跳和输入超时门控；速度按比例限幅；手动控制只在development模式生效 |
| `robot_agent` | 发布`/robot_N/state`（10 Hz）和`/robot_N/phase_ack`；提供`execute_navigation_goal`和`execute_rescue_task`动作，内部调用Nav2 |

在正式代理完成前，P2和P4使用`edgeai_system_tests`中语义相同的`mock_robot_agent`开发。

## 5. 已知限制

- 目前只有仿真启动；实机启动等组织方技术教程后实现（P1计划阶段5）。
- 机器人ID只能是`robot_1`～`robot_4`。
