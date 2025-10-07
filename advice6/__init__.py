# advice6/__init__.py
from .app import app as _app

def create_app():
    # wsgi.py가 기대하는 팩토리 함수
    return _app

# 혹시 wsgi:app 형태로도 쓸 수 있게 노출
app = _app
