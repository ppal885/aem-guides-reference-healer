"""Tests for the reference index and for every repair step that needs no model."""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import refcheck  # noqa: E402
import refheal  # noqa: E402
import refplan  # noqa: E402

TOPIC = '<topic id="t"><title>Using it</title><body>%s</body></topic>'


def repo(*files):
    """files: (id, path, xml[, earlier versions])."""
    return refcheck.Repo(files=[{"id": f[0], "path": f[1], "xml": f[2], "previous": list(f[3:])} for f in files])


def broken(r):
    return {(ref["attribute"], ref["value"]): ref for ref in r.broken()}


class Index(unittest.TestCase):
    def setUp(self):
        self.repo = repo(
            ("GUID-a", "/d/a.dita", TOPIC % '<p>See <xref href="GUID-b.dita#b/sec"/>, <xref href="GUID-b.dita#b/gone"/>, '
                                            '<xref href="GUID-zzz.dita"/>, <xref href="https://example.com/x"/>. '
                                            '<ph keyref="k"/> <ph keyref="nokey"/></p><note conkeyref="lib/n1"/>'
                                            '<note conkeyref="lib/n9"/><p conref="#./intro"/><p id="intro">Hi</p>'),
            ("GUID-b", "/d/sub/b.dita", '<topic id="b"><title>B</title><body><section id="sec"/><note id="n1">N</note></body></topic>'),
            ("GUID-m", "/d/m.ditamap", '<map><keydef keys="k"><topicmeta><keywords><keyword>K</keyword></keywords></topicmeta></keydef>'
                                       '<keydef keys="lib" href="GUID-b.dita"/><topicref href="GUID-a.dita"/></map>'))

    def test_finds_only_the_references_that_do_not_resolve(self):
        self.assertEqual({key: ref["reason"] for key, ref in broken(self.repo).items()}, {
            ("href", "GUID-b.dita#b/gone"): "element-missing",
            ("href", "GUID-zzz.dita"): "file-missing",
            ("keyref", "nokey"): "key-undefined",
            ("conkeyref", "lib/n9"): "element-missing",
        })

    def test_a_repair_is_written_the_way_the_repository_stores_references(self):
        ref = broken(self.repo)[("href", "GUID-b.dita#b/gone")]
        self.assertEqual(self.repo.compose(ref, target="d/sub/b.dita", topic_id="b", element_id="sec"), "GUID-b.dita#b/sec")

    def test_on_disk_a_repair_is_a_relative_path(self):
        root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "samples", "ref-demo", "v2")
        on_disk = refcheck.Repo(root)
        ref = next(r for r in on_disk.broken() if r["value"].endswith("change-password"))
        self.assertEqual(on_disk.compose(ref, target="wifi_settings.dita", topic_id="wifi_settings", element_id="wifi-password"),
                         "wifi_settings.dita#wifi_settings/wifi-password")


class Samples(unittest.TestCase):
    def test_the_clean_sample_has_no_broken_references_and_the_changed_one_has_eleven(self):
        root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "samples", "ref-demo")
        self.assertEqual(len(refcheck.Repo(os.path.join(root, "v1")).broken()), 0)
        self.assertEqual(len(refcheck.Repo(os.path.join(root, "v2")).broken()), 11)


