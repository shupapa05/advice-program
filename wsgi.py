import os, sys, shutil, traceback

BASE = os.path.dirname(__file__)
sys.path.insert(0, BASE)  # 루트를 모듈 경로에 추가

# ---- 시드 DB 자동 복원 ----
SEED   = os.path.join(BASE, "seed", "consulting-seed.db")
TARGET = os.path.join(BASE, "advice6", "consulting.db")   # app.py의 기본 위치 가정
os.environ.setdefault("SQLITE_PATH", TARGET)

if not os.path.exists(TARGET) and os.path.exists(SEED):
    os.makedirs(os.path.dirname(TARGET), exist_ok=True)
    shutil.copyfile(SEED, TARGET)
# ---------------------------

# ---- app 객체 임포트 (여러 구조 자동 시도) ----
app = None
errors = []

for path in (
    "advice6.app:app",     # 가장 흔한 구조
    "advice6:app",         # __init__.py 안에 app가 있는 구조
    "advice6:create_app",  # 팩토리 패턴
):
    mod, attr = path.split(":")
    try:
        m = __import__(mod, fromlist=[attr])
        obj = getattr(m, attr)
        app = obj() if callable(obj) else obj
        break
    except Exception as e:
        errors.append(f"{path}: {e}\n{traceback.format_exc()}")

if app is None:
    raise RuntimeError("Cannot import Flask app.\n\n" + "\n".join(errors))
