"""HTML 片段分词：产出带字符位置区间的 token 流。"""

from __future__ import annotations

import re
from dataclasses import dataclass

_RAW_TEXT_TAGS = frozenset({"script", "style"})

_TAG_NAME_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9-]*")
_ATTR_WS = " \t\r\n\f"


def _has_hidden_attr(inner: str) -> bool:
    """在标签名之后的属性区扫描 hidden 属性（兼容引号与等号）。"""
    pos = 0
    size = len(inner)
    while pos < size:
        while pos < size and (inner[pos] in _ATTR_WS or inner[pos] == "/"):
            pos += 1
        if pos >= size:
            break
        start = pos
        while pos < size and inner[pos] not in _ATTR_WS + "/=>\"'":
            pos += 1
        name = inner[start:pos].lower()
        while pos < size and inner[pos] in _ATTR_WS:
            pos += 1
        if pos < size and inner[pos] == "=":
            pos += 1
            while pos < size and inner[pos] in _ATTR_WS:
                pos += 1
            if pos < size and inner[pos] in "\"'":
                quote = inner[pos]
                pos += 1
                while pos < size and inner[pos] != quote:
                    pos += 1
                pos += 1
            else:
                while pos < size and inner[pos] not in _ATTR_WS + ">":
                    pos += 1
        if name == "hidden":
            return True
    return False


@dataclass(frozen=True)
class Token:
    kind: str  # "text" | "start" | "end" | "comment"
    start: int  # 起始字符位置（含）
    end: int  # 结束字符位置（不含）
    name: str = ""  # 标签名（小写），text/comment 为空
    data: str = ""  # text 的文本内容
    self_closing: bool = False
    has_hidden: bool = False


def tokenize(html: str) -> list[Token]:
    tokens: list[Token] = []
    pos = 0
    size = len(html)
    while pos < size:
        lt = html.find("<", pos)
        if lt < 0:
            tokens.append(Token("text", pos, size, data=html[pos:]))
            break
        if lt > pos:
            tokens.append(Token("text", pos, lt, data=html[pos:lt]))
        if html.startswith("<!--", lt):
            close = html.find("-->", lt + 4)
            end = size if close < 0 else close + 3
            tokens.append(Token("comment", lt, end))
            pos = end
            continue
        if lt + 1 < size and html[lt + 1] == "/":
            match = _TAG_NAME_RE.match(html, lt + 2)
            if match is None:
                tokens.append(Token("text", lt, lt + 1, data="<"))
                pos = lt + 1
                continue
            gt = html.find(">", match.end())
            end = size if gt < 0 else gt + 1
            tokens.append(Token("end", lt, end, name=match.group().lower()))
            pos = end
            continue
        match = _TAG_NAME_RE.match(html, lt + 1)
        if match is None:
            tokens.append(Token("text", lt, lt + 1, data="<"))
            pos = lt + 1
            continue
        name = match.group().lower()
        gt = html.find(">", match.end())
        end = size if gt < 0 else gt + 1
        inner = html[match.end() : gt if gt >= 0 else size]
        self_closing = inner.rstrip().endswith("/")
        tokens.append(
            Token(
                "start",
                lt,
                end,
                name=name,
                self_closing=self_closing,
                has_hidden=_has_hidden_attr(inner),
            )
        )
        pos = end
        if name in _RAW_TEXT_TAGS and not self_closing:
            close_match = re.search(r"</" + name + r"(?=[\s/>])", html[pos:], re.IGNORECASE)
            if close_match is None:
                if pos < size:
                    tokens.append(Token("text", pos, size, data=html[pos:]))
                break
            close_start = pos + close_match.start()
            if close_start > pos:
                tokens.append(Token("text", pos, close_start, data=html[pos:close_start]))
            pos = close_start
    return tokens
