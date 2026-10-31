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

"""Collision evidence is live, complete, latched, and replayable after a crash."""

import math

from edgeai_task_coordinator.collision import CollisionState
from edgeai_task_coordinator.evidence import Journal
import pytest


ROBOTS = ('robot_1', 'robot_2')
PAIR = ('world::robot_1::body::solid', 'world::wall::body::solid')


def frame(state, now, contacts=(), coverage=None, alive=ROBOTS):
    state.ingest(now, now, coverage if coverage is not None else dict.fromkeys(ROBOTS, 9),
                 alive, contacts)
    return state.snapshot(now, now)


def test_no_data_is_unknown_not_zero_collisions():
    state = CollisionState(ROBOTS)
    assert state.snapshot(1, 1)['state'] == 'UNKNOWN'
    assert frame(state, 1)['state'] == 'CLEAR'
    assert state.snapshot(1.6, 1.1)['state'] == 'UNKNOWN'
    assert state.snapshot(1, 2.1)['state'] == 'UNKNOWN'


@pytest.mark.parametrize('coverage,alive', [
    ({'robot_1': 9}, ROBOTS),
    (dict.fromkeys(ROBOTS, 9), ('robot_1',)),
    (dict.fromkeys(ROBOTS, 0), ROBOTS),
])
def test_clear_requires_coverage_and_active_physics_for_both(coverage, alive):
    assert frame(CollisionState(ROBOTS), 1, coverage=coverage, alive=alive)['state'] == 'UNKNOWN'


def test_contact_history_survives_separation_and_restore():
    state = CollisionState(ROBOTS)
    assert frame(state, 1, [PAIR])['state'] == 'CONTACT'
    assert frame(state, 1.1, [PAIR])['count'] == 1
    clear = frame(state, 1.2)
    assert clear['state'] == 'CLEAR' and clear['ever_contact']
    assert frame(state, 1.3, [PAIR])['count'] == 2
    restored = CollisionState(ROBOTS)
    restored.restore(state.history())
    assert restored.snapshot(2, 2)['state'] == 'UNKNOWN'
    assert frame(restored, 2)['ever_contact']
    assert restored.first['sim_time'] == 1 and restored.last['sim_time'] == 1.3


def test_peer_contact_deduplicates_reversed_pairs_and_ignores_self():
    state = CollisionState(ROBOTS)
    pair = (PAIR[0], 'world::robot_2::body::solid')
    own = (PAIR[0], 'world::robot_1::wheel::solid')
    assert frame(state, 1, [pair, tuple(reversed(pair)), own])['count'] == 1


def test_nonfinite_frame_disables_clear_status():
    state = CollisionState(ROBOTS)
    frame(state, 1)
    state.ingest(math.nan, 1, dict.fromkeys(ROBOTS, 9), ROBOTS, [])
    assert state.snapshot(1, 1)['state'] == 'UNKNOWN'


def test_contact_replays_even_if_crash_precedes_snapshot(tmp_path):
    journal = Journal(tmp_path, {'run_id': 'contact-run'})
    journal.event({'type': 'COLLISION', 'sim_time': 1, 'pair': list(PAIR)})
    journal.close()
    journal = Journal(tmp_path, {'run_id': 'contact-run'})
    assert journal.contacts == [{'sim_time': 1, 'pair': list(PAIR)}]
    journal.close()


def ledger(sequence, *events, instance='world-session-1'):
    return {'observer_instance': instance, 'sequence': sequence, 'events': list(events)}


def test_world_ledger_replays_contact_during_process_downtime_once():
    state = CollisionState(ROBOTS, require_replay=True)
    state.ingest(1, 1, dict.fromkeys(ROBOTS, 9), ROBOTS, [], ledger(0))
    saved = state.history()
    replacement = CollisionState(ROBOTS, require_replay=True)
    replacement.restore(saved)
    event = {'sequence': 1, 'sim_time': 2, 'pair': list(PAIR)}
    replacement.ingest(3, 3, dict.fromkeys(ROBOTS, 9), ROBOTS, [], ledger(1, event))
    snapshot = replacement.snapshot(3, 3)
    assert snapshot['state'] == 'CLEAR' and snapshot['ever_contact']
    assert snapshot['count'] == 1 and snapshot['last']['sim_time'] == 2
    replacement.ingest(3.1, 3.1, dict.fromkeys(ROBOTS, 9), ROBOTS, [], ledger(1, event))
    assert replacement.count == 1 and len(replacement.events) == 1


def test_world_ledger_does_not_credit_prior_run_contacts():
    state = CollisionState(ROBOTS, require_replay=True)
    state.monitor_started = 10
    old = [{'sequence': i, 'sim_time': i, 'pair': list(PAIR)} for i in range(1, 4)]
    state.ingest(10, 10, dict.fromkeys(ROBOTS, 9), ROBOTS, [], ledger(3, *old))
    assert state.count == 0 and state.snapshot(10, 10)['state'] == 'CLEAR'
    new = {'sequence': 4, 'sim_time': 11, 'pair': list(PAIR)}
    state.ingest(11, 11, dict.fromkeys(ROBOTS, 9), ROBOTS, [], ledger(4, *old, new))
    assert state.count == 1


def test_lost_world_history_or_changed_observer_is_unknown():
    state = CollisionState(ROBOTS, require_replay=True)
    state.ingest(1, 1, dict.fromkeys(ROBOTS, 9), ROBOTS, [], ledger(0))
    event = {'sequence': 3, 'sim_time': 2, 'pair': list(PAIR)}
    state.ingest(2, 2, dict.fromkeys(ROBOTS, 9), ROBOTS, [], ledger(3, event))
    assert state.snapshot(2, 2)['state'] == 'UNKNOWN'
    assert state.count > 0
    state = CollisionState(ROBOTS, require_replay=True)
    state.ingest(1, 1, dict.fromkeys(ROBOTS, 9), ROBOTS, [], ledger(0))
    state.ingest(2, 2, dict.fromkeys(ROBOTS, 9), ROBOTS, [], ledger(0, instance='new-world'))
    assert state.snapshot(2, 2)['state'] == 'UNKNOWN'
    assert state.error == 'PHYSICS_OBSERVER_RESTARTED'
