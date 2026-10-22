# Coordinator-owned executable task. goal_poses contains one pose for a normal
# target and two poses for a cooperative target. assigned_robot_ids and
# goal_poses use the same index ordering, and index i is rescue zone i.
std_msgs/Header header
string run_id
string map_id
uint32 map_revision
string task_id
string target_id

# Task 2B任务填写来源计划和步骤；Task 2A任务两者均为空。
string mission_id
string step_id

uint8 STAGE_TASK2A=1
uint8 STAGE_TASK2B=2
uint8 scoring_stage

uint8 TYPE_NORMAL=1
uint8 TYPE_COOPERATIVE=2
uint8 task_type

uint8 STATE_PENDING=0
uint8 STATE_READY=1
uint8 STATE_ASSIGNED=2
uint8 STATE_NAVIGATING=3
uint8 STATE_WAITING_FOR_PARTNER=4
uint8 STATE_DWELLING=5
uint8 STATE_COMPLETED=6
uint8 STATE_FAILED=7
uint8 STATE_CANCELLED=8
uint8 STATE_BLOCKED=9
uint8 state

uint32 priority
string[] predecessor_task_ids
string[] assigned_robot_ids
geometry_msgs/PoseStamped[] goal_poses
# 边缘救援验证器使用的判定参数，随任务公开以便审计。
float32 zone_tolerance_m
builtin_interfaces/Duration required_dwell
TaskReason status_reason
