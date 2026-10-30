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

"""ROS adapter for the official midterm; never owns phase, TF or velocity."""

import copy
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import time
import uuid

from action_msgs.srv import CancelGoal
from ament_index_python.packages import get_package_share_directory
from edgeai_common.config import load_runtime_contract
from edgeai_common.qos import qos_from_contract
from edgeai_robot_interfaces.action import ExecuteNavigationGoal, ExecuteRescueTask
from edgeai_robot_interfaces.msg import (
    CompetitionState, EmergencyStop, RescueEvent, RobotState, RobotStateArray, TaskReason,
)
from edgeai_robot_interfaces.srv import SetCompetitionPhase
from geometry_msgs.msg import Pose
from nav_msgs.msg import OccupancyGrid
import rclpy
from rclpy.action import ActionClient
from rclpy.clock import Clock, ClockType
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from rclpy.signals import SignalHandlerOptions
from std_msgs.msg import String
from unique_identifier_msgs.msg import UUID

from .engine import Command, Engine
from .evidence import Journal
from .model import load_configuration, Robot
from .planning import GridCost


def seconds(stamp):
    return stamp.sec + stamp.nanosec * 1e-9


def message_robot(msg):
    """Untrusted robot messages become finite map/base_footprint samples."""
    p = msg.pose.pose.position
    return Robot(msg.robot_id, seconds(msg.header.stamp), p.x, p.y,
                 localized=msg.localized and msg.header.frame_id == 'map',
                 navigation_available=msg.navigation_available, mode=msg.mode,
                 active_task=msg.active_task_id,
                 fault=any(f.severity >= 2 for f in msg.faults),
                 linear=msg.velocity.twist.linear.x, angular=msg.velocity.twist.angular.z)


