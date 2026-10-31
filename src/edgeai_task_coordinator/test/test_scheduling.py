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

"""Admission, bad layouts, stale peers, parked-robot drift and useful retries."""

from dataclasses import replace
import math
from pathlib import Path

from edgeai_task_coordinator.engine import Engine
from edgeai_task_coordinator.model import Configuration, load_configuration, Robot
from edgeai_task_coordinator.planning import allocate, GridCost
from edgeai_task_coordinator.scheduling import (
    entry_conflict, footprint, polygon_gap, validate_layout,
)
import pytest


CONFIG = load_configuration(Path(__file__).parents[1] / 'config' / 'midterm.yaml')


def start(cooperative=True):
    target = CONFIG.targets[int(cooperative)]
    config = Configuration(CONFIG.robots, (target,), CONFIG.settings)
    engine = Engine(config, 'scheduling-test')
    robots = {rid: Robot(rid, 1, 0.55 + 0.65 * i, 0.5)
              for i, rid in enumerate(config.robots)}
    engine.tick(1, robots, True, math.dist)
    first, = engine.drain_commands()
    engine.accepted(first.token, True, 1)
    return engine, robots, first


def park(engine, robots, first, now):
    robots = {rid: replace(r, stamp=now) for rid, r in robots.items()}
    robots[first.robot_id] = replace(
        robots[first.robot_id], mode=4, active_task=engine.task_id,
        x=engine.target.slots[0][0], y=engine.target.slots[0][1], yaw=-math.pi / 2)
    engine.tick(now, robots, True, math.dist)
    return robots


@pytest.mark.parametrize('bad', ['moving', 'wrong_position', 'wrong_owner'])
def test_holding_label_alone_does_not_release_partner(bad):
    engine, robots, first = start()
    robots = {rid: replace(r, stamp=1.1) for rid, r in robots.items()}
    pose = engine.target.slots[0]
    robot = replace(robots[first.robot_id], mode=4, active_task=engine.task_id,
                    x=pose[0], y=pose[1], yaw=-math.pi / 2)
    if bad == 'moving':
        robot = replace(robot, linear=0.03)
    elif bad == 'wrong_position':
        robot = replace(robot, y=2.0)
    else:
        robot = replace(robot, active_task='another-task')
    robots[first.robot_id] = robot
    engine.tick(1.1, robots, True, math.dist)
    assert not any(c.kind == 'send' for c in engine.drain_commands())


def test_cached_holding_samples_cannot_satisfy_stability_gate():
    engine, robots, first = start()
    robots = park(engine, robots, first, 1.1)
    for now in (1.2, 1.3, 1.4, 1.5):
        engine.tick(now, robots, True, math.dist)
        assert not engine.drain_commands()
    robots = park(engine, robots, first, 1.7)
    second, = engine.drain_commands()
    assert second.robot_id != first.robot_id


@pytest.mark.parametrize('failure', ['drift', 'motion', 'lost_holding'])
def test_first_robot_drift_cancels_partner_instead_of_continuing(failure):
    engine, robots, first = start()
    robots = park(engine, robots, first, 1.1)
    robots = park(engine, robots, first, 1.7)
    second, = engine.drain_commands()
    engine.accepted(second.token, True, 1.7)
    robots = {rid: replace(r, stamp=1.8) for rid, r in robots.items()}
    r = robots[first.robot_id]
    changes = {'y': r.y + 0.2} if failure == 'drift' else (
        {'angular': 0.04} if failure == 'motion' else {'mode': 3})
    robots[first.robot_id] = replace(r, **changes)
    engine.tick(1.8, robots, True, math.dist)
    assert engine.status == 'RELEASING' and engine.recovery_required
    assert engine.failure == 'PARKING_LOST'
    assert {c.token for c in engine.drain_commands() if c.kind == 'cancel'} == {
        first.token, second.token}


@pytest.mark.parametrize('failure', ['stale', 'unlocalized', 'moving'])
def test_nonparticipating_robot_is_still_part_of_scheduling_safety(failure):
    engine, robots, first = start(cooperative=False)
    other = next(r for r in robots if r != first.robot_id)
    robots = {rid: replace(r, stamp=1.1) for rid, r in robots.items()}
    changes = {'stamp': 0.0} if failure == 'stale' else (
        {'localized': False} if failure == 'unlocalized' else {'linear': 0.1})
    robots[other] = replace(robots[other], **changes)
    engine.tick(1.1, robots, True, math.dist)
    assert engine.status == 'RELEASING' and engine.recovery_required
    assert not engine.failures  # data/safety outage does not spend navigation retries
    assert any(c.kind == 'cancel' for c in engine.drain_commands())


def test_second_entry_is_rechecked_after_transit():
    engine, robots, first = start()
    robots = park(engine, robots, first, 1.1)
    robots = park(engine, robots, first, 1.7)
    engine.drain_commands()
    assert engine.can_enter(1, robots)
    # Same reference point, rotated body now intrudes into the nominal entry.
    robots[first.robot_id] = replace(robots[first.robot_id], x=4.4, yaw=0)
    assert not engine.can_enter(1, robots)
    assert engine.dispatch_gate.startswith('ENTRY_OCCUPIED:')


