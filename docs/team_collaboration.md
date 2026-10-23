# 小组GitHub协作流程

团队仓库：https://github.com/hzc333/edgeai_robot_ws
组织方基线：https://github.com/dongjw-hit/edgeai_robot_ws（远程名`upstream`，只读）

## 基本原则（2026-10-23起）

1. **现阶段不使用Pull Request。**每个人在本地完成检查后，直接提交并推送到团队`main`。
2. **每个人用README详细记录自己负责的文件**，要求见第4节。README是队友了解你工作的唯一入口，代码改了README必须同时更新。
3. **推送前必须通过本地检查**（第3.2节），永远不要对`main`强制推送。
4. 修改别人负责的文件或共享接口之前，先在群里说明并得到对方同意（第5节）。
5. **里程碑和比赛只使用打过标签的版本**，临近时冻结`main`（第7节）。

`main`没有启用分支保护，GitHub不会拦截错误操作，以上规则全靠大家自觉遵守。以后队友多了、冲突变多时，可以恢复PR流程（`.github/PULL_REQUEST_TEMPLATE.md`保留备用）。

## 1. 仓库所有者设置（hzc333）

1. **添加成员**：仓库 Settings → Collaborators → Add people，逐个输入队友的GitHub用户名。队友在邮件或 https://github.com/hzc333/edgeai_robot_ws/invitations 接受邀请后才有推送权限。
2. **分支保护**：当前不启用。

## 2. 每位成员首次设置

### 2.1 身份和登录

```bash
git config --global user.name "你的GitHub用户名"
git config --global user.email "你在GitHub账号中验证过的邮箱"
```

推送需要Personal Access Token（https://github.com/settings/personal-access-tokens/new ）：Repository access只选团队仓库；Permissions中Contents设为Read and write；需要修改`.github/`下文件时再加Workflows: Read and write。
为了避免每次输入Token，可以安装GitHub CLI（`sudo apt install gh`），再执行`gh auth login`和`gh auth setup-git`。Token不要发到群里，也不要写进任何文件。

### 2.2 情况A：还没有本地仓库

```bash
git clone https://github.com/hzc333/edgeai_robot_ws.git
cd edgeai_robot_ws
git remote add upstream https://github.com/dongjw-hit/edgeai_robot_ws.git
pixi install --locked
pixi run build
pixi run bash -c "source install/setup.bash && python tools/check_environment.py"
```

### 2.3 情况B：已经克隆过组织方仓库，并且有自己的改动

团队`main`的历史完整包含组织方的提交，团队的工作是在组织方提交之后追加的。所以只要找到“你的改动是从组织方哪个提交开始的”，就可以把这之后你自己的提交原样搬到团队`main`上，不会重复也不会丢失。下面的命令让Git自动计算这个起点，不需要你记提交号。

先把远程改过来：

```bash
cd edgeai_robot_ws
git remote rename origin upstream
git remote add origin https://github.com/hzc333/edgeai_robot_ws.git
git fetch origin
git fetch upstream
```

确认团队`main`已经包含组织方的最新提交（正常情况下会输出“已包含”）：

```bash
git merge-base --is-ancestor upstream/main origin/main && echo 已包含 || echo 未包含
```

如果输出“未包含”，说明组织方有了团队尚未同步的更新。先不要迁移，在群里通知负责同步的人按第6节同步，完成后再继续。

**改动还没有提交**：

```bash
git stash push -u -m "my-work"
git switch -C main origin/main
git stash pop
```

**改动已经提交在本地`main`上**：

```bash
BASE=$(git merge-base HEAD upstream/main)  # 你的改动从组织方哪个提交开始
git log --oneline $BASE..HEAD              # 先确认：这里列出的应全部是你自己的提交
git switch -c my-work                      # 给当前带改动的提交起个临时分支名
git rebase --onto origin/main $BASE        # 只把BASE之后你自己的提交搬到团队main上
git switch -C main my-work                 # 本地main = 团队main + 你的提交
git branch -D my-work
```

第二条命令列出的提交里如果出现了不是你写的提交，先停下来在群里问，不要继续。

有冲突时，按提示逐个修改文件，`git add`后执行`git rebase --continue`。不确定怎么解决时，执行`git rebase --abort`可以完全恢复到迁移之前的状态。最后检查`git log --oneline origin/main..`，应只剩你自己的提交，然后按第3节检查并推送。

切换环境后（例如以前用系统ROS构建过），先删除`build/`、`install/`和`log/`再重新构建。

## 3. 日常流程

### 3.1 开发与提交

```bash
# 1. 开始工作前先同步
git switch main
git pull --rebase

# 2. 小步提交：一个提交只做一件事，说明写清楚做了什么、为什么
git add 相关文件
git commit -m "说明做了什么"
```

只提交与本次工作有关的文件，不要用`git add .`一次性加入所有改动。实验性的代码可以先放在本地分支里，确认可用后再合入本地`main`。

### 3.2 推送前检查（必须全部通过）

```bash
rm -rf build install log          # 新增或删除了包、启动文件时建议清理后重建
pixi run build
pixi run test                     # 全部包的测试，任一失败时返回非零
pixi run validate
pixi run check-env
git diff --check origin/main
```

- `pixi run test`最后一行必须是`0 errors, 0 failures`。CI每次推送都会运行同样的测试。
- `pixi run test`按顺序运行各包测试，并使用独立的DDS域（默认42，可用环境变量`EDGEAI_TEST_DOMAIN_ID`修改）且只在本机通信，避免测试之间、测试与正在运行的仿真或网络中的真机互相干扰。自己写的测试如果会发布`/competition/state`、急停等全局话题，必须在测试结束时销毁节点，不要依赖其他测试的状态。
- 调试时可以只测自己的包：`pixi run bash -c "source install/setup.bash && colcon test --packages-select 包名 && colcon test-result --verbose"`。但推送前必须跑全部测试。
- 改动影响仿真或运行行为时，按自己包README中的验证步骤实际运行一次。
- 同时检查README是否已随代码更新（第4节）。

