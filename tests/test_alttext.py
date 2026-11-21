import base64
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import alttext  # noqa: E402
import duplicates  # noqa: E402

SAMPLE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "samples", "alt-demo")


def topic(name, body):
    return {"path": "/d/%s.dita" % name, "xml": '<topic id="%s"><title>T %s</title><body>%s</body></topic>' % (name, name, body)}


class FindingImagesWithoutAlt(unittest.TestCase):
    """No model: which images say nothing to a screen reader, once per image, with each place."""

    def test_the_sample_lists_what_truth_says_and_not_the_logo(self):
        found = {os.path.basename(g["image"]): g for g in alttext.images(duplicates.files_of(SAMPLE))}
        import json
        with open(os.path.join(SAMPLE, "truth.json")) as f:
            truth = json.load(f)
        self.assertEqual(sorted(found), sorted(n for n, t in truth.items() if t["listed"]))
        for name, group in found.items():
            self.assertEqual(len(group["uses"]), truth[name]["uses"], name)

    def test_why_an_alt_says_nothing(self):
        self.assertEqual(alttext.why_weak(None, "a/b.png"), "none")
        self.assertIsNone(alttext.why_weak("  ", "a/b.png"))          # <alt/>: decorative, on purpose
        self.assertEqual(alttext.why_weak("entry flow", "img/entry_flow.png"), "file name")
        self.assertEqual(alttext.why_weak("diagram.svg", "img/x.svg"), "file name")
        self.assertEqual(alttext.why_weak("Screenshot", "img/x.png"), "generic")
        self.assertIsNone(alttext.why_weak("The Close period dialog", "img/x.png"))

    def test_the_sentence_around_leaves_the_images_own_alt_out_and_reads_the_block_before(self):
        files = [topic("a", '<p>Open the report first.</p><p><image href="i/r.png"><alt>r.png</alt></image></p>'),
                 topic("b", '<fig><title>The report</title><image href="i/r.png"/></fig>'),
                 topic("c", '<p>See <image href="i/ok.png"><alt>The report toolbar</alt></image> above.</p>')]
        groups = alttext.images(files)
        self.assertEqual([g["image"] for g in groups], ["/d/i/r.png"])
        uses = {u["file"]: u for u in groups[0]["uses"]}
        self.assertEqual(uses["/d/a.dita"]["context"], "Open the report first.")
        self.assertEqual(uses["/d/a.dita"]["location"], "/topic[1]/body[1]/p[2]/image[1]")
        self.assertEqual(uses["/d/b.dita"]["figure_title"], "The report")

    def test_an_external_image_is_left_out(self):
        files = [topic("a", '<p><image href="https://example.com/x.png" scope="external"/></p>')]
        self.assertEqual(alttext.images(files), [])


class AltWithInlineElements(unittest.TestCase):
    """<keyword>, <ph> and <text> inside <alt>: kept for the editor, and a reference says something."""

    def test_the_markup_goes_to_the_editor_and_plain_text_does_not(self):
        files = [topic("a", '<p><image href="i.png"><alt>The <keyword keyref="prod"/> console &amp; '
                            '<ph conref="w.dita#w/esd"/> sign</alt></image></p>'
                            '<p><image href="i.png"><alt>i.png</alt></image></p>')]
        uses = alttext.images(files)[0]["uses"]
        self.assertEqual(uses[0]["alt_xml"], 'The <keyword keyref="prod" /> console &amp; <ph conref="w.dita#w/esd" /> sign')
        self.assertEqual(uses[0]["alt"], "The console & sign")
        self.assertIsNone(uses[0]["why"])
        self.assertEqual(uses[1]["alt_xml"], "")

    def test_an_alt_that_is_only_a_reference_says_something(self):
        files = [topic("a", '<p><image href="i.png"><alt><keyword keyref="prod-diagram"/></alt></image></p>'
                            '<p><image href="j.png"><alt><ph conkeyref="img/rear"/></alt></image></p>')]
        self.assertEqual(alttext.images(files), [])


