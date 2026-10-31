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

"""Gazebo physics observer transport; no robot or velocity ownership."""

from collections import deque
import importlib.util
import json
from pathlib import Path
import threading
import time


TOPIC = '/edgeai/physics_contacts'


def plugin_path():
    spec = importlib.util.find_spec('edgeai_task_coordinator._gazebo_contacts')
    if spec is None or not spec.origin:
        raise RuntimeError('Gazebo observer is not built; build edgeai_task_coordinator')
    return str(Path(spec.origin).resolve())


def main():
    """Print the world plugin element for the current machine's built library."""
    import xml.etree.ElementTree as ET
    print(ET.tostring(ET.Element('plugin', name='edgeai::Contacts', filename=plugin_path()),
                      encoding='unicode'))


class ContactFeed:
    """Queue every frame until the ROS thread journals it; never drop contacts."""

    def __init__(self):
        from gz.msgs10.contacts_pb2 import Contacts
        from gz.transport13 import Node
        self.lock = threading.Lock()
        self.pending = deque()
        self.overflow = False
        self.node = Node()
        if not self.node.subscribe(Contacts, TOPIC, self._receive):
            raise RuntimeError('cannot subscribe to Gazebo physics observer')

    def _receive(self, msg):
        coverage, alive = {}, []
        ledger = {'events': [], 'sequence': 0}
        for item in msg.header.data:
            if item.key == 'coverage':
                for value in item.value:
                    name, count = value.rsplit(':', 1)
                    coverage[name] = int(count)
            elif item.key == 'physics_alive':
                alive.extend(item.value)
            elif item.key == 'observer_instance':
                ledger['observer_instance'] = item.value[0]
            elif item.key == 'sequence':
                ledger['sequence'] = int(item.value[0])
            elif item.key == 'contact_event':
                ledger['events'].extend(json.loads(v) for v in item.value)
        frame = (msg.header.stamp.sec + msg.header.stamp.nsec * 1e-9,
                 time.monotonic(), coverage, alive,
                 [(c.collision1.name, c.collision2.name) for c in msg.contact],
                 ledger if 'observer_instance' in ledger else None)
        with self.lock:
            if len(self.pending) >= 1000:
                self.overflow = True
            else:
                self.pending.append(frame)

    def drain(self):
        with self.lock:
            result = list(self.pending)
            self.pending.clear()
        return result

    def close(self):
        self.node.unsubscribe(TOPIC)
