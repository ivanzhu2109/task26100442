# task26100442

HTML 正文净化与证据回查库。输入 UTF-8 HTML 正文片段，全部在内存中处理。

## 用法

```python
from html_cleanse import cleanse

result = cleanse("A&amp;<b>中</b>")
result.text            # "A&中"（正文位置按 Unicode 码点，从 0 开始）
result.evidence(1, 3)  # [(1, 6), (9, 12)]（原始字节区间并集，左闭右开）
result.media           # [MediaEvent(anchor, byte_start, byte_end), ...]
```

- `cleanse(html)`：接受 `str` 或 UTF-8 `bytes`，返回 `CleanseResult`。
- `CleanseResult.text`：净化正文。删除注释及 script/style/template/hidden 子树；
  p/div/li 起止标签与 br 形成分隔；ASCII 空白与分隔合并为空格或换行，首尾裁剪。
- `CleanseResult.media`：零宽媒体事件（img/video），锚点为正文字符边界。
- `CleanseResult.evidence(start, end)`：正文区间 `[start, end)` 内字符贡献的
  原始字节区间并集，仅合并重叠或相邻区间。

## 测试

```sh
python3 -m unittest discover -s tests
```