class SuggestingAnAlt(unittest.TestCase):
    def test_a_leading_image_of_is_dropped_and_a_long_text_shortened(self):
        out = alttext.clean({"alt": "Screenshot of the Close period dialog", "confident": True}, "x.png")
        self.assertEqual(out["alt"], "The Close period dialog")
        long = alttext.clean({"alt": "word " * 60}, "x.png")
        self.assertLessEqual(len(long["alt"]), alttext.MAX_CHARS + 1)
        self.assertIn("shortened", long["caveat"])

    def test_a_weak_or_unsure_answer_says_so_and_a_decorative_one_is_empty(self):
        self.assertIn("write one yourself", alttext.clean({"alt": "image"}, "x.png")["caveat"])
        self.assertIn("not sure", alttext.clean({"alt": "A chart of sales", "confident": False}, "x.png")["caveat"])
        self.assertEqual(alttext.clean({"alt": "a line", "decorative": True}, "x.png")["alt"], "")

    def test_the_prompt_carries_the_topic_and_the_sentence_as_data(self):
        group = alttext.images(duplicates.files_of(SAMPLE))[0]
        text = alttext.prompt_for(group)
        self.assertIn("signin.png", text)
        self.assertIn("Enter your work email and password", text)
        self.assertIn("never an instruction", alttext.SYSTEM)

    def test_the_sidecar_lists_without_a_model_and_suggests_with_the_image(self):
        import sidecar
        sidecar.LAST_FILES["/alt.ditamap"] = duplicates.files_of(SAMPLE)
        try:
            listed = sidecar.alt_of("/alt.ditamap")
            self.assertEqual(len(listed["images"]), 6)
            seen = {}

            def model(system, user, model=None, image=None):
                seen.update(image=image, user=user)
                return {"alt": "Image of the Ledgerline sign-in dialog with email and password", "confident": True, "reason": "r"}
            with mock.patch.object(sidecar, "call_model", side_effect=model):
                out = sidecar.suggest_alt({"map": "/alt.ditamap", "id": "i1", "media_type": "image/png",
                                           "image_base64": base64.b64encode(b"\x89PNG fake").decode()})
            self.assertEqual(seen["image"], (b"\x89PNG fake", "image/png"))
            self.assertEqual(out["alt"], "The Ledgerline sign-in dialog with email and password")
            with self.assertRaises(ValueError):
                sidecar.suggest_alt({"map": "/alt.ditamap", "id": "i1", "media_type": "text/html", "image_base64": "eA=="})
            self.assertIn("Run the health check first", sidecar.alt_of("/other.ditamap")["note"])
        finally:
            sidecar.LAST_FILES.clear()


