#!/bin/zsh
# 사용: ./run.sh public | admin | export
cd "${0:A:h}" || exit 1
[ -f .env ] && set -a && source .env && set +a
export PYTHONPATH=.
case "$1" in
  public) exec .venv/bin/python -m uvicorn hive.public_app:app --host 127.0.0.1 --port "${PUBLIC_PORT:-8010}" ;;
  admin)  exec .venv/bin/python -m uvicorn hive.admin_app:app --host 127.0.0.1 --port "${ADMIN_PORT:-8110}" ;;
  export) exec .venv/bin/python -m hive.export ;;
  *) echo "사용: ./run.sh public|admin|export"; exit 1 ;;
esac
