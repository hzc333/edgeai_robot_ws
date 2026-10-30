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

"""Small-fleet assignment and conservative static-grid allocation estimates."""

import heapq
import itertools
import math


class GridCost:
    """Estimate path length with A*; execution remains exclusively P1/Nav2."""

    def __init__(self, width, height, resolution, origin, data, clearance=0.26):
        self.width, self.height, self.resolution = width, height, resolution
        self.ox, self.oy, self.yaw = origin
        self.data = data
        self.clearance = clearance
        self.blocked = set()
        cells = math.ceil(clearance / resolution)
        offsets = [(dx, dy) for dx in range(-cells, cells + 1)
                   for dy in range(-cells, cells + 1)
                   if math.hypot(dx, dy) * resolution <= clearance + resolution * 0.71]
        for i, value in enumerate(data):
            if value < 0 or value >= 65:
                x, y = i % width, i // width
                self.blocked.update((x + dx, y + dy) for dx, dy in offsets)

    def cell(self, point):
        """Transform a map point into the possibly rotated occupancy grid."""
        dx, dy = point[0] - self.ox, point[1] - self.oy
        c, s = math.cos(self.yaw), math.sin(self.yaw)
        return (math.floor((c * dx + s * dy) / self.resolution),
                math.floor((-s * dx + c * dy) / self.resolution))

    def free(self, cell):
        x, y = cell
        return 0 <= x < self.width and 0 <= y < self.height and cell not in self.blocked

    def __call__(self, start, goal):
        """Return metres or infinity for blocked/unreachable endpoints."""
        source, destination = self.cell(start), self.cell(goal)
        if not self.free(source) or not self.free(destination):
            return math.inf
        queue = [(0.0, 0.0, source)]
        best = {source: 0.0}
        while queue:
            _, cost, current = heapq.heappop(queue)
            if cost != best[current]:
                continue
            if current == destination:
                return cost * self.resolution
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1),
                           (1, 1), (-1, 1), (1, -1), (-1, -1)):
                nxt = (current[0] + dx, current[1] + dy)
                if not self.free(nxt):
                    continue
                if dx and dy and (not self.free((current[0] + dx, current[1]))
                                  or not self.free((current[0], current[1] + dy))):
                    continue
                proposed = cost + math.hypot(dx, dy)
                if proposed < best.get(nxt, math.inf):
                    best[nxt] = proposed
                    heapq.heappush(queue, (proposed + math.dist(nxt, destination),
                                           proposed, nxt))
        return math.inf


def allocate(robots, slots, path_cost, approaches=()):
    """Minimise makespan, then total path length, with deterministic tie breaks."""
    choices = []
    for assignment in itertools.permutations(sorted(robots), len(slots)):
        costs = []
        for i, (r, slot) in enumerate(zip(assignment, slots)):
            first = approaches[i][:2] if approaches else slot[:2]
            cost = path_cost((robots[r].x, robots[r].y), first)
            if approaches:
                cost += path_cost(first, slot[:2])
            costs.append(cost)
        if all(math.isfinite(c) for c in costs):
            choices.append(((max(costs), sum(costs), assignment), assignment))
    return min(choices)[1] if choices else None
