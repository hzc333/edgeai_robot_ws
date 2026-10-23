# edgeai_robot_navigation

P1负责的导航包：每台机器人的Nav2和AMCL配置与启动，以及提供`/robot_N/relocalize`服务的`localization`节点。

| 项目 | 内容 |
|---|---|
| 负责人 | P1（hzc333） |
| 状态 | **只有包骨架，尚无可运行内容**（2026-10-23） |
| 下一步 | P1执行计划阶段2（Nav2和AMCL）和阶段3（`relocalize`） |

## 1. 文件清单

| 文件 | 作用 |
|---|---|
| `edgeai_robot_navigation/__init__.py` | Python包入口，目前没有节点 |
| `launch/.gitkeep`、`config/.gitkeep` | 占位，将来放启动文件和Nav2参数 |
| `test/test_copyright.py`、`test_flake8.py`、`test_pep257.py` | 版权头、代码风格和文档字符串检查 |
| `setup.py`、`setup.cfg`、`package.xml`、`resource/` | `ament_python`包配置；`launch/*.py`和`config/*.yaml`会安装到包共享目录 |

## 2. 计划中的内容

| 内容 | 说明 |
|---|---|
| `config/nav2_sim.yaml` | 以Pixi环境中Nav2默认参数为起点，帧名和话题用`<ROBOT>`占位符，启动时替换 |
| `launch/nav_robot.launch.py` | 在`/robot_N`命名空间中启动Nav2；参数`mode:=slam|amcl` |
| `localization`节点 | `relocalize`服务的三种模式，并管理本机器人AMCL的生命周期 |

已确定的约定（ADR-0002、ADR-0003）：

- Nav2启动时**不把`/tf`重映射到命名空间内**；所有机器人使用全局`/tf`和带前缀的帧名。
- `robot_base_frame`一律为`robot_N/base_footprint`（驱动轮轴中点）。
- 全局代价地图静态层和AMCL订阅全局`/map`（默认的相对话题会变成`/robot_N/map`）。
- 速度链：控制器 → `cmd_vel_nav` → 平滑器 → `cmd_vel_smoothed` → 碰撞监视器 → `cmd_vel_safe_in` → `safety_watchdog` → `/robot_N/cmd_vel`。
- 足迹（相对`base_footprint`）：`[[0.115, 0.175], [0.115, -0.175], [-0.315, -0.175], [-0.315, 0.175]]`。机器人大部分在轴中点后方，原地旋转时后角扫过半径约0.36 m。

## 3. 验证

```bash
colcon test --packages-select edgeai_robot_navigation && colcon test-result --verbose
```

目前只有代码风格检查。
