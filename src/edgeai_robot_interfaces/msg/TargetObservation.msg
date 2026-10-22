# One raw, robot-local target observation. The header frame is the sensor frame
# in which marker_pose is expressed. A fusion node is responsible for TF lookup,
# outlier rejection, deduplication, and conversion into a Target.
std_msgs/Header header
string run_id
string robot_id
int32 marker_id
string target_id

uint8 TYPE_UNKNOWN=0
uint8 TYPE_NORMAL=1
uint8 TYPE_COOPERATIVE=2
uint8 target_type

geometry_msgs/PoseWithCovariance marker_pose
float32 confidence
string detector_version
