# A deduplicated rescue target in the shared global map frame.
std_msgs/Header header
string run_id
string map_id
uint32 map_revision
string target_id
int32 marker_id

uint8 TYPE_UNKNOWN=0
uint8 TYPE_NORMAL=1
uint8 TYPE_COOPERATIVE=2
uint8 target_type

geometry_msgs/PoseWithCovariance marker_pose
# Derived from marker_pose using the versioned official geometry rule. Empty
# while that rule is unavailable; one pose is expected for normal targets and
# two for cooperative targets.
geometry_msgs/PoseStamped[] rescue_poses
uint32 observation_count
float32 confidence
string[] observed_by

# True only if the target was present in the frozen Task 1 target list.
bool eligible_for_basic_rescue
