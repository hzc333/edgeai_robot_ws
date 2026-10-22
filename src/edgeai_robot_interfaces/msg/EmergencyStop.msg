# 独立于任务协调器的急停状态，发布于/competition/estop。
# generation每次改变active时递增，便于检测重复或过期消息。
std_msgs/Header header
string run_id
uint64 generation
bool active
string source
string reason