class Coordinator(Node):
    """Single-threaded scheduling avoids races between phase and action callbacks."""

    def __init__(self, *, parameter_overrides=None):
        super().__init__('task_allocator', namespace='/edge',
                         parameter_overrides=parameter_overrides)
        default = str(Path(get_package_share_directory('edgeai_task_coordinator'))
                      / 'config' / 'midterm.yaml')
        self.declare_parameter('config_file', default)
        self.declare_parameter('config_dir', '')
        self.declare_parameter('output_dir', str(Path.cwd() / 'runs' / 'p4'))
        self.declare_parameter('require_map', True)
        self.declare_parameter('test_mode', False)
        self.declare_parameter('request_finish', True)
        if not self.has_parameter('use_sim_time'):
            self.declare_parameter('use_sim_time', True)
        if (not self.get_parameter('use_sim_time').value
                and not self.get_parameter('test_mode').value):
            raise ValueError('official midterm holds require use_sim_time=true')
        if (not self.get_parameter('require_map').value
                and not self.get_parameter('test_mode').value):
            raise ValueError('only test_mode may bypass the shared map requirement')
        self.config = load_configuration(self.get_parameter('config_file').value)
        self.config_hash = hashlib.sha256(json.dumps(asdict(self.config), sort_keys=True)
                                          .encode()).hexdigest()
        contract = load_runtime_contract(self.get_parameter('config_dir').value or None)
        self.qos = {name: qos_from_contract(contract, name)
                    for name in ('robot_state', 'snapshot', 'control_state', 'event_stream')}
        self.registry = Node('robot_state_registry', namespace='/edge')
        self.verifier_node = Node('rescue_verifier', namespace='/edge')
        self.aggregate_pub = self.registry.create_publisher(
            RobotStateArray, '/edge/robot_states', self.qos['robot_state'])
        self.event_pub = self.verifier_node.create_publisher(
            RescueEvent, '/edge/rescue_events', self.qos['event_stream'])
        self.status_pub = self.create_publisher(
            String, '/edge/midterm_rescue/status', self.qos['snapshot'])
        self.create_subscription(CompetitionState, '/competition/state', self._on_phase,
                                 self.qos['control_state'])
        self.create_subscription(EmergencyStop, '/competition/estop', self._on_estop,
                                 self.qos['control_state'])
        self.create_subscription(OccupancyGrid, '/map', self._on_map, self.qos['snapshot'])
        self.action_clients = {}
        self.cancel_clients = {}
        self.phase_client = self.create_client(SetCompetitionPhase, '/competition/set_phase')
        self.finish_request = 'NOT_REQUESTED'
        self.finish_future = None
        for robot_id in self.config.robots:
            self.create_subscription(
                RobotState, f'/{robot_id}/state',
                lambda msg, rid=robot_id: self._on_robot(msg, rid), self.qos['robot_state'])
            for kind, action_type, suffix in (
                    ('rescue', ExecuteRescueTask, 'execute_rescue_task'),
                    ('navigation', ExecuteNavigationGoal, 'execute_navigation_goal')):
                action = f'/{robot_id}/{suffix}'
                self.action_clients[(robot_id, kind)] = ActionClient(self, action_type, action)
                self.cancel_clients[(robot_id, kind)] = self.create_client(
                    CancelGoal, action + '/_action/cancel_goal')
        self.robots, self.raw_states = {}, {}
        self.phase = None
        self.phase_received = None
        self.estop_generation = -1
        self.estop = False
        self.grid = None
        self.engine = None
        self.journal = None
        self.identity = None
        self.handles = {}
        self.goal_records = {}
        self.cancel_pending = set()
        self.last_error = ''
        self.last_sample = None
        self.recovered = False
        self.shutdown_requested = False
        self.steady_clock = Clock(clock_type=ClockType.STEADY_TIME)
        self.timer = self.create_timer(0.1, self._tick, clock=self.steady_clock)

    def _on_robot(self, msg, robot_id):
        if msg.robot_id != robot_id or (self.phase and msg.run_id != self.phase.run_id):
            return
        previous = self.robots.get(robot_id)
        robot = message_robot(msg)
        if previous is not None and robot.stamp < previous.stamp:
            return
        self.robots[robot_id], self.raw_states[robot_id] = robot, msg

    def _on_phase(self, msg):
        if self.phase and msg.run_id == self.phase.run_id and \
                msg.phase_sequence < self.phase.phase_sequence:
            return
        if self.phase and msg.run_id == self.phase.run_id and \
                msg.phase_sequence == self.phase.phase_sequence and (
                    msg.phase, msg.map_id, msg.map_revision, msg.frozen,
                    msg.estop_active, msg.reset_in_progress) != (
                        self.phase.phase, self.phase.map_id, self.phase.map_revision,
                        self.phase.frozen, self.phase.estop_active, self.phase.reset_in_progress):
            self.last_error = 'CONFLICTING_PHASE_SEQUENCE'
            return
        if self.phase and msg.run_id != self.phase.run_id:
            self.robots.clear()
            self.raw_states.clear()
        self.phase = msg
        self.phase_received = time.monotonic()

    def _on_estop(self, msg):
        if msg.generation > self.estop_generation:
            self.estop_generation, self.estop = msg.generation, msg.active

    def _on_map(self, msg):
        q = msg.info.origin.orientation
        values = (msg.info.resolution, msg.info.origin.position.x,
                  msg.info.origin.position.y, q.x, q.y, q.z, q.w)
        if (not all(math.isfinite(v) for v in values)
                or abs(sum(v * v for v in (q.x, q.y, q.z, q.w)) - 1.0) > 0.01):
            self.last_error = 'INVALID_MAP_GEOMETRY'
            return
        yaw = math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))
        if (msg.header.frame_id != 'map' or msg.info.resolution <= 0
                or msg.info.width * msg.info.height != len(msg.data)):
            self.last_error = 'INVALID_MAP'
            return
        self.grid = GridCost(msg.info.width, msg.info.height, msg.info.resolution,
                             (msg.info.origin.position.x, msg.info.origin.position.y, yaw),
                             msg.data, self.config.settings.allocation_clearance_m)

    def _enabled(self, now):
        p = self.phase
        return bool(p and p.phase == p.PHASE_TASK2A and not p.frozen and not p.estop_active
                    and not p.reset_in_progress and not self.estop and not self.last_error
                    and not self.shutdown_requested
                    and now > 0 and -0.1 <= now - seconds(p.header.stamp) <= 2.0
                    and time.monotonic() - self.phase_received <=
                    self.config.settings.phase_heartbeat_timeout_s
                    and (self.grid is not None or not self.get_parameter('require_map').value))

    def _start(self):
        p = self.phase
        self.identity = {'run_id': p.run_id, 'map_id': p.map_id,
                         'map_revision': p.map_revision, 'config_sha256': self.config_hash,
                         'rule_profile': self.config.profile,
                         'target_source': 'official_midterm_coordinates',
                         'rule_source': 'KTH_EdgeAI_Midterm_Check_Task_Description.docx'}
        self.journal = Journal(self.get_parameter('output_dir').value, self.identity)
        self.engine = Engine(self.config, p.run_id, self.journal.completed)
        previous = self.journal.previous
        if previous:
            # Restarting never silently resumes a partly executed mission. Cancel
            # only exact recorded UUIDs, not all actions on another owner's server.
            self.goal_records = previous.get('goals', {})
            if previous['status'] not in ('DONE', 'WAITING') or self.goal_records:
                self.recovered = True
                self.engine.status = 'HALTED'
                self.engine.failure = 'RESTART_REQUIRES_NEW_RUN'
                for token in self.goal_records:
                    self.cancel_pending.add(token)
        self.get_logger().info(f'P4 evidence: {self.journal.directory}')

    def _send(self, command):
        if self.engine.target.approaches:
            self._send_navigation(command)
        else:
            self._send_rescue(command)

    def _send_navigation(self, command):
        engine = self.engine
        x, y, yaw = engine.target.approaches[command.slot]
        goal = ExecuteNavigationGoal.Goal(
            run_id=engine.run_id, request_id=engine.task_id,
            map_id=self.identity['map_id'], map_revision=self.identity['map_revision'],
            purpose=ExecuteNavigationGoal.Goal.PURPOSE_TRANSIT,
            xy_tolerance_m=0.10, yaw_tolerance_rad=0.25)
        goal.timeout.sec = int(self.config.settings.executor_timeout_wall_s)
        goal.goal_pose.header.frame_id = 'map'
        goal.goal_pose.header.stamp = self.get_clock().now().to_msg()
        goal.goal_pose.pose.position.x, goal.goal_pose.pose.position.y = x, y
        goal.goal_pose.pose.orientation.z = math.sin(yaw / 2)
        goal.goal_pose.pose.orientation.w = math.cos(yaw / 2)
        self._dispatch(command, goal, 'navigation')

    def _send_rescue(self, command):
        engine = self.engine
        target = engine.target
        x, y, yaw = target.slots[command.slot]
        goal = ExecuteRescueTask.Goal(
            run_id=engine.run_id, task_id=engine.task_id, target_id=target.target_id,
            map_id=self.identity['map_id'], map_revision=self.identity['map_revision'],
            target_type=1 if target.required == 1 else 2, rescue_zone_index=command.slot,
            arrival_xy_tolerance_m=self.config.settings.arrival_tolerance_m)
        goal.rescue_pose.header.frame_id = 'map'
        goal.rescue_pose.header.stamp = self.get_clock().now().to_msg()
        goal.rescue_pose.pose.position.x, goal.rescue_pose.pose.position.y = x, y
        goal.rescue_pose.pose.orientation.z = math.sin(yaw / 2)
        goal.rescue_pose.pose.orientation.w = math.cos(yaw / 2)
        self._dispatch(command, goal, 'rescue')

    def _dispatch(self, command, goal, kind):
        client = self.action_clients[(command.robot_id, kind)]
        if not client.server_is_ready():
            self.engine.accepted(command.token, False, self._now())
            return
        goal_uuid = UUID(uuid=list(uuid.uuid4().bytes))
        self.goal_records[command.token] = {
            'robot_id': command.robot_id, 'uuid': [int(v) for v in goal_uuid.uuid], 'kind': kind}
        self._save()  # Write-ahead receipt, even if the acceptance reply is lost.
        future = client.send_goal_async(goal, goal_uuid=goal_uuid)
        future.add_done_callback(lambda f, token=command.token: self._accepted(token, f, kind))

    def _accepted(self, token, future, kind):
        try:
            handle = future.result()
        except Exception as error:
            self.last_error = f'ACTION_TRANSPORT: {error}'
            self.cancel_pending.add(token)
            return
        if handle.accepted:
            self.handles[token] = handle
            handle.get_result_async().add_done_callback(
                lambda f, tok=token: self._ended(tok, f, kind))
        else:
            self.goal_records.pop(token, None)
        callback = self.engine.transit_accepted if kind == 'navigation' else self.engine.accepted
        callback(token, handle.accepted, self._now())
        if self.engine.status in ('RELEASING', 'HALTED') and handle.accepted:
            self.cancel_pending.add(token)

    def _ended(self, token, future, kind):
        success = False
        try:
            response = future.result()
            reason = f'ACTION_ENDED:{response.result.reason.code}:{response.result.reason.detail}'
            success = kind == 'navigation' and response.result.success
        except Exception as error:
            reason = f'ACTION_RESULT_ERROR:{error}'
        self.handles.pop(token, None)
        self.goal_records.pop(token, None)
        self.cancel_pending.discard(token)
        if success and self.engine.status == 'ACTIVE':
            self.engine.transit_finished(token)
        else:
            self.engine.ended(token, self._now(), reason)

    def _cancel(self, token):
        record = self.goal_records.get(token)
        if not record:
            self.cancel_pending.discard(token)
            return
        client = self.cancel_clients[(record['robot_id'], record.get('kind', 'rescue'))]
        if not client.service_is_ready():
            return
        if time.monotonic() - record.get('last_cancel', -100.0) < 0.5:
            return
        request = CancelGoal.Request()
        request.goal_info.goal_id = UUID(uuid=record['uuid'])
        record['last_cancel'] = time.monotonic()
        # Keep retrying until the action result and idle state confirm release.
        client.call_async(request)

    def _now(self):
        return self.get_clock().now().nanoseconds / 1e9

    def _request_finish(self):
        if not self.get_parameter('request_finish').value:
            self.finish_request = 'DISABLED'
        elif self.phase.phase != CompetitionState.PHASE_TASK2A:
            self.finish_request = 'PHASE_ALREADY_ENDED'
        elif self.finish_future is None and self.phase_client.service_is_ready():
            request = SetCompetitionPhase.Request(
                run_id=self.engine.run_id,
                requested_phase=SetCompetitionPhase.Request.PHASE_FROZEN,
                requester_type=SetCompetitionPhase.Request.REQUESTER_SYSTEM,
                requester_node=self.get_fully_qualified_name(),
                reason='official midterm S1 and C1 completed and robot actions released')
            self.finish_request = 'PENDING'
            self.finish_future = self.phase_client.call_async(request)
        elif self.finish_future is None:
            self.finish_request = 'WAITING_FOR_P2_SERVICE'
        if self.finish_future is not None and self.finish_future.done():
            try:
                response = self.finish_future.result()
                self.finish_request = ('ACCEPTED' if response.accepted
                                       else 'REJECTED:' + response.message)
            except Exception as error:
                self.finish_request = 'TRANSPORT_ERROR:' + str(error)

    def _publish_event(self, event):
        types = {'ASSIGNED': RescueEvent.EVENT_ASSIGNED,
                 'NAVIGATION_STARTED': RescueEvent.EVENT_NAVIGATION_STARTED,
                 'DWELL_STARTED': RescueEvent.EVENT_DWELL_STARTED,
                 'DWELL_RESET': RescueEvent.EVENT_DWELL_RESET,
                 'COMPLETED': RescueEvent.EVENT_COMPLETED,
                 'FAILED': RescueEvent.EVENT_FAILED,
                 'HALTED': RescueEvent.EVENT_BLOCKED}
        if event['type'] not in types:
            return
        msg = RescueEvent(run_id=self.engine.run_id, event_id=event['event_id'],
                          task_id=event['task_id'], target_id=event['target_id'],
                          scoring_stage=RescueEvent.STAGE_TASK2A, event_type=types[event['type']],
                          robot_ids=event['robot_ids'])
        msg.header.frame_id = 'map'
        msg.header.stamp.sec = int(event['sim_time'])
        msg.header.stamp.nanosec = int((event['sim_time'] % 1) * 1e9)
        msg.rescue_zone_indices = list(range(len(msg.robot_ids)))
        msg.robot_poses = []
        for rid in msg.robot_ids:
            robot = self.robots.get(rid)
            raw = self.raw_states.get(rid)
            pose = copy.deepcopy(raw.pose.pose) if raw else Pose()
            if robot:
                pose.position.x, pose.position.y = robot.x, robot.y
            msg.robot_poses.append(pose)
        elapsed = event['dwell_elapsed_s']
        msg.dwell_elapsed.sec = int(elapsed)
        msg.dwell_elapsed.nanosec = int(elapsed % 1 * 1e9)
        reason = event['reason']
        codes = {'': TaskReason.NONE, 'ROBOT_STATE_INVALID': TaskReason.ROBOT_UNAVAILABLE,
                 'ACTION_REJECTED': TaskReason.ROBOT_UNAVAILABLE,
                 'ACTION_RESPONSE_TIMEOUT': TaskReason.NAVIGATION_TIMEOUT,
                 'NAVIGATION_TIMEOUT': TaskReason.NAVIGATION_TIMEOUT,
                 'TASK_TIMEOUT': TaskReason.PARTNER_UNAVAILABLE,
                 'OUTSIDE_OR_INVALID_SAMPLE': TaskReason.DWELL_RESET,
                 'PHASE_OR_SAFETY_STOP': TaskReason.SAFETY_STOP if self.estop
                 else TaskReason.PHASE_CHANGED,
                 'RELEASE_NOT_CONFIRMED': TaskReason.SAFETY_STOP,
                 'CLOCK_REWIND': TaskReason.CONFIGURATION_INVALID}
        code = codes.get(reason, TaskReason.INTERNAL_ERROR)
        if reason.startswith('ACTION_ENDED:'):
            code = int(reason.split(':', 2)[1])
        msg.reason = TaskReason(code=code, detail=reason)
        self.event_pub.publish(msg)

    def _flush(self):
        while self.engine.events:
            event = self.engine.events[0]
            event['robots'] = {r: asdict(self.robots[r]) for r in event['robot_ids']
                               if r in self.robots}
            target = next((t for t in self.config.targets
                           if t.target_id == event['target_id']), None)
            if target:
                event['verification_region'] = {'kind': 'target_center_circle',
                                                'center': list(target.center),
                                                'radius_m': target.radius,
                                                'required_dwell_s': target.dwell}
            saved = self.journal.event(event)
            self.engine.events.pop(0)
            if saved:
                self._publish_event(saved)
                self.get_logger().info(
                    f'{event["type"]} {event["target_id"]} {event["reason"]}')
        self._save()

    def _save(self):
        if self.journal:
            self.journal.atomic('snapshot.json',
                                dict(self.engine.snapshot(), goals=self.goal_records,
                                     finish_request=self.finish_request))

    def _tick(self):
        try:
            self._advance()
        except Exception as error:
            message = f'FAIL_CLOSED:{type(error).__name__}:{error}'
            if message != self.last_error:
                self.get_logger().error(message)
            self.last_error = message
            if self.engine:
                self.engine.status = 'HALTED'
                self.engine.failure = message
            # Cancellation must still run when storage or serialization fails.
            for token in list(self.goal_records):
                self.cancel_pending.add(token)
                self._cancel(token)
            self.status_pub.publish(String(data=json.dumps({'status': 'HALTED', 'error': message})))

    def _advance(self):
        now = self._now()
        enabled = self._enabled(now)
        if self.engine is None and enabled and self.phase.run_id and self.phase.map_id \
                and self.phase.map_revision > 0:
            self._start()
        if self.engine:
            if (self.phase.run_id, self.phase.map_id, self.phase.map_revision) != (
                    self.identity['run_id'], self.identity['map_id'],
                    self.identity['map_revision']):
                self.last_error = 'RUN_OR_MAP_CHANGED_RESTART_REQUIRED'
                enabled = False
            self.engine.tick(now, self.robots, enabled,
                             self.grid if self.grid is not None else math.dist)
            self._flush()
            if self.engine.status == 'ACTIVE' and enabled:
                for token, slot in self.engine.slots.items():
                    robot = self.robots.get(slot['robot'])
                    if slot['state'] == 'transit_ready' and robot and robot.idle(
                            now, self.config.settings.state_stale_s):
                        self.engine.rescue_requested(token, now)
                        self._send_rescue(Command('send', slot['robot'], token, slot['index']))
            for command in self.engine.drain_commands():
                if command.kind == 'send' and enabled:
                    self._send(command)
                elif command.kind == 'cancel':
                    self.cancel_pending.add(command.token)
            self._flush()
            for token in list(self.cancel_pending):
                self._cancel(token)
            if self.engine.status == 'DONE' and not self.goal_records:
                self._request_finish()
            snapshot = dict(self.engine.snapshot(), sim_time=now, schema_version=1,
                            rule_profile=self.config.profile, identity=self.identity,
                            error=self.last_error, action_goals_outstanding=len(self.goal_records),
                            finish_request=self.finish_request,
                            collision_status='external_verification_required')
            sample_key = (now, self.engine.task_id)
            if sample_key != self.last_sample:
                self.journal.sample(snapshot)
                self.last_sample = sample_key
        else:
            snapshot = {'schema_version': 1, 'status': 'WAITING_FOR_PHASE_MAP_AND_CLOCK',
                        'error': self.last_error}
        self.status_pub.publish(String(data=json.dumps(snapshot, allow_nan=False)))
        aggregate = RobotStateArray(robots=list(self.raw_states.values()))
        aggregate.header.frame_id = 'map'
        aggregate.header.stamp = self.get_clock().now().to_msg()
        aggregate.run_id = self.phase.run_id if self.phase else ''
        self.aggregate_pub.publish(aggregate)

    def close(self):
        """Best-effort cancellation; the existing P1 watchdog remains authoritative."""
        for token in list(self.goal_records):
            self._cancel(token)
        if self.journal:
            self.journal.close()
        self.registry.destroy_node()
        self.verifier_node.destroy_node()
        self.destroy_node()


def main(args=None):
    # Keep the context alive during Ctrl+C so cancellation can reach P1 before
    # destroying the clients; P2 may still be publishing its phase heartbeat.
    rclpy.init(args=args, signal_handler_options=SignalHandlerOptions.NO)
    node = Coordinator()
    executor = SingleThreadedExecutor()
    for item in (node, node.registry, node.verifier_node):
        executor.add_node(item)
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        node.shutdown_requested = True
        deadline = time.monotonic() + 3.0
        try:
            while rclpy.ok() and time.monotonic() < deadline:
                executor.spin_once(timeout_sec=0.05)
                if not node.goal_records:
                    break
        except KeyboardInterrupt:
            pass
        node.timer.cancel()
        node.close()
        executor.shutdown()
        if rclpy.ok():
            rclpy.shutdown()
