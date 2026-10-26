"""옵시디언 마크다운 → HTML. 위키링크·콜아웃·각주·표를 웹 화면용으로 바꾼다."""
import html
import re

import markdown

LINK_RE = re.compile(r"(!?)\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|([^\]]+))?\]\]")
CALLOUT_RE = re.compile(r"^> ?\[!(\w+)\][+-]?[ \t]*(.*)$")
CALLOUT_LABEL = {"quote": "원문", "note": "참고", "warning": "주의", "info": "정보", "important": "중요", "tip": "팁"}


def make_resolver(paths, href):
    """[[대상]] → 볼트 경로. 전체 경로, 확장자 없는 경로, 파일 이름(마지막 조각) 순으로 찾는다."""
    by_path = {p: p for p in paths}
    by_stem = {}
    for p in paths:
        by_stem.setdefault(p.rsplit("/", 1)[-1], p)

    def resolve(target):
        t = target.strip().removesuffix(".md")
        p = by_path.get(t) or by_path.get(f"wiki/{t}") or by_stem.get(t.rsplit("/", 1)[-1])
        return href(p) if p else None
    return resolve


def _links(text, resolve):
    def sub(m):
        if m.group(1):  # 임베드(![[...]])는 화면에 넣지 않는다
            return ""
        target, alias = m.group(2).rstrip("\\"), m.group(3)
        label = alias or target.rsplit("/", 1)[-1].replace("-", " ")
        url = resolve(target)
        if url:
            return f"[{label}]({url})"
        if target.startswith("raw/"):  # 원문 사본은 공개하지 않는다 (원문 링크는 각주 URL로 제공)
            return ""
        return label
    return LINK_RE.sub(sub, text)


def _callouts(text):
    out, lines, i = [], text.split("\n"), 0
    while i < len(lines):
        m = CALLOUT_RE.match(lines[i])
        if not m:
            out.append(lines[i]); i += 1; continue
        kind, title = m.group(1).lower(), m.group(2) or CALLOUT_LABEL.get(m.group(1).lower(), m.group(1))
        inner = []
        i += 1
        while i < len(lines) and lines[i].startswith(">"):
            inner.append(re.sub(r"^> ?", "", lines[i])); i += 1
        out += ["", f'<div class="callout callout-{html.escape(kind)}" markdown="1">',
                f'<div class="callout-title" markdown="span">{title}</div>', "", *inner, "", "</div>", ""]
    return "\n".join(out)


def to_html(body, resolve):
    text = _callouts(_links(body, resolve))
    md = markdown.Markdown(extensions=["tables", "footnotes", "fenced_code", "md_in_html", "sane_lists"],
                           extension_configs={"footnotes": {"BACKLINK_TEXT": "↩"}})
    out = md.convert(text)
    # 외부 링크는 새 창
    return re.sub(r'<a href="(https?://[^"]+)"', r'<a target="_blank" rel="noopener" href="\1"', out)
