"""승인된 wiki/ 문서만 공개 사용자 화면용 data/public/docs.json으로 내보낸다.

  python -m hive.export

내보내지 않는 것: raw/ 원문 사본, workspaces/ 사내 자료, 검토중·반려 문서, 디스코드 스레드 ID.
"""
import datetime
import json
import os
import pathlib
import re

from . import render, vault

OUT = pathlib.Path(os.environ.get("HIVE_PUBLIC_DIR", pathlib.Path(__file__).resolve().parents[1] / "data/public"))
DROP_KEYS = {"discord_thread", "review_status", "group"}


def public_href(path):
    return "/doc/" + path.removeprefix("wiki/")


def clean_fm(fm):
    fm = {k: v for k, v in fm.items() if k not in DROP_KEYS}
    if isinstance(fm.get("sources"), list):
        fm["sources"] = [{k: v for k, v in s.items() if k != "raw"} if isinstance(s, dict) else s for s in fm["sources"]]
    return fm


def plain_text(body, resolve):
    """검색·답변 근거용 텍스트: 링크는 글자만 남기고 원문 사본 링크는 지운다."""
    t = render._links(body, lambda target: None)
    return re.sub(r"\n{3,}", "\n\n", t).strip()


def main():
    docs = [d for d in vault.load("wiki") if vault.is_public(d)]
    resolve = render.make_resolver([d["path"] for d in docs], public_href)
    out = []
    for d in docs:
        out.append({
            "path": d["path"].removeprefix("wiki/"),
            "title": d["title"],
            "summary": d["summary"],
            "type": d["type"],
            "category": d["fm"].get("category") or d["path"].removeprefix("wiki/").rsplit("/", 1)[0],
            "updated": d["fm"].get("updated") or d["fm"].get("created") or d["mtime"][:10],
            "fm": clean_fm(d["fm"]),
            "html": render.to_html(d["body"], resolve),
            "text": plain_text(d["body"], resolve),
        })
    OUT.mkdir(parents=True, exist_ok=True)
    tmp = OUT / "docs.json.tmp"
    tmp.write_text(json.dumps({"exported_at": datetime.datetime.now().isoformat(timespec="seconds"), "docs": out},
                              ensure_ascii=False, default=str))
    tmp.replace(OUT / "docs.json")
    from . import index, snapshot
    snapshot.write()
    index.main()  # 조각·임베딩·관계 그래프 다시 만들기
    if os.environ.get("NEO4J_URI"):
        from . import graphdb
        print(json.dumps({"neo4j": graphdb.sync()}, ensure_ascii=False))
    print(json.dumps({"exported": len(out), "out": str(OUT / "docs.json")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
