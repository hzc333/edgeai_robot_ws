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

echo "Starting EdgeAI realistic robot simulation..."

ros2 launch edgeai_robot_description simulation_real.launch.py &
SIM_PID=$!
CHILD_PIDS+=("$SIM_PID")

sleep 5

echo "Starting RViz..."

rviz2 -d \
    "$WS_DIR/src/edgeai_robot_description/rviz/realistic_robot.rviz" &
RVIZ_PID=$!
CHILD_PIDS+=("$RVIZ_PID")

wait "$SIM_PID"