### 3.3 推送

```bash
git pull --rebase       # 先拿到队友的最新提交，自己的提交排在后面
# 如果拉到了新提交，重新执行3.2的检查
git push
```

- `git push`被拒绝（提示远程有新提交）时，执行`git pull --rebase`，重新检查后再推送。**不要用`--force`。**
- rebase有冲突时，按提示逐个解决，`git add`后`git rebase --continue`；不确定时`git rebase --abort`恢复原状，再在群里找相关负责人。
- 推送后CI会自动运行：契约检查，以及在锁定环境中构建、环境检查和全部测试。CI失败时，推送者负责尽快修复；修复前其他人暂停推送。

## 4. README要求

每个包都必须有`README.md`，由包负责人维护，详细记录这个包里的每一个文件。仓库根目录`README.md`只写整体入口，各包的细节写在各自的README里。

README至少包含：

1. **负责人和状态**：负责角色、当前完成到哪一步、哪些部分还没实现或没验证。
2. **文件清单**：包内每个文件（launch、config、源码、测试、模型、地图等）的路径和作用。
3. **怎样使用**：构建、启动的命令，以及全部启动参数（含义、默认值、单位）。
4. **接口**：发布和订阅的话题、服务、动作，以及消息类型、QoS、频率、坐标系、时间戳来源。共享接口的定义以`edgeai_robot_interfaces`为准，README中写清本包怎样使用它们。
5. **参数**：所有ROS参数的含义、单位、默认值和来源（哪个配置文件、比赛官方值还是开发值）。
6. **怎样验证**：测试命令，以及需要手动执行的验证步骤和预期结果。
7. **已知限制**：已发现但尚未解决的问题、占位值和与组织方资料的差异。

改代码时同步改README；修改了接口、参数或启动方式而README没有更新，视为工作未完成。

## 5. 容易出问题的地方

- **共享接口和别人的文件**：修改`src/edgeai_robot_interfaces`、`schemas/`、`config/interface_runtime.yaml`或其他人负责的包之前，先在群里说明改动和影响，得到生产方、消费方和P5同意后再推送，并在提交说明中写明谁同意了。包的负责人见`docs/package_and_node_layout.md`。
- **`pixi.lock`冲突不要手工合并**：先取团队`main`中的版本（`git checkout origin/main -- pixi.lock`），再执行`pixi lock`按你的`pixi.toml`重新生成，并在提交说明中写明依赖变化。
- **不要提交**：`build/`、`install/`、`log/`、`.pixi/`、`runs/`下的运行产物、rosbag、模型权重、密码、Token、实机IP或序列号。大文件（模型、数据集）放在团队网盘，仓库中只记录名称、版本和SHA-256。
- **永远不要强制推送`main`**，也不要改写已经推送的历史。

## 6. 同步组织方更新

组织方仓库有更新时，由P5（或指定的一人）同步，其他人不要各自合并`upstream`：

```bash
git switch main
git pull --rebase
git fetch upstream
git merge upstream/main
# 按第3.2节检查
git push
```

在群里说明组织方改了什么、影响哪些模块。规则书更新还要按`docs/rule_assumptions_and_tbd.md`第5节的检查清单执行。

## 7. 版本标签、比赛版本和冻结

`main`一直在变化，里程碑评审和比赛不能直接使用`main`的最新提交，必须使用打过标签的固定版本。

### 7.1 标签

| 标签 | 何时打 | 说明 |
|---|---|---|
| `rehearsal-YYYYMMDD-N` | 每次完整演练通过后 | N为当天第几次；说明中写演练场景、`run_id`和发现的问题 |
| `milestone-YYYYMMDD` | 里程碑评审使用的版本 | 必须是通过演练的提交 |
| `competition-YYYYMMDD` | 比赛使用的版本 | 必须满足开发计划的发布门槛：连续三次完整演练无人工干预 |
| `competition-YYYYMMDD.1`、`.2`… | 比赛版本发现问题并修复后 | 不移动原标签，修复后打新标签 |

规则：

- 标签由P5打；P5不在时，由演练负责人（P2）打，并在群里说明。
- 只能给已经推送到`main`、CI全部通过的提交打标签。
- 使用带说明的标签（annotated tag），说明中写清验证了什么、`run_id`、已知问题。
- **已推送的标签永远不移动、不删除。**有问题就修复后打新标签。

```bash
git switch main && git pull --rebase
git tag -a milestone-20261215 -m "里程碑版本：S01/S03/S06通过，run_id=run-...；已知问题：..."
git push origin milestone-20261215
```

### 7.2 比赛和评审机器使用标签版本

```bash
git fetch --tags
git switch --detach competition-20270310        # 切到标签对应的固定提交
rm -rf build install log
pixi install --locked
pixi run build && pixi run test
git describe --tags                               # 确认当前版本，写入运行记录
```

每次运行的`system/component_versions.json`会记录Git提交，赛后可以对应到标签。

### 7.3 冻结

- 里程碑评审和比赛前**3天**起冻结`main`，具体日期由P5在群里公布。
- 冻结期间只允许修复缺陷，不加新功能。每个修复推送前必须由另一名成员看过并测试过（可以临时用PR，也可以当面检查），提交说明中写明检查人。
- 新功能在本地分支继续开发，冻结结束后再合入`main`。
- 冻结期间修复后需要重新完整演练，通过后打新标签。
