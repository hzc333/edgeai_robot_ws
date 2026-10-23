#!/usr/bin/env bash
set -e

# Workspace directory
WS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$WS_DIR"

# Prefer the locked Pixi environment, but support a complete system ROS 2 Jazzy
# installation for development machines that do not have Pixi installed.
if command -v pixi >/dev/null 2>&1; then
    PIXI_HOOK="$(pixi shell-hook)"
    eval "$PIXI_HOOK"
    unset PIXI_HOOK
    BUILD_COMMAND="pixi run colcon build --symlink-install"
elif [[ -f /opt/ros/jazzy/setup.bash ]]; then
    source /opt/ros/jazzy/setup.bash
    export RMW_IMPLEMENTATION="${RMW_IMPLEMENTATION:-rmw_cyclonedds_cpp}"
    BUILD_COMMAND="source /opt/ros/jazzy/setup.bash && colcon build --symlink-install"
else
    echo "Neither Pixi nor /opt/ros/jazzy/setup.bash is available."
    exit 1
fi

# Source ROS 2 workspace
if [[ ! -f install/setup.bash ]]; then
    echo "Workspace has not been built."
    echo "Run: $BUILD_COMMAND"
    exit 1
fi

source install/setup.bash

# Register cleanup before starting any background processes.
CHILD_PIDS=()
cleanup() {
    trap - EXIT INT TERM
    if (( ${#CHILD_PIDS[@]} )); then
        kill "${CHILD_PIDS[@]}" 2>/dev/null || true
        wait "${CHILD_PIDS[@]}" 2>/dev/null || true
    fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# Number of robots to spawn (1-4); robot IDs are robot_1 .. robot_N.
ROBOT_COUNT="${1:-1}"
if ! [[ "$ROBOT_COUNT" =~ ^[1-4]$ ]]; then
    echo "Usage: $0 [robot_count 1-4]"
    exit 1
fi
ROBOTS="$(seq -s, -f 'robot_%g' 1 "$ROBOT_COUNT")"

# Launch files and nodes locate the repository config/ through this variable.
export EDGEAI_CONFIG_DIR="$WS_DIR/config"

echo "Starting EdgeAI simulation with robots: $ROBOTS"

# Development mode without a competition phase manager: the safety watchdog
# lets manual commands on /robot_N/cmd_vel_manual through (ADR-0003).
ros2 launch edgeai_robot_bringup sim_multi_robot.launch.py \
    robots:="$ROBOTS" rviz:=true run_mode:=development require_competition_state:=false &
SIM_PID=$!
CHILD_PIDS+=("$SIM_PID")

wait "$SIM_PID"
