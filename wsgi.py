# wsgi.py
import os, sys, shutil, traceback
from importlib import import_module
from flask import Flask

BASE = os.path.dirname(__file__)
sys.path.insert(0, BASE)  # 루트를 import 경로에 추가

# ----- 시드 DB 자동 복원 -----
SEED   = os.path.join(BASE, "seed", "consulting-seed.db")
TARGET = os.path.join(BASE, "advice6", "consulting.db")
os.environ.setdefault("SQLITE_PATH", TARGET)

if not os.path.exists(TARGET) and os.path.exists(SEED):
    os.makedirs(os.path.dirname(TARGET), exist_ok=True)
    shutil.copyfile(SEED, TARGET)
# --------------------------------


def load_flask_app():
    errors = []

    # 1) 가장 정상적인 구조: advice6/app.py 안의 app 변수
    try:
        mod = import_module("advice6.app")
        a = getattr(mod, "app")
        # 절대 호출하지 않음: Flask 인스턴스도 callable 이라서!
        return a
    except Exception as e:
        errors.append(f"advice6.app:app -> {e}\n{traceback.format_exc()}")

    # 2) 팩토리 패턴: advice6/__init__.py 안의 create_app()
    try:
        pkg = import_module("advice6")
        create = getattr(pkg, "create_app")
        if callable(create):
            return create()
    except Exception as e:
        errors.append(f"advice6:create_app -> {e}\n{traceback.format_exc()}")

    # 3) 실패 내역 반환
    return None, errors


app = None
load_result = load_flask_app()
if isinstance(load_result, tuple):
    app, import_errors = load_result
else:
    app, import_errors = load_result, []

# ----- 실패해도 '안전모드'로 반드시 기동 -----
if app is None:
    print("=== SAFE MODE: advice6 임포트 실패, 임시 앱으로 실행합니다 ===")
    for i, msg in enumerate(import_errors, 1):
        print(f"[IMPORT ERR {i}]\n{msg}")

    app = Flask(__name__)

    @app.get("/")
    def _home():
        return (
            "<h2>임시 안전모드</h2>"
            "<p>Deploy는 성공했지만 advice6 임포트 오류가 있습니다.<br>"
            "Render 로그의 [IMPORT ERR …] 내용을 확인해 주세요.</p>"
        )

    @app.get("/healthz")
    def _hz():
        return {"ok": True, "mode": "safe"}, 200

# 일부 플랫폼 호환(혹시 wsgi:application을 찾는 경우 대비)
application = app
