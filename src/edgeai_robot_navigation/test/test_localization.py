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

"""Tests for the localization node and its relocalize service (P1 plan 3-02)."""

import math
from pathlib import Path
import threading
import time

from builtin_interfaces.msg import Duration
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus
from edgeai_common.config import load_runtime_contract
from edgeai_common.qos import qos_from_contract
from edgeai_robot_interfaces.msg import CompetitionState, TaskReason
from edgeai_robot_interfaces.srv import Relocalize
from edgeai_robot_navigation.localization import converged, Localization, scan_match_ratio
from geometry_msgs.msg import PoseWithCovarianceStamped, TransformStamped
from nav2_msgs.srv import ManageLifecycleNodes
from nav_msgs.msg import OccupancyGrid
import pytest
import rclpy
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.parameter import Parameter
from rclpy.qos import DurabilityPolicy, qos_profile_sensor_data, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import LaserScan
from std_srvs.srv import Empty, Trigger
from tf2_ros import StaticTransformBroadcaster

RUN_ID, MAP_ID = 'run-test', 'map-test'
START_POSES = '{task1_start: {x: -1.5, y: -1.5, yaw: 0.0}}'


def test_convergence_check():
    cov = [0.0] * 36
    cov[0] = cov[7] = 0.005
    cov[35] = 0.005
    assert converged(cov, 0.10, 0.10)
    cov[35] = 0.02
    assert not converged(cov, 0.10, 0.10)


def _room(size_cells=60, res=0.05):
    """Square room centred on the origin with one-cell walls."""
    data = [0] * (size_cells * size_cells)
    for i in range(size_cells):
        for j in (0, size_cells - 1):
            data[j * size_cells + i] = 100
            data[i * size_cells + j] = 100
    half = size_cells * res / 2.0
    return {'width': size_cells, 'height': size_cells, 'resolution': res,
            'origin_x': -half, 'origin_y': -half, 'origin_yaw': 0.0, 'data': data}


def test_scan_match_ratio_distinguishes_right_and_wrong_pose():
    room = _room()           # walls at about +-1.475 m
    n = 360
    inc = 2 * math.pi / n
    ranges = []
    for i in range(n):
        a = -math.pi + i * inc
        # Distance from the centre to the square wall along direction a.
        ranges.append(1.475 / max(abs(math.cos(a)), abs(math.sin(a))))
    right, valid = scan_match_ratio(ranges, -math.pi, inc, 0.15, 12.0, room, (0.0, 0.0, 0.0))
    wrong, _ = scan_match_ratio(ranges, -math.pi, inc, 0.15, 12.0, room, (0.6, -0.4, 0.5))
    assert valid == n
    assert right > 0.95
    assert wrong < 0.5


def _config_dir():
    for parent in Path(__file__).resolve().parents:
        if (parent / 'config' / 'interface_runtime.yaml').is_file():
            return str(parent / 'config')
    pytest.skip('repository config directory not found')


