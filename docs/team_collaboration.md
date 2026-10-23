# 小组GitHub协作流程

团队仓库：https://github.com/hzc333/edgeai_robot_ws
组织方基线：https://github.com/dongjw-hit/edgeai_robot_ws（远程名`upstream`，只读）

基本原则：所有人从同一个团队`main`出发；每项工作在自己的分支上完成，通过Pull Request（PR）合并回`main`；**任何人都不直接推送`main`**。分支命名、审核人和合并门槛见`CONTRIBUTING.md`。

## 1. 仓库所有者一次性设置（hzc333）

1. **添加成员**：仓库 Settings → Collaborators → Add people，逐个输入队友的GitHub用户名。队友在邮件或GitHub通知中接受邀请后才有推送权限。
2. **保护`main`（可选，当前未启用）**：Settings → Branches → Add branch ruleset（或Add rule），目标分支`main`：
   - 勾选 Require a pull request before merging，Required approvals设为1；
   - 勾选 Require status checks to pass，添加`validate-contracts`和`pixi-environment`；
   - 勾选 Block force pushes；
   - 不要勾选允许绕过（包括管理员），否则规则对所有者无效。
3. **合并方式**：Settings → General → Pull Requests，只保留 Allow squash merging，并勾选 Automatically delete head branches。这样`main`上一项工作对应一个提交，历史清晰。

当前状态：仓库所有者决定暂不启用第2项保护。这意味着GitHub**不会阻止**任何协作者直接推送或强制推送`main`，第3节的流程完全依靠大家自觉遵守：不直接推送`main`、不对`main`强制推送、合并前确认CI通过。没有启用第3项设置时，合并PR前请在 Merge 按钮旁的下拉菜单中手动选择 **Squash and merge**。

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

团队`main`的历史完整包含组织方的提交，团队的准备工作是在组织方提交之后追加的。所以只要找到“你的改动是从组织方哪个提交开始的”，就可以把这之后你自己的提交原样搬到团队`main`上，不会重复也不会丢失。下面的命令让Git自动计算这个起点，不需要你记提交号。

先把远程改过来：

```bash
cd edgeai_robot_ws
git remote rename origin upstream
git remote add origin https://github.com/hzc333/edgeai_robot_ws.git
git fetch origin
git fetch upstream
```

先确认团队`main`已经包含组织方的最新提交（正常情况下会输出“已包含”）：

```bash
git merge-base --is-ancestor upstream/main origin/main && echo 已包含 || echo 未包含
```

如果输出“未包含”，说明组织方有了团队尚未同步的更新。先不要迁移，在群里通知负责同步的人按第5节同步，同步合并后再继续。

**改动还没有提交**：

```bash
git stash push -u -m "my-work"
git switch -c feature/pN-简短描述 origin/main
git stash pop
```

**改动已经提交在本地`main`上**：

```bash
BASE=$(git merge-base HEAD upstream/main)  # 你的改动从组织方哪个提交开始
git log --oneline $BASE..HEAD              # 先确认：这里列出的应全部是你自己的提交
git switch -c feature/pN-简短描述          # 从当前带改动的main分出
git rebase --onto origin/main $BASE        # 只把BASE之后你自己的提交搬到团队main上
git switch -C main origin/main             # 本地main对齐团队main
```

第二条命令列出的提交里如果出现了不是你写的提交，先停下来在群里问，不要继续。

有冲突时，按提示逐个修改文件，`git add`后执行`git rebase --continue`。不确定怎么解决时，执行`git rebase --abort`可以完全恢复到迁移之前的状态。最后检查`git log --oneline origin/main..`，应只剩你自己的提交。

切换环境后（例如以前用系统ROS构建过），先删除`build/`、`install/`和`log/`再重新构建。

## 3. 日常流程

```bash
# 1. 从最新的团队main开始一项工作
git switch main
git pull --ff-only
git switch -c feature/p1-multi-robot-namespace

# 2. 小步提交
git add 相关文件
git commit -m "说明做了什么"

# 3. 推送分支（第一次加-u）
git push -u origin feature/p1-multi-robot-namespace
```

然后在GitHub页面上点 Compare & pull request，按PR模板填写负责人、影响模块、接口变化、验证命令和回退方式，并指定审核人。CI的两项检查都通过、审核人批准后，由PR作者点 Squash and merge。

合并后清理本地：

```bash
git switch main
git pull --ff-only
git branch -D feature/p1-multi-robot-namespace
```

这里必须用大写`-D`。Squash合并会把分支上的提交压成`main`上的一个新提交，原分支的提交并没有原样进入`main`，所以Git会认为分支“未合并”，小写`-d`会报错拒绝删除。这不代表合并失败：PR页面显示Merged即可。

**合并后不要在旧分支上继续提交**。下一项工作一律从最新的`main`新开分支，否则已合并的改动会以冲突的形式重新出现。

### 让自己的分支跟上main

别人的PR合并后，在自己的分支上执行：

```bash
git fetch origin
git rebase origin/main
git push --force-with-lease
```

`--force-with-lease`只用于**自己的功能分支**，永远不要对`main`强制推送。

## 4. 容易出问题的地方

- **一个PR只做一件事**，尽量在几天内合并。分支存活越久，冲突越多。
- **共享接口单独提PR**：修改`src/edgeai_robot_interfaces`、`schemas/`或`config/interface_runtime.yaml`时，先单独提接口PR，由生产方、消费方和P5审核，合并后再提实现PR。
- **`pixi.lock`冲突不要手工合并**：先取团队`main`中的版本（`git checkout origin/main -- pixi.lock`），再执行`pixi lock`按你的`pixi.toml`重新生成，并在PR中说明依赖变化。
- **不要提交**：`build/`、`install/`、`log/`、`.pixi/`、`runs/`下的运行产物、rosbag、模型权重、密码、Token、实机IP或序列号。大文件（模型、数据集）放在团队网盘，仓库中只记录名称、版本和SHA-256。
- **同一文件多人修改**：先在群里说一声，或者由文件的负责人（见`docs/package_and_node_layout.md`）统一修改。
- **提交前自查**：

  ```bash
  pixi run validate
  git diff --check
  ```

## 5. 同步组织方更新

组织方仓库有更新时，由P5（或指定的一人）同步，其他人不要各自合并`upstream`：

```bash
git fetch upstream
git switch -c chore/sync-upstream origin/main
git merge upstream/main
git push -u origin chore/sync-upstream
```

然后提PR，在说明中列出组织方改了什么、影响哪些模块，由受影响负责人审核。规则书更新还要按`docs/rule_assumptions_and_tbd.md`第5节的检查清单执行。