class RepairsWithoutAModel(unittest.TestCase):
    LIB_OLD = '<topic id="lib"><title>Lib</title><body><note id="hot">Surface is hot.</note><p id="help">Call us.</p></body></topic>'
    LIB_NEW = '<topic id="lib"><title>Lib</title><body><note id="burn-risk">Surface is hot.</note><p id="support">Ring the desk.</p></body></topic>'
    MAP_OLD = '<map><keydef keys="lib" href="GUID-lib.dita"/><keydef keys="app"><topicmeta><keywords><keyword>Admin</keyword></keywords></topicmeta></keydef></map>'
    MAP_NEW = '<map><keydef keys="shared" href="GUID-lib.dita"/><keydef keys="admin-app"><topicmeta><keywords><keyword>Admin</keyword></keywords></topicmeta></keydef></map>'

    def setUp(self):
        self.repo = repo(
            ("GUID-lib", "/d/lib.dita", self.LIB_NEW, self.LIB_OLD),
            ("GUID-m", "/d/m.ditamap", self.MAP_NEW, self.MAP_OLD),
            ("GUID-t1", "/d/t1.dita", TOPIC % '<note conref="GUID-lib.dita#lib/hot"/><p conref="GUID-lib.dita#lib/help"/>'
                                              '<ph keyref="app"/><note conkeyref="lib/hot"/>'),
            ("GUID-t2", "/d/t2.dita", TOPIC % '<note conref="GUID-lib.dita#lib/hot"/><ph keyref="app"/>'))

    def fix(self, attribute, value):
        ref = broken(self.repo)[(attribute, value)]
        found = refheal.rule_fix(self.repo, ref)
        return refheal.new_value(self.repo, ref, found) if found else None

    def test_renamed_id_is_settled_from_the_previous_version_when_the_text_is_unchanged(self):
        self.assertEqual(self.fix("conref", "GUID-lib.dita#lib/hot"), "GUID-lib.dita#lib/burn-risk")

    def test_reworded_element_is_left_to_the_agent(self):
        self.assertIsNone(self.fix("conref", "GUID-lib.dita#lib/help"))

    def test_renamed_key_is_settled_from_the_previous_version_of_the_map(self):
        self.assertEqual(self.fix("keyref", "app"), "admin-app")

    def test_renamed_key_and_renamed_id_together(self):
        self.assertEqual(self.fix("conkeyref", "lib/hot"), "shared/burn-risk")

    def test_nothing_is_settled_without_a_previous_version(self):
        self.repo = repo(("GUID-lib", "/d/lib.dita", self.LIB_NEW),
                         ("GUID-t1", "/d/t1.dita", TOPIC % '<note conref="GUID-lib.dita#lib/hot"/>'))
        self.assertIsNone(self.fix("conref", "GUID-lib.dita#lib/hot"))

    def test_two_elements_with_the_same_text_are_not_guessed_between(self):
        twice = self.LIB_NEW.replace("</body>", '<note id="also-hot">Surface is hot.</note></body>')
        self.repo = repo(("GUID-lib", "/d/lib.dita", twice, self.LIB_OLD),
                         ("GUID-t1", "/d/t1.dita", TOPIC % '<note conref="GUID-lib.dita#lib/hot"/>'))
        self.assertIsNone(self.fix("conref", "GUID-lib.dita#lib/hot"))

    def test_key_that_differs_only_in_punctuation_needs_no_history(self):
        self.repo = repo(("GUID-m", "/d/m.ditamap", '<map><keydef keys="product_name"><topicmeta><keywords><keyword>X</keyword></keywords></topicmeta></keydef></map>'),
                         ("GUID-t1", "/d/t1.dita", TOPIC % '<ph keyref="product-name"/>'))
        self.assertEqual(self.fix("keyref", "product-name"), "product_name")

    def item(self, attribute, value, new):
        refs = [r for r in self.repo.broken() if (r["attribute"], r["value"]) == (attribute, value)]
        return dict(refs[0], uses=[{"file": r["file"]} for r in refs], repair={"verdict": "fix", "new_value": new})

    def test_in_a_repository_with_guid_names_a_renamed_key_is_renamed_back(self):
        # AEM Guides reads keys="a b" as one key, so a second name is not an option there.
        fix = refheal.source_fix(self.repo, self.item("keyref", "app", "admin-app"))
        self.assertEqual((fix["file"], fix["element"], fix["attribute"], fix["current"], fix["new"], fix["references"]),
                         ("/d/m.ditamap", "keydef", "keys", "admin-app", "app", 2))

    def test_a_key_is_not_renamed_back_when_something_uses_its_new_name(self):
        self.repo = repo(
            ("GUID-m", "/d/m.ditamap", self.MAP_NEW, self.MAP_OLD),
            ("GUID-t1", "/d/t1.dita", TOPIC % '<ph keyref="app"/>'),
            ("GUID-t2", "/d/t2.dita", TOPIC % '<ph keyref="app"/>'),
            ("GUID-t3", "/d/t3.dita", TOPIC % '<ph keyref="admin-app"/>'))
        self.assertIsNone(refheal.source_fix(self.repo, self.item("keyref", "app", "admin-app")))

    def test_on_disk_a_renamed_key_gets_its_old_name_back_as_a_second_name(self):
        root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "samples", "ref-demo", "v2")
        self.repo = refcheck.Repo(root)
        fix = refheal.source_fix(self.repo, self.item("keyref", "admin-app", "mobile-app"))
        self.assertEqual((fix["file"], fix["current"], fix["new"], fix["references"]),
                         ("/router_guide.ditamap", "mobile-app", "mobile-app admin-app", 4))

    def test_fix_at_the_source_puts_an_id_back_when_nothing_uses_the_new_one(self):
        fix = refheal.source_fix(self.repo, self.item("conref", "GUID-lib.dita#lib/hot", "GUID-lib.dita#lib/burn-risk"))
        self.assertEqual((fix["file"], fix["element"], fix["attribute"], fix["current"], fix["new"]),
                         ("/d/lib.dita", "note", "id", "burn-risk", "hot"))

    def test_no_fix_at_the_source_when_the_new_id_is_already_in_use(self):
        self.repo = repo(
            ("GUID-lib", "/d/lib.dita", self.LIB_NEW, self.LIB_OLD),
            ("GUID-t1", "/d/t1.dita", TOPIC % '<note conref="GUID-lib.dita#lib/hot"/>'),
            ("GUID-t2", "/d/t2.dita", TOPIC % '<note conref="GUID-lib.dita#lib/hot"/>'),
            ("GUID-t3", "/d/t3.dita", TOPIC % '<note conref="GUID-lib.dita#lib/burn-risk"/>'))
        self.assertIsNone(refheal.source_fix(self.repo, self.item("conref", "GUID-lib.dita#lib/hot", "GUID-lib.dita#lib/burn-risk")))

    def test_no_fix_at_the_source_for_a_single_reference_or_without_a_repair(self):
        single = self.item("conkeyref", "lib/hot", "shared/burn-risk")
        self.assertIsNone(refheal.source_fix(self.repo, single))
        none = dict(self.item("keyref", "app", None), repair={"verdict": "none", "new_value": None})
        self.assertIsNone(refheal.source_fix(self.repo, none))


class WholeRunWithoutAModel(unittest.TestCase):
    def test_server_payload_in_repairs_and_source_fixes_out(self):
        case = RepairsWithoutAModel()
        payload = {"files": [
            {"id": "GUID-lib", "path": "/d/lib.dita", "xml": case.LIB_NEW.replace('<p id="support">Ring the desk.</p>', ""),
             "previous": [case.LIB_OLD.replace('<p id="help">Call us.</p>', "")]},
            {"id": "GUID-t1", "path": "/d/t1.dita", "xml": TOPIC % '<note conref="GUID-lib.dita#lib/hot"/>'},
            {"id": "GUID-t2", "path": "/d/t2.dita", "xml": TOPIC % '<note conref="GUID-lib.dita#lib/hot"/>'}]}

        def no_model(*args, **kwargs):
            raise AssertionError("a rename proven by the previous version must not reach the model")

        original, refheal.agentloop.run = refheal.agentloop.run, no_model
        try:
            out = refheal.heal_files(payload, log=lambda message: None)
        finally:
            refheal.agentloop.run = original
        self.assertEqual([(r["file"], r["old"], r["new"], r["verdict"], r["stage"]) for r in sorted(out["repairs"], key=lambda r: r["file"])], [
            ("/d/t1.dita", "GUID-lib.dita#lib/hot", "GUID-lib.dita#lib/burn-risk", "fix", "history"),
            ("/d/t2.dita", "GUID-lib.dita#lib/hot", "GUID-lib.dita#lib/burn-risk", "fix", "history"),
        ])
        self.assertEqual(out["repairs"][0]["target"], 'element "burn-risk" in "Lib" (lib.dita)')
        self.assertEqual(len(out["source_fixes"]), 1)

    def test_payload_without_files_is_rejected(self):
        with self.assertRaises(ValueError):
            refheal.heal_files({"nope": 1})


if __name__ == "__main__":
    unittest.main()