class FakeAmclStack(Node):
    """AMCL, its lifecycle manager and the navigation lifecycle manager."""

    def __init__(self):
        super().__init__('fake_amcl', namespace='robot_1')
        group = ReentrantCallbackGroup()
        self.amcl_active = False
        self.nav_active = False
        self.converge = True           # report a small covariance after initialpose
        self.global_inits = 0
        self.nomotion_calls = 0
        self.pose = None
        self.initial_covariance = None
        self.pub = self.create_publisher(PoseWithCovarianceStamped, 'amcl_pose', 10)
        self.create_subscription(PoseWithCovarianceStamped, 'initialpose', self._on_initial, 10,
                                 callback_group=group)
        for name, attr in (('lifecycle_manager_localization', 'amcl_active'),
                           ('lifecycle_manager_navigation', 'nav_active')):
            self.create_service(ManageLifecycleNodes, f'{name}/manage_nodes',
                                self._manager(attr), callback_group=group)
            self.create_service(Trigger, f'{name}/is_active', self._is_active(attr),
                                callback_group=group)
        self.create_service(Empty, 'reinitialize_global_localization', self._global,
                            callback_group=group)
        self.create_service(Empty, 'request_nomotion_update', self._nomotion,
                            callback_group=group)
        self.create_timer(0.1, self._publish, callback_group=group)
        # Scan, map and laser mounting used by the scan-to-map check.
        self.map_occupied = True
        self.scan_pub = self.create_publisher(LaserScan, 'scan', qos_profile_sensor_data)
        self.map_pub = self.create_publisher(OccupancyGrid, '/map', QoSProfile(
            depth=1, reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL))
        self.publish_map()
        laser = TransformStamped()
        laser.header.frame_id = 'robot_1/base_footprint'
        laser.child_frame_id = 'robot_1/lidar_link'
        laser.transform.rotation.w = 1.0
        self.static_tf = StaticTransformBroadcaster(self)
        self.static_tf.sendTransform(laser)

    def publish_map(self):
        grid = OccupancyGrid()
        grid.header.frame_id = 'map'
        grid.info.width = grid.info.height = 100
        grid.info.resolution = 0.1
        grid.info.origin.position.x = grid.info.origin.position.y = -5.0
        grid.info.origin.orientation.w = 1.0
        grid.data = [100 if self.map_occupied else 0] * (100 * 100)
        self.map_pub.publish(grid)

    def _manager(self, attr):
        def handle(request, response):
            if request.command == ManageLifecycleNodes.Request.STARTUP:
                setattr(self, attr, True)
            response.success = True
            return response
        return handle

    def _is_active(self, attr):
        def handle(_request, response):
            response.success = getattr(self, attr)
            return response
        return handle

    def _on_initial(self, msg):
        self.pose = (msg.pose.pose.position.x, msg.pose.pose.position.y)
        self.initial_covariance = list(msg.pose.covariance)

    def _global(self, _request, response):
        self.global_inits += 1
        self.pose = (0.3, 0.4)
        return response

    def _nomotion(self, _request, response):
        self.nomotion_calls += 1
        return response

    def _publish(self):
        scan = LaserScan()
        scan.header.frame_id = 'robot_1/lidar_link'
        scan.header.stamp = self.get_clock().now().to_msg()
        scan.angle_min, scan.angle_increment = -math.pi, 2 * math.pi / 360
        scan.range_min, scan.range_max = 0.15, 12.0
        scan.ranges = [1.0] * 360
        self.scan_pub.publish(scan)
        if not self.amcl_active or self.pose is None:
            return
        msg = PoseWithCovarianceStamped()
        msg.header.frame_id = 'map'
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.pose.pose.position.x, msg.pose.pose.position.y = self.pose
        msg.pose.pose.orientation.w = 1.0
        value = 0.003 if self.converge else 0.25
        msg.pose.covariance[0] = msg.pose.covariance[7] = msg.pose.covariance[35] = value
        self.pub.publish(msg)


class Harness:

    def __init__(self, **params):
        config_dir = _config_dir()
        values = {'robot_id': 'robot_1', 'config_dir': config_dir,
                  'start_poses_yaml': START_POSES, 'convergence_hold_s': 0.3,
                  'nomotion_update_rate_hz': 50.0}
        values.update(params)
        self.node = Localization(namespace='robot_1', parameter_overrides=[
            Parameter(k, value=v) for k, v in values.items()])
        self.fake = FakeAmclStack()
        self.edge = Node('edge_harness')
        qos = qos_from_contract(load_runtime_contract(config_dir), 'control_state')
        self.state_pub = self.edge.create_publisher(CompetitionState, '/competition/state', qos)
        self.diagnostics = []
        self.edge.create_subscription(DiagnosticArray, '/diagnostics',
                                      lambda m: self.diagnostics.extend(m.status), 10)
        self.phase = CompetitionState.PHASE_HANDOVER
        self.edge.create_timer(0.2, lambda: self.state_pub.publish(CompetitionState(
            run_id=RUN_ID, map_id=MAP_ID, map_revision=1, phase=self.phase)))
        self.client = self.edge.create_client(Relocalize, '/robot_1/relocalize')
        self.executor = MultiThreadedExecutor(num_threads=8)
        for node in (self.node, self.fake, self.edge):
            self.executor.add_node(node)
        threading.Thread(target=self.executor.spin, daemon=True).start()
        assert self.client.wait_for_service(timeout_sec=5.0)
        end = time.monotonic() + 5.0
        while self.node.competition is None and time.monotonic() < end:
            time.sleep(0.05)

    def call(self, timeout_s=3, **fields):
        request = Relocalize.Request(run_id=RUN_ID, map_id=MAP_ID, map_revision=1,
                                     timeout=Duration(sec=timeout_s))
        for key, value in fields.items():
            setattr(request, key, value)
        future = self.client.call_async(request)
        end = time.monotonic() + timeout_s + 10.0
        while not future.done() and time.monotonic() < end:
            time.sleep(0.02)
        assert future.done()
        return future.result()

    def close(self):
        self.executor.shutdown()
        for node in (self.node, self.fake, self.edge):
            node.destroy_node()


@pytest.fixture
def harness():
    rclpy.init()
    h = Harness()
    yield h
    h.close()
    rclpy.shutdown()


def test_known_start_pose_starts_amcl_and_navigation(harness):
    response = harness.call(mode=Relocalize.Request.MODE_KNOWN_START_POSE,
                            start_pose_id='task1_start')
    assert response.success, response.message
    assert response.estimated_pose.pose.pose.position.x == pytest.approx(-1.5)
    assert harness.fake.amcl_active and harness.fake.nav_active
    assert harness.fake.nomotion_calls >= 1


