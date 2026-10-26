"""Neo4j 연결 — graph.json을 Neo4j에 올리고(sync), GraphRAG가 이웃을 질의한다(neighbors).

  python -m hive.graphdb sync

접속 정보: 환경변수 NEO4J_URI / NEO4J_USERNAME / NEO4J_PASSWORD
(Aura에서 내려받은 Neo4j-*.txt를 .env에 옮겨 적는다)

노드: (:Doc {path, title, type, category}), (:Source {url})
관계: MANUFACTURED_BY, COMPATIBLE_WITH, RELATED_TO, LINKS_TO, IN_CATEGORY (Doc→Doc), CITES (Doc→Source)
"""
import json
import os
import sys
from functools import lru_cache

from .export import OUT


@lru_cache(maxsize=1)
def driver():
    from neo4j import GraphDatabase
    return GraphDatabase.driver(os.environ["NEO4J_URI"], auth=(os.environ.get("NEO4J_USERNAME", "neo4j"), os.environ["NEO4J_PASSWORD"]))


def sync():
    g = json.loads((OUT / "graph.json").read_text())
    docs = {n["id"] for n in g["nodes"]}
    with driver().session() as s:
        s.run("MATCH (n) WHERE n:Doc OR n:Source DETACH DELETE n")
        s.run("CREATE CONSTRAINT doc_path IF NOT EXISTS FOR (d:Doc) REQUIRE d.path IS UNIQUE")
        s.run("CREATE CONSTRAINT source_url IF NOT EXISTS FOR (s:Source) REQUIRE s.url IS UNIQUE")
        s.run("UNWIND $rows AS r MERGE (d:Doc {path: r.id}) SET d.title = r.title, d.type = r.type, d.category = r.category",
              rows=g["nodes"])
        by_rel = {}
        for e in g["edges"]:
            by_rel.setdefault(e["rel"], []).append(e)
        for rel, rows in by_rel.items():  # 관계 이름은 매개변수로 못 넘기므로 종류별로 실행 (값은 고정 목록)
            if rel == "CITES":
                s.run("UNWIND $rows AS r MATCH (d:Doc {path: r.src}) MERGE (x:Source {url: r.dst}) MERGE (d)-[:CITES]->(x)", rows=rows)
            else:
                rows = [r for r in rows if r["src"] in docs and r["dst"] in docs]
                s.run(f"UNWIND $rows AS r MATCH (a:Doc {{path: r.src}}), (b:Doc {{path: r.dst}}) MERGE (a)-[:{rel}]->(b)", rows=rows)
        n = s.run("MATCH (d:Doc) RETURN count(d) AS n").single()["n"]
        m = s.run("MATCH ()-[r]->() RETURN type(r) AS t, count(r) AS n").data()
    return {"docs": n, "rels": {x["t"]: x["n"] for x in m}}


def neighbors(paths, rels):
    """{문서: [(이웃 문서, 관계)]} — 방향 무관 1단계."""
    q = ("UNWIND $paths AS p MATCH (a:Doc {path: p})-[r]-(b:Doc) WHERE type(r) IN $rels "
         "RETURN p AS src, b.path AS dst, type(r) AS rel")
    out = {p: [] for p in paths}
    with driver().session() as s:
        for row in s.run(q, paths=paths, rels=rels):
            out[row["src"]].append((row["dst"], row["rel"]))
    return out


if __name__ == "__main__":
    if sys.argv[1:] == ["sync"]:
        print(json.dumps(sync(), ensure_ascii=False))
    else:
        print("사용: python -m hive.graphdb sync")
