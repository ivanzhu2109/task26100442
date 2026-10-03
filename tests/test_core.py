import pytest

from html_evidence import sanitize


class TestEvidenceLookup:
    def test_spec_example_entity_and_inline_tag(self):
        r = sanitize("A&amp;<b>中</b>")
        assert r.text == "A&中"
        assert r.lookup(1, 3) == [(1, 6), (9, 12)]

    def test_lookup_merges_only_adjacent(self):
        r = sanitize("ab<i></i>cd")
        assert r.text == "abcd"
        # 普通内联标签不算证据，两侧相邻字符各自合并
        assert r.lookup(0, 4) == [(0, 2), (9, 11)]

    def test_lookup_single_char(self):
        r = sanitize("x&amp;y")
        assert r.lookup(1, 2) == [(1, 6)]
        assert r.lookup(0, 1) == [(0, 1)]
        assert r.lookup(2, 3) == [(6, 7)]

    def test_lookup_empty_range(self):
        r = sanitize("abc")
        assert r.lookup(1, 1) == []

    def test_lookup_out_of_range(self):
        r = sanitize("abc")
        with pytest.raises(ValueError):
            r.lookup(0, 4)
        with pytest.raises(ValueError):
            r.lookup(-1, 2)

    def test_multi_codepoint_entity(self):
        # &NotEqualTilde; 解码为两个码点，均对应整个实体字节范围
        r = sanitize("x&NotEqualTilde;y")
        assert r.text == "x≂̸y"
        assert len(r.text) == 4
        assert r.lookup(1, 3) == [(1, 16)]

    def test_numeric_entity(self):
        r = sanitize("&#x4E2D;&#25991;")
        assert r.text == "中文"
        assert r.lookup(0, 2) == [(0, 16)]


class TestWhitespaceCollapsing:
    def test_merge_across_inline_tags_and_hidden_subtree(self):
        s = "a <b> </b> <span hidden>x</span>  b"
        r = sanitize(s)
        assert r.text == "a b"
        # 合并后的空格对应全部参与合并的原始空白，跳过标签与隐藏子树
        assert r.lookup(1, 2) == [(1, 2), (5, 6), (10, 11), (32, 34)]

    def test_hidden_subtree_deleted_without_separator(self):
        s = "a <div hidden>x</div> b"
        r = sanitize(s)
        assert r.text == "a b"
        # 被删除元素整体无正文对应位置；证据不跨过被删除的字节
        assert r.lookup(1, 2) == [(1, 2), (21, 22)]

    def test_block_tags_and_br_form_newline(self):
        r = sanitize("<p>a</p><p>b<br>c</p>")
        assert r.text == "a\nb\nc"

    def test_li_separator(self):
        r = sanitize("<ul><li>a</li><li>b</li></ul>")
        assert r.text == "a\nb"

    def test_leading_trailing_trim(self):
        r = sanitize(" \t\r\n\f a \n<p></p> ")
        assert r.text == "a"

    def test_nbsp_preserved(self):
        r = sanitize("a&nbsp; b")
        assert r.text == "a  b"

    def test_separator_evidence_includes_tag_ranges(self):
        s = "a <br> b"
        r = sanitize(s)
        assert r.text == "a\nb"
        assert r.lookup(1, 2) == [(1, 7)]


class TestMedia:
    def test_media_inside_collapsed_whitespace(self):
        r = sanitize("a <img> b")
        assert r.text == "a b"
        assert [(m.anchor, m.tag) for m in r.media] == [(2, "img")]

    def test_media_between_text_no_whitespace(self):
        r = sanitize("a<img>b")
        assert r.text == "ab"
        assert [m.anchor for m in r.media] == [1]

    def test_media_in_trimmed_leading_and_trailing_whitespace(self):
        r = sanitize("  <img> a <video></video>  ")
        assert r.text == "a"
        assert [(m.anchor, m.tag) for m in r.media] == [(0, "img"), (1, "video")]

    def test_empty_text_media_anchor_zero(self):
        r = sanitize("<img><video></video>")
        assert r.text == ""
        assert [(m.anchor, m.tag) for m in r.media] == [(0, "img"), (0, "video")]

    def test_same_anchor_preserves_source_order(self):
        r = sanitize("<img><img><img>")
        assert [m.anchor for m in r.media] == [0, 0, 0]
        starts = [m.byte_start for m in r.media]
        assert starts == sorted(starts)

    def test_video_ignores_children_including_nested_media(self):
        r = sanitize("a<video><source><img><p>x</p></video>b")
        assert r.text == "ab"
        assert [(m.anchor, m.tag) for m in r.media] == [(1, "video")]

    def test_media_byte_range(self):
        r = sanitize("中<img>文")
        assert r.text == "中文"
        m, = r.media
        assert (m.anchor, m.byte_start, m.byte_end) == (1, 3, 8)
        assert r.lookup(0, 1) == [(0, 3)]
        assert r.lookup(1, 2) == [(8, 11)]


class TestRemoval:
    def test_comment_script_style_template_removed(self):
        r = sanitize("a<!-- c --><script>var x = 1;</script>b")
        assert r.text == "ab"
        r = sanitize("a<style>.x { color: red; }</style>b")
        assert r.text == "ab"
        r = sanitize("a<template><p>t</p></template>b")
        assert r.text == "ab"

    def test_hidden_attribute_with_value(self):
        r = sanitize('a<span hidden="hidden">x</span>b')
        assert r.text == "ab"

    def test_nested_hidden_subtree(self):
        r = sanitize("a<div hidden><div><p>x</p></div></div>b")
        assert r.text == "ab"

    def test_removed_content_has_no_text_position(self):
        r = sanitize("<script>x</script>a")
        assert r.text == "a"
        assert r.lookup(0, 1) == [(18, 19)]


class TestInput:
    def test_bytes_input(self):
        r = sanitize("中 <img> 文".encode("utf-8"))
        assert r.text == "中 文"
        assert [m.anchor for m in r.media] == [2]

    def test_empty_input(self):
        r = sanitize("")
        assert r.text == ""
        assert r.media == []
