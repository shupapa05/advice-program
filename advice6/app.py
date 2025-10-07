from flask import Flask, render_template, request, redirect, session, flash, url_for, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import os, re, logging
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")

app = Flask(__name__)

# 기능 토글
EDIT_DATE_ENABLED = os.getenv('EDIT_DATE_ENABLED', '1') == '1'          # 신청일(서버 DB) 수정 폼
EDIT_LOG_DATE_ENABLED = os.getenv('EDIT_LOG_DATE_ENABLED', '0') == '1'  # 교사 답변일 수정 UI

# Secret
app.secret_key = os.getenv('SECRET_KEY', 'your_secret_key')

# DB 설정 (Postgres -> fallback SQLite)
basedir = os.path.abspath(os.path.dirname(__file__))
sqlite_path = os.getenv("SQLITE_PATH") or os.path.join(basedir, "consulting.db")
database_url = os.getenv("DATABASE_URL") or ("sqlite:///" + sqlite_path.replace("\\", "/"))

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# 로깅
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')

def now_kst_str():
    return datetime.now(KST).strftime('%Y-%m-%d %H:%M')

# 문자열 ↔ datetime 유틸
def parse_dt(s: str):
    """consulting.db 문자열 날짜를 datetime(KST)으로 파싱."""
    if not s:
        return None
    for fmt in ('%Y-%m-%d %H:%M', '%Y/%m/%d %H:%M', '%Y.%m.%d %H:%M', '%Y-%m-%dT%H:%M'):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=KST)
        except ValueError:
            continue
    return None

def _to_input_value(dt_str_or_none):
    dt = parse_dt(dt_str_or_none) if dt_str_or_none else datetime.now(KST)
    return dt.astimezone(KST).strftime("%Y-%m-%dT%H:%M")  # input[type=datetime-local] 값

def _from_input_value(inp):
    # '2025-09-30T12:15' -> '2025-09-30 12:15'
    return inp.replace('T', ' ') if inp else datetime.now(KST).strftime("%Y-%m-%d %H:%M")

# === 모델 ===
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

# SQLite 자동 생성
if (database_url.startswith('sqlite:///') and not os.path.exists(sqlite_path)):
    with app.app_context():
        db.create_all()

# 헬스체크
@app.route('/healthz')
def healthz():
    return {'ok': True, 'time_kst': now_kst_str()}, 200

# DB 점검
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

# === 학생 신청 ===
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
            topic=topic,
            content=content,
            date=now_kst_str()
        )
        db.session.add(new_request)
        db.session.commit()
        return render_template('student_complete.html')

    return render_template('student_request.html')

# === 학생 신청 수정/삭제 ===
# 학생이 자기 신청내용을 수정 (비밀번호 없이, 기존 작성 폼과 동일 UI)
@app.route('/student_request_edit/<int:req_id>', methods=['GET', 'POST'])
def student_request_edit(req_id):
    r = ConsultRequest.query.get_or_404(req_id)

    # 돌아갈 위치: 쿼리 ?next=... 또는 폼 hidden next. 없으면 내 상담 내역(/check_request)로.
    next_url = request.args.get('next') or request.form.get('next') or url_for('check_request')

    if request.method == 'POST':
        # 주제: '기타' 선택 시 custom_topic 사용
        topic = (request.form.get('topic') or r.topic).strip()
        if topic == '기타':
            topic = (request.form.get('custom_topic') or '').strip() or '기타'

        # 내용
        content = (request.form.get('content') or r.content).strip()

        # 수정 반영
        r.topic = topic
        r.content = content
        db.session.commit()

        # 저장 후 원하는 페이지로
        return redirect(next_url)

    # GET: 편집 페이지 렌더링(기존 작성 폼과 유사 UI)
    # topic 목록은 기존 student_request.html 과 동일하게 맞춰 주세요.
    topics = ['친구관계', '학교생활', '정서·행동', '진로', '가족', '학업', '기타']
    return render_template(
        'student_request_edit.html',
        req=r,
        topics=topics,
        next_url=next_url
    )


