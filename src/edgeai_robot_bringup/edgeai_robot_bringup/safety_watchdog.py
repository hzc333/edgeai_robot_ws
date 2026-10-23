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

"""
Final velocity gate of a robot: the only publisher of /<robot_id>/cmd_vel (ADR-0003).

The node republishes the latest automatic (cmd_vel_safe_in) or, in development
mode only, manual (cmd_vel_manual) command at a fixed rate and outputs zero
whenever any gate is closed: no CompetitionState yet, a phase without motion,
an active emergency stop, a lost edge heartbeat or a stale input. Commands are
scaled down uniformly to the speed limits so the path curvature is preserved.
"""

from dataclasses import dataclass, field
import time

from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue
from edgeai_common.config import load_runtime_contract
from edgeai_common.frames import validate_robot_id
from edgeai_common.qos import qos_from_contract
from edgeai_robot_interfaces.msg import CompetitionState, EmergencyStop
from geometry_msgs.msg import Twist
import rclpy
from rclpy.node import Node

MOTION_PHASES = (CompetitionState.PHASE_TASK1, CompetitionState.PHASE_TASK2A,
                 CompetitionState.PHASE_TASK2B)
PHASE_NAMES = {
    CompetitionState.PHASE_PREPARATION: 'preparation',
    CompetitionState.PHASE_TASK1: 'task1',
    CompetitionState.PHASE_HANDOVER: 'handover',
    CompetitionState.PHASE_TASK2A: 'task2a',
    CompetitionState.PHASE_FROZEN: 'frozen',
    CompetitionState.PHASE_TASK2B: 'task2b',
    CompetitionState.PHASE_FINISHED: 'finished',
    CompetitionState.PHASE_ESTOP: 'estop',
}


@dataclass
class GateInputs:
    """Everything the gate decision depends on, with times in seconds."""

    now: float
    require_competition_state: bool = True
    phase: int | None = None
    last_state_time: float | None = None
    estop_active: bool = False
    auto_command: tuple[float, float] | None = None
    auto_time: float | None = None
    manual_allowed: bool = False
    manual_command: tuple[float, float] | None = None
    manual_time: float | None = None
    input_timeout_s: float = 0.5
    edge_timeout_s: float = 1.0
    max_linear_mps: float = 0.15
    max_angular_radps: float = 0.30


@dataclass
class GateDecision:
    linear: float
    angular: float
    reasons: list[str] = field(default_factory=list)
    source: str = 'none'


def limit_command(linear, angular, max_linear, max_angular):
    """Scale (linear, angular) uniformly so both respect their limits."""
    scale = max(abs(linear) / max_linear if max_linear > 0 else float('inf'),
                abs(angular) / max_angular if max_angular > 0 else float('inf'),
                1.0)
    if scale == float('inf'):
        return 0.0, 0.0
    return linear / scale, angular / scale


def decide(inputs: GateInputs) -> GateDecision:
    """Return the command to publish and every reason that closes the gate."""
    reasons = []
    if inputs.require_competition_state:
        if inputs.last_state_time is None:
            reasons.append('waiting_for_competition_state')
        else:
            if inputs.now - inputs.last_state_time > inputs.edge_timeout_s:
                reasons.append('edge_connection_lost')
            if inputs.phase not in MOTION_PHASES:
                reasons.append(f'phase_{PHASE_NAMES.get(inputs.phase, inputs.phase)}')
    if inputs.estop_active:
        reasons.append('estop')

    def fresh(stamp):
        return stamp is not None and inputs.now - stamp <= inputs.input_timeout_s

    command, source = None, 'none'
    if inputs.manual_allowed and inputs.manual_command is not None and \
            fresh(inputs.manual_time):
        command, source = inputs.manual_command, 'manual'
    elif inputs.auto_command is not None and fresh(inputs.auto_time):
        command, source = inputs.auto_command, 'auto'
    else:
        reasons.append('input_timeout')

    if command is None or any(r != 'input_timeout' for r in reasons):
        return GateDecision(0.0, 0.0, reasons, source)
    linear, angular = limit_command(command[0], command[1], inputs.max_linear_mps,
                                    inputs.max_angular_radps)
    return GateDecision(linear, angular, reasons, source)


