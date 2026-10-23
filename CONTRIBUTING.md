# 协作与Git流程

完整步骤见[小组GitHub协作流程](docs/team_collaboration.md)。

## 提交方式

- 现阶段不使用Pull Request：在本地完成检查后，直接提交并推送到`main`。
- 一个提交只处理一个可验证目标。提交说明写清楚：做了什么、为什么、影响哪些模块、怎样验证。
- 永远不要强制推送`main`，也不要改写已经推送的历史。
- 实验性代码可以先放在本地分支，确认可用后再合入本地`main`推送。需要长期并行开发时，分支命名为`feature/pN-short-description`或`fix/pN-short-description`（`pN`为职责编号）。

## 修改前的约定

- 共享接口（`src/edgeai_robot_interfaces`、`schemas/`、`config/interface_runtime.yaml`）的修改，必须先得到生产方、消费方和P5同意，并在提交说明中写明谁同意了。
- 修改别人负责的包之前，先得到该包负责人同意。包的负责人见`docs/package_and_node_layout.md`。
- 安全、TF、地图坐标、救援状态机或得分证据的修改，推送前至少让一名其他成员看过。
- 不得把官方TBD值作为事实写入代码。
- 不得提交密钥、实机密码、个人Token或未脱敏网络配置。

## README要求

每个包都必须有`README.md`，由包负责人详细记录包内每个文件的作用、使用方法、接口、参数、验证步骤和已知限制。代码改了README必须同时更新，否则视为工作未完成。具体要求见`docs/team_collaboration.md`第4节。

## 推送前检查

```bash
pixi run build
pixi run bash -c "source install/setup.bash && colcon test && colcon test-result --verbose"
pixi run validate
git diff --check origin/main
```

测试必须0失败。涉及共享接口或公共包时，必须重新构建并测试全部包。推送后CI会在锁定环境中构建工作空间并运行环境与契约检查；CI失败时由推送者尽快修复。

修改`pixi.toml`时必须同时提交重新生成的`pixi.lock`，并在提交说明中写明新增、升级或删除的包。OpenCV系列升级需要P3同意，ROS核心包升级需要P1和P5同意。

## 版本与发布

- 接口破坏性修改增加包版本及持久化`schema_version`。
- 每次比赛演练使用唯一`run_id`并记录Git提交。
- 发布候选版本必须固定规则版本、配置、模型、组件版本和依赖锁文件，并打上`release/YYYY-MM-DD`标签。
