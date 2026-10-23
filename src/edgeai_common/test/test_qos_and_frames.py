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

from edgeai_common.frames import frame, topic, validate_robot_id
from edgeai_common.qos import qos_from_contract
import pytest
from rclpy.qos import DurabilityPolicy, ReliabilityPolicy

CONTRACT = {
    'qos': {
        'robot_state': {'reliability': 'reliable', 'durability': 'volatile',
                        'history': 'keep_last', 'depth': 1},
        'control_state': {'reliability': 'reliable', 'durability': 'transient_local',
                          'history': 'keep_last', 'depth': 1},
        'sensor_data': {'reliability': 'best_effort', 'durability': 'volatile',
                        'history': 'keep_last', 'depth': 5},
    },
}


def test_qos_profiles_follow_contract():
    control = qos_from_contract(CONTRACT, 'control_state')
    assert control.reliability == ReliabilityPolicy.RELIABLE
    assert control.durability == DurabilityPolicy.TRANSIENT_LOCAL
    assert control.depth == 1
    sensor = qos_from_contract(CONTRACT, 'sensor_data')
    assert sensor.reliability == ReliabilityPolicy.BEST_EFFORT
    assert sensor.depth == 5


def test_unknown_qos_profile_is_an_error():
    with pytest.raises(KeyError):
        qos_from_contract(CONTRACT, 'missing')


def test_frame_and_topic_names():
    assert frame('robot_2', 'odom') == 'robot_2/odom'
    assert topic('robot_3', 'scan') == '/robot_3/scan'
    assert topic('robot_3', '/camera/image') == '/robot_3/camera/image'


@pytest.mark.parametrize('robot_id', ['robot_0', 'robot_5', 'robot1', '/robot_1', ''])
def test_invalid_robot_ids_are_rejected(robot_id):
    with pytest.raises(ValueError):
        validate_robot_id(robot_id)
