# P4 Task Coordinator

负责人：P4。状态：中期 Part 2 实现完成，核心/ROS测试和一次真实双机仿真通过。
实测证据与限制见 [VALIDATION.md](VALIDATION.md)，队友接入见 [INTEGRATION.md](INTEGRATION.md)。

实现依据为官方 `KTH_EdgeAI_Midterm_Check_Task_Description.docx`，尤其第 3、5、7 节。
仓库原有 MD 是协作和接口参考。中期 Part 2 可独立使用预建地图和官方目标坐标。

本包提供任务分配、普通/协同执行、官方圆形范围的连续停留验证与证据记录。
P1 继续拥有机器人、Nav2、定位和速度安全链；P2 继续拥有地图、阶段和总计时。
没有实现最终比赛 LLM/DAG 功能；任务、分配、验证及 ROS 适配已分开以便扩展。

## 官方规则与工程参数

`config/midterm.yaml` 中官方规则：S1=(1.0,4.1)，半径0.5m，1台；
C1=(4.1,1.0)，半径0.7m，2台不同机器人；均为连续10秒**仿真时间**。
距离参考点是 `map` 中的机器人 `base_footprint`，判定中心不是导航停靠点。
官方规则值被校验，错误套用旧开发默认值将拒绝启动。

停靠点、导航到达容差、状态新鲜度、配对时间差、重试次数和超时属于工程选择，
并非官方要求。实际车身安全性必须在对应地图和机器人模型上验证。
两个协同槽位同时预留，按配置顺序依次进入：第一台保持后才发送第二台。
每个槽位先通过通用导航到安全接近点，确认动作终止和空闲，再调用救援动作。
接近点及朝向来自配置，实际路线由Nav2自主规划，不播放预录运动轨迹。
计时在机器人进入HOLDING后开始，这是保守工程策略；官方仍只要求范围与时间。
额外0.3秒采样余量可使完成前的十秒区间更容易由异步真值采样独立核验。
A*只用于分配代价，不向机器人发送路径或速度。未知/膨胀区域不可用于分配估价。

## 构建与启动

在仓库根目录：

```bash
pixi run colcon build --symlink-install --packages-select edgeai_task_coordinator
pixi run bash -c 'source install/setup.bash && ros2 launch edgeai_task_coordinator midterm_rescue.launch.py'
```

启动参数：`config_file`（默认本包midterm.yaml），`config_dir`（共享契约目录，默认自动搜索），
`output_dir`（默认工作目录`runs/p4`）。启动文件固定`use_sim_time=true`。
节点参数另有`require_map=true`和`test_mode=false`，仅自动测试可关闭地图检查。
`request_finish=true`时，全部完成且动作释放后请求P2的`TASK2A -> FROZEN`服务；
服务尚未提供时在状态中显示等待，不自行发布阶段。拒绝或通信错误会显示具体结果。

正式联调由P1/P2提供：

* 符合官方场地的 `/map`，地图、目标、机器人位姿坐标一致。
* 两台已定位机器人及其救援动作服务器。
* `/clock` 与 `TASK2A` 阶段心跳，非空run_id/map_id、正map_revision。
* 全程13分钟总计时、Part 1结果及Part 1/2切换；本包不宣称验证这些团队功能。

## ROS接口及权威归属

订阅：`/robot_N/state`（RobotState，Reliable/Volatile/KeepLast1）、
`/competition/state`和`/competition/estop`（共享control_state QoS）、
`/map`（OccupancyGrid，Reliable/TransientLocal/KeepLast1）。
调用：`/robot_N/execute_navigation_goal`（接近点，TRANSIT）和
`/robot_N/execute_rescue_task`（最终停靠保持），与P1现有定义完全相同。
通用导航的timeout显式传入240秒墙钟预算；救援短距离接近保留P1默认超时。
阶段结束调用`/competition/set_phase`（SetCompetitionPhase，REQUESTER_SYSTEM）。
完成后主动取消保持动作，`RELEASED_BY_COORDINATOR`是正常释放。

进程内三个节点：`/edge/task_allocator`、`/edge/robot_state_registry`、`/edge/rescue_verifier`。
发布：

* `/edge/robot_states`：RobotStateArray，robot_state QoS，10Hz墙钟调度。
* `/edge/rescue_events`：RescueEvent，共享event_stream QoS；持久化成功后才发布。
* `/edge/midterm_rescue/status`：std_msgs/String，JSON，snapshot QoS，10Hz；
  显式包含目标圆心、半径、完成条件、距离、阶段和清理状态。

所有任务与事件引用P2提供的run_id和地图版本，绝不自行生成替代值。
不发布cmd_vel、TF、权威targets或competition/state，也不请求擅自跳过阶段。
暂不发布`RescueTask`：旧协议把zone_tolerance_m绑定到各独立救援点，
直接把它改解释为中期目标半径会误导现有消费者。共享格式适配须与P1/P2/P3/P5确认。

## 故障、恢复和证据

