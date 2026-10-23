# Copyright 2026 EdgeAI Robotics Challenge Team
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Frame and topic naming helpers for the robot_N/ prefix convention (ADR-0002)."""

from __future__ import annotations

import re

GLOBAL_FRAME = 'map'
_ROBOT_ID = re.compile(r'^robot_[1-4]$')


def validate_robot_id(robot_id: str) -> str:
    """Return ``robot_id`` unchanged or raise ValueError if it is not robot_1..robot_4."""
    if not _ROBOT_ID.fullmatch(robot_id):
        raise ValueError(f'invalid robot_id {robot_id!r}; expected robot_1 .. robot_4')
    return robot_id


def frame(robot_id: str, name: str) -> str:
    """Return the robot-prefixed frame name, for example robot_2/odom."""
    return f'{validate_robot_id(robot_id)}/{name}'


def topic(robot_id: str, name: str) -> str:
    """Return the absolute robot topic name, for example /robot_2/scan."""
    return f'/{validate_robot_id(robot_id)}/{name.lstrip("/")}'
