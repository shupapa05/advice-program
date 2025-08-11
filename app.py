from flask import Flask, render_template, request, redirect, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os, logging
from zoneinfo import ZoneInfo

app = Flask(__name__)

# ── 기본 설정 ────────────────────────────────────────────────────────────────
app.secret_key = os.getenv('SECRET_KEY', 'your_secret_key')

# DB 경로: Render에선 DATA_DIR=/data(퍼시스턴트 디스크) 권장, 없으면 instance 사용
basedir = os.path.abspath(os.path.dirname(__file__))
instance_dir = os.path.join(basedir, 'instance')
os.makedirs(instance_dir, exist_ok=True)

data_dir = os.getenv('DATA_DIR')  # 예: /data (Render Persistent Disk)
local_db_path = os.path.join(instance_dir, 'consulting.db')
sqlite_path = os.path.join(data_dir, 'consulting.db') if data_dir else local_db_path

database_url = os.getenv('DATABASE_URL') or f"sqlite:///{sqlite_path}"
app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# 시간/로그
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
KST = ZoneInfo("Asia/Seoul")
def now_kst_str():
    return datetime.now(KST).strftime('%Y-%m-%d %H:%M')

# ── 모델 ────────────────────────────────────────────────────────────────────
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

# 최초 구동 시 비어 있으면 생성(스키마만). 기존 파일은 건드리지 않음.
if database_url.startswith('sqlite:///'):
    db_file = database_url.replace('sqlite:///', '', 1)
    if not os.path.exists(db_file):
        with app.app_context():
            db.create_all()

# ── 헬스체크 ────────────────────────────────────────────────────────────────
@app.route('/healthz')
def healthz():
    return {'ok': True, 'time_kst': now_kst_str()}, 200

# ── 라우트 ──────────────────────────────────────────────────────────────────
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

        # 주제 선택(‘기타’ 처리 포함)
        topic = request.form['topic']
        if topic == '기타':
            topic = (request.form.get('custom_topic') or '').strip() or '기타'

        new_request = ConsultRequest(
            grade=grade, class_num=class_num, number=number, name=name,
            password=request.form['password'], category="상담",
            topic=topic, content=content, date=now_kst_str()
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
            grade=grade, class_num=class_num, number=number, name=name, password=pw
        ).all()

        data = []
        for r in matched:
            log = ConsultLog.query.filter_by(request_id=r.id).first()
            status = '✅ 확인됨' if log else '🟡 대기 중'
            answer = log.memo if log else ''
            data.append({
                'id': r.id, 'date': r.date, 'topic': r.topic,
                'content': r.content, 'status': status, 'answer': answer
            })
        return render_template('my_requests.html', data=data, name=name)

    return render_template('check_request.html')

@app.route('/teacher_signup', methods=['GET', 'POST'])
def teacher_signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        confirm  = request.form['confirm']
        grade    = int(request.form['grade'])
        class_num= int(request.form['class_num'])
        signup_code = request.form['signup_code']

        if signup_code != 'PAJU2025':
            return "올바른 가입 코드가 아닙니다."
        if password != confirm:
            return "비밀번호가 일치하지 않습니다."
        if Teacher.query.filter_by(username=username).first():
            return "이미 존재하는 아이디입니다."

        db.session.add(Teacher(
            username=username, password=password, grade=grade,
            class_num=class_num, is_approved=False
        ))
        db.session.commit()
        return "가입이 완료되었습니다. 관리자의 승인 후 로그인할 수 있습니다."
    return render_template('teacher_signup.html')

@app.route('/teacher_login', methods=['GET', 'POST'])
def teacher_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        teacher = Teacher.query.filter_by(username=username, password=password).first()
        if teacher:
            if not teacher.is_approved:
                return render_template("teacher_login.html", message="⛔ 승인되지 않은 계정입니다.")
            session['teacher_id'] = teacher.id
            session['teacher_username'] = teacher.username
            session['grade'] = teacher.grade
            session['class_num'] = teacher.class_num
            return redirect('/teacher_home')
        else:
            return render_template("teacher_login.html", message="❌ 아이디 또는 비밀번호가 올바르지 않습니다.")
    return render_template('teacher_login.html')

@app.route('/teacher_home')
def teacher_home():
    if 'teacher_id' not in session:
        return redirect('/teacher_login')
    return render_template('teacher_home.html', username=session['teacher_username'])

