"""An eval whose model calls did not all answer gives no score (usage.refuse_unanswered)."""
import io
import os
import sys
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import usage  # noqa: E402


class UnansweredCalls(unittest.TestCase):
    def test_failed_calls_since_a_mark_are_counted_with_the_first_reason(self):
        mark = usage.position()
        usage.note(True, 10, 5)
        usage.note(False, error="OAuth session expired")
        usage.note(False, error="later failure")
        self.assertEqual(usage.failed_since(mark), (2, 3, "OAuth session expired"))
        self.assertEqual(usage.failed_since(usage.position()), (0, 0, None))

    def test_an_eval_with_a_failed_call_stops_without_a_score_and_one_without_goes_on(self):
        said = io.StringIO()
        with redirect_stdout(said), self.assertRaises(SystemExit) as stop:
            usage.refuse_unanswered(8, 8, "failed: claude CLI failed", "the injection eval")
        self.assertEqual(stop.exception.code, 3)
        self.assertIn("NOT SCORED: 8 of 8 model calls of the injection eval did not answer", said.getvalue())
        self.assertIsNone(usage.refuse_unanswered(0, 12, None, "the planner eval"))

    def test_a_few_failed_calls_are_a_warning_and_many_stop_the_eval(self):
        said = io.StringIO()
        with redirect_stdout(said):
            self.assertIsNone(usage.refuse_unanswered(1, 80, "Extra data: line 3 column 1", "the seeded eval"))
        self.assertIn("WARNING: 1 of 80 model calls of the seeded eval did not answer", said.getvalue())
        for failed, total in ((9, 80), (1, 1)):
            with redirect_stdout(io.StringIO()), self.assertRaises(SystemExit):
                usage.refuse_unanswered(failed, total, "x", "an eval")


if __name__ == "__main__":
    unittest.main()
