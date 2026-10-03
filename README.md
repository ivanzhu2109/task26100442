# task26100442
# html_evidence

HTML 正文净化与证据回查库。输入 UTF-8 编码的 HTML 正文片段，输出净化正文、
零宽媒体事件以及逐字符的原始字节证据映射；原文与结果仅在内存中处理。

## 位置约定

- 原始位置按字节（UTF-8），正文位置按 Unicode 码点，均从 0 开始，区间左闭右开。

## 用法

```python
from html_evidence import sanitize

result = sanitize("A&amp;<b>中</b>")
result.text            # 'A&中'
result.lookup(1, 3)    # [(1, 6), (9, 12)] —— 正文区间对应的原始字节区间并集

result = sanitize("a <img> b")
result.text            # 'a b'
result.media           # [MediaEvent(anchor=2, tag='img', byte_start=2, byte_end=7)]
```

## 规则摘要

- 删除注释及 `script`/`style`/`template`/带 `hidden` 属性元素的整个子树，不补空格。
- 其他标签不输出文字但保留文本内容；`p`/`div`/`li` 的起止标签与 `br` 各形成一个分隔。
- 实体解码后，ASCII 空白（空格/制表/回车/换行/换页符）与分隔组成连续空白段：
  含分隔则合并为一个换行，否则一个空格；正文首尾的此类空白被裁掉。
- 实体按 HTML5 解释（仅带分号的合法引用），实体产生的每个码点对应整个实体字节。
- 未删除的 `img`/`video` 各保留一个零宽媒体事件；`video` 忽略全部子节点。
  媒体不打断空白合并，夹在空白段内时锚定在合并字符之后。
- `lookup(start, end)` 只合并重叠或相邻的字节区间，不跨过未贡献的字节。

## 测试

```bash
python3 -m pytest tests/ -q
```
