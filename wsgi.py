import os, sys, shutil, traceback
from flask import Flask

BASE = os.path.dirname(__file__)
sys.path.insert(0, BASE)

# ----- 시드 DB 자동 복원 -----
SEED   = os.path.join(BASE, "seed", "consulting-seed.db")
TARGET = os.path.join(BASE, "advice6", "consulting.db")
os.environ.setdefault("SQLITE_PATH", TARGET)

if not os.path.exists(TARGET) and os.path.exists(SEED):
    os.makedirs(os.path.dirname(TARGET), exist_ok=True)
    shutil.copyfile(SEED, TARGET)
# --------------------------------

# ----- Flask app 임포트 (여러 구조 자동 시도) -----
def _try(path):
    mod, attr = path.split(":")
    m = __import__(mod, fromlist=[attr])
    obj = getattr(m, attr)
    return obj() if callable(obj) else obj

app = None
errors = []
for cand in ("advice6.app:app", "advice6:app", "advice6:create_app"):
    try:
        app = _try(cand)
        break
    except Exception as e:
        errors.append(f"{cand}: {e}\n{traceback.format_exc()}")

# ----- 실패해도 '안전모드'로 반드시 기동 -----
if app is None:
    print("=== SAFE MODE: advice6 임포트 실패, 임시 앱으로 실행합니다 ===")
    for i, msg in enumerate(errors, 1):
        print(f"[IMPORT ERR {i}]\n{msg}")
    app = Flask(__name__)

    @app.get("/")
    def _home():
        return "<h2>임시 안전모드</h2><p>Deploy는 성공했지만 advice6 임포트 오류가 있습니다. Render 로그를 확인하세요.</p>"

    @app.get("/healthz")
    def _hz():
        return {"ok": True, "mode": "safe"}, 200
