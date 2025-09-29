from flask import Flask, render_template, request, redirect, session, flash, url_for, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os, re, logging
from zoneinfo import ZoneInfo

app = Flask(__name__)

# 기능 토글: 신청일 수정 보이기/숨기기
EDIT_DATE_ENABLED = os.getenv('EDIT_DATE_ENABLED', '1') == '1'

# === PATCH: SECRET_KEY 환경변수 우선 ===
app.secret_key = os.getenv('SECRET_KEY', 'your_secret_key')

# === PATCH: DATABASE_URL / SQLITE_PATH 환경변수 우선 + sqlite 폴백 ===
basedir = os.path.abspath(os.path.dirname(__file__))

# SQLITE_PATH가 지정되어 있으면 해당 경로의 sqlite 파일 사용, 없으면 프로젝트 루트의 consulting.db 사용
sqlite_path = os.getenv("SQLITE_PATH") or os.path.join(basedir, "consulting.db")

# DATABASE_URL(예: Postgres)이 있으면 우선 사용, 없으면 위 sqlite를 사용
database_url = os.getenv("DATABASE_URL") or ("sqlite:///" + sqlite_path.replace("\\", "/"))

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# === PATCH: 로깅/KST 헬퍼 ===
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
KST = ZoneInfo("Asia/Seoul")
def now_kst_str():
    return datetime.now(KST).strftime('%Y-%m-%d %H:%M')

class ConsultRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    grade = db.Column(db.Integer, nullable=False)
    class_num = db.Column(db.Integer, nullable=False)
    number = db.Column(db.Integer, nullable=False)
    name = db.Column(db.String(20), nullable=False)
    password = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(20), nullable=False)
    topic = db.Column(db.String(50), nullable=False)
    content = db.Column(db.Text, nullable=False)
    date = db.Column(db.String(20), nullable=False)

class ConsultLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(db.Integer, db.ForeignKey('consult_request.id'), nullable=False)
    teacher_name = db.Column(db.String(30), nullable=False)
    memo = db.Column(db.Text, nullable=False)
    date = db.Column(db.String(20), nullable=False)

class Teacher(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(30), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    grade = db.Column(db.Integer, nullable=False)
    class_num = db.Column(db.Integer, nullable=False)
    is_approved = db.Column(db.Boolean, default=False)

class QuestionTemplate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey('teacher.id'), nullable=False)
    question = db.Column(db.Text, nullable=False)

# === PATCH: DB 자동 생성(폴백 sqlite일 때만) ===
if (database_url.startswith('sqlite:///')
    and not os.path.exists(sqlite_path)):
    with app.app_context():
        db.create_all()

# === PATCH: 헬스체크(배포/슬립 대응) ===
@app.route('/healthz')
def healthz():
    return {'ok': True, 'time_kst': now_kst_str()}, 200

# === PATCH: DB 점검용(선택) ===
@app.get("/dbcheck")
def dbcheck():
    try:
        cnt = db.session.execute("SELECT COUNT(*) AS c FROM consult_request").first()[0]
        return {"ok": True, "db": database_url, "rows": cnt}, 200
    except Exception as e:
        return {"ok": False, "db": database_url, "error": str(e)}, 500

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/student_request', methods=['GET', 'POST'])
def student_request():
    if request.method == 'POST':
        applicant_type = request.form['applicant_type']

        if applicant_type == '학생':
            grade = int(request.form['grade_student'])
            class_num = int(request.form['class_num_student'])
            number = int(request.form['number_student'])
            name = request.form['name_student']
            content = request.form['content']
        else:
            grade = int(request.form['grade_parent'])
            class_num = int(request.form['class_num_parent'])
            number = int(request.form['number_parent'])
            name = request.form['name_parent']
            relation = request.form['relation']
            contact = request.form['contact']
            content = f"[관계: {relation}, 연락처: {contact}]\n{request.form['content']}"

        # === PATCH: 주제 선택 처리(기타 입력 반영) ===
        topic = request.form['topic']
        if topic == '기타':
            topic = (request.form.get('custom_topic') or '').strip() or '기타'

        new_request = ConsultRequest(
            grade=grade,
            class_num=class_num,
            number=number,
            name=name,
            password=request.form['password'],
            category="상담",
            topic=topic,  # ← topic 변수 사용
            content=content,
            date=now_kst_str()  # === PATCH: 표준 KST 포맷 사용
        )
        db.session.add(new_request)
        db.session.commit()
        return render_template('student_complete.html')

    return render_template('student_request.html')

@app.route('/check_request', methods=['GET', 'POST'])
def check_request():
    if request.method == 'POST':
        grade = int(request.form['grade'])
        class_num = int(request.form['class_num'])
        number = int(request.form['number'])
        name = request.form['name']
        pw = request.form['password']

        matched = ConsultRequest.query.filter_by(
            grade=grade,
            class_num=class_num,
            number=number,
            name=name,
            password=pw
        ).all()

        data = []
        for r in matched:
            log = ConsultLog.query.filter_by(request_id=r.id).first()
