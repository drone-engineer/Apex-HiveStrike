"""Hugging Face Space에 배포 — 저장소의 배포용 파일만 올리고 비밀 변수를 넣는다.

  python deploy/hf_deploy.py <사용자명>/<space 이름>

올리는 것: Dockerfile, requirements.txt, hive/, data/public/, data/model/, Space용 README(deploy/hf_space/README.md)
비밀 변수: .env의 GOOGLE_API_KEY, ADMIN_PASSWORD (값은 출력하지 않는다)
"""
import pathlib
import sys

from huggingface_hub import HfApi

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import hive  # noqa: E402,F401 — .env를 환경변수로 읽는다
import os  # noqa: E402


def main(repo_id):
    api = HfApi()
    api.create_repo(repo_id, repo_type="space", space_sdk="docker", exist_ok=True)
    for key in ("GOOGLE_API_KEY", "ADMIN_PASSWORD"):
        if os.environ.get(key):
            api.add_space_secret(repo_id, key, os.environ[key])
    api.add_space_variable(repo_id, "ASK_PER_HOUR", "10")
    api.add_space_variable(repo_id, "ASK_PER_DAY", "200")
    api.upload_folder(repo_id=repo_id, repo_type="space", folder_path=str(ROOT),
                      allow_patterns=["Dockerfile", "requirements.txt", "hive/**", "data/public/**", "data/model/**"],
                      ignore_patterns=["**/__pycache__/**", "*.pyc"],
                      commit_message="배포: 사용자 화면 + 관리자 스냅샷")
    api.upload_file(repo_id=repo_id, repo_type="space", path_or_fileobj=str(ROOT / "deploy/hf_space/README.md"),
                    path_in_repo="README.md", commit_message="Space 설명")
    print(f"https://huggingface.co/spaces/{repo_id}")


if __name__ == "__main__":
    main(sys.argv[1])
