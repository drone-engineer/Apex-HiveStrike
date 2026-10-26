"""임베딩 모델 경량판 만들기 — 무료 서버(메모리 512MB)용.

  python -m hive.slim_model

원본 MiniLM은 25만 토큰 사전이 메모리 대부분이다 — 모델 word_embeddings(192MB, 실행 시 약 500MB)와
토크나이저(약 400MB). ① 우리 문서 조각에 실제로 나오는 토큰 ② 사전 앞쪽 토큰 KEEP_TOP개 ③ 특수 토큰만 남겨
모델과 토크나이저를 같은 순서로 줄인다.
문서 조각의 임베딩은 원본과 같다(Unigram은 쓰던 조각이 남아 있으면 분할 결과가 같다).
질문에만 나오는 드문 토큰은 더 짧은 조각으로 나뉘거나 <unk>가 된다.

결과 (data/model/):
  model.onnx      사전을 줄인 모델
  tokenizer.json  사전을 줄인 토크나이저 (번호가 모델과 같다)
"""
import json
import pathlib

import numpy as np

from .export import OUT
from . import index

DIR = pathlib.Path(__file__).resolve().parents[1] / "data/model"
KEEP_TOP = 40000


def main():
    import onnx
    from onnx import numpy_helper
    from tokenizers import Tokenizer

    src = pathlib.Path(index.embedder().model._model_dir)
    tok = Tokenizer.from_file(str(src / "tokenizer.json"))
    m = onnx.load(str(src / "model_optimized.onnx"))
    init = next(t for t in m.graph.initializer if t.name == "embeddings.word_embeddings.weight")
    w = numpy_helper.to_array(init)
    vocab = w.shape[0]

    chunks = json.loads((OUT / "chunks.json").read_text())
    texts = [f'{c["title"]} — {c["heading"]}\n{c["text"]}' for c in chunks]
    used = {i for e in tok.encode_batch(texts) for i in e.ids}
    special = {tok.token_to_id(t) for t in ("<s>", "</s>", "<pad>", "<unk>", "<mask>") if tok.token_to_id(t) is not None}
    keep = sorted(set(range(min(KEEP_TOP, vocab))) | used | special)

    new_id = {old: new for new, old in enumerate(keep)}

    init.CopyFrom(numpy_helper.from_array(w[keep], init.name))
    DIR.mkdir(parents=True, exist_ok=True)
    onnx.save(m, str(DIR / "model.onnx"))

    tj = json.loads((src / "tokenizer.json").read_text())
    pieces = tj["model"]["vocab"]
    tj["model"]["vocab"] = [pieces[i] for i in keep if i < len(pieces)]
    tj["model"]["unk_id"] = new_id[tj["model"]["unk_id"]]
    for a in tj["added_tokens"]:
        a["id"] = new_id[a["id"]]
    (DIR / "tokenizer.json").write_text(json.dumps(tj, ensure_ascii=False))
    (DIR / "id_map.npy").unlink(missing_ok=True)
    print(json.dumps({"vocab": vocab, "kept": len(keep), "corpus_tokens": len(used),
                      "model_mb": round((DIR / "model.onnx").stat().st_size / 1e6, 1)}))


if __name__ == "__main__":
    main()
