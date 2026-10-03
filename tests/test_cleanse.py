import unittest

from html_cleanse import cleanse


class TestEntityAndEvidence(unittest.TestCase):
    def test_spec_example(self):
        result = cleanse("A&amp;<b>中</b>")
        self.assertEqual(result.text, "A&中")
        self.assertEqual(result.evidence(1, 3), [(1, 6), (9, 12)])

    def test_adjacent_ranges_merge(self):
        result = cleanse("A&amp;<b>中</b>")
        self.assertEqual(result.evidence(0, 3), [(0, 6), (9, 12)])

    def test_charref_maps_whole_entity(self):
        result = cleanse("&#x4E2d;")
        self.assertEqual(result.text, "中")
        self.assertEqual(result.evidence(0, 1), [(0, 8)])

    def test_multi_codepoint_entity(self):
        result = cleanse("&acE;")
        self.assertEqual(len(result.text), 2)
        self.assertEqual(result.evidence(0, 1), [(0, 5)])
        self.assertEqual(result.evidence(1, 2), [(0, 5)])

    def test_invalid_entity_stays_literal(self):
        result = cleanse("&notanentity; &amp x")
        self.assertEqual(result.text, "&notanentity; &amp x")

    def test_out_of_range_query(self):
        result = cleanse("ab")
        with self.assertRaises(IndexError):
            result.evidence(1, 3)


class TestWhitespaceMerging(unittest.TestCase):
    def test_merge_across_inline_tags(self):
        result = cleanse("a <b> <i> </i></b> c")
        self.assertEqual(result.text, "a c")
        self.assertEqual(result.evidence(1, 2), [(1, 2), (5, 6), (9, 10), (18, 19)])

    def test_merge_across_hidden_subtree(self):
        result = cleanse("x <span hidden>drop</span> y")
        self.assertEqual(result.text, "x y")
        self.assertEqual(result.evidence(1, 2), [(1, 2), (26, 27)])
        self.assertEqual(result.evidence(0, 3), [(0, 2), (26, 28)])

    def test_block_separators_become_newline(self):
        result = cleanse("<p>a</p> <div>b</div><br><li>c</li>")
        self.assertEqual(result.text, "a\nb\nc")

    def test_separator_only_segment(self):
        result = cleanse("a<div>b")
        self.assertEqual(result.text, "a\nb")

    def test_trim_leading_and_trailing(self):
        self.assertEqual(cleanse("  a  ").text, "a")
        self.assertEqual(cleanse("<p>a</p>").text, "a")
        self.assertEqual(cleanse(" \t\r\n\f").text, "")

    def test_unicode_whitespace_preserved(self):
        self.assertEqual(cleanse("a　b").text, "a　b")


class TestDeletion(unittest.TestCase):
    def test_script_style_template_comment(self):
        self.assertEqual(cleanse("a<script>1</script>b").text, "ab")
        self.assertEqual(cleanse("a<style>.x{}</style>b").text, "ab")
        self.assertEqual(cleanse("a<template><div>t</div></template>b").text, "ab")
        self.assertEqual(cleanse("a<!--x-->b").text, "ab")

    def test_script_raw_text_not_parsed(self):
        self.assertEqual(cleanse("a<script>x</div>y</script>b").text, "ab")

    def test_no_space_for_deleted_content(self):
        result = cleanse("ab<script>long</script>cd")
        self.assertEqual(result.text, "abcd")
        self.assertEqual(result.evidence(0, 4), [(0, 2), (23, 25)])


class TestMedia(unittest.TestCase):
    def test_media_inside_collapsed_whitespace(self):
        result = cleanse("a <img> b")
        self.assertEqual(result.text, "a b")
        self.assertEqual([m.anchor for m in result.media], [2])
        self.assertEqual((result.media[0].byte_start, result.media[0].byte_end), (2, 7))

    def test_media_inside_separator_segment(self):
        result = cleanse("a <br> <img> b")
        self.assertEqual(result.text, "a\nb")
        self.assertEqual([m.anchor for m in result.media], [2])

    def test_empty_body_anchors_zero(self):
        for html in ("<img>", " <img> ", "<video><img></video>"):
            result = cleanse(html)
            self.assertEqual(result.text, "")
            self.assertTrue(result.media)
            self.assertTrue(all(m.anchor == 0 for m in result.media), html)

    def test_trailing_trimmed_whitespace_media(self):
        result = cleanse("a <img> ")
        self.assertEqual(result.text, "a")
        self.assertEqual([m.anchor for m in result.media], [1])

    def test_video_ignores_children(self):
        result = cleanse("<video><source><img></video>x")
        self.assertEqual(result.text, "x")
        self.assertEqual(len(result.media), 1)
        self.assertEqual(result.media[0].anchor, 0)

    def test_same_anchor_keeps_source_order(self):
        result = cleanse("<img><img>")
        self.assertEqual([m.anchor for m in result.media], [0, 0])
        self.assertLess(result.media[0].byte_start, result.media[1].byte_start)

    def test_hidden_media_dropped(self):
        result = cleanse("<div hidden><img></div>a")
        self.assertEqual(result.text, "a")
        self.assertEqual(result.media, [])


class TestInput(unittest.TestCase):
    def test_bytes_input(self):
        result = cleanse("中".encode("utf-8"))
        self.assertEqual(result.text, "中")
        self.assertEqual(result.evidence(0, 1), [(0, 3)])


if __name__ == "__main__":
    unittest.main()
