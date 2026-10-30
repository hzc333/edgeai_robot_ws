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

"""Real DDS/actions with P1's existing mock; no private substitute interfaces."""

import json
import threading
import time

from edgeai_common.config import load_runtime_contract
from edgeai_common.qos import qos_from_contract
from edgeai_robot_interfaces.msg import CompetitionState, EmergencyStop
from edgeai_robot_interfaces.srv import SetCompetitionPhase
from edgeai_system_tests.mocks.mock_robot_agent import MockRobotAgent
from edgeai_task_coordinator.coordinator import Coordinator
import pytest
import rclpy
from rclpy.executors import MultiThreadedExecutor, SingleThreadedExecutor
from rclpy.node import Node
from rclpy.parameter import Parameter
from rosgraph_msgs.msg import Clock
from std_msgs.msg import String


def wait_for(predicate, timeout=15):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(0.02)
    return False


class Harness:
    def __init__(self, tmp_path):
        self.control = Node('p4_test_control')
        self.started = time.monotonic()
        self.sim_time = 100.0
        self.heartbeat = True
        self.phase = CompetitionState.PHASE_TASK2A
        self.phase_sequence = 1
        self.generation = 1
        self.control_qos = qos_from_contract(load_runtime_contract(), 'control_state')
        self.phase_pub = self.control.create_publisher(
            CompetitionState, '/competition/state', self.control_qos)
        self.estop_pub = self.control.create_publisher(
            EmergencyStop, '/competition/estop', self.control_qos)
        self.finish_requests = []
        self.control.create_service(SetCompetitionPhase, '/competition/set_phase', self._set_phase)
        self.clock_pub = self.control.create_publisher(Clock, '/clock', 10)
        self.control.create_timer(0.02, self._publish_clock)
        self.control.create_timer(0.2, self._publish_phase)
        self.snapshots = []
        self.control.create_subscription(String, '/edge/midterm_rescue/status',
                                         lambda m: self.snapshots.append(json.loads(m.data)),
                                         qos_from_contract(load_runtime_contract(), 'snapshot'))
        overrides = [Parameter('use_sim_time', value=True),
                     Parameter('require_map', value=False),
                     Parameter('test_mode', value=True),
                     Parameter('output_dir', value=str(tmp_path))]
        self.coordinator = Coordinator(parameter_overrides=overrides)
        self.mocks = [MockRobotAgent(namespace=f'/robot_{i + 1}', parameter_overrides=[
            Parameter('robot_id', value=f'robot_{i + 1}'),
            Parameter('use_sim_time', value=True),
            Parameter('initial_x', value=0.5 + i * 0.7),
            Parameter('initial_y', value=0.5),
            Parameter('linear_speed', value=12.0),
            Parameter('angular_speed', value=12.0),
        ]) for i in range(2)]
        # Mirror production: P4 has a serial executor; P1's blocking action
        # servers run independently, as they do in their own real processes.
        self.executor = SingleThreadedExecutor()
        self.mock_executor = MultiThreadedExecutor(num_threads=6)
        for node in (self.control, self.coordinator, self.coordinator.registry,
                     self.coordinator.verifier_node):
            self.executor.add_node(node)
        for node in self.mocks:
            self.mock_executor.add_node(node)
        self.thread = threading.Thread(target=self.executor.spin, daemon=True)
        self.mock_thread = threading.Thread(target=self.mock_executor.spin, daemon=True)
        self.thread.start()
        self.mock_thread.start()

    def _publish_clock(self):
        self.sim_time = 100 + 2 * (time.monotonic() - self.started)
        msg = Clock()
        msg.clock.sec = int(self.sim_time)
        msg.clock.nanosec = int(self.sim_time % 1 * 1e9)
        self.clock_pub.publish(msg)

    def _publish_phase(self):
        if self.heartbeat:
            msg = CompetitionState(run_id='p4-test-run', map_id='p4-test-map', map_revision=1,
                                   phase=self.phase, phase_sequence=self.phase_sequence)
            msg.header.stamp.sec = int(self.sim_time)
            msg.header.stamp.nanosec = int(self.sim_time % 1 * 1e9)
            self.phase_pub.publish(msg)

    def _set_phase(self, request, response):
        self.finish_requests.append(request)
        response.accepted = bool(self.coordinator.engine
                                 and self.coordinator.engine.status == 'DONE')
        if response.accepted:
            self.phase = request.requested_phase
            self.phase_sequence += 1
            self._publish_phase()
        response.current_phase = self.phase
        response.phase_sequence = self.phase_sequence
        return response

    def active(self):
        return self.coordinator.engine and self.coordinator.engine.status == 'ACTIVE'

    def close(self):
        self.phase, self.phase_sequence = CompetitionState.PHASE_FROZEN, self.phase_sequence + 1
        self.heartbeat = True
        self._publish_phase()
        wait_for(lambda: all(m.active_goal is None for m in self.mocks)
                 and not self.coordinator.handles and not self.coordinator.goal_records, timeout=3)
        self.coordinator.timer.cancel()
        time.sleep(0.3)
        self.executor.shutdown(timeout_sec=5)
        self.mock_executor.shutdown(timeout_sec=5)
        self.thread.join(timeout=5)
        self.mock_thread.join(timeout=5)
        self.coordinator.close()
        for mock in self.mocks:
            mock.destroy_node()
        self.control.destroy_node()