@app.route('/consult_list')
def consult_list():
    if 'teacher_id' not in session:
        return redirect('/teacher_login')

    grade = session['grade']
    class_num = session['class_num']
    filtered_requests = (ConsultRequest.query
                         .filter_by(grade=grade, class_num=class_num)
                         .order_by(ConsultRequest.date.desc())
                         .all())

    result = []
    for r in filtered_requests:
        log = ConsultLog.query.filter_by(request_id=r.id).first()
        checked = '✅' if log else '🟡'
        btn_label = '수정' if log else '작성'
        is_parent = (r.content or '').strip().startswith('[관계:')
        applicant_type = '👨‍👩‍👧 학부모' if is_parent else '👦 학생'
        result.append({
            'id': r.id, 'date': r.date, 'grade': r.grade, 'class_num': r.class_num,
            'number': r.number, 'name': r.name, 'topic': r.topic, 'content': r.content,
            'checked': checked, 'btn_label': btn_label, 'applicant_type': applicant_type,
            'answer': log.memo if log else ''
        })

    # 신청일 '수정' UI는 템플릿에서 제거하거나 그대로 날짜만 표시하도록 해 두세요.
    return render_template('consult_list.html', requests=result)

@app.route('/write_log/<int:req_id>', methods=['GET', 'POST'])
def write_log(req_id):
    if 'teacher_id' not in session:
        return redirect('/teacher_login')

    request_data = ConsultRequest.query.get_or_404(req_id)
    log = ConsultLog.query.filter_by(request_id=req_id).first()

    if request.method == 'POST':
        memo = request.form['memo']
        if log:
            log.memo = memo
            log.date = now_kst_str()
        else:
            db.session.add(ConsultLog(
                request_id=req_id, teacher_name=session['teacher_username'],
                memo=memo, date=now_kst_str()
            ))
        db.session.commit()
        return redirect('/consult_list')

    return render_template('write_log.html', request_data=request_data, log=log)

@app.route('/statistics')
def statistics():
    if 'teacher_id' not in session:
        return redirect('/teacher_login')

    logs = ConsultLog.query.all()
    requests = ConsultRequest.query.all()

    topic_count = {}
    grade_count = {}
    for r in requests:
        topic_count[r.topic] = topic_count.get(r.topic, 0) + 1
        grade_count[r.grade] = grade_count.get(r.grade, 0) + 1

    return render_template('statistics.html', topic_count=topic_count, grade_count=grade_count)

@app.route('/question_template', methods=['GET', 'POST'])
def question_template():
    if 'teacher_id' not in session:
        return redirect('/teacher_login')

    if request.method == 'POST':
        question = request.form['question']
        db.session.add(QuestionTemplate(teacher_id=session['teacher_id'], question=question))
        db.session.commit()
        return redirect('/question_template')

    questions = QuestionTemplate.query.filter_by(teacher_id=session['teacher_id']).all()
    return render_template('question_template.html', questions=questions)

@app.route('/view_answer/<int:req_id>')
def view_answer(req_id):
    log = ConsultLog.query.filter_by(request_id=req_id).first()
    if not log:
        return "아직 답변이 작성되지 않았습니다."
    return render_template('view_answer.html', log=log)

@app.route('/teacher_logout')
def teacher_logout():
    session.pop('teacher_id', None)
    session.pop('teacher_username', None)
    session.pop('grade', None)
    session.pop('class_num', None)
    return redirect('/')

# 📂 상담자료실: 외부 사이트로 리다이렉트 (로그인 필요)
@app.route('/materials')
def materials():
    if 'teacher_id' not in session:
        return redirect('/teacher_login')
    target_url = os.getenv('MATERIALS_URL', 'https://sites.google.com/paju.es.kr/mindtalkhub')
    return redirect(target_url, code=302)

# 에러 핸들러(선택)
@app.errorhandler(500)
def handle_500(e):
    app.logger.exception('Server Error')
    return "<h3>서버 오류가 발생했습니다. 로그를 확인해 주세요.</h3>", 500

# ── 관리자: 미승인 교사 승인 ────────────────────────────────────────────────
@app.route('/admin/approve_teachers', methods=['GET', 'POST'])
def approve_teachers():
    if request.method == 'POST':
        teacher_id = int(request.form['teacher_id'])
        teacher = Teacher.query.get(teacher_id)
        if teacher:
            teacher.is_approved = True
            db.session.commit()
    unapproved = Teacher.query.filter_by(is_approved=False).all()
    return render_template('approve_teachers.html', teachers=unapproved)

# ── 로컬 실행용 ─────────────────────────────────────────────────────────────
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
