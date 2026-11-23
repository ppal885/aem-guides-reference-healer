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


def topic(n, body):
    return {"path": "d/s%d.dita" % n, "xml": '<topic id="s%d"><title>S%d</title><body>%s</body></topic>' % (n, n, body)}


class Spellings(unittest.TestCase):
    """One name, one spelling: the names the topics write more than one way."""

    def test_a_name_written_with_a_space_and_with_a_dash_is_found_most_used_first(self):
        found = names.spellings([
            topic(1, '<p>The <keyword>HX-200</keyword> holds the cache. Each HX-200 has two.</p>'),
            topic(2, '<p>Install the HX 200 first.</p>'),
            topic(3, '<p>Then the HX-200 again.</p>')])
        self.assertEqual(len(found), 1)
        one = found[0]
        self.assertEqual((one["main"], one["case_only"], one["places"], one["topics"]), ("HX-200", False, 1, 1))
        self.assertEqual([(f["form"], f["count"], f["files"]) for f in one["forms"]],
                         [("HX-200", 3, ["/d/s1.dita", "/d/s3.dita"]), ("HX 200", 1, ["/d/s2.dita"])])

    def test_names_that_differ_only_in_capitals_come_after_and_say_so(self):
        found = names.spellings([
            topic(1, '<p><keyword>HX-200</keyword> and HX 200.</p>'),
            topic(2, '<p><wintitle>System Console</wintitle>, System Console, System Console.</p>'),
            topic(3, '<p>Open the system console.</p><p><tm>System console</tm></p>')])
        self.assertEqual([(s["main"], s["case_only"]) for s in found], [("HX-200", False), ("System Console", True)])
        self.assertEqual([s["id"] for s in found], ["s0", "s1"])

    def test_code_comments_attributes_and_keys_to_press_are_not_prose(self):
        found = names.spellings([
            topic(1, '<p><keyword>HX-200</keyword></p>'),
            topic(2, '<codeblock>HX 200</codeblock><!-- HX 200 --><p outputclass="HX 200">x</p>'),
            topic(3, '<p><uicontrol>Enter</uicontrol> or <uicontrol>ENTER</uicontrol></p>')])
        self.assertEqual(found, [])

    def test_a_short_word_or_one_without_a_digit_or_capital_inside_is_not_a_name(self):
        found = names.spellings([topic(1, '<p><keyword>Log in</keyword> or <keyword>Login</keyword>, '
                                          '<keyword>V06</keyword> or <keyword>v06</keyword></p>')])
        self.assertEqual(found, [])

    def test_a_spelling_inside_a_longer_name_is_not_counted(self):
        found = names.spellings([topic(1, '<p><keyword>HX-200</keyword> and <keyword>HX 200</keyword></p>'),
                                 topic(2, '<p>The HX-200X and HX 200-B are other machines.</p>')])
        self.assertEqual([(f["form"], f["count"]) for f in found[0]["forms"]], [("HX 200", 1), ("HX-200", 1)])

    def test_placeholders_and_names_in_code_are_not_spellings(self):
        found = names.spellings([
            topic(1, '<p><keyword>1xxx-xxxx</keyword> and 1xxx xxxx</p>'),
            topic(2, '<p><wintitle>Modify Group</wintitle>; Modify Group; call modifyGroup or modify_group.</p>')])
        self.assertEqual(found, [])

    def test_a_one_letter_prefix_like_pseries_is_still_a_name(self):
        found = names.spellings([topic(1, '<p><keyword>pSeries</keyword> pSeries</p>'), topic(2, '<p>P-Series</p>')])
        self.assertEqual([f["form"] for f in found[0]["forms"]], ["pSeries", "P-Series"])


class CodeThatClosesItself(unittest.TestCase):
    def test_prose_after_an_empty_code_element_is_read(self):
        spelled = names.spellings([topic(1, '<p><keyword>HX-200</keyword></p>'),
                                   topic(2, '<p>Open <filepath keyref="dir"/> first.</p><p>The HX 200 runs.</p>'
                                            '<p>Edit <filepath>conf.ini</filepath>.</p>')])
        self.assertEqual([(f["form"], f["count"]) for f in spelled[0]["forms"]], [("HX-200", 1), ("HX 200", 1)])


