from flask import Flask
app = Flask(__name__)

@app.get("/")
def home():
    return "<h2>초기화 완료</h2><p>학교 네트워크 프로그램 업로드 준비됨.</p>"

@app.get("/healthz")
def healthz():
    return {"ok": True}, 200
