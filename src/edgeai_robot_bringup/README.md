# edgeai_robot_bringup

P1负责的机器人启动包：多机器人启动、`safety_watchdog`和`robot_agent`。

状态：骨架。后续内容按`docs/decisions/0002-multi-robot-tf-and-naming.md`和`0003-velocity-safety-chain.md`逐步加入。

## 计划内容

| 内容 | 说明 |
|---|---|
| `launch/sim_multi_robot.launch.py` | 启动Gazebo世界和1～4台仿真机器人 |
| `safety_watchdog`节点 | `/robot_N/cmd_vel`的唯一发布者，按阶段、急停、边缘心跳和输入超时门控（ADR-0003） |
| `robot_agent`节点 | 发布`/robot_N/state`和`/robot_N/phase_ack`，提供`execute_navigation_goal`和`execute_rescue_task`动作 |

## 约定

- 机器人ID只通过启动参数`robot_id`传入，节点内部不写死`robot_N`。
- 比赛参数通过`edgeai_common.config`解析后作为ROS参数传入，不写成常量。
