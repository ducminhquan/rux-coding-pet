import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from codex_trial import Reaction

class ReactionsTest(unittest.TestCase):
    def run_stream(self, events, code=0):
        seen = []
        reaction = Reaction(seen.append)
        for event in events:
            reaction.feed({'type': event})
        result = reaction.finish(code)
        return seen, result

    def test_success(self):
        self.assertEqual(self.run_stream(['turn.started', 'item.started', 'turn.completed']), (['working', 'completed'], 0))
    def test_retry_error_is_not_terminal(self):
        self.assertEqual(self.run_stream(['turn.started', 'error', 'turn.completed']), (['working', 'completed'], 0))
    def test_missing_completion_is_failure(self):
        self.assertEqual(self.run_stream(['turn.started']), (['working', 'failed'], 1))
    def test_failure_is_not_announced_twice(self):
        self.assertEqual(self.run_stream(['turn.started', 'turn.failed', 'turn.failed'], 1), (['working', 'failed'], 1))
    def test_no_turn_and_exit_error(self):
        self.assertEqual(self.run_stream([], 1), (['failed'], 1))
    def test_robot_failure_is_visible(self):
        def fail(state):
            raise RuntimeError('USB disconnected')
        reaction = Reaction(fail)
        reaction.feed({'type': 'turn.started'})
        reaction.feed({'type': 'turn.completed'})
        self.assertEqual(reaction.finish(0), 1)

if __name__ == '__main__': unittest.main()