class SpellingsLine(unittest.TestCase):
    """The plan's line, which the editor counts from."""

    def test_the_line_names_the_count_the_worst_name_and_the_capitals(self):
        import refplan
        spelled = names.spellings([topic(1, '<p><keyword>HX-200</keyword> HX-200</p>'),
                                   topic(2, '<p>HX 200</p><p><wintitle>System Console</wintitle> <tm>System console</tm></p>')])
        self.assertEqual(refplan.spellings_line(spelled),
                         'Names written two ways: 2 names are written more than one way: 1 in 1 place, such as "HX 200" '
                         'for "HX-200" (1 place in 1 topic), and 1 only in capital letters. Open "Names written two ways" '
                         'to make each one spelling.')

    def test_the_example_counts_only_its_own_spelling(self):
        import refplan
        spelled = names.spellings([topic(1, '<p><keyword>HX-200</keyword> HX-200 HX-200</p>'),
                                   topic(2, '<p>HX200 and HX200</p>'), topic(3, '<p>HX 200</p>')])
        self.assertIn('such as "HX200" for "HX-200" (2 places in 1 topic)', refplan.spellings_line(spelled))

    def test_the_sidecar_lists_the_names_with_the_titles_of_their_topics(self):
        sidecar.LAST_FILES["/m.ditamap"] = [topic(1, '<p><keyword>HX-200</keyword> HX-200</p>'), topic(2, '<p>HX 200</p>')]
        try:
            answer = sidecar.spellings_of("/m.ditamap")
        finally:
            del sidecar.LAST_FILES["/m.ditamap"]
        self.assertEqual(answer["names"][0]["main"], "HX-200")
        self.assertEqual(answer["titles"], {"/d/s1.dita": "S1", "/d/s2.dita": "S2"})
        self.assertEqual(sidecar.spellings_of("/other.ditamap")["names"], [])

    def test_spellings_written_over_leave_the_list(self):
        sidecar.LAST_FILES["/m.ditamap"] = [topic(1, '<p><keyword>HX-200</keyword> HX-200</p>'),
                                            topic(2, '<p>HX 200 and HX 200</p>'), topic(3, '<p>HX200</p>')]
        try:
            self.assertEqual(sidecar.spellings_of("/m.ditamap")["names"][0]["places"], 3)
            sidecar.spellings_written("/m.ditamap", [{"file": "/d/s2.dita", "attribute": "name", "was": "HX 200", "now": "HX-200"},
                                                     {"file": "/d/s9.dita", "attribute": "alt", "was": "HX200", "now": "x"}])
            left = sidecar.spellings_of("/m.ditamap")["names"][0]
            self.assertEqual((left["places"], [f["form"] for f in left["forms"]]), (1, ["HX-200", "HX200"]))
            sidecar.spellings_written("/m.ditamap", [{"file": "/d/s3.dita", "attribute": "name", "was": "HX200", "now": "HX-200"}])
            self.assertEqual(sidecar.spellings_of("/m.ditamap")["names"], [])
        finally:
            del sidecar.LAST_FILES["/m.ditamap"]
            sidecar.SPELLED.pop("/m.ditamap", None)


