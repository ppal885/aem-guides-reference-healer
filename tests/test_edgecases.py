"""Edge cases of the case matrix (eval/cases.json) that had no test of their own. No model."""
import base64
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import alttext  # noqa: E402
import duplicates  # noqa: E402
import refcheck  # noqa: E402

WORDS = "Back up the payroll database before you close the pay period, every single time."


def topic(path, body, lang=None):
    name = os.path.splitext(os.path.basename(path))[0]
    return {"path": path, "xml": '<topic id="%s"%s><title>T</title><body>%s</body></topic>' % (
        name, ' xml:lang="%s"' % lang if lang else "", body)}


class EdgeCases(unittest.TestCase):
    def test_a_pushed_conref_whose_target_is_gone_is_broken(self):
        files = [topic("/d/a.dita", '<p conaction="pushafter" conref="lib.dita#lib/p1">More.</p>'
                                    '<p conaction="mark" conref="lib.dita#lib/p1"/>')]
        broken = refcheck.Repo(files=files).broken()
        self.assertEqual([(r["attribute"], r["reason"]) for r in broken], [("conref", "file-missing")] * 2)

    def test_a_copy_that_holds_a_variable_keeps_its_keyref(self):
        files = [topic("/d/%s.dita" % n, '<p>Open <ph keyref="product"/> and %s</p>' % WORDS) for n in "ab"]
        group = duplicates.find(files)[0]
        self.assertEqual(group["copies"][0]["markup"], "<ph keyref=product>")

    def test_a_copy_with_a_phrase_something_links_to_is_not_offered(self):
        # 24 Nov 2026: a paragraph whose <ph id> another topic linked to was shared, and the link broke.
        p = '<p>Save the <ph id="cfg">running configuration</ph> and %s</p>' % WORDS
        linked = topic("/d/d.dita", '<p>See the <xref href="a.dita#a/cfg">configuration</xref>.</p>')
        files = [topic("/d/%s.dita" % n, p) for n in "abc"] + [linked]
        self.assertEqual(sorted(c["file"] for c in duplicates.find(files)[0]["copies"]), ["d/b.dita", "d/c.dita"])
        by_key = topic("/d/d.dita", '<p>Use <ph conkeyref="vars/cfg"/> here.</p>')
        self.assertEqual(duplicates.find([topic("/d/%s.dita" % n, p) for n in "abc"] + [by_key]), [])

    def test_one_sentence_twice_in_one_topic_both_copies_are_in_the_group(self):
        files = [topic("/d/a.dita", "<p>%s</p><p>%s</p>" % (WORDS, WORDS.replace("database", "database and the attachments"))),
                 topic("/d/b.dita", "<p>%s</p>" % WORDS)]
        group = duplicates.find(files)[0]
        self.assertEqual(sorted(c["location"] for c in group["copies"] if c["file"] == "d/a.dita"),
                         ["/topic[1]/body[1]/p[1]", "/topic[1]/body[1]/p[2]"])

    def test_an_image_named_by_a_key_is_listed_by_the_path_of_the_key(self):
        files = [{"path": "/d/m.ditamap", "xml": '<map><keydef keys="logo" href="i/logo.png" format="png"/>'
                                                  '<topicref href="a.dita"/></map>'},
                 topic("/d/a.dita", '<p>See this.</p><p><image keyref="logo"/></p>')]
        self.assertEqual([(g["image"], g["why"]) for g in alttext.images(files)], [("/d/i/logo.png", "none")])

    def test_an_image_over_5_mb_is_not_sent_to_the_model(self):
        import sidecar
        sidecar.LAST_FILES["/m"] = [topic("/d/a.dita", '<p>See.</p><p><image href="i/x.png"/></p>')]
        try:
            with self.assertRaises(ValueError):
                sidecar.suggest_alt({"map": "/m", "id": "i1", "media_type": "image/png",
                                     "image_base64": base64.b64encode(b"x" * (5 * 1024 * 1024 + 1)).decode()})
        finally:
            sidecar.LAST_FILES.clear()


    def test_copies_in_table_cells_are_one_group(self):
        cell = '<table><tgroup cols="2"><tbody><row><entry>Close</entry><entry colname="c2">%s</entry></row></tbody></tgroup></table>'
        files = [topic("/d/%s.dita" % n, cell % WORDS) for n in "ab"]
        self.assertEqual([(g["tag"], len(g["files"])) for g in duplicates.find(files)], [("entry", 2)])

    def test_topics_of_two_languages_are_never_one_group(self):
        files = [topic("/en/a.dita", "<p>%s</p>" % WORDS, "en-US"), topic("/en/b.dita", "<p>%s</p>" % WORDS, "en-US"),
                 topic("/fr/a.dita", "<p>%s</p>" % WORDS, "fr-FR"), topic("/content/dam/guide/fr/b.dita", "<p>%s</p>" % WORDS)]
        groups = sorted(sorted(g["files"]) for g in duplicates.find(files))
        self.assertEqual(groups, [["content/dam/guide/fr/b.dita", "fr/a.dita"], ["en/a.dita", "en/b.dita"]])
        # A folder that only looks like a code (cb, ui) is not a language.
        self.assertEqual(duplicates.language_of("content/dam/cb/ui/x.dita", None), "")

    def test_a_file_renamed_in_case_only_is_repaired_by_a_rule(self):
        import refheal
        files = [topic("/d/a.dita", '<p><xref href="Setup.dita"/></p>'), topic("/d/setup.dita", "<p>Setup</p>")]
        repo = refcheck.Repo(files=files)
        ref = repo.broken()[0]
        self.assertEqual(refheal.rule_fix(repo, ref)["target_path"], "d/setup.dita")
        # Two files that differ from the name in case only: not guessed between.
        files.append(topic("/d/SETUP.dita", "<p>Setup too</p>"))
        repo = refcheck.Repo(files=files)
        self.assertFalse(refheal.rule_fix(repo, repo.broken()[0]))

    def test_an_image_renamed_in_case_only_is_repaired_by_a_rule(self):
        import refheal
        files = [topic("/d/a.dita", '<p><image href="images/Panel.png"/></p>')]
        repo = refcheck.Repo(files=files, assets=["/d/images/panel.png"])
        self.assertEqual(refheal.rule_fix(repo, repo.broken()[0])["target_path"], "d/images/panel.png")


if __name__ == "__main__":
    unittest.main()