class Planner(unittest.TestCase):
    """The planner's tools, driven by hand: what the agent may and may not do with them."""

    def setUp(self):
        case = RepairsWithoutAModel
        self.session = refplan.Session([
            {"id": "GUID-lib", "path": "/d/lib.dita", "xml": case.LIB_NEW, "previous": [case.LIB_OLD]},
            {"id": "GUID-m", "path": "/d/m.ditamap", "xml": case.MAP_NEW, "previous": [case.MAP_OLD]},
            {"id": "GUID-t1", "path": "/d/t1.dita",
             "xml": TOPIC % '<note conref="GUID-lib.dita#lib/hot"/><p conref="GUID-lib.dita#lib/help"/><ph keyref="app"/>'},
            {"id": "GUID-t2", "path": "/d/t2.dita", "xml": TOPIC % '<note conref="GUID-lib.dita#lib/hot"/><ph keyref="app"/>'},
        ], log=lambda message: None)
        self.groups = {g["broken_value"]: g for g in self.session.tool_overview({})["groups"]}

    def decide(self, value, decision):
        return self.session.tool_decide({"group_ids": [self.groups[value]["id"]], "decision": decision, "reason": "test"})

    def test_overview_groups_references_by_target_and_names_files_by_their_own_name(self):
        self.assertEqual({value: (g["references"], (g["repair"] or {}).get("found_by")) for value, g in self.groups.items()}, {
            "lib.dita#lib/hot": (2, "history"), "lib.dita#lib/help": (1, None), "app": (2, "history")})
        self.assertIn("source_option", self.groups["app"])

    def test_a_repair_that_is_not_known_or_not_proven_cannot_be_applied(self):
        self.assertEqual(self.decide("lib.dita#lib/help", "repair_references")["accepted"], [])
        self.assertEqual(self.decide("lib.dita#lib/help", "repair_at_source")["accepted"], [])
        self.assertEqual(len(self.decide("lib.dita#lib/help", "leave_broken")["accepted"]), 1)
        self.assertIn("error", self.session.tool_decide({"group_ids": [], "decision": "delete_everything", "reason": "x"}))

    def test_apply_and_recheck_reports_what_resolves_and_the_result_says_how_each_reference_was_settled(self):
        self.decide("lib.dita#lib/hot", "repair_references")
        self.decide("app", "repair_at_source")
        self.decide("lib.dita#lib/help", "leave_broken")
        recheck = self.session.tool_apply_and_recheck({})
        self.assertEqual((recheck["reference_edits"], recheck["edits_at_the_source"], recheck["still_broken_and_undecided"]), (2, 1, 0))
        out = self.session.result()
        self.assertEqual(sorted((r["old"], r["verdict"], r["new"]) for r in out["repairs"]), [
            ("GUID-lib.dita#lib/help", "none", None),
            ("GUID-lib.dita#lib/hot", "fix", "GUID-lib.dita#lib/burn-risk"),
            ("GUID-lib.dita#lib/hot", "fix", "GUID-lib.dita#lib/burn-risk"),
            ("app", "covered", None), ("app", "covered", None)])
        self.assertEqual([(f["attribute"], f["current"], f["new"], f["chosen"]) for f in out["source_fixes"]],
                         [("keys", "admin-app", "app", True)])
        self.assertTrue(any("checked again" in step for step in out["plan"]))

    def test_groups_the_planner_never_decided_get_the_cautious_default(self):
        self.session.finish_unfinished()
        verdicts = {r["old"]: r["verdict"] for r in self.session.result()["repairs"]}
        self.assertEqual(verdicts, {"GUID-lib.dita#lib/hot": "fix", "app": "fix", "GUID-lib.dita#lib/help": "none"})

    def test_an_edit_that_breaks_the_planners_own_repair_comes_back_in_the_next_round(self):
        # Rename the key back at the source for one group while another group is repaired to the new name.
        session = refplan.Session([
            {"id": "GUID-lib", "path": "/d/lib.dita", "xml": RepairsWithoutAModel.LIB_NEW, "previous": [RepairsWithoutAModel.LIB_OLD]},
            {"id": "GUID-m", "path": "/d/m.ditamap", "xml": RepairsWithoutAModel.MAP_NEW, "previous": [RepairsWithoutAModel.MAP_OLD]},
            {"id": "GUID-t1", "path": "/d/t1.dita", "xml": TOPIC % '<note conkeyref="lib/hot"/><note conkeyref="lib/burn-risk"/>'},
            {"id": "GUID-t2", "path": "/d/t2.dita", "xml": TOPIC % '<note conkeyref="lib/burn-risk"/>'},
        ], log=lambda message: None)
        groups = {g["broken_value"]: g for g in session.tool_overview({})["groups"]}
        session.tool_decide({"group_ids": [groups["lib/burn-risk"]["id"]], "decision": "repair_at_source", "reason": "test"})
        session.tool_decide({"group_ids": [groups["lib/hot"]["id"]], "decision": "repair_references", "reason": "test"})
        recheck = session.tool_apply_and_recheck({})
        self.assertEqual(recheck["still_broken_and_undecided"], 1)
        self.assertEqual(session.tool_overview({})["groups"][0]["broken_value"], "shared/burn-risk")

    def test_an_answer_an_author_gave_before_is_used_again_without_an_agent(self):
        files = [dict(f) for f in self.session.original]
        session = refplan.Session(files, log=lambda message: None,
                                  memory={"conref|GUID-lib.dita#lib/help": "GUID-lib.dita#lib/support"})
        group = next(g for g in session.tool_overview({})["groups"] if g["broken_value"] == "lib.dita#lib/help")
        self.assertEqual((group["repair"]["found_by"], group["repair"]["verdict"], group["repair"]["new_value"]),
                         ("author", "fix", "lib.dita#lib/support"))

    def test_a_remembered_answer_that_no_longer_resolves_is_ignored(self):
        session = refplan.Session([dict(f) for f in self.session.original], log=lambda message: None,
                                  memory={"conref|GUID-lib.dita#lib/help": "GUID-lib.dita#lib/not-there"})
        group = next(g for g in session.tool_overview({})["groups"] if g["broken_value"] == "lib.dita#lib/help")
        self.assertIsNone(group["repair"])

    def test_answers_are_stored_and_bad_ones_refused(self):
        import tempfile
        path = os.path.join(tempfile.mkdtemp(), "answers.json")
        self.assertEqual(refplan.remember("href", "a#b/old", "a#b/new", path), 1)
        self.assertEqual(refplan.load_memory(path)["answers"], {"href|a#b/old": "a#b/new"})
        for bad in (("href", "same", "same"), ("href", "", "x"), (None, "a", "b")):
            with self.assertRaises(ValueError):
                refplan.remember(*bad, path=path)

    def test_attribute_edits_change_only_that_attribute_and_that_value(self):
        xml, changed = refplan.apply_attribute_edits(
            '<a keyref="app"/><b keyref="app-pro"/><c conkeyref="app"/>', [("keyref", "app", "admin-app")])
        self.assertEqual((xml, changed), ('<a keyref="admin-app"/><b keyref="app-pro"/><c conkeyref="app"/>', 1))