class SpellingsWhereTheyCanBeWritten(unittest.TestCase):
    """What is counted is what the editor can write: whole in one text, and once."""

    def test_a_name_split_by_markup_is_not_counted(self):
        found = names.spellings([topic(1, '<p><keyword>HX-200</keyword> and HX-200</p>'),
                                 topic(2, '<p><tm>HX</tm> 200 and <?pi HX 200?><![CDATA[HX 200]]></p>')])
        self.assertEqual(found, [])

    def test_the_longest_name_wins_at_one_place(self):
        found = names.spellings([
            topic(1, '<p><keyword>HX-200</keyword> and <keyword>HX-200 Gateway</keyword>. HX-200.</p>'),
            topic(2, '<p>HX 200 Gateway, and HX 200 alone.</p>')])
        self.assertEqual([(s["main"], [(f["form"], f["count"]) for f in s["forms"]]) for s in found],
                         [("HX-200", [("HX-200", 2), ("HX 200", 1)]), ("HX-200 Gateway", [("HX-200 Gateway", 1), ("HX 200 Gateway", 1)])])

    def test_numbers_split_another_way_are_other_names_not_other_spellings(self):
        found = names.spellings([
            topic(1, '<p><keyword>Atlas 1.10</keyword> ships. Atlas 1.10 again. <keyword>Port 8080</keyword></p>'),
            topic(2, '<p><keyword>Atlas 11.0</keyword> is next, on Port 80-80. Atlas 1-10 is a typo.</p>')])
        self.assertEqual([(s["main"], [f["form"] for f in s["forms"]]) for s in found], [])
        found = names.spellings([topic(1, '<p><keyword>HX-200 R4.2</keyword></p>'), topic(2, '<p>HX 200 R4.2</p>')])
        self.assertEqual([f["form"] for f in found[0]["forms"]], ["HX-200 R4.2", "HX 200 R4.2"])


class AfterAWrite(unittest.TestCase):
    """What the list says after an author wrote some topics: the author's choice is the name now."""

    SPELLED = [{"id": "s0", "main": "HX-200", "case_only": False, "places": 6, "topics": 3, "inside": [], "forms": [
        {"form": "HX-200", "count": 10, "files": ["/a", "/b", "/c", "/d", "/e"],
         "per_topic": {"/a": 2, "/b": 2, "/c": 2, "/d": 2, "/e": 2}},
        {"form": "HX 200", "count": 6, "files": ["/f", "/g", "/h"], "per_topic": {"/f": 2, "/g": 2, "/h": 2}}]}]

    def test_the_less_used_spelling_an_author_chose_becomes_the_main_one_with_the_places_written(self):
        written = [(path, "HX-200", "HX 200") for path in ("/a", "/b", "/c", "/d")]
        left = names.without(self.SPELLED, written)[0]
        self.assertEqual((left["main"], [(f["form"], f["count"]) for f in left["forms"]], left["places"], left["topics"]),
                         ("HX 200", [("HX 200", 14), ("HX-200", 2)], 2, 1))

    def test_a_spelling_written_back_counts_where_it_is_now(self):
        written = [("/a", "HX-200", "HX 200"), ("/a", "HX 200", "HX-200"), ("/f", "HX 200", "HX-200")]
        left = names.without(self.SPELLED, written)[0]
        self.assertEqual([(f["form"], f["count"]) for f in left["forms"]], [("HX-200", 12), ("HX 200", 4)])

    def test_an_author_who_writes_a_topic_one_way_then_back_leaves_it_saying_the_last(self):
        spelled = [dict(self.SPELLED[0], forms=[
            {"form": "HX-200", "count": 3, "files": ["/t", "/v"], "per_topic": {"/t": 2, "/v": 1}},
            {"form": "HX 200", "count": 1, "files": ["/t"], "per_topic": {"/t": 1}}])]
        self.assertEqual(names.without(spelled, [("/t", "HX-200", "HX 200"), ("/t", "HX 200", "HX-200")]), [])

    def test_file_names_paths_addresses_and_code_words_are_not_names(self):
        found = names.spellings([topic(1, '<p><keyword>HX-200</keyword> HX-200. Run HX200_setup.exe from '
                                          'https://example.com/HX200/ or https://x.com/?model=HX200 or page.html#HX200 or open HX200.pdf, setup_HX200 or '
                                          '<option>HX200</option><apiname>HX200</apiname>. Then HX200, and HX200/CX9.</p>')])
        self.assertEqual([(f["form"], f["count"]) for f in found[0]["forms"]], [("HX-200", 2), ("HX200", 2)])

    def test_each_name_lists_the_longer_names_found_around_its_spellings_as_written(self):
        found = names.spellings([topic(1, '<p><keyword>HX-200</keyword> and <keyword>HX 200 Gateway</keyword>. '
                                          'The HX 200 Gateway runs HX 200. HX-200, the HX 200 GATEWAY.</p>')])
        self.assertEqual((found[0]["main"], found[0]["inside"]), ("HX-200", ["HX 200 GATEWAY", "HX 200 Gateway"]))