class SafetyWatchdog(Node):
    """ROS wrapper around decide(); publishes cmd_vel at a fixed rate."""

    def __init__(self, **kwargs):
        super().__init__('safety_watchdog', **kwargs)
        self.robot_id = validate_robot_id(self.declare_parameter('robot_id', 'robot_1').value)
        self.run_mode = self.declare_parameter('run_mode', 'development').value
        self.max_linear = float(self.declare_parameter('max_linear_mps', 0.15).value)
        self.max_angular = float(self.declare_parameter('max_angular_radps', 0.30).value)
        self.input_timeout = float(self.declare_parameter('input_timeout_s', 0.5).value)
        self.edge_timeout = float(self.declare_parameter('edge_timeout_s', 1.0).value)
        self.require_state = self.declare_parameter('require_competition_state', True).value
        rate = float(self.declare_parameter('publish_rate_hz', 20.0).value)
        config_dir = self.declare_parameter('config_dir', '').value or None

        if self.run_mode not in ('development', 'rehearsal', 'competition'):
            raise ValueError(f'unknown run_mode {self.run_mode!r}')
        if not self.require_state and self.run_mode != 'development':
            raise ValueError('require_competition_state:=false is only allowed in development')
        if self.max_linear <= 0.0 or self.max_angular <= 0.0:
            raise ValueError('speed limits must be positive')

        contract = load_runtime_contract(config_dir)
        control_qos = qos_from_contract(contract, 'control_state')
        self.phase = None
        self.last_state_time = None
        self.estop_generation = None
        self.estop_active = False
        self.auto = (None, None)
        self.manual = (None, None)
        self.last_reasons = []

        self.create_subscription(Twist, 'cmd_vel_safe_in', self._on_auto, 10)
        self.create_subscription(Twist, 'cmd_vel_manual', self._on_manual, 10)
        self.create_subscription(CompetitionState, '/competition/state', self._on_state,
                                 control_qos)
        self.create_subscription(EmergencyStop, '/competition/estop', self._on_estop,
                                 control_qos)
        self.cmd_pub = self.create_publisher(Twist, 'cmd_vel', 10)
        self.diag_pub = self.create_publisher(DiagnosticArray, '/diagnostics', 10)
        self.create_timer(1.0 / rate, self._tick)
        self.create_timer(1.0, self._publish_diagnostics)
        self.get_logger().info(
            f'{self.robot_id} safety_watchdog run_mode={self.run_mode} '
            f'limits=({self.max_linear} m/s, {self.max_angular} rad/s) '
            f'require_competition_state={self.require_state}')

    def _on_auto(self, msg):
        self.auto = ((msg.linear.x, msg.angular.z), time.monotonic())

    def _on_manual(self, msg):
        self.manual = ((msg.linear.x, msg.angular.z), time.monotonic())

    def _on_state(self, msg):
        self.phase = msg.phase
        self.last_state_time = time.monotonic()

    def _on_estop(self, msg):
        if self.estop_generation is not None and msg.generation <= self.estop_generation:
            return
        self.estop_generation = msg.generation
        self.estop_active = msg.active

    def _tick(self):
        decision = decide(GateInputs(
            now=time.monotonic(),
            require_competition_state=self.require_state,
            phase=self.phase,
            last_state_time=self.last_state_time,
            estop_active=self.estop_active,
            auto_command=self.auto[0], auto_time=self.auto[1],
            manual_allowed=self.run_mode == 'development',
            manual_command=self.manual[0], manual_time=self.manual[1],
            input_timeout_s=self.input_timeout,
            edge_timeout_s=self.edge_timeout,
            max_linear_mps=self.max_linear,
            max_angular_radps=self.max_angular,
        ))
        self.last_reasons = decision.reasons
        msg = Twist()
        msg.linear.x = decision.linear
        msg.angular.z = decision.angular
        self.cmd_pub.publish(msg)

    def _publish_diagnostics(self):
        blocking = [r for r in self.last_reasons if r != 'input_timeout']
        status = DiagnosticStatus(
            level=DiagnosticStatus.WARN if blocking else DiagnosticStatus.OK,
            name=f'{self.robot_id}/safety_watchdog',
            hardware_id=self.robot_id,
            message=', '.join(self.last_reasons) or 'passing commands',
            values=[KeyValue(key='run_mode', value=self.run_mode),
                    KeyValue(key='estop_generation', value=str(self.estop_generation)),
                    KeyValue(key='phase', value=str(self.phase))],
        )
        array = DiagnosticArray(status=[status])
        array.header.stamp = self.get_clock().now().to_msg()
        self.diag_pub.publish(array)


def main(args=None):
    rclpy.init(args=args)
    node = SafetyWatchdog()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        # Leave the robot with an explicit zero command on shutdown.
        if rclpy.ok():
            node.cmd_pub.publish(Twist())
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
