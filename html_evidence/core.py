"""HTML 正文净化与证据回查核心实现。

输入为 UTF-8 编码的 HTML 正文片段（str 或 bytes），输出净化后的正文、
媒体事件以及每个正文字符对应的原始字节区间，全部仅在内存中处理。

位置约定：
- 原始位置按字节（UTF-8），从 0 开始，区间左闭右开。
- 正文位置按 Unicode 码点，从 0 开始，区间左闭右开。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.entities import html5

# 内部事件（分词器输出，区间均为原始字节区间）：
# ("char", ch, byte_start, byte_end)    解码后的一个正文字符
# ("sep", byte_start, byte_end)         分隔标签（p/div/li 的起止标签、br）
# ("media", tag, byte_start, byte_end)  零宽媒体事件（img/video）

_VOID_TAGS = frozenset(
    "area base br col embed hr img input link meta param source track wbr".split()
)
_RAWTEXT_TAGS = frozenset({"script", "style"})
_SEP_TAGS = frozenset({"p", "div", "li"})

_TAG_NAME_RE = re.compile(r"[a-zA-Z][^\s/>]*")
_ENTITY_RE = re.compile(r"&(#(?:[xX][0-9a-fA-F]+|\d+)|[0-9a-zA-Z]+);")
_HIDDEN_RE = re.compile(r"(?:^|\s)hidden(?=\s|=|$)", re.IGNORECASE)


def _byte_offsets(s: str) -> list[int]:
    """每个字符索引对应的 UTF-8 字节偏移（含末尾哨兵）。"""
    offsets = [0] * (len(s) + 1)
    pos = 0
    for i, ch in enumerate(s):
        pos += len(ch.encode("utf-8"))
        offsets[i + 1] = pos
    return offsets


def _decode_entity(body: str) -> str | None:
    """解码带分号的合法实体引用，失败返回 None。"""
    if body.startswith("#"):
        try:
            if body[1] in "xX":
                codepoint = int(body[2:], 16)
            else:
                codepoint = int(body[1:], 10)
            return chr(codepoint)
        except (ValueError, OverflowError):
            return "�"
    return html5.get(body + ";")


def _decode_text(s: str, i: int, j: int):
    """对 s[i:j] 做实体解码，产出 (ch, char_start, char_end)（字符索引）。"""
    out = []
    k = i
    while k < j:
        if s[k] == "&":
            m = _ENTITY_RE.match(s, k, j)
            if m:
                decoded = _decode_entity(m.group(1))
                if decoded is not None:
                    for c in decoded:
                        out.append((c, k, m.end()))
                    k = m.end()
                    continue
        out.append((s[k], k, k + 1))
        k += 1
    return out


def _scan_tag(s: str, i: int):
    """扫描 s[i] 处的标签（i 指向 '<'）。

    返回 (j, name, is_close, self_closing, attrs_text)，j 为 '>' 之后的位置。
    name 为空串表示 '<' 后不是合法标签名。
    """
    n = len(s)
    k = i + 1
    is_close = False
    if k < n and s[k] == "/":
        is_close = True
        k += 1
    m = _TAG_NAME_RE.match(s, k)
    if not m:
        return i + 1, "", is_close, False, ""
    k = m.end()
    quote = None
    while k < n:
        c = s[k]
        if quote:
            if c == quote:
                quote = None
        elif c in "\"'":
            quote = c
        elif c == ">":
            break
        k += 1
    j = k + 1 if k < n else n
    attrs_text = s[m.end() : k]
    self_closing = attrs_text.rstrip().endswith("/")
    return j, m.group(0).lower(), is_close, self_closing, attrs_text


def _skip_rawtext(s: str, i: int, name: str) -> int:
    """跳过 script/style 的原始文本内容，返回匹配闭合标签之后的位置。"""
    m = re.search(r"</\s*" + re.escape(name) + r"\s*>", s[i:], re.IGNORECASE)
    if not m:
        return len(s)
    return i + m.end()


def _skip_subtree(s: str, i: int, name: str) -> int:
    """跳过 name 元素的整个子树，返回匹配闭合标签之后的位置。"""
    depth = 1
    n = len(s)
    while i < n:
        if s[i] == "<":
            if s.startswith("<!--", i):
                j = s.find("-->", i + 4)
                i = n if j < 0 else j + 3
                continue
            j, tname, is_close, self_closing, _ = _scan_tag(s, i)
            if not tname:
                i = j
                continue
            if tname == name:
                if is_close:
                    depth -= 1
                    if depth == 0:
                        return j
                elif not self_closing and tname not in _VOID_TAGS:
                    depth += 1
            i = j
        else:
            i += 1
    return i


def _tokenize(s: str, offsets: list[int]) -> list[tuple]:
    """把 HTML 片段切成内部事件流，区间转换为字节。"""

    def b(i: int) -> int:
        return offsets[i]

    events: list[tuple] = []
    i = 0
    n = len(s)
    while i < n:
        lt = s.find("<", i)
        if lt < 0:
            lt = n
        if lt > i:
            for ch, a, z in _decode_text(s, i, lt):
                events.append(("char", ch, b(a), b(z)))
        i = lt
        if i >= n:
            break
        if s.startswith("<!--", i):
            j = s.find("-->", i + 4)
            i = n if j < 0 else j + 3
            continue
        if s.startswith("<!", i) or s.startswith("<?", i):
            j = s.find(">", i + 2)
            i = n if j < 0 else j + 1
            continue
        j, name, is_close, self_closing, attrs_text = _scan_tag(s, i)
        if not name:
            events.append(("char", "<", b(i), b(i + 1)))
            i += 1
            continue
        if is_close:
            if name in _SEP_TAGS:
                events.append(("sep", b(i), b(j)))
            i = j
            continue
        if name in _RAWTEXT_TAGS or name == "template" or _HIDDEN_RE.search(attrs_text):
            if self_closing:
                i = j
            elif name in _RAWTEXT_TAGS:
                i = _skip_rawtext(s, j, name)
            else:
                i = _skip_subtree(s, j, name)
            continue
        if name in _SEP_TAGS or name == "br":
            events.append(("sep", b(i), b(j)))
        if name == "img":
            events.append(("media", "img", b(i), b(j)))
            i = j
            continue
        if name == "video":
            events.append(("media", "video", b(i), b(j)))
            i = j if self_closing else _skip_subtree(s, j, name)
            continue
        i = j
    return events


@dataclass(frozen=True)
class MediaEvent:
    """零宽媒体事件，锚定在正文字符边界上。"""

    anchor: int
    tag: str
    byte_start: int
    byte_end: int


@dataclass
class SanitizedText:
    """净化结果：正文、媒体事件及逐字符证据映射。"""

    text: str
    media: list[MediaEvent] = field(default_factory=list)
    _char_ranges: list[list[tuple[int, int]]] = field(default_factory=list)

    def lookup(self, start: int, end: int) -> list[tuple[int, int]]:
        """返回正文区间 [start, end) 内所有字符贡献的原始字节区间并集。

        只合并重叠或相邻的区间，不跨过未贡献的字节。
        """
        if not (0 <= start <= end <= len(self.text)):
            raise ValueError(f"正文区间越界: [{start}, {end})，正文长度 {len(self.text)}")
        merged: list[list[int]] = []
        for i in range(start, end):
            for bs, be in self._char_ranges[i]:
                if merged and bs <= merged[-1][1]:
                    merged[-1][1] = max(merged[-1][1], be)
                else:
                    merged.append([bs, be])
        return [(bs, be) for bs, be in merged]


# 参与折叠的 ASCII 空白：空格、制表、回车、换行、换页符。
_COLLAPSIBLE = frozenset(" \t\r\n\f")


def sanitize(html: str | bytes) -> SanitizedText:
    """净化 HTML 正文片段，返回 SanitizedText。"""
    if isinstance(html, (bytes, bytearray)):
        s = bytes(html).decode("utf-8")
    else:
        s = html
    events = _tokenize(s, _byte_offsets(s))

    chars: list[str] = []
    char_ranges: list[list[tuple[int, int]]] = []
    media: list[MediaEvent] = []
    run_ranges: list[tuple[int, int]] = []
    run_media: list[tuple[str, int, int]] = []
    run_has_sep = False
    started = False

    def flush(trailing: bool = False) -> None:
        nonlocal run_has_sep
        if run_ranges and started and not trailing:
            chars.append("\n" if run_has_sep else " ")
            char_ranges.append(list(run_ranges))
        anchor = len(chars)
        for tag, bs, be in run_media:
            media.append(MediaEvent(anchor=anchor, tag=tag, byte_start=bs, byte_end=be))
        run_ranges.clear()
        run_media.clear()
        run_has_sep = False

    for ev in events:
        kind = ev[0]
        if kind == "char":
            ch = ev[1]
            if ch in _COLLAPSIBLE:
                run_ranges.append((ev[2], ev[3]))
            else:
                flush()
                chars.append(ch)
                char_ranges.append([(ev[2], ev[3])])
                started = True
        elif kind == "sep":
            run_has_sep = True
            run_ranges.append((ev[1], ev[2]))
        else:
            run_media.append((ev[1], ev[2], ev[3]))
    flush(trailing=True)

    return SanitizedText(text="".join(chars), media=media, _char_ranges=char_ranges)
