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

"""Timestamped collision coverage and durable per-run contact history."""

import math


class CollisionState:
    """Keep UNKNOWN distinct from clear, and preserve evidence after separation."""

    def __init__(self, robots, require_replay=False):
        self.robots = tuple(robots)
        self.stamp = None
        self.received = None
        self.coverage = {}
        self.physics_alive = set()
        self.active = set()
        self.count = 0
        self.first = None
        self.last = None
        self.events = []
        self.error = ''
        self.require_replay = require_replay
        self.observer_instance = None
        self.last_sequence = None
        self.monitor_started = 0.0

    def restore(self, history):
        self.count = int(history.get('count', 0))
        self.first = history.get('first')
        self.last = history.get('last')
        self.observer_instance = history.get('observer_instance')
        self.last_sequence = history.get('last_sequence')
        self.error = history.get('error', '')

    def history(self):
        return {'count': self.count, 'first': self.first, 'last': self.last,
                'observer_instance': self.observer_instance,
                'last_sequence': self.last_sequence, 'error': self.error}

    def ingest(self, stamp, wall, coverage, physics_alive, contacts, ledger=None):
        if not math.isfinite(stamp) or not math.isfinite(wall):
            self.error = 'NONFINITE_COLLISION_FRAME'
            return
        if self.stamp is not None and stamp < self.stamp:
            self.active.clear()
        self.stamp, self.received = stamp, wall
        self.coverage = dict(coverage)
        self.physics_alive = set(physics_alive)
        pairs = set()
        for first, second in contacts:
            first_robot = next((r for r in self.robots if r in first.split('::')), None)
            second_robot = next((r for r in self.robots if r in second.split('::')), None)
            if first_robot is None and second_robot is None:
                continue
            if first_robot and first_robot == second_robot:
                continue
            pair = tuple(sorted((first, second)))
            if ledger is None and pair not in self.active and pair not in pairs:
                event = {'sim_time': stamp, 'pair': list(pair)}
                self.count += 1
                self.first = self.first or event
                self.last = event
                self.events.append(event)
            pairs.add(pair)
        self.active = pairs
        if ledger is not None:
            instance = ledger['observer_instance']
            if self.observer_instance is not None and self.observer_instance != instance:
                self.error = 'PHYSICS_OBSERVER_RESTARTED'
                self.last_sequence = None
            self.observer_instance = instance
            initial = self.last_sequence is None
            for event in ledger['events']:
                sequence = event['sequence']
                if self.last_sequence is not None and sequence <= self.last_sequence:
                    continue
                if self.last_sequence is not None and sequence > self.last_sequence + 1:
                    self.error = 'CONTACT_HISTORY_TRUNCATED'
                if self.last_sequence is None and sequence > 1 and \
                        event['sim_time'] >= self.monitor_started:
                    self.error = 'CONTACT_HISTORY_TRUNCATED'
                eligible = not initial or event['sim_time'] >= self.monitor_started
                self.last_sequence = sequence
                if eligible and any(r in name.split('::') for r in self.robots
                                    for name in event['pair']):
                    contact = dict(event, physics_instance=instance,
                                   physics_event_id=f'{instance}:{sequence}')
                    self.count += 1
                    self.first = self.first or contact
                    self.last = contact
                    self.events.append(contact)
            if self.last_sequence is not None and ledger['sequence'] > self.last_sequence:
                self.error = 'CONTACT_HISTORY_MISSING'
            self.last_sequence = ledger['sequence']

    def snapshot(self, now, wall):
        ready = (not self.error and (not self.require_replay or self.observer_instance is not None)
                 and self.stamp is not None
                 and -0.05 <= now - self.stamp <= 0.5
                 and 0 <= wall - self.received <= 1.0
                 and all(self.coverage.get(r, 0) > 0 and r in self.physics_alive
                         for r in self.robots))
        return {'state': ('CONTACT' if self.active else 'CLEAR') if ready else 'UNKNOWN',
                'source': 'gazebo_physics_all_robot_collisions',
                'sim_time': self.stamp, 'coverage': self.coverage,
                'physics_alive': sorted(self.physics_alive),
                'active_pairs': [list(p) for p in sorted(self.active)],
                'ever_contact': self.count > 0, **self.history(), 'error': self.error}
