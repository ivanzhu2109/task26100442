"""数据模型：净化结果与媒体事件。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class MediaEvent:
    """零宽媒体事件，锚定在正文字符边界上。"""

    anchor: int
    byte_start: int
    byte_end: int


@dataclass
class CleanseResult:
    """净化结果：正文、媒体事件，以及逐字符的原始字节区间证据。"""

    text: str
    media: list[MediaEvent] = field(default_factory=list)
    _spans: list[tuple[tuple[int, int], ...]] = field(default_factory=list, repr=False)

    def evidence(self, start: int, end: int) -> list[tuple[int, int]]:
        """返回正文区间 [start, end) 内字符贡献的原始字节区间并集。"""
        if not 0 <= start <= end <= len(self.text):
            raise IndexError(f"正文区间越界: [{start}, {end})，正文长度 {len(self.text)}")
        ranges: list[tuple[int, int]] = []
        for spans in self._spans[start:end]:
            ranges.extend(spans)
        ranges.sort()
        merged: list[list[int]] = []
        for lo, hi in ranges:
            if merged and lo <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], hi)
            else:
                merged.append([lo, hi])
        return [(lo, hi) for lo, hi in merged]