def test_unsafe_initial_fleet_clearance_prevents_dispatch():
    target = CONFIG.targets[0]
    engine = Engine(Configuration(CONFIG.robots, (target,), CONFIG.settings), 'test')
    robots = {r: Robot(r, 1, 0.6 + 0.2 * i, 0.5) for i, r in enumerate(CONFIG.robots)}
    engine.tick(1, robots, True, math.dist)
    assert engine.recovery_required
    assert not any(c.kind == 'send' for c in engine.drain_commands())


def test_single_task_retry_changes_robot_and_waits_for_release_and_backoff():
    engine, robots, first = start(cooperative=False)
    engine.ended(first.token, 1.1, 'ACTION_ENDED:blocked')
    robots = {rid: replace(r, stamp=1.2) for rid, r in robots.items()}
    engine.tick(1.2, robots, True, math.dist)
    engine.tick(1.3, robots, True, math.dist)
    assert engine.status == 'WAITING' and not engine.drain_commands()
    robots = {rid: replace(r, stamp=2.2) for rid, r in robots.items()}
    engine.tick(2.2, robots, True, math.dist)
    second, = engine.drain_commands()
    assert second.robot_id != first.robot_id
    assert second.token != first.token


def test_retry_keeps_reachable_fallback_if_only_failed_robot_can_reach():
    robots = {'robot_1': Robot('robot_1', 1, 0, 0), 'robot_2': Robot('robot_2', 1, 10, 0)}

    def cost(a, b):
        return math.dist(a, b) if a[0] < 5 else math.inf

    assert allocate(robots, [(1, 0, 0)], cost, discouraged=['robot_1']) == ('robot_1',)


def test_cooperative_reassignment_preserves_occupied_slots_after_failure():
    target = CONFIG.targets[1]
    robots = {rid: Robot(rid, 1, *target.slots[i][:2])
              for i, rid in enumerate(CONFIG.robots)}
    assert allocate(robots, target.slots, math.dist, target.approaches,
                    CONFIG.settings.arrival_tolerance_m) == CONFIG.robots


@pytest.mark.parametrize('bad', ['overlap', 'entry_crossing'])
def test_bad_parking_layout_is_rejected(bad):
    target = CONFIG.targets[1]
    if bad == 'overlap':
        target = replace(target, slots=(target.slots[0], (4.4, 1.45, -math.pi / 2)))
    else:
        target = replace(target, approaches=(target.approaches[0], (4.6, 1.4, math.pi)))
    with pytest.raises(ValueError):
        validate_layout(target, CONFIG.settings)


def test_geometry_respects_asymmetric_rotating_footprint_and_containment():
    s = CONFIG.settings
    a = footprint(0, 0, 0, s)
    b = footprint(0.5, 0, 0, s)
    assert polygon_gap(a, b) == pytest.approx(0.07)
    assert polygon_gap(a, footprint(0.5, 0, math.pi, s)) == pytest.approx(0.27)
    assert polygon_gap(a, a) == 0
    assert polygon_gap(a, [(-1, -1), (1, -1), (1, 1), (-1, 1)]) == 0


@pytest.mark.parametrize('rotated', [False, True])
def test_map_preflight_rejects_obstacle_inside_stop_footprint(rotated):
    settings = CONFIG.settings
    target = replace(CONFIG.targets[0], slots=((1.0, 1.0, 0),), approaches=())
    data = [0] * 400
    # Rotated-grid origin still maps the target footprint into the grid.
    origin = (2.0, 0, math.pi / 2) if rotated else (0, 0, 0)
    grid = GridCost(20, 20, 0.1, origin, data)
    grid.validate_parking([target], settings)
    x, y = grid.cell((0.85, 1.0))
    data[y * 20 + x] = 100
    with pytest.raises(ValueError, match='stop footprint'):
        grid.validate_parking([target], settings)


def test_entry_guard_uses_actual_parked_peer_orientation():
    t, s = CONFIG.targets[1], CONFIG.settings
    mover = Robot('robot_2', 1, 3.95, 2.3)
    holder = Robot('robot_1', 1, 4.4, 1.45, yaw=-math.pi / 2)
    assert not entry_conflict(t, 1, mover, [holder], s)
    holder = replace(holder, yaw=0)
    assert entry_conflict(t, 1, mover, [holder], s) == 'robot_1'


def test_raw_free_start_near_wall_can_still_be_allocated():
    data = [0] * 400
    for x in range(20):
        data[x] = 100
    grid = GridCost(20, 20, 0.1, (0, 0, 0), data, clearance=0.26)
    goal = (1.5, 1.5)
    grid.prepare([goal])
    assert not grid.free(grid.cell((0.5, 0.25)))
    assert math.isfinite(grid((0.5, 0.25), goal))
    assert math.isinf(grid((0.5, 0.05), goal))  # actual occupied cell


def test_inflation_escape_cannot_jump_through_a_thin_wall():
    data = [0] * 400
    for y in range(20):
        data[y * 20 + 2] = 100
    grid = GridCost(20, 20, 0.1, (0, 0, 0), data, clearance=0.26)
    grid.prepare([(1.5, 1.5)])
    assert math.isinf(grid((0.15, 1.0), (1.5, 1.5)))
