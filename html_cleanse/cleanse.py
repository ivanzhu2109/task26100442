"""正文净化：token 流 -> 净化正文 + 媒体事件 + 逐字符证据区间。"""

from __future__ import annotations

import re
from html.entities import html5

from .model import CleanseResult, MediaEvent
from .tokenizer import Token, tokenize

_VOID_TAGS = frozenset(
    {"area", "base", "br", "col", "embed", "hr", "img", "input",
     "link", "meta", "param", "source", "track", "wbr"}
)
_DROP_TAGS = frozenset({"script", "style", "template"})
_SEPARATOR_TAGS = frozenset({"p", "div", "li", "br"})
_ASCII_WS = frozenset(" \t\r\n\f")

_ENTITY_RE = re.compile(r"&(#(?:[xX][0-9a-fA-F]+|[0-9]+)|[a-zA-Z][a-zA-Z0-9]*);")


def _decode_entity(body: str) -> str | None:
    """解码带分号的合法实体引用，非法时返回 None。"""
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


class _Builder:
    def __init__(self, html: str) -> None:
        self._html = html
        self._chars: list[str] = []
        self._spans: list[tuple[tuple[int, int], ...]] = []
        self._media: list[MediaEvent] = []
        # 待合并空白段：原始字符区间、是否含标签分隔、段内媒体标签区间
        self._ws_ranges: list[tuple[int, int]] = []
        self._ws_has_sep = False
        self._ws_media: list[tuple[int, int]] = []

    def _emit_char(self, char: str, span: tuple[int, int]) -> None:
        self._flush_ws()
        self._chars.append(char)
        self._spans.append((span,))

    def _emit_separator(self, span: tuple[int, int]) -> None:
        self._ws_ranges.append(span)
        self._ws_has_sep = True

    def _emit_media(self, span: tuple[int, int]) -> None:
        if self._ws_ranges:
            self._ws_media.append(span)
        else:
            anchor = len(self._chars)
            self._media.append(MediaEvent(anchor, span[0], span[1]))

    def _flush_ws(self) -> None:
        if not self._ws_ranges:
            return
        ranges = self._ws_ranges
        media = self._ws_media
        has_sep = self._ws_has_sep
        self._ws_ranges = []
        self._ws_has_sep = False
        self._ws_media = []
        if not self._chars:
            # 正文首部的空白段被裁掉，段内媒体锚定为 0
            for lo, hi in media:
                self._media.append(MediaEvent(0, lo, hi))
            return
        self._chars.append("\n" if has_sep else " ")
        self._spans.append(tuple(ranges))
        anchor = len(self._chars)
        for lo, hi in media:
            self._media.append(MediaEvent(anchor, lo, hi))

    def feed_text(self, token: Token) -> None:
        data = token.data
        base = token.start
        pos = 0
        for match in _ENTITY_RE.finditer(data):
            self._feed_plain(data, pos, match.start(), base)
            decoded = _decode_entity(match.group(1))
            span = (base + match.start(), base + match.end())
            if decoded is None:
                self._feed_plain(data, match.start(), match.end(), base)
            else:
                for char in decoded:
                    self._feed_decoded_char(char, span)
            pos = match.end()
        self._feed_plain(data, pos, len(data), base)

    def _feed_plain(self, data: str, start: int, end: int, base: int) -> None:
        for index in range(start, end):
            self._feed_decoded_char(data[index], (base + index, base + index + 1))

    def _feed_decoded_char(self, char: str, span: tuple[int, int]) -> None:
        if char in _ASCII_WS:
            self._ws_ranges.append(span)
        else:
            self._emit_char(char, span)

    def finish(self) -> CleanseResult:
        # 正文尾部的空白段被裁掉，段内媒体锚定为正文长度
        trailing_media = self._ws_media
        self._ws_ranges = []
        self._ws_media = []
        text = "".join(self._chars)
        for lo, hi in trailing_media:
            self._media.append(MediaEvent(len(text), lo, hi))
        return CleanseResult(text=text, media=self._media, _spans=self._spans)


def cleanse(html: bytes | str) -> CleanseResult:
    """净化 HTML 正文片段，返回正文、媒体事件与证据回查句柄。"""
    if isinstance(html, (bytes, bytearray)):
        html = bytes(html).decode("utf-8")
    builder = _Builder(html)
    stack: list[tuple[str, bool]] = []  # (标签名, 是否处于被删除/忽略子树)

    def skipped() -> bool:
        return any(flag for _, flag in stack)

    for token in tokenize(html):
        span = (token.start, token.end)
        if token.kind == "comment":
            continue
        if token.kind == "text":
            if not skipped():
                builder.feed_text(token)
            continue
        name = token.name
        if token.kind == "start":
            if skipped():
                if name not in _VOID_TAGS and not token.self_closing:
                    stack.append((name, True))
                continue
            if name in _DROP_TAGS or token.has_hidden:
                if name not in _VOID_TAGS and not token.self_closing:
                    stack.append((name, True))
                continue
            if name == "video":
                builder._emit_media(span)
                if not token.self_closing:
                    stack.append((name, True))
                continue
            if name == "img":
                builder._emit_media(span)
                continue
            if name in _SEPARATOR_TAGS:
                builder._emit_separator(span)
            if name not in _VOID_TAGS and not token.self_closing:
                stack.append((name, False))
            continue
        # end 标签：弹栈至匹配项
        matched_skip = False
        for index in range(len(stack) - 1, -1, -1):
            if stack[index][0] == name:
                matched_skip = stack[index][1]
                del stack[index:]
                break
        if not matched_skip and not skipped() and name in _SEPARATOR_TAGS:
            builder._emit_separator(span)

    result = builder.finish()
    byte_of = [0] * (len(html) + 1)
    offset = 0
    for index, char in enumerate(html):
        byte_of[index] = offset
        offset += len(char.encode("utf-8"))
    byte_of[len(html)] = offset
    spans = [
        tuple((byte_of[lo], byte_of[hi]) for lo, hi in group)
        for group in result._spans
    ]
    media = [
        MediaEvent(event.anchor, byte_of[event.byte_start], byte_of[event.byte_end])
        for event in result.media
    ]
    return CleanseResult(text=result.text, media=media, _spans=spans)

