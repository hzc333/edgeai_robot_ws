# edgeai_common

比赛系统各节点共用的Python工具，不包含任何运行节点。

| 归属 | 说明 |
|---|---|
| 负责人 | P5（接口与公共设施治理） |
| 当前实现 | P1临时创建（2026-10-23），供`mock_robot_agent`和P1节点使用；P5接手后可调整 |

## 模块

- `edgeai_common.config`：查找仓库根目录`config/`，并按运行模式解析`competition_parameters.yaml`。
  - 查找顺序：显式参数`config_dir` → 环境变量`EDGEAI_CONFIG_DIR` → 当前目录及其上级中的`config/`。
  - `resolve_parameters(run_mode)`返回`ResolvedParameters`：`values`（解析后的参数树）、`fallbacks`（回退到`development`的参数路径）、`missing_for_motion`（仍未设置的必需参数）、`sha256`（参数集合哈希，可写入`CompetitionState.parameters_sha256`）。
  - 规则与`competition_parameters.yaml`头部注释一致：`competition`只用`official`，必需参数缺失时抛出`MissingOfficialParameters`；`rehearsal`允许回退但必需参数必须有值；`development`允许必需参数缺失。空映射（如未公布的`aruco.id_mapping: {}`）视为未设置。
- `edgeai_common.qos`：`qos_from_contract(contract, name)`按`interface_runtime.yaml`的`qos`段生成`rclpy`的`QoSProfile`。
- `edgeai_common.frames`：`frame('robot_2', 'odom') -> 'robot_2/odom'`、`topic('robot_2', 'scan') -> '/robot_2/scan'`，以及机器人ID校验（ADR-0002）。

## 使用约定

节点不要自己读YAML，也不要自己实现回退逻辑：由启动文件调用`resolve_parameters`，把需要的值作为ROS参数传给节点。统一的参数解析服务完成后（P2的`system_manager`生成`system/parameters.yaml`），只需修改启动文件。

## 测试

```bash
colcon build --symlink-install --packages-select edgeai_common
colcon test --packages-select edgeai_common && colcon test-result --verbose
```