class Learning(unittest.TestCase):
    """What the planner keeps between checks, and what it does with the outcome of the last Fix all."""

    LIB = ('<topic id="lib"><title>Lib</title><body><note id="support">Call us.</note><note id="other">No.</note>'
           '<p id="para">Text.</p></body></topic>')
    OLD = '<topic id="lib"><title>Lib</title><body><note id="help">Call us.</note><p id="para">Text.</p></body></topic>'

    def files(self, *topics):
        return [{"id": "GUID-lib", "path": "/d/lib.dita", "xml": self.LIB, "previous": []}] + [
            {"id": "GUID-t%d" % i, "path": "/d/t%d.dita" % i, "xml": TOPIC % body, "previous": []} for i, body in enumerate(topics, 1)]

    def session(self, files, **more):
        return refplan.Session(files, log=lambda message: None, **more)

    def path(self):
        import tempfile
        return os.path.join(tempfile.mkdtemp(), "memory.json")

    def test_the_old_flat_memory_file_is_still_read(self):
        self.assertEqual(refplan._memory({"href|a": "b"})["answers"], {"href|a": "b"})

    def test_an_accepted_rename_is_used_for_the_same_target_reached_by_another_attribute(self):
        path = self.path()
        refplan.remember("conref", "GUID-lib.dita#lib/help", "GUID-lib.dita#lib/support", path)
        session = self.session(self.files('<p>See <xref href="GUID-lib.dita#lib/help"/></p>'), memory=refplan.load_memory(path))
        repair = session.tool_overview({})["groups"][0]["repair"]
        self.assertEqual((repair["found_by"], repair["verdict"], repair["new_value"]), ("author", "fix", "lib.dita#lib/support"))

    def test_an_element_renamed_behind_a_key_is_only_a_hint_for_another_key(self):
        path = self.path()
        refplan.remember("conkeyref", "one/help", "one/support", path)
        files = self.files('<note conkeyref="two/help"/>') + [
            {"id": "GUID-m", "path": "/d/m.ditamap", "xml": '<map><keydef keys="two" href="GUID-lib.dita"/></map>', "previous": []}]
        repair = self.session(files, memory=refplan.load_memory(path)).tool_overview({})["groups"][0]["repair"]
        self.assertEqual((repair["verdict"], repair["new_value"]), ("review", "two/support"))

    def test_forgetting_an_answer_drops_what_was_learned_from_it(self):
        path = self.path()
        refplan.remember("conref", "GUID-lib.dita#lib/help", "GUID-lib.dita#lib/support", path)
        self.assertTrue(refplan.forget("conref", "GUID-lib.dita#lib/help", path))
        self.assertEqual((refplan.load_memory(path)["answers"], refplan.load_memory(path)["renames"]), ({}, []))
        self.assertFalse(refplan.forget("conref", "GUID-lib.dita#lib/help", path))

    def test_a_target_an_author_passed_over_is_not_proposed_again(self):
        path = self.path()
        refplan.remember("conref", "GUID-lib.dita#lib/help", "GUID-lib.dita#lib/support", path,
                         rejected=["GUID-lib.dita#lib/other"])
        refplan.forget("conref", "GUID-lib.dita#lib/help", path)
        session = self.session(self.files('<note conref="GUID-lib.dita#lib/help"/>'), memory=refplan.load_memory(path))
        ref = session.current["groups"]["r1-g1"]["refs"][0]
        known = {"new_value": "GUID-lib.dita#lib/other", "verdict": "fix", "reason": "r", "caveat": "", "candidates": [
            {"new_value": "GUID-lib.dita#lib/other", "likelihood": 60, "why": "first"},
            {"new_value": "GUID-lib.dita#lib/support", "likelihood": 30, "why": "second"}]}
        session._drop_declined(ref, known)
        self.assertEqual((known["new_value"], known["verdict"], len(known["candidates"])), ("GUID-lib.dita#lib/support", "review", 1))

    def test_the_same_text_is_repaired_and_changed_text_is_asked_about(self):
        files = self.files('<note conref="GUID-lib.dita#lib/help"/>')
        files[0]["previous"] = [self.OLD]
        session = self.session(files)
        ref = next(r for r in session.current["repo"].broken())
        same = {"new_value": "GUID-lib.dita#lib/support", "verdict": "review", "reason": "Same.", "caveat": "Not sure.", "reviewer": True}
        session._weigh(session.current["repo"], ref, same)
        self.assertEqual((same["verdict"], same["caveat"], same["same_text"]), ("fix", "", True))
        changed = {"new_value": "GUID-lib.dita#lib/other", "verdict": "fix", "reason": "Close.", "caveat": "", "reviewer": True}
        session._weigh(session.current["repo"], ref, changed)
        self.assertEqual((changed["verdict"], changed["same_text"]), ("review", False))
        refused = {"new_value": "GUID-lib.dita#lib/support", "verdict": "review", "reason": "Same.", "caveat": "c", "reviewer": False}
        session._weigh(session.current["repo"], ref, refused)
        self.assertEqual(refused["verdict"], "review")

    def test_after_fix_all_it_tells_saved_from_unsaved_and_waits_before_blaming_a_repair(self):
        files = self.files('<note conref="GUID-lib.dita#lib/help"/>', '<note conref="GUID-lib.dita#lib/support"/>',
                           '<note conref="GUID-lib.dita#lib/other"/>')
        reported = [{"file": "/d/t3.dita", "attribute": "conref", "value": "GUID-lib.dita#lib/other"}]
        edit = lambda n, new: {"file": "/d/t%d.dita" % n, "attribute": "conref", "old": "GUID-lib.dita#lib/help", "new": "GUID-lib.dita#lib/" + new}
        applied = {"when": 1000, "checks": 0, "edits": [edit(1, "support"), edit(2, "support"), edit(3, "other")]}
        lines, failed, finished = self.session(files, reported=reported).look_back(applied, now=1010)
        self.assertEqual((failed, finished), ([], False))
        self.assertIn("1 repair saved and resolves", lines[0])
        self.assertIn("1 repair from the last Fix all did not reach the repository", lines[1])
        self.assertIn("has not indexed the change yet", lines[2])
        session = self.session(files, reported=reported)
        lines, failed, finished = session.look_back(dict(applied, checks=1), now=1000 + refplan.SETTLE_SECONDS)
        self.assertEqual((failed, finished), ([("conref", "GUID-lib.dita#lib/help", "GUID-lib.dita#lib/other")], True))
        only = [r for r in session.result()["repairs"] if r["stage"] == "planner"]
        self.assertEqual([(r["file"], r["verdict"]) for r in only], [("/d/t3.dita", "none")])

    def test_an_edit_at_the_source_that_the_repository_does_not_honour_is_not_chosen_again(self):
        files = self.files('<ph keyref="old-name"/>') + [
            {"id": "GUID-m", "path": "/d/m.ditamap", "xml": '<map><keydef keys="old-name"/></map>', "previous": []}]
        reported = [{"file": "/d/t1.dita", "attribute": "keyref", "value": "old-name"}]
        applied = {"when": 1000, "checks": 1, "edits": [
            {"file": "/d/m.ditamap", "attribute": "keys", "old": "new-name", "new": "old-name"}]}
        session = self.session(files, reported=reported)
        lines, failed, finished = session.look_back(applied, now=1000 + refplan.SETTLE_SECONDS)
        self.assertEqual((session.distrust, failed, finished), (["keys"], [], True))
        self.assertIn("does not hold in AEM", lines[-1])
        early = self.session(files, reported=reported)
        self.assertEqual((early.look_back(applied, now=1100)[2], early.distrust), (False, []))
        # Until AEM has indexed the edit, the references it repaired are waiting, not findings.
        self.assertEqual([(r["verdict"], r["reason"][:30]) for r in early.result()["repairs"] if r["stage"] == "planner"],
                         [("pending", "Repaired by the last Fix all. ")])
        r = RepairsWithoutAModel
        learned = refplan.Session([
            {"id": "GUID-lib", "path": "/d/lib.dita", "xml": r.LIB_NEW, "previous": [r.LIB_OLD]},
            {"id": "GUID-m", "path": "/d/m.ditamap", "xml": r.MAP_NEW, "previous": [r.MAP_OLD]},
            {"id": "GUID-t1", "path": "/d/t1.dita", "xml": TOPIC % '<ph keyref="app"/>'},
            {"id": "GUID-t2", "path": "/d/t2.dita", "xml": TOPIC % '<ph keyref="app"/>'}], log=lambda message: None,
            memory={"no_source_edit": ["keys"]})
        self.assertNotIn("source_option", learned.tool_overview({})["groups"][0])

    def test_files_outside_the_map_that_use_the_target_are_named(self):
        session = self.session(self.files('<note conref="GUID-lib.dita#lib/help"/>'), outside={"/d/lib.dita": ["/x/a.dita", "/x/b.dita"]})
        group = session.tool_overview({})["groups"][0]
        self.assertEqual(group["also_used_from_files_outside_this_map"], 2)
        self.assertEqual(session.result()["repairs"][0]["detail"]["outside"], ["a.dita", "b.dita"])