状态过期、定位/健康失效会取消当前尝试；可重试故障最多尝试配置次数。
动作部分接受时撤销整个配对。每次尝试有独立标识；迟到接受仍被取消。
必须收到动作终态且状态确认空闲、停稳后才释放资源。清理超时进入HALTED。
阶段变化、急停、身份变化、时钟回退均停止当前执行，不自行恢复运动。
Ctrl+C退出时保留ROS上下文最多3秒用于取消动作；P2继续心跳也不会阻止P4主动取消。

每次run独立写入`output_dir/<run_id的SHA256前24位>/`：

* `identity.json`：官方规则来源、配置哈希、地图版本及目标来源。
* `events.jsonl`：P4专用、只追加、带序号的事件；关键事件fsync。
* `distances.jsonl`：逐仿真时间采样的距离、计时与状态。
* `snapshot.json`：原子替换，含活动动作UUID和完成快照。
* `owner.lock`：同一证据目录只允许一个活动进程。

这是P4专用格式，不冒充P2的全局events.jsonl/Manifest Schema。
已完成收据从事件重建以防重复完成。中断进程重启后按持久化UUID尝试取消原动作，
进入HALTED并要求P2发起新run后重启本节点，绝不根据旧位置自动恢复计时或运动。
正式碰撞状态需要外部接触/真值证据，运行状态明确标为`external_verification_required`。

## 文件清单

* `model.py`：配置校验、任务及机器人样本数据。
* `planning.py`：静态网格A*与小规模分配枚举。
* `verification.py`：目标圆形区域的共同连续停留验证。
* `engine.py`：预留、串行进入、重试、取消和释放状态机。
* `evidence.py`：证据锁、只追加事件、原子快照与收据重建。
* `coordinator.py`：ROS状态、动作、阶段、事件与状态快照适配。
* `config/midterm.yaml`：官方条件和独立标注的工程参数。
* `launch/midterm_rescue.launch.py`：仅P4正式模块启动入口。
* `test/test_core.py`：规则、时间边界、调度、迟到回调和持久化行为测试。
* `test/test_ros.py`：使用P1现有Mock的DDS/Action集成测试。
* `test/test_quality.py`：沿用ament版权与flake8检查。
* `launch/development_sim.launch.py`：独立Part 2开发仿真，复用P1机器人/导航启动。
* `tools/generate_midterm_fixture.py`：按官方布局生成测试世界、地图及几何清单。
* `tools/run_simulation.py`：隔离域内真实仿真；P2测试替身负责阶段/重新定位，
  Gazebo真值检查距离与足迹；可选NVIDIA EGL环境只影响当前测试。
* `tools/audit_simulation.py`：不导入P4判定器，独立核验每个完成事件前最后十秒的真值。
* `test_assets/midterm.sdf`：官方主要布局与竖直ArUco支架的Part 2测试场景。
* `test_assets/midterm.pgm`、`midterm.yaml`：由同一几何生成的预建地图，0.02m栅格。
* `test_assets/geometry.json`：测试障碍物的尺寸与位置。
* `validation/part2_simulation_2026-10-30.json`：已完成仿真的小型独立核验摘要。
* `INTEGRATION.md`、`VALIDATION.md`、`LICENSE`：交接、验证说明与许可证。
* `setup.py`、`setup.cfg`、`package.xml`、`resource/`、`__init__.py`：ROS包安装入口。

## 验证

```bash
pixi run bash -c 'source install/setup.bash && colcon test --packages-select edgeai_task_coordinator --event-handlers console_direct+ && colcon test-result --verbose'
```

测试应在独立DDS域执行，团队统一入口`pixi run test`会处理此设置。
核心逻辑和Mock测试不证明真实导航、物理碰撞、官方全场流程或最终比赛规则符合性。

从仓库运行独立真实仿真（output必须为新目录，默认域73）：

```bash
pixi run bash -c 'source install/setup.bash && python src/edgeai_task_coordinator/tools/run_simulation.py --output runs/p4-my-rehearsal'
pixi run python src/edgeai_task_coordinator/tools/audit_simulation.py runs/p4-my-rehearsal
```

`--domain`指定独立DDS域；`--timeout-wall`默认900秒是开发测试退出预算，不是官方任务时限；
`--gui`打开Gazebo窗口。测试程序创建独立Gazebo分区，输出完整启动日志、真值轨迹、
P4证据及报告，结束后清理自己的进程组。现有的ROS系统/其他仿真不会被全局终止。
NVIDIA设备可用时自动选择其EGL驱动；也可显式设置EGL环境变量，测试不会安装或改动驱动。
场景物理步长0.002秒、预建栅格和停靠/接近点属于工程选择，P1原始资源未被覆盖。

工程参数完整定义见`model.Settings`和`config/midterm.yaml`：距离单位m，
`*_s`使用仿真秒，只有`phase_heartbeat_timeout_s`与`executor_timeout_wall_s`使用墙钟秒；
动作响应和释放超时使用仿真时间；`max_attempts`为正整数。
节点另有墙钟级心跳超时，机器人最终停车由P1安全链独立保证。
