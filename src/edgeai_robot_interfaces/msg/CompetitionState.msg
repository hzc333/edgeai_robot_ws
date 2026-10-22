# 当前比赛阶段的权威快照，发布于/competition/state。
std_msgs/Header header
string run_id
uint64 phase_sequence
string map_id
uint32 map_revision
uint32 target_revision

uint8 RUN_MODE_DEVELOPMENT=0
uint8 RUN_MODE_REHEARSAL=1
uint8 RUN_MODE_COMPETITION=2
uint8 run_mode
# 本次运行实际生效的参数集合哈希，与manifest中的system/parameters.yaml一致。
string parameters_sha256

uint8 PHASE_PREPARATION=0
uint8 PHASE_TASK1=1
uint8 PHASE_HANDOVER=2
uint8 PHASE_TASK2A=3
uint8 PHASE_FROZEN=4
uint8 PHASE_TASK2B=5
uint8 PHASE_FINISHED=6
uint8 PHASE_ESTOP=7
uint8 PHASE_NONE=255
uint8 phase
# ESTOP或由急停释放进入的FROZEN中，记录被中断的阶段；其他情况为PHASE_NONE。
uint8 interrupted_phase

builtin_interfaces/Time phase_started_at
bool frozen
bool estop_active

uint32 reset_count
bool reset_in_progress
string[] resetting_robot_ids
string reason