class WaysOut(unittest.TestCase):
    """When the content is gone, the agents say what can be done about it. A person chooses."""

    OLD = ('<topic id="lib"><title>Lib</title><body><note id="keep">Keep.</note>'
           '<note id="notice" type="note">The old page stays until <b>the end of the year</b>.</note>'
           '<note id="hot" type="warning">The plate is hot.</note><p id="tail">Tail.</p></body></topic>')
    NEW = '<topic id="lib"><title>Lib</title><body><note id="keep">Keep.</note><p id="tail">Tail.</p></body></topic>'

    def session(self, *topics, **more):
        files = [{"id": "GUID-lib", "path": "/d/lib.dita", "xml": self.NEW, "previous": [self.OLD]},
                 {"id": "GUID-m", "path": "/d/m.ditamap", "xml": '<map><keydef keys="shared" href="GUID-lib.dita"/></map>',
                  "previous": ['<map><keydef keys="notes" href="GUID-lib.dita"/></map>']}]
        files += [{"id": "GUID-t%d" % i, "path": "/d/t%d.dita" % i, "xml": TOPIC % body, "previous": []}
                  for i, body in enumerate(topics, 1)]
        return refplan.Session(files, log=lambda message: None, **more)

    def gone(self, session, value):
        group = next(g for g in session.current["groups"].values() if value in g["refs"][0]["value"])
        group["known"] = {"new_value": None, "verdict": "none", "how": "finder", "reason": "It was removed.", "caveat": ""}
        return group

    def test_a_removed_note_can_be_put_back_kept_as_text_or_removed(self):
        session = self.session('<note conref="GUID-lib.dita#lib/notice"/>', '<note conref="GUID-lib.dita#lib/notice"/>')
        group = self.gone(session, "notice")
        described = next(g for g in session.tool_overview({})["groups"] if g["id"] == group["id"])
        self.assertEqual([w["decision"] for w in described["ways_out"]], ["restore_at_source", "keep_text_in_topics", "remove_references"])
        self.assertEqual((described["safety_content"], described["was"]), (False, "The old page stays until the end of the year ."))
        ways = {o["kind"]: o for o in group["ways"]["options"]}
        self.assertEqual(ways["restore"]["anchor"], {"after": "keep"})
        self.assertEqual(ways["restore"]["xml"], '<note id="notice" type="note">The old page stays until <b>the end of the year</b>.</note>')
        self.assertEqual(ways["inline"]["xml"], '<note type="note">The old page stays until <b>the end of the year</b>.</note>')

    def test_a_removed_warning_is_never_offered_for_removal(self):
        session = self.session('<note conref="GUID-lib.dita#lib/hot"/>')
        group = self.gone(session, "hot")
        described = session.tool_overview({})["groups"][0]
        self.assertEqual((described["safety_content"], [w["decision"] for w in described["ways_out"]]),
                         (True, ["restore_at_source", "keep_text_in_topics"]))
        refused = session.tool_decide({"group_ids": [group["id"]], "decision": "remove_references", "reason": "Old."})
        self.assertIn("safety content", refused["rejected"][group["id"]])

    def test_a_link_to_removed_content_can_only_be_put_back(self):
        session = self.session('<p>See <xref href="GUID-lib.dita#lib/notice"/></p>')
        self.gone(session, "notice")
        self.assertEqual([w["decision"] for w in session.tool_overview({})["groups"][0]["ways_out"]], ["restore_at_source"])

    def test_the_planners_recommendation_reaches_the_author_and_nothing_is_changed(self):
        session = self.session('<note conref="GUID-lib.dita#lib/notice"/>')
        group = self.gone(session, "notice")
        accepted = session.tool_decide({"group_ids": [group["id"]], "decision": "remove_references",
                                        "reason": "The notice is about a page that stayed until the end of the year; it is out of date."})
        self.assertEqual(accepted["accepted"], [group["id"]])
        session.tool_apply_and_recheck({})
        repair = session.result()["repairs"][0]
        self.assertEqual((repair["verdict"], repair["new"]), ("none", None))
        self.assertTrue(repair["reason"].startswith("Suggested: Remove the 1 references from the 1 topics."))
        ways = repair["detail"]["ways_out"]
        self.assertEqual((ways["recommended"]["kind"], [o["kind"] for o in ways["options"]]), ("remove", ["restore", "inline", "remove"]))
        self.assertIn('conref="GUID-lib.dita#lib/notice"', session.files[2]["xml"])

    def test_putting_a_piece_back_also_follows_a_key_that_was_renamed(self):
        session = self.session('<note conkeyref="notes/notice"/>')
        group = self.gone(session, "notes/notice")
        session.tool_decide({"group_ids": [group["id"]], "decision": "restore_at_source", "reason": "Removed by mistake."})
        session.tool_apply_and_recheck({})
        ways = session.result()["repairs"][0]["detail"]["ways_out"]
        restore = ways["options"][0]
        self.assertEqual((restore["kind"], restore["file"], restore["reference_edits"]),
                         ("restore", "/d/lib.dita", [{"attribute": "conkeyref", "old": "notes/notice", "new": "shared/notice"}]))
        self.assertEqual(ways["recommended"]["kind"], "restore")


