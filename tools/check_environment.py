#!/usr/bin/env python3
"""Check that the active shell matches the team's canonical ROS 2 environment.

Run inside the environment being checked, for example ``pixi run check-env``.
"""

from __future__ import annotations

import argparse
import importlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tomllib


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_ROS_PACKAGES = (
    # Simulation and robot description
    "ros_gz_sim",
    "ros_gz_bridge",
    "robot_state_publisher",
    "xacro",
    # Mapping and navigation
    "slam_toolbox",
    "nav2_bringup",
    "nav2_map_server",
    "nav2_amcl",
    "nav2_lifecycle_manager",
    "nav2_planner",
    "nav2_controller",
    "nav2_bt_navigator",
    "nav2_behaviors",
    "nav2_costmap_2d",
    # Recording
    "rosbag2_py",
    "rosbag2_storage_mcap",
    # Perception
    "cv_bridge",
)

errors: list[str] = []
warnings: list[str] = []


def ok(message: str) -> None:
    print(f"OK    {message}")


def warn(message: str) -> None:
    warnings.append(message)
    print(f"WARN  {message}")


def error(message: str) -> None:
    errors.append(message)
    print(f"ERROR {message}")


def pinned_opencv_series() -> str:
    """Return the OpenCV major.minor series pinned in pixi.toml, e.g. '4.12'."""
    manifest = tomllib.loads((ROOT / "pixi.toml").read_text(encoding="utf-8"))
    pin = manifest["dependencies"]["py-opencv"]
    match = re.fullmatch(r"(\d+\.\d+)\.\*", pin)
    if match is None:
        raise ValueError(f"pixi.toml: py-opencv pin must look like '4.12.*', got {pin!r}")
    return match.group(1)


def detect_environment() -> str:
    if os.environ.get("PIXI_PROJECT_ROOT") or os.environ.get("PIXI_ENVIRONMENT_NAME"):
        return "pixi"
    if sys.prefix.startswith(str(ROOT / ".pixi")):
        return "pixi"
    return "system_ros"


def check_ros_basics() -> None:
    distro = os.environ.get("ROS_DISTRO")
    if distro == "jazzy":
        ok("ROS_DISTRO=jazzy")
    else:
        error(f"ROS_DISTRO must be jazzy, got {distro!r}; activate pixi or source /opt/ros/jazzy")

    rmw = os.environ.get("RMW_IMPLEMENTATION")
    if rmw == "rmw_cyclonedds_cpp":
        ok("RMW_IMPLEMENTATION=rmw_cyclonedds_cpp")
    else:
        error(f"RMW_IMPLEMENTATION must be rmw_cyclonedds_cpp, got {rmw!r}")


def check_ros_packages() -> None:
    try:
        from ament_index_python.packages import (
            PackageNotFoundError,
            get_package_prefix,
        )
    except ImportError:
        error("ament_index_python unavailable; ROS environment is not active")
        return

    missing = []
    for package in REQUIRED_ROS_PACKAGES:
        try:
            get_package_prefix(package)
        except PackageNotFoundError:
            missing.append(package)
    if missing:
        error(f"missing ROS packages: {', '.join(missing)}")
    else:
        ok(f"{len(REQUIRED_ROS_PACKAGES)} required ROS packages found")

    try:
        get_package_prefix("edgeai_robot_interfaces")
        importlib.import_module("edgeai_robot_interfaces.msg")
        ok("workspace interfaces built and importable")
    except (PackageNotFoundError, ImportError):
        warn("edgeai_robot_interfaces not found; run the build and source install/setup.bash")


def check_opencv(environment: str, allow_system_opencv: bool) -> None:
    expected = pinned_opencv_series()
    try:
        import cv2
    except ImportError:
        error("python cv2 unavailable")
        return

    actual = ".".join(cv2.__version__.split(".")[:2])
    if actual == expected:
        ok(f"OpenCV {cv2.__version__} matches pinned series {expected}")
    else:
        message = (
            f"OpenCV {cv2.__version__} does not match pinned series {expected} "
            f"({environment}); ArUco detection results are not valid acceptance evidence"
        )
        if environment == "system_ros" and allow_system_opencv:
            warn(message)
        else:
            error(message)

    if hasattr(cv2, "aruco") and hasattr(cv2.aruco, "ArucoDetector"):
        ok("cv2.aruco.ArucoDetector available")
    else:
        message = "cv2.aruco.ArucoDetector unavailable (OpenCV < 4.7 API)"
        if environment == "system_ros" and allow_system_opencv:
            warn(message)
        else:
            error(message)

    try:
        importlib.import_module("cv_bridge")
        ok("cv_bridge python module importable")
    except ImportError as exc:
        error(f"cv_bridge python module import failed: {exc}")


def check_python_tools() -> None:
    try:
        import yaml  # noqa: F401
        ok("PyYAML available")
    except ImportError:
        error("PyYAML unavailable")

    try:
        import jsonschema  # noqa: F401
    except ImportError:
        error("jsonschema unavailable; contract schema validation would be skipped")
        return
    try:
        importlib.import_module("referencing")
        ok("jsonschema with referencing available")
    except ImportError:
        warn("jsonschema < 4.18; validator falls back to the deprecated RefResolver")


def check_gazebo() -> None:
    if shutil.which("gz") is None:
        warn("gz not on PATH; Gazebo Harmonic is a host requirement for simulation")
        return
    result = subprocess.run(
        ["gz", "sim", "--version"], capture_output=True, text=True, timeout=30
    )
    match = re.search(r"version (\d+)\.", result.stdout + result.stderr)
    if match and match.group(1) == "8":
        ok("Gazebo Sim 8.x (Harmonic)")
    else:
        warn(f"could not confirm Gazebo Sim 8.x: {result.stdout.strip() or result.stderr.strip()}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--allow-system-opencv",
        action="store_true",
        help="downgrade OpenCV mismatches to warnings in a system ROS shell "
        "(local non-perception development only)",
    )
    args = parser.parse_args()

    environment = detect_environment()
    print(f"Environment: {environment} (python {sys.version.split()[0]} at {sys.prefix})")
    if environment != "pixi":
        warn("system ROS is a secondary development environment; acceptance and "
             "integration runs must use pixi")

    check_ros_basics()
    check_ros_packages()
    check_opencv(environment, args.allow_system_opencv)
    check_python_tools()
    check_gazebo()

    print(f"\n{len(errors)} error(s), {len(warnings)} warning(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
