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
        groups = duplicates.find(duplicates.files_of(SAMPLE))
        kinds = lambda start: {g["kind"] for g in groups if any(v["text"].startswith(start) for v in g["variants"])}
        for case in truth["groups"]:
            found = kinds(case["text_starts"]) & {"numbers", "wording", "maybe"}
            want = {"drifted": {"numbers", "wording"}, "facts differ": {"numbers", "wording"},
                    "maybe, same": {"maybe"}, "maybe, other": {"maybe"}, "says more": {"maybe"}}.get(case["label"], set())
            # meant to differ, or another sentence: not listed at all
            self.assertEqual(bool(found), bool(want), case["why"])
            if want:
                self.assertTrue(found <= want, (case["why"], found))
            if case["label"] == "says more":
                self.assertEqual({g.get("why") for g in groups if g["kind"] == "maybe"
                                  and any(v["text"].startswith(case["text_starts"]) for v in g["variants"])}, {"says more"})
        self.assertFalse(kinds(truth["not_listed"][0]) & {"numbers", "wording", "maybe"})

    def test_a_short_copy_with_a_word_or_three_changed_is_found(self):
        base = "Back up the ledger database before you close the period, every time, even for a short period."
        files = [topic("a", "<p>%s</p>" % base), topic("b", "<p>%s</p>" % base),
                 topic("c", "<p>%s</p>" % base.replace("database", "database and the attachments"))]
        self.assertEqual([g["kind"] for g in duplicates.find(files)], ["wording"])

    def test_a_copy_that_says_more_is_a_maybe_group_not_dropped(self):
        a = "Record the change in the audit log and tell the controller which accounts it touched."
        b = a.rstrip(".") + ", and attach the signed approval form to the closing case."
        found = duplicates.find([topic("a", "<p>%s</p>" % a), topic("b", "<p>%s</p>" % b)])
        # Never a group of copies: code cannot tell a lost instruction from one meant for that topic.
        self.assertEqual([(g["kind"], g.get("why")) for g in found], [("maybe", "says more")])

    def test_says_more_pairs_are_not_chained_and_a_rare_longer_wording_is_one_sided(self):
        s = "Use the following table to find the part number for the replaceable unit in the ledger rack."
        w = s.replace("replaceable unit", "replaceable part")              # a wording copy of s
        l1 = s.rstrip(".") + ", and record the serial number on the service form first."
        l2 = s.rstrip(".") + ", then call the ledger service desk before you order it."
        files = ([topic("s%d" % i, "<p>%s</p>" % s) for i in range(12)] + [topic("w%d" % i, "<p>%s</p>" % w) for i in range(3)]
                 + [topic("l1", "<p>%s</p>" % l1), topic("l2", "<p>%s</p>" % l2)])
        groups = duplicates.find(files)
        more = [g for g in groups if g.get("why") == "says more"]
        # One group per longer wording, each with only its own two wordings: no chain through s.
        self.assertEqual(sorted(len(g["copies"]) for g in more), [13, 13])
        self.assertTrue(all(len(g["variants"]) == 2 and g["variants"][0]["text"] == s for g in more))
        self.assertTrue(all(g["one_sided"] == {"longer_topics": 1, "shorter_topics": 12} for g in more))
        # The wording copies of s stay one group of their own.
        self.assertEqual([len(g["copies"]) for g in groups if g["kind"] == "wording"], [15])

    def test_a_balanced_says_more_pair_is_not_one_sided(self):
        a = "Record the change in the audit log and tell the controller which accounts it touched."
        b = a.rstrip(".") + ", and attach the signed approval form to the closing case."
        groups = duplicates.find([topic("a%d" % i, "<p>%s</p>" % a) for i in range(2)] + [topic("b%d" % i, "<p>%s</p>" % b) for i in range(2)])
        self.assertEqual([(g.get("why"), g.get("one_sided")) for g in groups if g["kind"] == "maybe"], [("says more", None)])

    def test_words_changed_as_well_as_added_are_not_says_more(self):
        a = "Record the change in the audit log and tell the controller which accounts it touched."
        b = "Write the change to the audit log and tell the controller which accounts it touched, and attach the form."
        self.assertEqual(duplicates.find([topic("a", "<p>%s</p>" % a), topic("b", "<p>%s</p>" % b)]), [])

    def test_a_sentence_that_is_a_small_part_of_a_long_paragraph_is_not_says_more(self):
        a = "Record the change in the audit log before the period closes."
        b = a.rstrip(".") + (", then export the trial balance, compare it with the bank statement, mark each"
                             " difference in the review sheet and send the sheet to the controller for approval.")
        self.assertEqual(duplicates.find([topic("a", "<p>%s</p>" % a), topic("b", "<p>%s</p>" % b)]), [])

    def test_one_word_written_as_two_is_the_same_word(self):
        a = "Customers on version 4.2 must remove both the Ledgerline Installer and the Scanner Webclient first."
        b = a.replace("Webclient", "Web client")
        self.assertEqual([g["kind"] for g in duplicates.find([topic("a", "<p>%s</p>" % a), topic("b", "<p>%s</p>" % b)])],
                         ["wording"])

    def test_two_words_or_more_put_for_others_are_another_sentence(self):
        a = "Assist a client with checking their eligibility for the new cash flow tool today."
        files = [topic("a", "<p>%s</p>" % a), topic("b", "<p>%s</p>" % a.replace("checking their eligibility", "scheduling a demo"))]
        # Never a group of copies: a "maybe" group, which nothing shares until someone settles it.
        self.assertEqual([g["kind"] for g in duplicates.find(files)], ["maybe"])

    def test_a_short_form_is_the_same_words_and_a_synonym_is_a_maybe(self):
        said = "Do not share the ledger file with anyone outside the closing team, even for a review."
        files = [topic("a", "<p>%s</p>" % said), topic("b", "<p>%s</p>" % said.replace("Do not", "Don't"))]
        self.assertEqual([g["kind"] for g in duplicates.find(files)], ["wording"])
        unlock = "Ask the IT service desk to unlock the ledger before you reopen a period that was closed by mistake."
        files = [topic("a", "<p>%s</p>" % unlock), topic("b", "<p>%s</p>" % unlock),
                 topic("c", "<p>%s</p>" % unlock.replace("service desk", "support team"))]
        kinds = sorted((g["kind"], len(g["copies"])) for g in duplicates.find(files))
        self.assertEqual(kinds, [("maybe", 3), ("same", 2)])

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
        self.assertEqual((first["mode"], first["drifted"], first["kept"]), ("share", 9, 0))   # 6 drifted, 3 maybe (1 "says more")
        self.assertEqual(self.sidecar.set_keep({"map": "/drift.ditamap", "mode": "keep"})["mode"], "keep")
        drifted = next(g for g in first["groups"] if g["kind"] == "numbers")
        self.sidecar.set_keep({"map": "/drift.ditamap", "keep": drifted["key"]})
        again = self.sidecar.copies_of("/drift.ditamap")
        self.assertEqual((again["mode"], again["drifted"], again["kept"]), ("keep", 8, 1))
        self.assertTrue(next(g for g in again["groups"] if g["key"] == drifted["key"])["kept"])
        self.assertEqual(self.sidecar.keep_of("/other.ditamap"), {"mode": "share", "kept": []})
        self.sidecar.set_keep({"map": "/drift.ditamap", "unkeep": drifted["key"]})
        self.assertEqual(self.sidecar.copies_of("/drift.ditamap")["kept"], 0)
        with self.assertRaises(ValueError):
            self.sidecar.set_keep({"map": "/drift.ditamap", "mode": "merge"})


if __name__ == "__main__":
    unittest.main()