class RememberedFindings(unittest.TestCase):
    """What finder agents found is kept between checks, the biggest causes go first, and one
    broken target that two topics mean differently gets an answer per topic."""

    LIB = ('<topic id="lib"><title>Lib</title><body><note id="before-upgrade">Back up before you upgrade.</note>'
           '<note id="retention">Backups are kept for 30 days.</note></body></topic>')
    OLD = '<topic id="lib"><title>Lib</title><body><note id="backup">Back up before you upgrade. Kept for 30 days.</note></body></topic>'

    def files(self, lib=None):
        topic = '<topic id="%s"><title>%s</title><body><p>%s</p><note conref="GUID-lib.dita#lib/backup"/></body></topic>'
        return [{"id": "GUID-lib", "path": "/d/lib.dita", "xml": lib or self.LIB, "previous": [self.OLD]},
                {"id": "GUID-t1", "path": "/d/t1.dita", "xml": topic % ("t1", "Upgrade", "Before you upgrade:"), "previous": []},
                {"id": "GUID-t2", "path": "/d/t2.dita", "xml": topic % ("t2", "Retention", "Old backups are removed."), "previous": []}]

    def found(self, group):
        """What a finder agent would have answered, put where the session keeps it."""
        group["known"] = {"new_value": "GUID-lib.dita#lib/before-upgrade", "verdict": "review", "how": "finder", "reason": "Split.",
                          "caveat": "", "reviewer": True, "candidates": [
                              {"new_value": "GUID-lib.dita#lib/before-upgrade", "likelihood": 60, "why": "First half."},
                              {"new_value": "GUID-lib.dita#lib/retention", "likelihood": 35, "why": "Second half."}]}

    def session(self, files=None, **more):
        return refplan.Session(files or self.files(), log=lambda message: None, **more)

    def test_each_reference_gets_the_candidate_its_own_sentence_asks_for(self):
        asked = []

        def choose(was, candidates, references):
            asked.append((was, candidates, references))
            return {r["reference"]: 2 if r["topic"] == "Retention" else 1 for r in references}

        session = self.session(choose=choose)
        group = session.current["groups"]["r1-g1"]
        self.found(group)
        session._settle(session.current["repo"], group)
        self.assertEqual(len(asked[0][1]), 2)
        self.assertEqual(asked[0][1][1]["shows_now"], "Backups are kept for 30 days.")
        session.tool_decide({"group_ids": ["r1-g1"], "decision": "ask_author", "reason": "Split in two."})
        session.tool_apply_and_recheck({})
        proposed = {r["file"]: r["new"] for r in session.result()["repairs"]}
        self.assertEqual(proposed, {"/d/t1.dita": "GUID-lib.dita#lib/before-upgrade", "/d/t2.dita": "GUID-lib.dita#lib/retention"})

    def test_a_finding_is_used_again_until_what_it_rests_on_changes(self):
        cache = {}
        first = self.session(cache=cache, choose=lambda *a: {})
        group = first.current["groups"]["r1-g1"]
        self.found(group)
        first._to_cache(first.current["repo"], group)
        again = self.session(cache=cache, choose=lambda *a: {})
        self.assertTrue(again._from_cache(again.current["repo"], again.current["groups"]["r1-g1"]))
        self.assertEqual(again.current["groups"]["r1-g1"]["known"]["new_value"], "GUID-lib.dita#lib/before-upgrade")
        changed = self.session(self.files(self.LIB.replace("30 days", "60 days")), cache=cache)
        self.assertFalse(changed._from_cache(changed.current["repo"], changed.current["groups"]["r1-g1"]))

    def test_a_search_that_broke_down_is_not_remembered(self):
        cache = {}
        session = self.session(cache=cache)
        group = session.current["groups"]["r1-g1"]
        self.found(group)
        session._to_cache(session.current["repo"], group, failed=True)
        self.assertEqual(cache, {})

    def test_past_the_budget_the_targets_with_fewer_references_wait_and_say_so(self):
        files = self.files() + [{"id": "GUID-t3", "path": "/d/t3.dita", "previous": [],
                                 "xml": TOPIC % '<note conref="GUID-lib.dita#lib/other-gone"/>'}]
        cache = {}
        session = self.session(files, cache=cache, max_groups=0)
        ids = list(session.current["groups"])
        result = session.tool_investigate({"group_ids": ids})
        self.assertEqual(result["waiting_for_the_next_check"], 2)
        self.assertTrue(all("Not looked at in this check" in g["known"]["reason"] for g in session.current["groups"].values()))
        self.assertIn("wait for the next check (3 references)", session.plan[-1])
        self.assertEqual(cache, {})


