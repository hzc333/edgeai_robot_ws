# Task 2B中一个任务步骤的执行状态。
string step_id
string target_id

uint8 STATE_WAITING_FOR_PREDECESSORS=0
uint8 STATE_READY=1
uint8 STATE_IN_PROGRESS=2
uint8 STATE_COMPLETED=3
uint8 STATE_FAILED=4
uint8 STATE_BLOCKED=5
uint8 STATE_CANCELLED=6
uint8 state

# 该步骤当前或最后一次对应的RescueTask；尚未生成任务时为空。
string task_id
string[] robot_ids
builtin_interfaces/Time completed_at
TaskReason reason
