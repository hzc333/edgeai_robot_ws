# edgeai_robot_navigation

P1负责的导航包：每台机器人的Nav2和AMCL配置与启动，以及提供`/robot_N/relocalize`服务的`localization`节点。

状态：骨架。

## 计划内容

| 内容 | 说明 |
|---|---|
| `config/nav2_sim.yaml` | 以Pixi环境中Nav2默认参数为基础，帧名和话题使用`<ROBOT>`占位符 |
| `launch/nav_robot.launch.py` | 在`/robot_N`命名空间内启动Nav2（不重映射`/tf`），`mode:=slam|amcl` |
| `localization`节点 | `relocalize`服务的三种模式，并管理本机器人AMCL的生命周期 |

## 约定

- Nav2的`robot_base_frame`一律为`robot_N/base_footprint`（驱动轮轴中点，ADR-0002）。
- 全局代价地图静态层和AMCL订阅全局`/map`。
- 碰撞监视器输出到`cmd_vel_safe_in`，由`safety_watchdog`最终发布（ADR-0003）。
