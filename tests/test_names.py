import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import duplicates  # noqa: E402
import names  # noqa: E402
import sidecar  # noqa: E402

MAP = ('<map><keydef keys="product"><topicmeta><keywords><keyword>Atlas Cloud</keyword></keywords></topicmeta></keydef>'
       '<topicref href="a.dita" keys="intro"><topicref href="b.dita" keys="setup"/></topicref>'
       '<keydef keys="cli" href="c.dita"><topicmeta><linktext>atlasctl</linktext></topicmeta></keydef>'
       '<topicgroup keyscope="admin"><keydef keys="console"><topicmeta><keywords><keyword>Admin Console</keyword>'
       '</keywords></topicmeta></keydef></topicgroup></map>')
OLD_MAP = '<map><keydef keys="cli-name"><topicmeta><keywords><keyword>atlasctl</keyword></keywords></topicmeta></keydef></map>'


def files(*topics):
    return [{"path": "d/m.ditamap", "xml": MAP, "previous": [OLD_MAP]},
            {"path": "d/a.dita", "xml": '<topic id="a"><title>Getting started</title></topic>'},
            {"path": "d/b.dita", "id": "GUID-b", "xml": '<topic id="b"><title>Set up the account</title>'
             '<body><section id="limits"><title>Account limits</title></section></body></topic>'}] + [
        {"path": "d/t%d.dita" % n, "xml": '<topic id="t%d"><title>T</title><body>%s</body></topic>' % (n, body)}
        for n, body in enumerate(topics, 1)]


class KeyNames(unittest.TestCase):
    """The name a reader sees where a topic says something by key."""

    def test_every_kind_of_key_definition_gets_its_name(self):
        found = names.key_names(files())
        self.assertEqual(found["product"], "Atlas Cloud")               # keyword
        self.assertEqual(found["cli"], "atlasctl")                       # link text
        self.assertEqual((found["intro"], found["setup"]), ("Getting started", "Set up the account"))   # the topic's title
        self.assertEqual((found["console"], found["admin.console"]), ("Admin Console", "Admin Console"))  # in a key scope
        self.assertEqual(found["cli-name"], "atlasctl")                  # gone from the map, named by its earlier version

    def test_a_link_to_a_section_gone_in_this_version_shows_its_earlier_title(self):
        now = files()
        now[2]["previous"] = [now[2]["xml"].replace('</body>', '<section id="old"><title>Old limits</title></section></body>')]
        links = names.link_titles(now)
        self.assertEqual((links["d/b.dita#b/old"], links["d/b.dita#b/limits"]), ("Old limits", "Account limits"))

    def test_the_text_shows_names_titles_and_says_what_is_unknown(self):
        found, links = names.key_names(files()), names.link_titles(files())
        text = "Use ⟦cli-name⟧ , see ⟦@d/b.dita#b/limits⟧ . Ask ⟦nope⟧ ; ⟦*⟧"
        self.assertEqual(names.shown(text, found, links), "Use atlasctl, see Account limits. Ask [nope]; [varies]")


class RepeatedTextAsReadersSeeIt(unittest.TestCase):
    """The Repeated Text card shows a copy's words with the names its keys and links show."""

    def group_of(self, *bodies):
        all_files = files(*bodies)
        group = duplicates.find(all_files)[0]
        group.update(id="g1", decision="share")
        return sidecar._compact(group, names.key_names(all_files), names.link_titles(all_files))

    def test_a_key_and_an_empty_link_are_named_and_the_compared_text_stays_as_it_was(self):
        body = ('<p>Install <keyword keyref="cli"/> before you start, then read <xref href="b.dita#b/limits"/> '
                'for every account in <ph keyref="product"/>.</p>')
        out = self.group_of(body, body)
        self.assertEqual(out["shown"], "Install atlasctl before you start, then read Account limits for every account in Atlas Cloud.")
        self.assertEqual(out["text"], "Install before you start, then read for every account in .")
        self.assertEqual(out["variants"][0]["shown"], out["shown"])

    def test_copies_that_say_different_keys_show_varies(self):
        say = '<p>Install <keyword keyref="%s"/> before you start the long migration of every account.</p>'
        out = self.group_of(say % "cli", say % "product")
        self.assertIn("[varies]", out["shown"])


if __name__ == "__main__":
    unittest.main()
