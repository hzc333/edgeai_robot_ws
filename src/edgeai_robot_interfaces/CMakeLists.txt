cmake_minimum_required(VERSION 3.8)
project(edgeai_robot_interfaces)

find_package(ament_cmake REQUIRED)
find_package(builtin_interfaces REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(std_msgs REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/TargetObservation.msg"
  "msg/Target.msg"
  "msg/TargetArray.msg"
  "msg/SystemFault.msg"
  "msg/TaskReason.msg"
  "msg/RobotState.msg"
  "msg/RobotStateArray.msg"
  "msg/RobotPhaseAck.msg"
  "msg/CompetitionState.msg"
  "msg/EmergencyStop.msg"
  "msg/ExplorationStatus.msg"
  "msg/RescueTask.msg"
  "msg/RescueEvent.msg"
  "msg/MissionStep.msg"
  "msg/MissionPlan.msg"
  "msg/MissionValidationIssue.msg"
  "msg/MissionIntakeResult.msg"
  "msg/MissionStepState.msg"
  "msg/MissionExecutionState.msg"
  "action/ExecuteNavigationGoal.action"
  "action/ExecuteRescueTask.action"
  "srv/FinalizeTask1.srv"
  "srv/SetCompetitionPhase.srv"
  "srv/SubmitMission.srv"
  "srv/ValidateMission.srv"
  "srv/RequestReset.srv"
  "srv/Relocalize.srv"
  DEPENDENCIES builtin_interfaces geometry_msgs std_msgs
)

ament_export_dependencies(rosidl_default_runtime)
ament_package()
