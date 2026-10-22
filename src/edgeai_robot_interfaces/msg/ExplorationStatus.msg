# Task 1探索状态。coverage_fraction取值[0,1]；无法计算时使用NaN。
std_msgs/Header header
string run_id
string map_id
uint32 map_revision

uint8 STATE_IDLE=0
uint8 STATE_RUNNING=1
uint8 STATE_PAUSED=2
uint8 STATE_COMPLETED=3
uint8 STATE_FAILED=4
uint8 state

string[] active_robot_ids
float32 coverage_fraction
uint32 active_frontier_count
builtin_interfaces/Duration elapsed
TaskReason reason
