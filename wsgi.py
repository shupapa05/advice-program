import os, shutil

BASE = os.path.dirname(__file__)
# 앱이 이 경로(advice6/consulting.db)를 쓰도록 기본값 지정
TARGET1 = os.path.join(BASE, "advice6", "consulting.db")
TARGET2 = os.path.join(BASE, "consulting.db")  # 혹시 루트를 보는 앱일 대비
SEED    = os.path.join(BASE, "seed", "consulting-seed.db")

# 환경변수로도 힌트 제공(앱이 SQLITE_PATH를 읽는 경우)
os.environ.setdefault("SQLITE_PATH", TARGET1)

# DB 파일이 하나도 없으면 시드로 복원
if not (os.path.exists(TARGET1) or os.path.exists(TARGET2)):
    if os.path.exists(SEED):
        os.makedirs(os.path.dirname(TARGET1), exist_ok=True)
        shutil.copyfile(SEED, TARGET1)

# advice6/app.py 안에 app = Flask(__name__) 가 있다고 가정
from advice6.app import app
