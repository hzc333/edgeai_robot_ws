# Aggregated state reported by one robot. header.frame_id must be map whenever
# localized is true. Consumers determine staleness from header.stamp.
std_msgs/Header header
string run_id
string robot_id

uint8 MODE_OFFLINE=0
uint8 MODE_STANDBY=1
uint8 MODE_EXPLORING=2
uint8 MODE_NAVIGATING=3
# 已到达救援位姿并保持静止。是否在救援区内、是否在等待伙伴或停留计时，
# 由边缘救援验证器判断，机器人不判断。取值5保留。
uint8 MODE_HOLDING=4
uint8 MODE_SAFE=6
uint8 MODE_ESTOP=7
uint8 MODE_ERROR=8
uint8 mode

geometry_msgs/PoseWithCovariance pose
geometry_msgs/TwistWithCovariance velocity
bool localized
bool navigation_available
# 取值0到100；无法读取电池信息时使用NaN。
float32 battery_percentage
string active_task_id
SystemFault[] faults