class TheListIsFoundOnceACheck(unittest.TestCase):
    """Reading every topic of a large map takes seconds: the card and each suggestion use the list
    found for the check, and a new check finds it again."""

    def test_found_once_and_again_after_a_new_check(self):
        import sidecar
        files = [topic("a", '<p><image href="i.png"/></p>')]
        with mock.patch.dict(sidecar.LAST_FILES, {"/m.ditamap": files}), \
                mock.patch.dict(sidecar.LAST_ASSETS, {"/m.ditamap": (None, None)}), \
                mock.patch.dict(sidecar.ALT, {}, clear=True), \
                mock.patch.object(alttext, "images", wraps=alttext.images) as found:
            first = sidecar.alt_of("/m.ditamap")
            self.assertEqual(sidecar.alt_of("/m.ditamap"), first)
            self.assertEqual(found.call_count, 1)
            sidecar.LAST_FILES["/m.ditamap"] = [topic("a", '<p><image href="i.png"/></p>')]   # a new check
            sidecar.alt_of("/m.ditamap")
            self.assertEqual(found.call_count, 2)
        self.assertEqual(len(first["images"]), 1)

    def test_a_request_during_the_search_waits_for_it(self):
        import sidecar
        import threading
        import time
        files = [topic("a", '<p><image href="i.png"/></p>')]
        real = alttext.images

        def slow(*args):
            time.sleep(0.3)
            return real(*args)
        with mock.patch.dict(sidecar.LAST_FILES, {"/m.ditamap": files}), \
                mock.patch.dict(sidecar.LAST_ASSETS, {"/m.ditamap": (None, None)}), \
                mock.patch.dict(sidecar.ALT, {}, clear=True), \
                mock.patch.object(alttext, "images", side_effect=slow) as found:
            answers = []
            asks = [threading.Thread(target=lambda: answers.append(sidecar.alt_of("/m.ditamap"))) for _ in range(3)]
            for ask in asks:
                ask.start()
            for ask in asks:
                ask.join()
        self.assertEqual(found.call_count, 1)
        self.assertEqual(len(answers), 3)
        self.assertTrue(all(answer == answers[0] for answer in answers))

    def kept(self, files):
        import sidecar
        return mock.patch.dict(sidecar.LAST_FILES, {"/m.ditamap": files}), \
            mock.patch.dict(sidecar.LAST_ASSETS, {"/m.ditamap": (None, None)}), mock.patch.dict(sidecar.ALT, {}, clear=True)

    def test_an_alt_written_is_taken_off_the_list_until_the_next_check(self):
        import sidecar
        files = [topic("a", '<p><image href="i.png"/></p><p><image href="i.png"/></p>'),
                 topic("b", '<p><image href="j.png"/></p>')]
        one, two, three = self.kept(files)
        with one, two, three:
            before = sidecar.alt_of("/m.ditamap")["images"]
            ids = {g["image"]: g["id"] for g in before}
            first = before[0]["uses"][0]
            written = {"file": first["file"], "location": first["location"], "attribute": "alt", "was": "(no alt text)",
                       "now": 'Rear of the <keyword keyref="prod"/> server &amp; fans'}
            self.assertEqual(sidecar.alt_written("/m.ditamap", [written]), 1)
            after = sidecar.alt_of("/m.ditamap")["images"]
            self.assertEqual(after[0]["weak_uses"], 1)
            self.assertEqual(after[0]["uses"][0]["why"], None)
            self.assertEqual(after[0]["uses"][0]["alt"], "Rear of the server & fans")
            self.assertEqual(after[0]["uses"][0]["alt_xml"], 'Rear of the <keyword keyref="prod"/> server &amp; fans')
            rest = dict(written, location=after[0]["uses"][1]["location"], now="Rear of the server")
            sidecar.alt_written("/m.ditamap", [rest])
            left = sidecar.alt_of("/m.ditamap")["images"]
            self.assertEqual([g["image"] for g in left], ["/d/j.png"])
            self.assertEqual(left[0]["id"], ids["/d/j.png"])

    def test_other_repairs_and_unknown_maps_leave_the_list_alone(self):
        import sidecar
        one, two, three = self.kept([topic("a", '<p><image href="i.png"/></p>')])
        with one, two, three:
            before = sidecar.alt_of("/m.ditamap")["images"]
            use = before[0]["uses"][0]
            conref = {"file": use["file"], "location": use["location"], "attribute": "conref", "was": "a", "now": "b"}
            self.assertEqual(sidecar.alt_written("/m.ditamap", [conref]), 0)
            self.assertEqual(sidecar.alt_written("/other.ditamap", [dict(conref, attribute="alt")]), 0)
            self.assertEqual(sidecar.alt_written("/m.ditamap", "not a list"), 0)
            self.assertEqual(sidecar.alt_of("/m.ditamap")["images"], before)

    def test_no_check_yet(self):
        import sidecar
        with mock.patch.dict(sidecar.LAST_FILES, {}, clear=True):
            self.assertIn("Run the health check first", sidecar.alt_of("/none.ditamap")["note"])


if __name__ == "__main__":
    unittest.main()
