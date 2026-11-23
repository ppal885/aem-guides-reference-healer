"""A running agent stops at its check's limit: one last call to finish, no more tool calls (agentloop)."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import agentloop  # noqa: E402
import sidecar  # noqa: E402

TOOLS = [{"name": "search", "description": "Search.", "properties": {"q": {"type": "string"}}, "required": ["q"],
          "fn": lambda args: {"summary": "found %s" % args["q"]}}]
FINISH = {"name": "finish", "description": "Answer.", "properties": {"answer": {"type": "string"}}, "required": ["answer"]}


class StopAtTheLimit(unittest.TestCase):
    def run_cli(self, answers, stop_after):
        prompts, calls = [], {"n": 0}

        def model(system, prompt, model=None):
            prompts.append(prompt)
            calls["n"] += 1
            return dict(answers[min(calls["n"], len(answers)) - 1])

        with mock.patch.object(sidecar, "call_model", model):
            out = agentloop.run("system", "task", TOOLS, FINISH, backend="cli", max_calls=8,
                                should_stop=lambda: calls["n"] >= stop_after)
        return out, prompts

    def test_an_agent_told_the_limit_is_reached_finishes_with_what_it_found(self):
        (answer, steps, problem), prompts = self.run_cli(
            [{"action": "search", "q": "a"}, {"action": "finish", "answer": "the target"}], stop_after=1)
        self.assertEqual((answer, problem, len(steps)), ({"answer": "the target"}, None, 1))
        self.assertIn(agentloop.LIMIT_NOTE, prompts[1])
        self.assertIn("Tool calls left: 0", prompts[1])

    def test_an_agent_that_goes_on_searching_after_the_limit_stops_without_an_answer(self):
        (answer, steps, problem), prompts = self.run_cli([{"action": "search", "q": "a"}], stop_after=1)
        self.assertEqual((answer, problem, len(prompts), len(steps)), (None, agentloop.STOPPED_AT_LIMIT, 2, 1))

    def test_without_the_limit_it_runs_as_before(self):
        (answer, steps, problem), prompts = self.run_cli(
            [{"action": "search", "q": "a"}, {"action": "search", "q": "b"}, {"action": "finish", "answer": "x"}], stop_after=99)
        self.assertEqual((answer, problem, len(steps)), ({"answer": "x"}, None, 2))
        self.assertNotIn(agentloop.LIMIT_NOTE, "".join(prompts))


if __name__ == "__main__":
    unittest.main()
