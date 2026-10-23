# ROS包、节点与所有权规划

该规划在创建业务代码前固定命名和依赖方向，避免五个人建立重复包。包名和公开节点名发生变化时，必须按照接口修改规则审核。

## 1. 依赖方向

```text
edgeai_robot_interfaces
        ^
        |
bringup/navigation/exploration/perception/fusion/coordinator/mission/system
```

`edgeai_robot_interfaces`不得依赖任何业务包。感知、探索和协调模块不得直接依赖仿真模型；通过标准ROS接口与机器人代理通信。

## 2. 包规划

| 包 | 负责人 | 主要节点/内容 | 禁止包含 |
|---|---|---|---|
| `edgeai_robot_interfaces` | P5治理，生产方与消费方共同审核 | 共享msg/srv/action | 算法和运行节点 |
| `edgeai_common` | P5（P1临时创建） | 运行模式参数解析、QoS、帧名工具；无运行节点 | 业务逻辑和运行节点 |
| `edgeai_robot_description` | P1 | URDF、世界、传感器、基础仿真 | 任务逻辑 |
| `edgeai_robot_bringup` | P1 | `robot_agent`、多机器人启动、驱动配置、安全看门狗 | 探索和任务分配 |
| `edgeai_robot_navigation` | P1 | Nav2参数、定位、恢复、动作适配器 | 全局机器人分配 |
| `edgeai_exploration` | P2 | `exploration_coordinator`、Frontier、地图管理 | 电机控制、目标识别 |
| `edgeai_system_manager` | P2 | `system_manager`、阶段管理、冻结、日志、Manifest | 感知/导航算法 |
| `edgeai_target_perception` | P3 | `target_detector`、相机标定、观测发布 | 全局任务状态 |
| `edgeai_target_fusion` | P3 | `target_fusion`、目标注册表、救援区生成、Task 1目标导出 | 机器人分配 |
| `edgeai_mission_interpreter` | P3 | `mission_interpreter`、本地模型适配、候选计划生成 | DAG调度、Nav2和机器人选择 |
| `edgeai_rescue_coordinator` | P4 | `mission_validator`、`robot_state_registry`、`task_allocator`、`rescue_verifier` | LLM推理、底层速度控制 |

`/robot_N/localization`提供`relocalize`服务；`/edge/system_manager`提供`/competition/set_phase`和`/competition/request_reset`；`/edge/mission_validator`提供`/edge/validate_mission`并且是`/edge/mission_plan`的唯一发布方。各权威数据的唯一生产节点见`config/interface_runtime.yaml`的`authority`。
| `edgeai_system_tests` | P5维护框架，P1～P4维护各自Mock/场景 | Mock节点、场景、端到端测试和回放 | 正式比赛算法 |

## 3. 公开节点名

机器人节点由Launch命名空间包裹：

```text
/robot_N/robot_agent
/robot_N/target_detector
/robot_N/localization
/robot_N/navigator
/robot_N/safety_watchdog
```

边缘节点使用固定名称：

```text
/edge/map_manager
/edge/exploration_coordinator
/edge/target_fusion
/edge/robot_state_registry
/edge/task_allocator
/edge/rescue_verifier
/edge/mission_interpreter
/edge/mission_validator
/edge/system_manager
/edge/event_logger
```

节点内部不得重复写`robot_N`。机器人ID和命名空间全部由Launch参数传入。

## 4. 配置目录

```text
config/
  competition_parameters.yaml   # 官方值和开发值
  interface_runtime.yaml        # QoS、频率、超时、身份规则
  team_assignments.yaml         # 人员分工
  sim/                           # 仿真驱动和传感器参数
  hardware/                      # 实机驱动和标定参数
  nav2/                          # 导航与定位参数
  perception/                    # ArUco和融合参数
```

实机序列号、IP和设备路径不能提交到通用默认配置；应使用每台机器人独立配置和受控的现场部署文件。

## 5. 代码所有权规则

- 负责人对包的接口稳定性、测试和说明最终负责。
- 任何人都可以提交跨包修复，但必须由包负责人审核。
- 公共接口修改必须同时获得生产方、消费方和P5审核。
- P5只维护测试入口和发布门槛；Mock节点与测试数据由对应生产模块负责人维护。
- 不允许业务包复制共享消息定义或维护私有同义字段。
- Mock节点必须使用真实接口包，不得另建简化消息类型。