class LiveView(unittest.TestCase):
    def test_every_change_of_who_does_what_is_sent_as_rows(self):
        seen = []
        r = RepairsWithoutAModel
        session = refplan.Session([
            {"id": "GUID-lib", "path": "/d/lib.dita", "xml": r.LIB_NEW, "previous": [r.LIB_OLD]},
            {"id": "GUID-t1", "path": "/d/t1.dita", "xml": TOPIC % '<note conref="GUID-lib.dita#lib/hot"/>'}],
            log=lambda message: None, timeline=seen.append)
        group = session.tool_overview({})["groups"][0]["id"]
        session.step("planner", "active", "Planner agent", "Reading")
        session.tool_decide({"group_ids": [group], "decision": "repair_references", "reason": "Renamed."})
        session.tool_apply_and_recheck({})
        session.step("planner", "done", "Planner agent", "Planned")
        last = {row["id"]: (row["state"], row["who"], row["text"]) for row in seen[-1]}
        self.assertEqual(last["planner"], ("done", "Planner agent", "Planned"))
        self.assertEqual(last["decide-1"], ("done", "Planner agent", "Decided: repair 1"))
        self.assertEqual(last["recheck-1"][2], "Tried the plan on a copy: 1 reference works, 0 left for the author")
        self.assertEqual([row["id"] for row in seen[-1]], ["planner", "decide-1", "recheck-1"])


class Scanner(unittest.TestCase):
    def test_behind_aem_two_names_in_keys_are_one_key_as_aem_reads_them(self):
        topic = TOPIC % '<ph keyref="a"/><ph keyref="b"/>'
        on_aem = repo(("GUID-m", "/d/m.ditamap", '<map><keydef keys="a b"/></map>'), ("GUID-t", "/d/t.dita", topic))
        self.assertEqual(sorted(k[1] for k in broken(on_aem)), ["a", "b"])
        plain = refcheck.Repo(files=[{"path": "/d/m.ditamap", "xml": '<map><keydef keys="a b"/></map>'}, {"path": "/d/t.dita", "xml": topic}])
        self.assertEqual(plain.broken(), [])

    def test_a_key_in_a_key_scope_can_be_named_with_the_scope(self):
        r = refcheck.Repo(files=[
            {"path": "/d/m.ditamap", "xml": '<map><topicgroup keyscope="eu"><keydef keys="price"/></topicgroup></map>'},
            {"path": "/d/t.dita", "xml": TOPIC % '<ph keyref="eu.price"/><ph keyref="price"/><ph keyref="us.price"/>'}])
        self.assertEqual([ref["value"] for ref in r.broken()], ["us.price"])

    def test_the_end_of_a_conref_range_must_exist_too(self):
        r = repo(("GUID-lib", "/d/lib.dita", '<topic id="lib"><title>L</title><body><p id="a">A</p><p id="b">B</p></body></topic>'),
                 ("GUID-t", "/d/t.dita", TOPIC % '<p conref="GUID-lib.dita#lib/a" conrefend="GUID-lib.dita#lib/z"/>'))
        self.assertEqual([(ref["attribute"], ref["reason"]) for ref in r.broken()], [("conrefend", "element-missing")])

    def test_an_undefined_key_with_a_working_fallback_is_not_broken(self):
        lib = '<topic id="lib"><title>L</title><body><note id="n">N</note></body></topic>'
        body = ('<p><xref keyref="gone" href="GUID-lib.dita"/> <xref keyref="gone" href="GUID-nofile.dita"/> <xref keyref="gone"/></p>'
                '<note conkeyref="gone/n" conref="GUID-lib.dita#lib/n"/><note conkeyref="gone/n" conref="GUID-lib.dita#lib/zzz"/>')
        r = repo(("GUID-lib", "/d/lib.dita", lib), ("GUID-t", "/d/t.dita", TOPIC % body))
        found = sorted((ref["attribute"], ref["value"]) for ref in r.broken())
        self.assertEqual(found, [("conkeyref", "gone/n"), ("conref", "GUID-lib.dita#lib/zzz"), ("href", "GUID-nofile.dita"),
                                 ("keyref", "gone"), ("keyref", "gone")])
        self.assertEqual(len([ref for ref in r.refs if ref["attribute"] in ("keyref", "conkeyref")]), 5)

    def test_a_key_defined_through_another_key_is_followed_to_its_target(self):
        r = repo(("GUID-lib", "/d/lib.dita", '<topic id="lib"><title>L</title><body><note id="n">N</note></body></topic>'),
                 ("GUID-m", "/d/m.ditamap", '<map><keydef keys="real" href="GUID-lib.dita"/><keydef keys="alias" keyref="real"/></map>'),
                 ("GUID-t", "/d/t.dita", TOPIC % '<note conkeyref="alias/n"/><note conkeyref="alias/zzz"/><ph keyref="alias"/>'))
        self.assertEqual([(ref["value"], ref["reason"]) for ref in r.broken()], [("alias/zzz", "element-missing")])

    def test_on_disk_a_percent_encoded_file_name_and_an_upper_case_extension_are_read(self):
        import tempfile
        root = tempfile.mkdtemp()
        lib = '<topic id="lib"><title>L</title><body><note id="n">N</note></body></topic>'
        for name, xml in (("my topic.dita", lib), ("BIG.DITA", lib),
                          ("a.dita", TOPIC % '<p><xref href="my%20topic.dita#lib/n"/> <xref href="BIG.DITA#lib/zzz"/></p>')):
            with open(os.path.join(root, name), "w") as handle:
                handle.write(xml)
        self.assertEqual([(ref["value"], ref["reason"]) for ref in refcheck.Repo(root).broken()], [("BIG.DITA#lib/zzz", "element-missing")])

    def test_the_conditions_a_reference_is_published_under_are_recorded(self):
        files = [
            {"id": "GUID-lib", "path": "/d/lib.dita", "xml": '<topic id="lib"><title>L</title><body><note id="a">A</note></body></topic>'},
            {"id": "GUID-t1", "path": "/d/t1.dita", "xml": TOPIC % ('<section audience="internal"><note platform="cloud  onprem" '
                                                                 'conref="GUID-lib.dita#lib/gone"/></section>')},
            {"id": "GUID-t2", "path": "/d/t2.dita", "xml": TOPIC % '<note conref="GUID-lib.dita#lib/gone"/>'},
            {"id": "GUID-m", "path": "/d/m.ditamap", "xml": '<map><topichead product="pro"><topicref href="GUID-t2.dita"/></topichead>'
                                                           '<topicref href="GUID-t1.dita"/><topicref href="GUID-t2.dita" audience="partner"/></map>'}]
        session = refplan.Session(files, log=lambda message: None)
        under = session.result()["repairs"][0]["detail"]["published_under"]
        by_topic = {json.dumps(entry["in_topic"]): entry for entry in under}
        inside = by_topic[json.dumps([{"audience": "internal"}, {"platform": "cloud onprem"}])]
        self.assertEqual((inside["references"], inside["in_map"]), (1, [[]]))
        plain = by_topic["[]"]
        self.assertEqual(plain["in_map"], [[{"product": "pro"}], [{"audience": "partner"}]])