@app.route('/student_request_delete/<int:req_id>', methods=['POST'])
def student_request_delete(req_id):
    r = ConsultRequest.query.get_or_404(req_id)
    pw = request.form.get('password', '')
    if r.password != pw:
        flash('비밀번호가 올바르지 않습니다.')
        return redirect(url_for('check_request'))
    ConsultLog.query.filter_by(request_id=req_id).delete()
    db.session.delete(r)
    db.session.commit()
    flash('삭제되었습니다.')
    return redirect(url_for('check_request'))

# === 내가 신청한 내역 보기 ===
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
                'id': r.id,
                'date': r.date,
                'topic': r.topic,
                'content': r.content,
                'status': status,
                'answer': answer
            })

        return render_template('my_requests.html', data=data, name=name)

    return render_template('check_request.html')

# === 교사 인증/홈 ===
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
        if Teacher.query.filter_by(username=username).first():
            return "이미 존재하는 아이디입니다."

        new_teacher = Teacher(
            username=username, password=password, grade=grade, class_num=class_num, is_approved=False
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

# === 담임용 목록(반 필터 + 스코프 전달) ===
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

    # 🔴 프런트 JS(Firestore 병합)가 사용할 스코프를 함께 전달
    return render_template(
        'consult_list.html',
        requests=result,
        edit_date_enabled=EDIT_DATE_ENABLED,
        filter_grade=grade,
        filter_class=class_num
    )

# === 상담일지 작성/수정 ===
FEATURE_LOG_DATE_EDIT = EDIT_LOG_DATE_ENABLED

@app.route('/write_log/<int:req_id>', methods=['GET', 'POST'])
def write_log(req_id):
    if 'teacher_id' not in session:
        return redirect('/teacher_login')

    request_data = ConsultRequest.query.get_or_404(req_id)

    # 🔒 권한: 담임 반만 접근
    if not (request_data.grade == session.get('grade') and
            request_data.class_num == session.get('class_num')):
        flash('이 반에 대한 권한이 없습니다.')
        return redirect(url_for('consult_list'))

    log = ConsultLog.query.filter_by(request_id=req_id).first()

    if request.method == 'POST':
        memo = request.form.get('memo', '').strip()
        apply_dt = request.form.get('apply_dt') == 'on'  # 체크됐을 때만 날짜 반영
        new_date_str = _from_input_value(request.form.get('log_dt')) if apply_dt else None

        if log:
            log.memo = memo
            if new_date_str:
                log.date = new_date_str
        else:
            log = ConsultLog(
                request_id=req_id,
                teacher_name=session.get('teacher_username'),
                memo=memo,
                date=new_date_str or now_kst_str()
            )
            db.session.add(log)

        db.session.commit()
        return redirect('/consult_list')

    # GET
    show_dt_edit = FEATURE_LOG_DATE_EDIT or (request.args.get('edit_dt') == '1')
    default_dt_input = _to_input_value(log.date if log else None)
    return render_template(
        'write_log.html',
        request_data=request_data,
        log=log,
        default_dt_input=default_dt_input,
        show_dt_edit=show_dt_edit
    )

# === 통계 ===
@app.route('/statistics')
def statistics():
    if 'teacher_id' not in session:
        return redirect('/teacher_login')

    requests = ConsultRequest.query.all()
    logs = ConsultLog.query.all()

    log_by_req_id = {}
    for lg in logs:
        cur = log_by_req_id.get(lg.request_id)
        if not cur:
            log_by_req_id[lg.request_id] = lg
        else:
            cur_dt = parse_dt(cur.date)
            lg_dt = parse_dt(lg.date)
            if cur_dt and lg_dt and lg_dt < cur_dt:
                log_by_req_id[lg.request_id] = lg

    now = datetime.now(KST)
    d7 = now - timedelta(days=7)
    d30 = now - timedelta(days=30)

    total = len(requests)
    handled = 0
    pending = 0
    by_topic = {}
    by_grade = {}
    by_grade_class = {}
    recent_unanswered = []
    teacher_activity_30d = {}
    parent_cnt = 0
    student_cnt = 0
    response_hours = []

    for r in requests:
        content = (r.content or "").strip()
        if content.startswith('[관계:'):
            parent_cnt += 1
        else:
            student_cnt += 1

        by_topic[r.topic] = by_topic.get(r.topic, 0) + 1
        by_grade[r.grade] = by_grade.get(r.grade, 0) + 1
        key_gc = (r.grade, r.class_num)
        by_grade_class[key_gc] = by_grade_class.get(key_gc, 0) + 1

        req_dt = parse_dt(r.date)
        lg = log_by_req_id.get(r.id)

        if lg:
            handled += 1
            lg_dt = parse_dt(lg.date)
            if req_dt and lg_dt and lg_dt >= req_dt:
                response_hours.append((lg_dt - req_dt).total_seconds() / 3600.0)
        else:
            pending += 1
            recent_unanswered.append({
                "id": r.id,
                "date": r.date,
                "grade": r.grade,
                "class_num": r.class_num,
                "number": r.number,
                "name": r.name,
                "topic": r.topic,
            })

    for lg in logs:
        lg_dt = parse_dt(lg.date)
        if lg_dt and lg_dt >= d30:
            teacher_activity_30d[lg.teacher_name] = teacher_activity_30d.get(lg.teacher_name, 0) + 1

    today = now.date()
    today_cnt = sum(1 for r in requests if (parse_dt(r.date) or now).date() == today)
    week_cnt = sum(1 for r in requests if (parse_dt(r.date) or now) >= d7)
    month_cnt = sum(1 for r in requests if (parse_dt(r.date) or now) >= d30)

    top_topics = sorted(by_topic.items(), key=lambda kv: kv[1], reverse=True)[:5]
    top_teachers_30d = sorted(teacher_activity_30d.items(), key=lambda kv: kv[1], reverse=True)[:5]

    recent_unanswered.sort(key=lambda x: (parse_dt(x["date"]) or now), reverse=True)
    recent_unanswered = recent_unanswered[:10]

    avg_response_h = round(sum(response_hours)/len(response_hours), 2) if response_hours else None
    handled_rate = round(handled / total * 100, 2) if total else 0.0
    parent_ratio = round(parent_cnt / total * 100, 2) if total else 0.0
    student_ratio = round(student_cnt / total * 100, 2) if total else 0.0

    by_grade_class_pretty = {}
    for (g, c), n in by_grade_class.items():
        by_grade_class_pretty.setdefault(g, {})[c] = n

    stats = {
        "total": total,
        "handled": handled,
        "pending": pending,
        "handled_rate": handled_rate,
        "today": today_cnt,
        "last7d": week_cnt,
        "last30d": month_cnt,
        "by_topic": by_topic,
        "top_topics": top_topics,
        "by_grade": by_grade,
        "by_grade_class": by_grade_class_pretty,
        "recent_unanswered": recent_unanswered,
        "teacher_activity_30d": dict(sorted(teacher_activity_30d.items(), key=lambda kv: kv[1], reverse=True)),
        "top_teachers_30d": top_teachers_30d,
        "applicant": {
            "student": student_cnt,
            "parent": parent_cnt,
            "student_ratio": student_ratio,
            "parent_ratio": parent_ratio,
        },
        "avg_response_hours": avg_response_h,
    }
    return render_template('statistics.html', stats=stats,
                           topic_count=by_topic, grade_count=by_grade)

# JSON 통계
@app.get('/api/stats')
def api_stats():
    if 'teacher_id' not in session:
        return jsonify({"ok": False, "error": "login required"}), 401

    requests = ConsultRequest.query.all()
    logs = ConsultLog.query.all()

    log_by_req_id = {}
    for lg in logs:
        log_by_req_id.setdefault(lg.request_id, lg)

    now = datetime.now(KST)
    d7 = now - timedelta(days=7)
    d30 = now - timedelta(days=30)

    total = len(requests)
    handled = sum(1 for r in requests if r.id in log_by_req_id)
    pending = total - handled
    today_cnt = sum(1 for r in requests if (parse_dt(r.date) or now).date() == now.date())
    week_cnt = sum(1 for r in requests if (parse_dt(r.date) or now) >= d7)
    month_cnt = sum(1 for r in requests if (parse_dt(r.date) or now) >= d30)

    by_topic, by_grade = {}, {}
    parent_cnt = 0
    student_cnt = 0
    response_hours = []

    for r in requests:
        by_topic[r.topic] = by_topic.get(r.topic, 0) + 1
        by_grade[r.grade] = by_grade.get(r.grade, 0) + 1
        if r.content.strip().startswith('[관계:'):
            parent_cnt += 1
        else:
            student_cnt += 1

        lg = log_by_req_id.get(r.id)
        if lg:
            rd = parse_dt(r.date)
            ld = parse_dt(lg.date)
            if rd and ld and ld >= rd:
                response_hours.append((ld - rd).total_seconds() / 3600.0)

    avg_response_h = round(sum(response_hours)/len(response_hours), 2) if response_hours else None
    handled_rate = round(handled / total * 100, 2) if total else 0.0

    return jsonify({
        "ok": True,
        "total": total,
        "handled": handled,
        "pending": pending,
        "handled_rate": handled_rate,
        "today": today_cnt,
        "last7d": week_cnt,
        "last30d": month_cnt,
        "by_topic": by_topic,
        "by_grade": by_grade,
        "applicant": {"student": student_cnt, "parent": parent_cnt},
        "avg_response_hours": avg_response_h,
    })

# 질문 템플릿
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

# 답변 보기
@app.route('/view_answer/<int:req_id>')
def view_answer(req_id):
    log = ConsultLog.query.filter_by(request_id=req_id).first()
    if not log:
        return "아직 답변이 작성되지 않았습니다."
    return render_template('view_answer.html', log=log)

# 로그아웃
@app.route('/teacher_logout')
def teacher_logout():
    session.pop('teacher_id', None)
    session.pop('teacher_username', None)
    session.pop('grade', None)
    session.pop('class_num', None)
    return redirect('/')

# 교사 승인
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

# 상담자료실
@app.route('/materials')
def materials():
    if 'teacher_id' not in session:
        return redirect('/teacher_login')
    return redirect("https://sites.google.com/paju.es.kr/mindtalkhub", code=302)

# 신청일 수정(서버 DB)
@app.route('/teacher/update_date', methods=['POST'])
def update_consult_date():
    if 'teacher_id' not in session:
        return redirect('/teacher_login')

    try:
        cid = int(request.form.get('id', '').strip())
    except (TypeError, ValueError):
        flash('잘못된 요청입니다.')
        return redirect(url_for('consult_list'))

    rec = ConsultRequest.query.get(cid)
    if not rec:
        flash('기록을 찾을 수 없습니다.')
        return redirect(url_for('consult_list'))

    # 🔒 본인 반만 수정 가능
    if not (rec.grade == session.get('grade') and rec.class_num == session.get('class_num')):
        flash('이 반에 대한 권한이 없습니다.')
        return redirect(url_for('consult_list'))

    raw = (request.form.get('date') or '').strip()
    if not raw:
        flash('날짜가 비었습니다.')
        return redirect(url_for('consult_list'))

    candidates = [raw, raw.replace('T', ' '), raw.replace('/', '-')]
    dt = None
    for s in candidates:
        for fmt in ('%Y-%m-%d %H:%M', '%Y-%m-%dT%H:%M', '%Y/%m/%d %H:%M', '%Y.%m.%d %H:%M'):
            try:
                dt = datetime.strptime(s, fmt)
                break
            except ValueError:
                continue
        if dt:
            break

    if not dt:
        m = re.search(r'(\d{4})\D?(\d{1,2})\D?(\d{1,2})\D+(\d{1,2})\D?(\d{1,2})', raw)
        if m:
            y, mo, d, h, mi = map(int, m.groups())
            mo = max(1, min(12, mo))
            d = max(1, min(31, d))
            h = max(0, min(23, h))
            mi = max(0, min(59, mi))
            dt = datetime(y, mo, d, h, mi)
            flash('입력 형식을 자동으로 보정했어요.')
        else:
            flash('날짜를 인식할 수 없어 현재 시각으로 저장했습니다.')
            dt = datetime.now(KST)

    rec.date = dt.strftime('%Y-%m-%d %H:%M')
    db.session.commit()
    flash('상담 신청일을 수정했습니다.')
    return redirect(url_for('consult_list'))

# 500 핸들러
@app.errorhandler(500)
def handle_500(e):
    app.logger.exception('Server Error')
    return "<h3>서버 오류가 발생했습니다. 로그를 확인해 주세요.</h3>", 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
