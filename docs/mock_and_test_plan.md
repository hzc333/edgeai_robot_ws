# Mock与集成测试计划

## 1. 原则

- Mock必须使用`edgeai_robot_interfaces`真实消息、服务和动作，不能创建简化私有类型。
- Mock时间、坐标系、QoS、错误码和超时行为必须与正式模块一致。
- 每个模块同时提供正常、超时、错误、重复和重启场景。
- 开发场景参数位于`config/development_scenarios.yaml`，不得作为官方比赛配置使用。

## 2. Mock节点

| Mock节点 | 负责人 | 模拟内容 | 主要消费者 |
|---|---|---|---|
| `mock_robot_agent` | P1 | 状态、通用导航和“到达并保持”救援动作、取消、故障、阶段确认和`relocalize` | P2、P4 |
| `mock_map_manager` | P2 | `/map`、`map_id/revision`、探索状态和冻结地图 | P3、P4 |
| `mock_target_fusion` | P3 | 目标快照、重复观测、未知ID和救援位姿 | P4 |
| `mock_mission_interpreter` | P3 | 候选任务计划、格式错误、虚构目标和`MissionIntakeResult` | P4 |
| `mock_rescue_coordinator` | P4 | `validate_mission`服务、任务状态、步骤状态、协同计时和事件流 | P2、P3 |
| `mock_competition_manager` | P2 | 阶段、`run_id`、急停、阶段序号、运行模式和重置流程 | 全员 |

Mock实现统一放入未来的`edgeai_system_tests`包，但由表中对应负责人维护；P5只维护测试入口、CI接线和验收报告。正式启动文件禁止包含Mock节点。

## 3. 固定测试场景

### S01：单主机器人Task 1

- `robot_1`执行SLAM和自主探索。
- `robot_2`连接并发布状态，但不写入地图。
- 检测四个开发Marker，冻结地图和目标列表。
- 验证地图、目标列表和Manifest中的版本一致。

### S02：重复目标观测

- 从不同时间和机器人发布同一Marker观测。
- 允许有测量噪声。
- 最终只能存在一个目标ID，观察次数和观察机器人列表正确累计。

### S03：导航失败

- 向机器人发送不可达目标或注入规划失败。
- 动作返回统一`TaskReason.NAVIGATION_FAILED`。
- 机器人最终速度为零，并且仍可接受后续任务。

### S04：协同停留重置

- 两台机器人分别进入TC1两个救援区。
- 停留未完成前让一台机器人离开。
- 验证计时清零；两台机器人重新同时进入后才重新计时。

### S05：LLM任务依赖

- 使用仓库中的任务计划样例。
- T2完成前T1/T3不可执行。
- T2完成后T1/T3可以并行。
- T1和T3均完成后TC1才可以执行。

### S06：冻结与急停

- 在导航和停留状态分别触发阶段冻结和急停。
- 所有在线机器人取消动作、发送零速度并发布匹配阶段序号的确认。
- 急停释放必须使用新的`generation`，且只能在允许阶段执行。

### S07：任务计划被拒绝

- 提交引用未知目标T9的指令，或候选计划中存在循环依赖。
- 验证器返回`CODE_UNKNOWN_TARGET`或`CODE_DEPENDENCY_CYCLE`。
- `/edge/mission_intake`记录`OUTCOME_REJECTED_BY_VALIDATOR`及原因；`/edge/mission_plan`没有新消息，机器人没有任何运动。

### S08：重置与重新定位

- Task 2A中对`robot_1`执行`ACTION_BEGIN`：其动作被取消、进入`MODE_SAFE`，任务被重新分配。
- 执行`ACTION_COMPLETE`后调用`relocalize`；成功前`robot_1`不进入分配候选，失败时报告`CODE_RELOCALIZATION_FAILED`。
- `reset_count`和`category=reset`事件正确累计。

## 4. 第一轮联调通过条件

1. 两个Mock机器人与所有边缘Mock能够同时启动。
2. 所有消息使用同一`run_id`。
3. 阶段切换在3秒内收到全部在线机器人确认。
4. 状态超过1秒未更新的机器人从任务分配候选中移除。
5. Task 1地图和目标版本完全一致。
6. S02～S08全部产生预期事件和失败原因。
7. 急停不依赖任务协调器正常运行。
