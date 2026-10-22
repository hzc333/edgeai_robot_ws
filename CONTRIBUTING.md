# 协作与Git流程

## 分支

- 功能分支：`feature/pN-short-description`
- 修复分支：`fix/pN-short-description`
- 文档分支：`docs/short-description`
- 比赛发布分支：`release/YYYY-MM-DD`

`pN`使用职责编号，例如`feature/p3-target-fusion`。禁止直接在`main`上开发。

## 提交与PR

- 一个PR只处理一个可验证目标。
- PR说明必须包含：负责人、影响模块、接口变化、验证命令、失败/回退方式。
- 接口变化必须由生产方、消费方和P5审核。
- 安全、TF、地图坐标、救援状态机或得分证据变化至少需要两名审核者。
- 不得把官方TBD值作为事实写入代码。
- 不得提交密钥、实机密码、个人Token或未脱敏网络配置。

## 合并门槛

至少执行：

```bash
python3 tools/validate_project_contracts.py
git diff --check
```

ROS环境可用后，还必须在Pixi环境中构建受影响包并运行对应测试。涉及共享接口时，应重新构建全部消费包。CI的`pixi-environment`任务会在锁定环境中构建工作空间并运行环境与契约检查。

修改`pixi.toml`时必须同时提交重新生成的`pixi.lock`，并在PR中说明新增、升级或删除的包。OpenCV系列升级需要P3审核，ROS核心包升级需要P1和P5审核。

## 版本与发布

- 接口破坏性修改增加包版本及持久化`schema_version`。
- 每次比赛演练使用唯一`run_id`并记录Git提交。
- 发布候选版本必须固定规则版本、配置、模型、组件版本和依赖锁文件。
