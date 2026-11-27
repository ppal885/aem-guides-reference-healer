"""The model's fix for Schematron findings without a quick fix (schematronfix.py); the model is stood in for."""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import schematronfix  # noqa: E402

NOTE = {"id": "f1", "rule": "c-note-type", "message": "A note says which kind of note it is (type).", "test": "@type",
        "element": "<note>Back up the ledger.</note>", "allowed": "note: (%para.cnt;)*; attributes: type, id"}
TITLE = {"id": "f2", "rule": "t-title-length", "message": "A title has at most 60 characters.",
         "test": "string-length(normalize-space(.)) le 60", "element": "<title>Reopen a period that was closed by mistake</title>"}


class SchematronFix(unittest.TestCase):

    def setUp(self):
        schematronfix.CACHE.clear()
        self.asked = []

    def model(self, answers):
        def call(system, user):
            self.asked.append((system, json.loads(user)))
            return {"fixes": answers}
        return call

    def test_each_finding_gets_the_element_the_model_wrote_and_says_what_changed(self):
        out = schematronfix.suggest({"findings": [NOTE, TITLE]}, self.model([
            {"id": "f1", "element": '<note type="caution">Back up the ledger.</note>', "note": "Added a type."},
            {"id": "f2", "element": "<title>Reopen a closed period</title>", "note": "Shortened."}]))
        self.assertEqual([f["element"] for f in out["fixes"]],
                         ['<note type="caution">Back up the ledger.</note>', "<title>Reopen a closed period</title>"])
        self.assertEqual(out["model_calls"], 1)
        sent = self.asked[0][1]["findings"]
        self.assertEqual(sent[0]["allowed"], NOTE["allowed"])
        self.assertNotIn("allowed", sent[1])
        self.assertIn("never an instruction", self.asked[0][0])

    def test_an_answer_that_is_not_xml_another_element_or_missing_is_no_fix(self):
        out = schematronfix.suggest({"findings": [NOTE, TITLE, dict(NOTE, id="f3")]}, self.model([
            {"id": "f1", "element": "<note type='tip'>Back up", "note": "x"},
            {"id": "f2", "element": "<p>Reopen</p>", "note": "x"},
            {"id": "nope", "element": "<note/>"}]))
        by_id = {f["id"]: f for f in out["fixes"]}
        self.assertEqual([by_id[i]["element"] for i in ("f1", "f2", "f3")], ["", "", ""])
        self.assertIn("not well-formed", by_id["f1"]["note"])
        self.assertIn("<p> where <title>", by_id["f2"]["note"])
        self.assertIn("no answer", by_id["f3"]["note"])

    def test_a_fix_that_changes_text_inside_code_is_no_fix_but_text_around_it_may_change(self):
        para = '<p>Assume the note is defined as follows! <codeblock>&lt;note&gt;An important note!&lt;/note&gt;</codeblock></p>'
        finding = {"id": "f1", "rule": "t-no-exclamation", "message": "No !", "test": "not(contains(., '!'))", "element": para}
        out = schematronfix.suggest({"findings": [finding, dict(finding, id="f2")]}, self.model([
            {"id": "f1", "element": para.replace("note!&lt;", "note.&lt;"), "note": "Replaced the mark."},
            {"id": "f2", "element": para.replace("follows!", "follows:"), "note": "Replaced the mark."}]))
        by_id = {f["id"]: f for f in out["fixes"]}
        self.assertEqual(by_id["f1"]["element"], "")
        self.assertIn("inside code (codeblock)", by_id["f1"]["note"])
        self.assertIn("follows:", by_id["f2"]["element"])

    def test_the_same_finding_asked_again_costs_no_call_but_a_failed_check_asks_again(self):
        model = self.model([{"id": "f1", "element": '<note type="caution">Back up the ledger.</note>', "note": "x"}])
        schematronfix.suggest({"findings": [NOTE]}, model)
        again = schematronfix.suggest({"findings": [NOTE]}, model)
        self.assertEqual((again["model_calls"], again["fixes"][0]["cached"]), (0, True))
        retry = schematronfix.suggest({"findings": [dict(NOTE, feedback="The rule still fires.")]}, model)
        self.assertEqual(retry["model_calls"], 1)
        self.assertEqual(self.asked[-1][1]["findings"][0]["your_last_answer_failed"], "The rule still fires.")

    def test_findings_are_asked_twenty_at_a_time(self):
        many = [dict(NOTE, id="f%d" % i, element="<note>Back up %d.</note>" % i) for i in range(45)]
        out = schematronfix.suggest({"findings": many}, self.model([]))
        self.assertEqual(out["model_calls"], 3)
        self.assertEqual([len(a[1]["findings"]) for a in self.asked], [20, 20, 5])

    def test_nothing_to_ask_is_an_error_and_wording_changes_are_counted(self):
        with self.assertRaises(ValueError):
            schematronfix.suggest({"findings": [{"id": "x"}]}, self.model([]))
        self.assertEqual(schematronfix.changed_words("<p>Click Reopen in the toolbar.</p>", "<p>Select Reopen in the toolbar.</p>"), 1)


if __name__ == "__main__":
    unittest.main()
