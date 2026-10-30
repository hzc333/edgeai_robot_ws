# P4 中期模块交接

## 边界

实现包名为`edgeai_task_coordinator`。仓库旧规划中的`edgeai_rescue_coordinator`
目前没有实现，团队后续可统一更新名称；本次没有修改共享规划、消息或队友源码。
官方中期文档决定救援规则；完整比赛的旧冻结目标资格规则没有套用于中期固定目标。

正常启动只运行P4三个节点，不包含测试控制器或Mock，也不加载测试地图。
开发验证脚本额外提供P2阶段/定位测试替身，以便独立验证P4；正式联调必须替换。

## P1交接

* 命名空间默认`/robot_1`和`/robot_2`，可在P4配置选择两台不同标准ID。
* `state`使用真实RobotState消息；frame为map，位姿参考base_footprint，时间来自/clock。
* 状态含localized、navigation_available、mode、active_task_id和faults；ERROR及以上故障
  不参与分配和计时。重复/旧时间戳不延长停留。
* 通用导航动作的request_id等于当前P4 task_id，purpose为TRANSIT；
  到达接近点后等待动作终态和空闲状态，再发送同一任务的救援动作。
* 救援hold_timeout=0：保持直至P4取消，不能把它设成10秒充当救援判定。
* C1两个机器人共享task_id，rescue_zone_index分别为0和1，对应导航槽位，
  官方完成判定仍围绕同一个C1中心。
* 释放必须有动作终态及空闲/停稳状态确认；不要把正常取消作为救援失败。
* 接近点需要在实际模型、地图上复核。新路径需要更长超时，应通过既有
  ExecuteNavigationGoal.timeout传入；本次没有修改P1的全局60秒默认值。

## P2交接

* 提供预建/map、正确地图原点与map坐标；官方S1/C1坐标不可未经变换直接放进旧中心原点地图。
* 提供/clock、/competition/state、/competition/estop及匹配的run_id/map_id/map_revision。
* 重新定位由P2编排。机器人全部定位就绪后进入TASK2A，P4自动开始。
* P4不会要求中期目标被Part 1观察、冻结，也不会伪造eligible_for_basic_rescue。
* 心跳应给P1一秒失联阈值留足余量；开发控制器使用5Hz墙钟心跳，未修改共享rate配置。
* P4完成两项救援、收到动作释放和停稳确认后，以REQUESTER_SYSTEM请求FROZEN。
  P2拥有服务与阶段发布权，负责收集phase_ack并确认最终冻结。
* 本包公开/edge/midterm_rescue/status作为JSON快照；DONE表示两项完成且资源释放，
  HALTED要求检查failure/error。WAITING_FOR_P2_SERVICE不代表救援失败。
* P4的事件目录只保存本模块证据，不替代P2全局events.jsonl或Manifest。
* Part 1/2切换、任务初始化、共用13分钟总计时仍由P2完成；不能在进入TASK2A时
  重启或暂停整队总计时。开发验证单独报告启动定位准备和TASK2A运行时长。

## P3与P5交接

P3：官方中期marker 1=S1、2=C1；本模块固定坐标输入不发布/edge/targets，
因此不会与感知权威注册表竞争。后续可为感知输入新增适配，复用验证与执行组件。

P5：RescueEvent沿用既有接口；新增私有JSON状态显式写出目标圆心与半径。
RescueTask旧zone_tolerance_m语义围绕各救援点，暂未被重新解释或发布。
正式统一消息时，需共同决定如何表达“导航目标”和“完成区域”，并版本化迁移。

共享参数解析仍按原仓库全流程required_for_motion执行，中期不使用的Task 2B参数
可能阻塞正式run_mode启动。需P1/P2/P5统一做中期流程门禁适配；不要为了通过门禁
填入假官方值。独立仿真明确使用development机器人栈，P4救援条件始终来自官方文档。

## 最小联调步骤

1. P1/P2启动官方布局、两台机器人、预建地图、时钟和HANDOVER心跳。
2. P2调用每台机器人的relocalize并确认定位、导航和安全状态。
3. 启动本包midterm_rescue.launch.py；确认只有一个状态注册表和救援验证器。
4. P2进入TASK2A，观察自动分配、接近点导航、S1完成、C1双机完成及释放。
5. P2接受FROZEN请求，核对两台机器人相同phase_sequence的safe确认。
6. 保存P4事件、距离记录和团队日志，核验Part 1与切换耗时也包含在13分钟内。

全程无需操作员逐个输入导航点。若发生地图/运行身份变化或进程中断，
先确认停车，由P2建立新run后重启P4；当前版本不自动续接未完成任务。
