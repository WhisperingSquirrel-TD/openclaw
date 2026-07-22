import importlib.util
import sys
from pathlib import Path

SOURCE = Path(__file__).with_name('watcher.py')
spec = importlib.util.spec_from_file_location('watcher', SOURCE)
watcher = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = watcher
spec.loader.exec_module(watcher)

legacy = {
    'seen_message_ids': ['legacy-id'],
    'item_states': {'a': {'status': 'routed'}},
    'scanned_non_candidates': ['b'],
    'last_run': '2026-07-22T11:00:00Z',
}
state = watcher.normalise_state(legacy)
assert 'seen_message_ids' not in state
assert state['item_states'] == legacy['item_states']
assert state['scanned_non_candidates'] == legacy['scanned_non_candidates']

state = watcher.default_state()
for i in range(watcher.MAX_LIFECYCLE_HISTORY + 5):
    watcher.advance_item_lifecycle(state, 'item', 'email', 'classified', str(i))
history = state['item_states']['item']['history']
assert len(history) == watcher.MAX_LIFECYCLE_HISTORY
assert history[-1]['detail'] == str(watcher.MAX_LIFECYCLE_HISTORY + 4)
print('watcher state tests passed')
