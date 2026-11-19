import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import duplicates  # noqa: E402
import fixrate  # noqa: E402
fixrate.PATH = os.path.join(tempfile.mkdtemp(), "copies-shown.jsonl")  # tests never write the real record

SAMPLE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "samples", "dupes-drift")


def topic(name, body):
    return {"path": "/d/%s.dita" % name, "xml": '<topic id="%s"><title>T</title><body>%s</body></topic>' % (name, body)}


class CopiesThatDrifted(unittest.TestCase):
    """What "Keep copies" lists: the groups whose copies no longer say the same."""

    def groups(self):
        return {g["text"][:20]: g for g in duplicates.find(duplicates.files_of(SAMPLE))}

    def test_the_sample_finds_what_truth_says(self):
        with open(os.path.join(SAMPLE, "truth.json")) as f:
            truth = json.load(f)
        drifted = [g["text"] for g in duplicates.find(duplicates.files_of(SAMPLE)) if g["kind"] in ("numbers", "wording")]
        listed = lambda start: any(text.startswith(start) for text in drifted)
        for case in truth["groups"]:
            # meant to differ, or another sentence: not a group of copies that drifted
            self.assertEqual(listed(case["text_starts"]), case["label"] in ("drifted", "facts differ"), case["why"])
        self.assertFalse(listed(truth["not_listed"][0]))

    def test_a_short_copy_with_a_word_or_three_changed_is_found(self):
        base = "Back up the ledger database before you close the period, every time, even for a short period."
        files = [topic("a", "<p>%s</p>" % base), topic("b", "<p>%s</p>" % base),
                 topic("c", "<p>%s</p>" % base.replace("database", "database and the attachments"))]
        self.assertEqual([g["kind"] for g in duplicates.find(files)], ["wording"])

    def test_two_words_or_more_put_for_others_are_another_sentence(self):
        a = "Assist a client with checking their eligibility for the new cash flow tool today."
        files = [topic("a", "<p>%s</p>" % a), topic("b", "<p>%s</p>" % a.replace("checking their eligibility", "scheduling a demo"))]
        self.assertEqual(duplicates.find(files), [])

    def test_the_condition_of_a_copy_stays_in_its_group(self):
        group = self.groups()["Ask the IT service d"]
        self.assertEqual({c["own"] for c in group["copies"]}, {"audience=internal"})


class KeepCopiesInTheSidecar(unittest.TestCase):
    def setUp(self):
        import sidecar
        self.sidecar = sidecar
        self.folder = tempfile.TemporaryDirectory()
        self.patch = mock.patch.object(sidecar, "KEEP_PATH", os.path.join(self.folder.name, "keep.json"))
        self.patch.start()
        sidecar.LAST_FILES["/drift.ditamap"] = duplicates.files_of(SAMPLE)

    def tearDown(self):
        self.patch.stop()
        self.folder.cleanup()
        self.sidecar.LAST_FILES.clear()
        self.sidecar.COPIES.clear()

    def test_the_mode_and_a_kept_group_are_remembered_per_map(self):
        first = self.sidecar.copies_of("/drift.ditamap")
        self.assertEqual((first["mode"], first["drifted"], first["kept"]), ("share", 4, 0))
        self.assertEqual(self.sidecar.set_keep({"map": "/drift.ditamap", "mode": "keep"})["mode"], "keep")
        drifted = next(g for g in first["groups"] if g["kind"] == "numbers")
        self.sidecar.set_keep({"map": "/drift.ditamap", "keep": drifted["key"]})
        again = self.sidecar.copies_of("/drift.ditamap")
        self.assertEqual((again["mode"], again["drifted"], again["kept"]), ("keep", 3, 1))
        self.assertTrue(next(g for g in again["groups"] if g["key"] == drifted["key"])["kept"])
        self.assertEqual(self.sidecar.keep_of("/other.ditamap"), {"mode": "share", "kept": []})
        self.sidecar.set_keep({"map": "/drift.ditamap", "unkeep": drifted["key"]})
        self.assertEqual(self.sidecar.copies_of("/drift.ditamap")["kept"], 0)
        with self.assertRaises(ValueError):
            self.sidecar.set_keep({"map": "/drift.ditamap", "mode": "merge"})


if __name__ == "__main__":
    unittest.main()