class Progress(unittest.TestCase):
    def test_each_map_has_its_own_progress(self):
        import sidecar
        sidecar.PROGRESS.clear()
        sidecar.progress_of("/dam/a.ditamap").update(running=True, lines=["a"])
        sidecar.progress_of("/dam/b.ditamap").update(running=True, lines=["b"])
        self.assertEqual(sidecar.PROGRESS["/dam/a.ditamap"]["lines"], ["a"])
        self.assertEqual(sidecar.PROGRESS["/dam/b.ditamap"]["lines"], ["b"])
        self.assertEqual(sidecar.PROGRESS.get("/dam/none.ditamap", sidecar.IDLE)["running"], False)


class LooseAnswers(unittest.TestCase):
    """The CLI model writes its final answer as free JSON; types are put right before checking."""

    def test_a_json_answer_is_read_out_of_a_fenced_block_and_prose_is_refused(self):
        import sidecar
        self.assertEqual(sidecar.parse_json('```json\n{"action": "finish", "key": ""}\n```'), {"action": "finish", "key": ""})
        with self.assertRaises(ValueError):
            sidecar.parse_json("I could not find it.")

    def test_a_number_becomes_text_and_a_single_candidate_becomes_a_list(self):
        import agentloop
        self.assertEqual(agentloop._coerce({"type": "string"}, 85), "85")
        self.assertEqual(agentloop._coerce({"type": "string"}, None), "")
        self.assertEqual(agentloop._coerce({"type": "array"}, None), [])
        self.assertEqual(agentloop._coerce({"type": "array"}, "a :: 10 :: why"), ["a :: 10 :: why"])
        self.assertEqual(agentloop._coerce({"type": "string"}, "kept"), "kept")

    def test_candidates_are_read_checked_and_ranked(self):
        r = repo(
            ("GUID-lib", "/d/lib.dita", '<topic id="lib"><title>Lib</title><body><note id="a">Hot.</note><note id="b">Cold.</note>'
                                        '<p id="c">Text.</p></body></topic>'),
            ("GUID-t1", "/d/t1.dita", TOPIC % '<note conref="GUID-lib.dita#lib/gone"/>'))
        ref = r.broken()[0]
        tools = refheal.Tools(r)
        tools.seen_files.add("d/lib.dita")
        answer = {"reason": "Same warning.", "likelihood": "70", "confidence": "medium", "other_candidates": [
            "d/lib.dita#lib/b :: 25 :: Also a note.",
            "d/lib.dita#lib/c :: 20 :: A paragraph, wrong type for a note conref.",
            "d/other.dita#x/y :: 90 :: A file no tool showed.",
            "not a candidate"]}
        ranked = refheal.ranked_candidates(r, ref, answer, tools, "GUID-lib.dita#lib/a")
        self.assertEqual([(c["new_value"], c["likelihood"]) for c in ranked],
                         [("GUID-lib.dita#lib/a", 70), ("GUID-lib.dita#lib/b", 25)])

    def test_preview_text_before_and_now(self):
        case = RepairsWithoutAModel
        r = repo(("GUID-lib", "/d/lib.dita", case.LIB_NEW, case.LIB_OLD),
                 ("GUID-m", "/d/m.ditamap", case.MAP_NEW, case.MAP_OLD),
                 ("GUID-t1", "/d/t1.dita", TOPIC % '<note conref="GUID-lib.dita#lib/hot"/><ph keyref="app"/>'))
        refs = broken(r)
        conref, keyref = refs[("conref", "GUID-lib.dita#lib/hot")], refs[("keyref", "app")]
        self.assertEqual(refheal.text_at(r, conref, conref["value"], previous=True), "Surface is hot.")
        self.assertEqual(refheal.text_at(r, conref, "GUID-lib.dita#lib/burn-risk"), "Surface is hot.")
        self.assertEqual(refheal.text_at(r, keyref, "app", previous=True), "Admin")
        self.assertEqual(refheal.text_at(r, keyref, "admin-app"), "Admin")
        self.assertEqual(refheal.text_at(r, keyref, "nokey"), "")