@pytest.fixture
def harness(tmp_path):
    rclpy.init()
    h = Harness(tmp_path)
    try:
        yield h
    finally:
        h.close()
        rclpy.shutdown()


def test_two_rescues_over_real_actions_and_persisted_evidence(harness):
    h = harness
    assert wait_for(lambda: h.coordinator.engine and h.coordinator.engine.status == 'DONE', 35)
    directory = h.coordinator.journal.directory
    events = [json.loads(line) for line in (directory / 'events.jsonl').read_text().splitlines()]
    completed = [e for e in events if e['type'] == 'COMPLETED']
    assert [e['target_id'] for e in completed] == ['S1', 'C1']
    for event in completed:
        region = event['verification_region']
        assert event['dwell_elapsed_s'] >= 10
        assert region['center'] == ([1.0, 4.1] if event['target_id'] == 'S1' else [4.1, 1.0])
    assert len(set(completed[1]['robot_ids'])) == 2
    assert not h.coordinator.goal_records
    assert all(m.active_goal is None for m in h.mocks)
    assert all(m.velocity == (0.0, 0.0) for m in h.mocks)
    assert h.snapshots[-1]['collision_status'] == 'external_verification_required'
    assert wait_for(lambda: len(h.finish_requests) == 1)
    assert h.finish_requests[0].requester_type == SetCompetitionPhase.Request.REQUESTER_SYSTEM
    assert h.finish_requests[0].requested_phase == CompetitionState.PHASE_FROZEN


def test_freeze_cancels_real_mock_action_and_halts(harness):
    h = harness
    assert wait_for(h.active)
    assert wait_for(lambda: bool(h.coordinator.handles))
    h.phase, h.phase_sequence = CompetitionState.PHASE_FROZEN, 2
    h._publish_phase()
    assert wait_for(lambda: h.coordinator.engine.status == 'HALTED')
    assert wait_for(lambda: all(m.active_goal is None for m in h.mocks))
    assert not h.coordinator.engine.completed


def test_estop_old_generation_cannot_release_stop(harness):
    h = harness
    assert wait_for(h.active)
    h.estop_pub.publish(EmergencyStop(generation=2, active=True, reason='P4 test'))
    assert wait_for(lambda: h.coordinator.estop)
    h.estop_pub.publish(EmergencyStop(generation=1, active=False))
    assert wait_for(lambda: h.coordinator.engine.status == 'HALTED')
    assert h.coordinator.estop
    assert not h.coordinator.engine.completed


def test_edge_heartbeat_loss_cancels_without_scoring(harness):
    h = harness
    assert wait_for(h.active)
    assert wait_for(lambda: bool(h.coordinator.handles))
    h.heartbeat = False
    assert wait_for(lambda: h.coordinator.engine.status == 'HALTED')
    assert wait_for(lambda: all(m.active_goal is None for m in h.mocks))
    assert not h.coordinator.engine.completed


def test_shutdown_cancels_even_while_p2_heartbeat_continues(harness):
    h = harness
    assert wait_for(h.active)
    assert wait_for(lambda: bool(h.coordinator.handles))
    h.coordinator.shutdown_requested = True
    assert wait_for(lambda: h.coordinator.engine.status == 'HALTED')
    assert wait_for(lambda: all(m.active_goal is None for m in h.mocks))
    assert h.heartbeat
    assert not h.coordinator.engine.completed