def test_unknown_start_pose_is_rejected(harness):
    response = harness.call(mode=Relocalize.Request.MODE_KNOWN_START_POSE,
                            start_pose_id='nowhere')
    assert not response.success
    assert response.reason.code == TaskReason.CONFIGURATION_INVALID
    assert not harness.fake.nav_active


def _hint(x, y):
    hint = PoseWithCovarianceStamped()
    hint.header.frame_id = 'map'
    hint.pose.pose.position.x, hint.pose.pose.position.y = x, y
    hint.pose.pose.orientation.w = 1.0
    return hint


def test_pose_hint_uses_default_covariance_when_missing(harness):
    harness.phase = CompetitionState.PHASE_TASK2A
    time.sleep(0.5)
    response = harness.call(mode=Relocalize.Request.MODE_POSE_HINT, pose_hint=_hint(1.0, 0.5))
    assert response.success, response.message
    assert harness.fake.pose == (1.0, 0.5)
    assert harness.fake.initial_covariance[0] == pytest.approx(0.10 ** 2)


def test_pose_hint_during_handover_uses_tight_covariance(harness):
    response = harness.call(mode=Relocalize.Request.MODE_POSE_HINT, pose_hint=_hint(1.0, 0.5))
    assert response.success, response.message
    assert harness.fake.initial_covariance[0] == pytest.approx(0.03 ** 2)
    assert harness.fake.initial_covariance[35] == pytest.approx(0.03 ** 2)
    hint = _hint(1.0, 0.5)                    # an explicit covariance is kept
    hint.pose.covariance[0] = hint.pose.covariance[7] = hint.pose.covariance[35] = 0.0016
    response = harness.call(mode=Relocalize.Request.MODE_POSE_HINT, pose_hint=hint)
    assert response.success, response.message
    assert harness.fake.initial_covariance[0] == pytest.approx(0.0016)


def test_pose_hint_must_be_in_map(harness):
    hint = PoseWithCovarianceStamped()
    hint.header.frame_id = 'robot_1/odom'
    response = harness.call(mode=Relocalize.Request.MODE_POSE_HINT, pose_hint=hint)
    assert not response.success
    assert response.reason.code == TaskReason.CONFIGURATION_INVALID


def test_global_localization(harness):
    response = harness.call(mode=Relocalize.Request.MODE_GLOBAL)
    assert response.success, response.message
    assert harness.fake.global_inits == 1
    assert harness.fake.nomotion_calls >= 30
    assert 'low confidence' in response.message


def test_no_convergence_fails_and_reports_diagnostics(harness):
    harness.fake.converge = False
    response = harness.call(timeout_s=2, mode=Relocalize.Request.MODE_KNOWN_START_POSE,
                            start_pose_id='task1_start')
    assert not response.success
    assert response.reason.code == TaskReason.RELOCALIZATION_FAILED
    assert not harness.fake.nav_active
    end = time.monotonic() + 3.0
    while time.monotonic() < end and not any(
            s.name == 'robot_1/localization' and s.level == DiagnosticStatus.ERROR
            for s in harness.diagnostics):
        time.sleep(0.05)
    assert any(s.name == 'robot_1/localization' and s.level == DiagnosticStatus.ERROR
               for s in harness.diagnostics)


def test_scan_that_does_not_match_the_map_fails(harness):
    harness.fake.map_occupied = False
    harness.fake.publish_map()
    time.sleep(0.5)
    response = harness.call(mode=Relocalize.Request.MODE_KNOWN_START_POSE,
                            start_pose_id='task1_start')
    assert not response.success
    assert response.reason.code == TaskReason.RELOCALIZATION_FAILED
    assert 'scan does not match' in response.message
    assert not harness.fake.nav_active


def test_success_after_failure_keeps_the_node_alive(harness):
    # rclpy raises when one logging call site changes severity; a failure after a
    # success must not kill the node.
    ok = harness.call(mode=Relocalize.Request.MODE_KNOWN_START_POSE, start_pose_id='task1_start')
    assert ok.success, ok.message
    bad = harness.call(mode=Relocalize.Request.MODE_KNOWN_START_POSE, start_pose_id='nowhere')
    assert not bad.success
    again = harness.call(mode=Relocalize.Request.MODE_KNOWN_START_POSE,
                         start_pose_id='task1_start')
    assert again.success, again.message


def test_run_id_and_map_must_match(harness):
    response = harness.call(run_id='other', mode=Relocalize.Request.MODE_GLOBAL)
    assert not response.success and response.reason.code == TaskReason.CONFIGURATION_INVALID
    response = harness.call(map_revision=2, mode=Relocalize.Request.MODE_GLOBAL)
    assert not response.success and 'map' in response.message
