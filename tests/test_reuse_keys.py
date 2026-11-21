import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import reuse  # noqa: E402

NOTE = "Back up the ledger before you close the period."


def entry(path, xml):
    return {"path": path, "xml": xml}


class SharedPiecesPulledByKey(unittest.TestCase):
    """A team that reuses by key: its pieces are found, and new ones go by key."""

    def files(self, conkeyref=True):
        ref = '<p conkeyref="notes/p_backup"/>' if conkeyref else "<p>Other text here.</p>"
        return [entry("d/guide.ditamap", '<map><keydef keys="notes" href="reuse/notes.dita"/>'
                                         '<keydef keys="shared-content" href="elsewhere.dita"/><topicref href="a.dita"/></map>'),
                entry("d/reuse/notes.dita",
                      '<topic id="notes_topic"><title>N</title><body><p id="p_backup">%s</p></body></topic>' % NOTE),
                entry("d/a.dita", '<topic id="a"><title>A</title><body>%s</body></topic>' % ref)]

    def test_a_piece_pulled_by_conkeyref_is_an_existing_piece(self):
        pieces = reuse.shared_pieces(self.files())
        self.assertEqual(pieces[("p", reuse._key(NOTE))], {"path": "d/reuse/notes.dita", "topic": "notes_topic", "id": "p_backup"})

    def test_keys_are_used_when_the_topics_already_pull_by_key(self):
        plan = reuse.key_plan(self.files(), "/d/guide.ditamap")
        self.assertTrue(plan["use"])
        self.assertEqual(plan["maps"], ["/d/guide.ditamap"])
        # "shared-content" names another file in this map: the new key takes a free name.
        self.assertEqual(plan["keys"]["/d/reuse/shared-content.dita"], "shared-content-2")
        self.assertEqual(plan["keys"]["/d/reuse/shared-steps.dita"], "shared-steps")
        self.assertFalse(reuse.key_plan(self.files(conkeyref=False), "/d/guide.ditamap")["use"])

    def test_a_key_inside_a_key_scope_is_not_the_shared_topics_key(self):
        scoped = entry("d/sub.ditamap", '<map><topicgroup keyscope="old"><keydef keys="old-notes" '
                                        'href="reuse/shared-content.dita"/></topicgroup></map>')
        plan = reuse.key_plan(self.files() + [scoped], "/d/guide.ditamap")
        self.assertEqual(plan["keys"]["/d/reuse/shared-content.dita"], "shared-content-2")

    def test_a_key_the_map_already_gives_the_shared_topic_is_kept(self):
        files = self.files() + [entry("d/sub.ditamap", '<map><keydef keys="common" href="reuse/shared-content.dita"/></map>')]
        self.assertEqual(reuse.key_plan(files, "/d/guide.ditamap")["keys"]["/d/reuse/shared-content.dita"], "common")


if __name__ == "__main__":
    unittest.main()
