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

"""Build rclpy QoS profiles from the ``qos`` section of interface_runtime.yaml."""

from __future__ import annotations

from typing import Any

from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy

_RELIABILITY = {
    'reliable': ReliabilityPolicy.RELIABLE,
    'best_effort': ReliabilityPolicy.BEST_EFFORT,
}
_DURABILITY = {
    'volatile': DurabilityPolicy.VOLATILE,
    'transient_local': DurabilityPolicy.TRANSIENT_LOCAL,
}
_HISTORY = {
    'keep_last': HistoryPolicy.KEEP_LAST,
    'keep_all': HistoryPolicy.KEEP_ALL,
}


def qos_from_contract(runtime_contract: dict[str, Any], name: str) -> QoSProfile:
    """Return the QoS profile ``name`` (e.g. ``robot_state``) from the runtime contract."""
    try:
        spec = runtime_contract['qos'][name]
    except KeyError as exc:
        raise KeyError(f'QoS profile {name!r} is not defined in interface_runtime.yaml') from exc
    return QoSProfile(
        reliability=_RELIABILITY[spec['reliability']],
        durability=_DURABILITY[spec['durability']],
        history=_HISTORY[spec['history']],
        depth=int(spec.get('depth', 1)),
    )
