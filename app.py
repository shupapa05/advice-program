from flask import Flask, render_template, request, redirect, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import os

app = Flask(__name__)
app.secret_key = 'your_secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///consulting.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

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

if not os.path.exists("consulting.db"):
    with app.app_context():
        db.create_all()

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

        new_request = ConsultRequest(
            grade=grade,
            class_num=class_num,
            number=number,
            name=name,
            password=request.form['password'],
            category="상담",
            topic=request.form['topic'],
            content=content,
            date=datetime.now().strftime('%Y-%m-%d %H:%M')
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
            status = '✅ 확인됨' if log else '🟡 대기 중'
            answer = log.memo if log else ''
            data.append({
                'id': r.id,
                'date': r.date,
                'topic': r.topic,
                'content': r.content,
                'status': status,
                'answer': answer
            })

        return render_template('my_requests.html', data=data, name=name)

    return render_template('check_request.html')

@app.route('/teacher_signup', methods=['GET', 'POST'])
def teacher_signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        confirm = request.form['confirm']
        grade = int(request.form['grade'])
        class_num = int(request.form['class_num'])
        signup_code = request.form['signup_code']

        if signup_code != 'PAJU2025':
            return "올바른 가입 코드가 아닙니다."

        if password != confirm:
            return "비밀번호가 일치하지 않습니다."

        existing = Teacher.query.filter_by(username=username).first()
        if existing:
            return "이미 존재하는 아이디입니다."

        new_teacher = Teacher(
            username=username,
            password=password,
            grade=grade,
            class_num=class_num,
            is_approved=False
        )
        db.session.add(new_teacher)
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

    filtered_requests = ConsultRequest.query.filter_by(
        grade=grade,
        class_num=class_num
    ).order_by(ConsultRequest.date.desc()).all()

    result = []
    for r in filtered_requests:
        log = ConsultLog.query.filter_by(request_id=r.id).first()
        checked = '✅' if log else '🟡'
        btn_label = '수정' if log else '작성'
        is_parent = r.content.strip().startswith('[관계:')
        applicant_type = '👨‍👩‍👧 학부모' if is_parent else '👦 학생'

        result.append({
            'id': r.id,
            'date': r.date,
            'grade': r.grade,
            'class_num': r.class_num,
            'number': r.number,
            'name': r.name,
            'topic': r.topic,
            'content': r.content,
            'checked': checked,
            'btn_label': btn_label,
            'applicant_type': applicant_type,
            'answer': log.memo if log else ''
        })

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
            log.date = datetime.now().strftime('%Y-%m-%d %H:%M')
        else:
            log = ConsultLog(
                request_id=req_id,
                teacher_name=session['teacher_username'],
                memo=memo,
                date=datetime.now().strftime('%Y-%m-%d %H:%M')
            )
            db.session.add(log)

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
        topic = r.topic
        topic_count[topic] = topic_count.get(topic, 0) + 1
        grade_count[r.grade] = grade_count.get(r.grade, 0) + 1

    return render_template('statistics.html', topic_count=topic_count, grade_count=grade_count)

@app.route('/question_template', methods=['GET', 'POST'])
def question_template():
    if 'teacher_id' not in session:
        return redirect('/teacher_login')

    if request.method == 'POST':
        question = request.form['question']
        new_q = QuestionTemplate(teacher_id=session['teacher_id'], question=question)
        db.session.add(new_q)
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

# ✅ 상담자료실 연동
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
FOLDER_ID = '12osonR4XQbgmsIUCEgrUwMCJy7dEvWlm'  # 상담자료실 공유 폴더 ID

@app.route('/materials')
def materials():
    creds = Credentials.from_service_account_file('credentials.json', scopes=SCOPES)
    service = build('drive', 'v3', credentials=creds)

    results = service.files().list(
        q=f"'{FOLDER_ID}' in parents and trashed=false",
        fields="files(id, name, mimeType, webViewLink)",
        orderBy="name"
    ).execute()

    files = results.get('files', [])
    print("가져온 파일 목록:", files)

    return render_template('materials.html', files=files)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
