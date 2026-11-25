import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import aftercheck  # noqa: E402

MAP = "/d/guide.ditamap"


def row(when, file, attribute, now, map_path=MAP):
    return {"when": when, "map": map_path, "file": file, "attribute": attribute, "now": now, "was": "(copied text) x"}


def result(start, broken):
    return {"status": "FINISHED", "startTime": start, "result": [{"ruleType": "BROKEN_LINK", "assetResults": [
        {"assetPath": file, "failures": [{"reason": "Broken reference: " + value}]} for file, value in broken]}]}


class FakeAem:
    def __init__(self, answers):
        self.answers, self.checks = list(answers), 0

    def run_check(self, map_path, preset=None):
        self.checks += 1
        return self.answers.pop(0)


ROWS = [
    row("2026-11-19T10:48:50+0530", "/d/old.dita", "conref", "GUID-1.dita#GUID-1/p_old"),
    row("2026-11-22T02:09:59+0530", "/d/a.dita", "conkeyref", "shared-content-2/note_back_up"),
    row("2026-11-22T02:09:59+0530", "/d/b.dita", "conref", "GUID-9.dita#shared_content/note_back_up"),
    row("2026-11-22T02:09:59+0530", MAP, "keydef", "shared-content-2 = shared-content.dita"),
    row("2026-11-22T02:09:59+0530", "/d/x.dita", "conref", "GUID-7.dita#t/p", map_path="/other.ditamap"),
]


class AfterAFix(unittest.TestCase):
    """AEM's own report, read after a Fix, against what the Fix wrote."""

    def test_the_last_press_of_the_map_and_the_keys_it_added(self):
        refs, keys = aftercheck.written(ROWS, MAP)
        self.assertEqual([r["file"] for r in refs], ["/d/a.dita", "/d/b.dita"])
        self.assertEqual(keys, ["shared-content-2"])
        self.assertEqual(len(aftercheck.written(ROWS, MAP, since="2026-11-19")[0]), 3)

    def test_nothing_written_is_broken(self):
        aem = FakeAem([result(1, [("/d/c.dita", "elsewhere.dita")])])
        out = aftercheck.check(aem, MAP, rows=ROWS, log=lambda m: None)
        self.assertEqual((out["code"], out["broken"], out["other_broken"]), (0, [], 1))
        self.assertIn("2 references written (1 by key), 0 broken in AEM's report", out["line"])

    def test_a_written_reference_aem_calls_broken_fails(self):
        aem = FakeAem([result(1, [("/d/b.dita", "GUID-9.dita#shared_content/note_back_up")])])
        out = aftercheck.check(aem, MAP, rows=ROWS, log=lambda m: None)
        self.assertEqual(out["code"], 1)
        self.assertEqual(out["broken"][0]["file"], "/d/b.dita")
        self.assertEqual(aem.checks, 1)          # a conref is not waited for

    def test_a_new_key_is_waited_for_until_aem_reads_it(self):
        late = [("/d/a.dita", "shared-content-2/note_back_up")]
        aem = FakeAem([result(1, late), result(2, late), result(3, [])])
        slept = []
        out = aftercheck.check(aem, MAP, rows=ROWS, wait={"every": 180, "up_to": 720}, sleep=slept.append, log=lambda m: None)
        self.assertEqual((out["code"], aem.checks, out["waited_s"]), (0, 3, 360))

    def test_a_new_key_still_broken_after_the_wait_fails(self):
        late = [("/d/a.dita", "shared-content-2/note_back_up")]
        aem = FakeAem([result(n, late) for n in range(5)])
        out = aftercheck.check(aem, MAP, rows=ROWS, wait={"every": 180, "up_to": 360}, sleep=lambda s: None, log=lambda m: None)
        self.assertEqual((out["code"], aem.checks), (1, 3))

    def test_a_map_never_checked_has_no_last_result(self):
        import io
        import urllib.error
        aem = aftercheck.Aem(url="http://aem.test")

        def never_checked(*args, **kwargs):
            raise urllib.error.HTTPError("http://aem.test", 400, "Bad Request", {}, io.BytesIO(b""))
        aem._call = never_checked
        self.assertEqual(aem.last_result("/d/new.ditamap"), {})

    def test_no_fix_for_the_map(self):
        out = aftercheck.check(FakeAem([]), "/none.ditamap", rows=ROWS)
        self.assertEqual(out["code"], 2)



class OutputName(unittest.TestCase):
    def test_maps_of_one_name_in_two_folders_get_two_files(self):
        # Seen 25 Nov 2026: large-demo-test/atlas_guide wrote over large-demo/atlas_guide's rows.
        self.assertEqual(aftercheck.out_name("/content/dam/large-demo/atlas_guide.ditamap"),
                         "aftercheck-large-demo-atlas_guide.json")
        self.assertNotEqual(aftercheck.out_name("/content/dam/dupes-lang/en/ledger_guide.ditamap"),
                            aftercheck.out_name("/content/dam/dupes-lang/fr/ledger_guide.ditamap"))


if __name__ == "__main__":
    unittest.main()
