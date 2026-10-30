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

"""Deterministic midterm scheduler with atomic reservations and serial entry."""

from dataclasses import dataclass, replace
import hashlib

from .planning import allocate
from .verification import DwellVerifier


@dataclass(frozen=True)
class Command:
    """A side effect for the ROS adapter; tokens isolate attempts and callbacks."""

    kind: str
    robot_id: str
    token: str
    slot: int


class Engine:
    """Run ordinary and cooperative tasks through the same execution path."""

    def __init__(self, config, run_id, completed=()):
        self.config, self.run_id = config, run_id
        self.status = 'WAITING'
        self.completed = set(completed)
        self.index = 0
        self.attempts = {}
        self.assignment = ()
        self.slots = {}
        self.commands = []
        self.events = []
        self.verifier = DwellVerifier()
        self.started_at = None
        self.releasing_at = None
        self.failure = ''
        self.retry = False
        self.last_now = None
        self.task_id = ''
        self.distances = {}

    @property
    def target(self):
        return self.config.targets[self.index] if self.index < len(self.config.targets) else None

    def emit(self, kind, now, reason=''):
        self.events.append({'type': kind, 'sim_time': now, 'reason': reason,
                            'target_id': self.target.target_id if self.target else '',
                            'task_id': self.task_id, 'robot_ids': list(self.assignment),
                            'dwell_elapsed_s': self.verifier.elapsed})

    def drain_commands(self):
        commands, self.commands = self.commands, []
        return commands

    def accepted(self, token, accepted, now):
        """Late acceptances remain owned until cancelled, never start a new attempt."""
        if token not in self.slots:
            return
        slot = self.slots[token]
        if slot['state'] != 'sending':
            return
        slot['state'] = 'active' if accepted else 'ended'
        if self.status == 'RELEASING' or self.status == 'HALTED':
            if accepted:
                self.commands.append(Command('cancel', slot['robot'], token, slot['index']))
        elif not accepted:
            self.fail('ACTION_REJECTED', now, retry=True)

    def transit_accepted(self, token, accepted, now):
        """Reserve the robot on approach acceptance without verifying a rescue."""
        self.accepted(token, accepted, now)
        if accepted and token in self.slots and self.slots[token]['state'] == 'active':
            self.slots[token]['state'] = 'transit'

    def transit_finished(self, token):
        """Wait for the state stream to confirm idle before sending rescue."""
        if token in self.slots and self.status == 'ACTIVE':
            self.slots[token]['state'] = 'transit_ready'

    def rescue_requested(self, token, now):
        """Keep the reservation across approach and final rescue actions."""
        self.slots[token]['state'], self.slots[token]['sent_at'] = 'sending', now

    def ended(self, token, now, reason='ACTION_ENDED'):
        """Unexpected terminal results fail the attempt; intentional release does not."""
        if token not in self.slots:
            return
        self.slots[token]['state'] = 'ended'
        if self.status == 'ACTIVE':
            self.fail(reason, now, retry=True)

    def release(self, now):
        self.status = 'RELEASING'
        self.releasing_at = now
        self.verifier.reset()
        for token, slot in self.slots.items():
            if slot['state'] == 'queued':
                slot['state'] = 'ended'
            elif slot['state'] in ('active', 'transit'):
                self.commands.append(Command('cancel', slot['robot'], token, slot['index']))
            elif slot['state'] == 'transit_ready':
                slot['state'] = 'ended'

    def fail(self, reason, now, retry=False):
        if self.status != 'ACTIVE':
            return
        if self.verifier.start is not None:
            self.emit('DWELL_RESET', now, reason)
        self.failure, self.retry = reason, retry
        self.emit('FAILED', now, reason)
        self.release(now)

    def interrupt(self, reason, now):
        """Freeze/reset/estop never automatically resumes an interrupted mission."""
        if self.status == 'ACTIVE':
            self.fail(reason, now)
        elif self.status == 'RELEASING':
            self.retry = False
            self.failure = self.failure or reason

    def _send_next(self, now, robots):
        ordered = sorted(self.slots.items(), key=lambda pair: pair[1]['index'])
        for token, slot in ordered:
            if slot['state'] == 'queued':
                previous = ordered[:slot['index']]
                if any(p['state'] != 'active' or robots.get(p['robot']) is None
                       or robots[p['robot']].mode != 4
                       or robots[p['robot']].active_task != self.task_id
                       for _, p in previous):
                    return
                slot['state'], slot['sent_at'] = 'sending', now
                self.commands.append(Command('send', slot['robot'], token, slot['index']))
                self.emit('NAVIGATION_STARTED', now)
                return

    def tick(self, now, robots, enabled, path_cost):
        """Advance without blocking; all durations here use ROS simulation time."""
        if self.last_now is not None and now < self.last_now:
            self.interrupt('CLOCK_REWIND', now)
        self.last_now = now
        if not enabled:
            self.interrupt('PHASE_OR_SAFETY_STOP', now)
        if self.status == 'RELEASING':
            ended = all(s['state'] == 'ended' for s in self.slots.values())
            idle = all(r in robots and robots[r].idle(now, self.config.settings.state_stale_s)
                       for r in self.assignment)
            if ended and idle:
                self.emit('RELEASED', now)
                if self.target.target_id in self.completed:
                    self.index += 1
                    self.status = 'WAITING'
                elif self.retry and self.attempts[self.target.target_id] < \
                        self.config.settings.max_attempts and enabled:
                    self.status = 'WAITING'
                else:
                    self.status = 'HALTED'
                self.assignment, self.slots = (), {}
            elif now - self.releasing_at > self.config.settings.release_timeout_s:
                self.failure = 'RELEASE_NOT_CONFIRMED'
                self.status = 'HALTED'
                self.emit('HALTED', now, self.failure)
            return
        if self.status == 'WAITING':
            while self.target and self.target.target_id in self.completed:
                self.index += 1
            if self.target is None:
                self.status = 'DONE'
                return
            if not enabled:
                return
            available = {r: robots[r] for r in self.config.robots
                         if r in robots and robots[r].idle(now, self.config.settings.state_stale_s)}
            assignment = allocate(available, self.target.slots, path_cost, self.target.approaches)
            if assignment is None:
                return
            self.assignment = assignment
            attempt = self.attempts.get(self.target.target_id, 0) + 1
            self.attempts[self.target.target_id] = attempt
            prefix = hashlib.sha256(self.run_id.encode()).hexdigest()[:12]
            self.task_id = f'p4-{prefix}-{self.target.target_id}-{attempt}'
            self.slots = {f'{self.task_id}:{i}': {'robot': r, 'index': i, 'state': 'queued'}
                          for i, r in enumerate(assignment)}
            self.started_at, self.failure, self.retry = now, '', False
            self.verifier = DwellVerifier()
            self.status = 'ACTIVE'
            self.emit('ASSIGNED', now)
        if self.status != 'ACTIVE' or not enabled:
            return
        settings = self.config.settings
        for token, slot in self.slots.items():
            robot = robots.get(slot['robot'])
            if robot is None or not robot.healthy(now, settings.state_stale_s):
                self.fail('ROBOT_STATE_INVALID', now, retry=True)
                return
            if robot.active_task and robot.active_task != self.task_id:
                self.fail('ROBOT_OWNERSHIP_CHANGED', now)
                return
            if slot['state'] == 'sending' and now - slot['sent_at'] > \
                    settings.action_response_timeout_s:
                self.fail('ACTION_RESPONSE_TIMEOUT', now)
                return
            if (slot['state'] in ('active', 'transit') and robot.mode != 4
                    and now - slot['sent_at'] > settings.navigation_timeout_s):
                self.fail('NAVIGATION_TIMEOUT', now, retry=True)
                return
        if now - self.started_at > settings.partner_wait_timeout_s:
            self.fail('TASK_TIMEOUT', now, retry=True)
            return
        self._send_next(now, robots)
        selected = [robots[r] for r in self.assignment]
        owned = (all(s['state'] == 'active' for s in self.slots.values())
                 and all(r.active_task == self.task_id for r in selected))
        # Start only after P1 has stopped at the navigation slots. This is an
        # engineering admission policy, not an extra official scoring rule.
        admitted = owned and (self.verifier.start is not None or all(r.mode == 4 for r in selected))
        before = self.verifier.start
        guarded_target = replace(self.target, dwell=self.target.dwell + settings.completion_guard_s)
        complete, reset, self.distances = self.verifier.update(
            now, selected, guarded_target, settings, valid=admitted)
        if reset:
            self.emit('DWELL_RESET', now, 'OUTSIDE_OR_INVALID_SAMPLE')
        if self.verifier.start is not None and (before is None or reset):
            self.emit('DWELL_STARTED', now)
        if complete:
            self.completed.add(self.target.target_id)
            self.emit('COMPLETED', now)
            self.release(now)

    def snapshot(self):
        """Return a JSON-safe view with explicit target-centred geometry."""
        target = self.target
        task_state = self.status
        if self.status == 'ACTIVE':
            task_state = ('DWELLING' if self.verifier.start is not None
                          else 'WAITING_FOR_PARTNER' if any(
                              s['state'] == 'queued' for s in self.slots.values())
                          else 'NAVIGATING')
        return {'status': self.status, 'task_state': task_state, 'task_id': self.task_id,
                'target_id': target.target_id if target else '',
                'center': list(target.center) if target else None,
                'radius_m': target.radius if target else None,
                'required_dwell_s': target.dwell if target else None,
                'dwell_elapsed_s': self.verifier.elapsed,
                'completed_targets': sorted(self.completed), 'failure': self.failure,
                'assignment': list(self.assignment), 'attempts': dict(self.attempts),
                'distances_m': dict(self.distances)}
