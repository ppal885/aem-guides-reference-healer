import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import casecheck  # noqa: E402


class TheCaseMatrix(unittest.TestCase):
    """eval/cases.json stays true to the tests: every case names a test that exists, or a file a
    measurement is written in, or says that it is not built or not handled."""

    def test_every_case_is_named_once_and_its_check_exists(self):
        cases = casecheck.load()
        self.assertEqual(len({c["id"] for c in cases}), len(cases))
        for case in cases:
            self.assertIn(case["level"], ("simple", "edge"), case["id"])
            check = case.get("check") or {}
            if "py" in check:
                self.assertNotEqual(casecheck.run_py(check["py"]), "no such test", case["id"])
            if "measured" in check:
                self.assertTrue(os.path.exists(os.path.join(casecheck.HERE, check["measured"])), case["id"])
            if "editor" in check:
                self.assertTrue(check.get("name"), case["id"])

    def test_a_wrong_name_is_told_apart_from_a_failing_test(self):
        self.assertEqual(casecheck.run_py("test_refs.CopiedText.test_does_not_exist"), "no such test")
        self.assertEqual(casecheck.run_py("test_nope.Nothing.test_here"), "no such test")


if __name__ == "__main__":
    unittest.main()
