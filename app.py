import os
from datetime import date, datetime, time, timedelta

from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'PASTE-YOUR-OWN-LONG-RANDOM-KEY-HERE')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///emp.db'
db = SQLAlchemy(app)

# The exam types and statuses from the brief
EXAM_TYPES = ['Viva', 'Practical', 'Project Demo', 'Assessment']
EXAM_STATUSES = ['Draft', 'Slot Creation', 'Booking Open', 'Closed', 'Completed']


# ---------------- Database tables ----------------

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    phone = db.Column(db.String(20), default='')
    department = db.Column(db.String(100), default='')
    role = db.Column(db.String(20), nullable=False)       # admin, examiner, student
    status = db.Column(db.String(20), default='active')   # pending, approved, deactivated, active


class Course(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(300), default='')
    status = db.Column(db.String(20), default='Active')   # Active, Inactive
    exams = db.relationship('Exam', backref='course', cascade='all, delete-orphan')


class Exam(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    exam_type = db.Column(db.String(30), nullable=False)
    duration = db.Column(db.Integer, nullable=False)      # in minutes
    max_marks = db.Column(db.Integer, nullable=False)
    slot_start = db.Column(db.Date, nullable=False)       # slot creation period
    slot_end = db.Column(db.Date, nullable=False)
    book_start = db.Column(db.Date, nullable=False)       # booking period
    book_end = db.Column(db.Date, nullable=False)         # last day to cancel a booking
    slot_creation_open = db.Column(db.Boolean, default=False)  # admin switch
    booking_open = db.Column(db.Boolean, default=False)       # admin switch
    status = db.Column(db.String(30), default='Draft')        # label worked out from the switches
    rubrics = db.relationship('Rubric', backref='exam', cascade='all, delete-orphan')
    slots = db.relationship('Slot', backref='exam', cascade='all, delete-orphan')
    assignments = db.relationship('Assignment', backref='exam', cascade='all, delete-orphan')


class Assignment(db.Model):
    # Which examiners are assigned to which examination
    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.Integer, db.ForeignKey('exam.id'), nullable=False)
    examiner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    examiner = db.relationship('User')


class Rubric(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.Integer, db.ForeignKey('exam.id'), nullable=False)
    criterion = db.Column(db.String(100), nullable=False)
    max_marks = db.Column(db.Integer, nullable=False)
    weightage = db.Column(db.Float, default=1.0)
    description = db.Column(db.String(300), default='')


class Slot(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.Integer, db.ForeignKey('exam.id'), nullable=False)
    examiner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    slot_date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    capacity = db.Column(db.Integer, nullable=False)
    cancelled = db.Column(db.Boolean, default=False)
    examiner = db.relationship('User')
    bookings = db.relationship('Booking', backref='slot', cascade='all, delete-orphan')


class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    slot_id = db.Column(db.Integer, db.ForeignKey('slot.id'), nullable=False)
    booked_on = db.Column(db.Date, default=date.today)
    status = db.Column(db.String(20), default='Booked')   # Booked, Cancelled, Completed
    student = db.relationship('User')
    evaluation = db.relationship('Evaluation', backref='booking', uselist=False,
                                 cascade='all, delete-orphan')


class Evaluation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey('booking.id'), unique=True, nullable=False)
    total = db.Column(db.Float, default=0)
    remarks = db.Column(db.String(300), default='')
    published = db.Column(db.Boolean, default=True)
    scores = db.relationship('Score', backref='evaluation', cascade='all, delete-orphan')


class Score(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    evaluation_id = db.Column(db.Integer, db.ForeignKey('evaluation.id'), nullable=False)
    rubric_id = db.Column(db.Integer, db.ForeignKey('rubric.id'), nullable=False)
    marks = db.Column(db.Float, default=0)


# ---------------- Helper functions ----------------

def current_user():
    user_id = session.get('user_id')
    if user_id is None:
        return None
    return db.session.get(User, user_id)


def is_role(role):
    # Only a logged-in user with this role, who is approved or active, may use the page
    user = current_user()
    if user is None or user.role != role:
        return False
    return user.status in ('approved', 'active')


@app.context_processor
def send_helpers():
    return {'me': current_user(), 'seats_left': seats_left, 'seats_taken': seats_taken,
            'slot_status': slot_status}


def to_int(text):
    try:
        return int(text)
    except (TypeError, ValueError):
        return None


def to_float(text):
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def to_date(text):
    try:
        return datetime.strptime(text, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return None


def to_time(text):
    try:
        return datetime.strptime(text, '%H:%M').time()
    except (TypeError, ValueError):
        return None


def matches(q, item_id, text):
    # Search box: empty shows everything, a number matches the ID, text matches the name
    if q == '':
        return True
    return q == str(item_id) or q.lower() in text.lower()


def seats_taken(slot):
    return Booking.query.filter(Booking.slot_id == slot.id, Booking.status != 'Cancelled').count()


def seats_left(slot):
    return slot.capacity - seats_taken(slot)


def can_book(exam):
    # Students can book only when the admin has opened booking and today is inside the booking dates
    today = date.today()
    return exam.booking_open and exam.book_start <= today <= exam.book_end


def can_create_slots(exam):
    # Examiners can create slots only when the admin has opened slot creation and today is inside the dates
    today = date.today()
    return exam.slot_creation_open and exam.slot_start <= today <= exam.slot_end


def slot_status(slot):
    if slot.cancelled:
        return 'Cancelled'
    if slot.slot_date < date.today():
        return 'Completed'
    if seats_left(slot) <= 0:
        return 'Full'
    return 'Available'


def make_status(old_status, slot_open, book_open, completed):
    # The status label is worked out from the admin's switches
    if completed:
        return 'Completed'
    if book_open:
        return 'Booking Open'
    if slot_open:
        return 'Slot Creation'
    if old_status in ('Slot Creation', 'Booking Open', 'Closed'):
        return 'Closed'
    return 'Draft'


def already_booked(student_id, exam_id):
    for booking in Booking.query.filter_by(student_id=student_id).all():
        if booking.status != 'Cancelled' and booking.slot.exam_id == exam_id:
            return True
    return False


# ---------------- Login, register, logout ----------------

@app.route('/')
def home():
    me = current_user()
    if me is None:
        return redirect(url_for('login'))
    if me.role == 'admin':
        return redirect(url_for('admin_page'))
    if me.role == 'examiner':
        return redirect(url_for('examiner_page'))
    return redirect(url_for('student_page'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        user = User.query.filter_by(email=email).first()
        if user is None or not check_password_hash(user.password, password):
            flash('Wrong email or password.')
        elif user.role == 'examiner' and user.status == 'pending':
            flash('Your examiner account is waiting for admin approval.')
        elif user.status == 'deactivated':
            flash('Your account is deactivated. Please contact the admin.')
        else:
            session['user_id'] = user.id
            return redirect(url_for('home'))
    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        role = request.form.get('role', '')
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        phone = request.form.get('phone', '').strip()
        department = request.form.get('department', '').strip()
        if role not in ('examiner', 'student'):
            flash('Please choose Examiner or Student.')
        elif name == '' or email == '' or password == '':
            flash('Name, email and password are required.')
        elif User.query.filter_by(email=email).first() is not None:
            flash('This email is already registered.')
        else:
            status = 'pending' if role == 'examiner' else 'active'
            db.session.add(User(name=name, email=email, password=generate_password_hash(password),
                                phone=phone, department=department, role=role, status=status))
            db.session.commit()
            if role == 'examiner':
                flash('Registration done. Please wait for admin approval before you log in.')
            else:
                flash('Registration done. You can log in now.')
            return redirect(url_for('login'))
    return render_template('register.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('You are logged out.')
    return redirect(url_for('login'))


# ---------------- Admin ----------------

@app.route('/admin')
def admin_page():
    if not is_role('admin'):
        return redirect(url_for('login'))
    q = request.args.get('q', '').strip()
    course_id = to_int(request.args.get('edit_course', ''))
    exam_id = to_int(request.args.get('edit_exam', ''))
    rubric_exam_id = to_int(request.args.get('rubrics', ''))
    edit_course = db.session.get(Course, course_id) if course_id else None
    edit_exam = db.session.get(Exam, exam_id) if exam_id else None
    rubric_exam = db.session.get(Exam, rubric_exam_id) if rubric_exam_id else None
    rubric_id = to_int(request.args.get('edit_rubric', ''))
    rubric_row = db.session.get(Rubric, rubric_id) if rubric_id else None
    edit_rubric = rubric_row if (rubric_row and rubric_exam and rubric_row.exam_id == rubric_exam.id) else None
    assigned_ids = [a.examiner_id for a in edit_exam.assignments] if edit_exam else []

    all_examiners = User.query.filter_by(role='examiner').order_by(User.id).all()
    approved_examiners = [e for e in all_examiners if e.status == 'approved']
    all_students = User.query.filter_by(role='student').order_by(User.id).all()
    all_exams = Exam.query.order_by(Exam.id).all()
    all_bookings = Booking.query.order_by(Booking.id).all()
    all_slots = Slot.query.order_by(Slot.slot_date, Slot.start_time).all()

    stats = {
        'courses': Course.query.count(),
        'exams': len(all_exams),
        'examiners': len(all_examiners),
        'students': len(all_students),
        'slots': len(all_slots),
        'bookings': len(all_bookings),
    }
    return render_template(
        'admin.html', q=q, stats=stats,
        courses=Course.query.order_by(Course.id).all(),
        edit_course=edit_course, edit_exam=edit_exam, assigned_ids=assigned_ids,
        rubric_exam=rubric_exam, approved_examiners=approved_examiners,
        exams=[e for e in all_exams if matches(q, e.id, e.name)],
        examiners=[e for e in all_examiners if matches(q, e.id, e.name)],
        students=[s for s in all_students if matches(q, s.id, s.name)],
        bookings=[b for b in all_bookings if matches(q, b.id, b.student.name)],
        slots=all_slots, exam_types=EXAM_TYPES, exam_statuses=EXAM_STATUSES,
        edit_rubric=edit_rubric,
    )


@app.route('/admin/password', methods=['POST'])
def admin_password():
    if not is_role('admin'):
        return redirect(url_for('login'))
    new_password = request.form.get('new_password', '')
    if len(new_password) < 6:
        flash('The new password needs at least 6 characters.')
    else:
        me = current_user()
        me.password = generate_password_hash(new_password)
        db.session.commit()
        flash('Admin password changed.')
    return redirect(url_for('admin_page'))


@app.route('/admin/course/save', methods=['POST'])
def admin_course_save():
    if not is_role('admin'):
        return redirect(url_for('login'))
    course_id = to_int(request.form.get('id', ''))
    code = request.form.get('code', '').strip().upper()
    name = request.form.get('name', '').strip()
    description = request.form.get('description', '').strip()
    status = request.form.get('status', 'Active')
    if code == '' or name == '':
        flash('Course code and name are required.')
    elif Course.query.filter(Course.code == code, Course.id != (course_id or 0)).first() is not None:
        flash('That course code already exists.')
    else:
        course = db.session.get(Course, course_id) if course_id else None
        if course is None:
            course = Course()
            db.session.add(course)
        course.code = code
        course.name = name
        course.description = description
        course.status = status
        db.session.commit()
        flash('Course saved.')
    return redirect(url_for('admin_page'))


@app.route('/admin/course/<int:course_id>/delete', methods=['POST'])
def admin_course_delete(course_id):
    if not is_role('admin'):
        return redirect(url_for('login'))
    db.session.delete(db.get_or_404(Course, course_id))
    db.session.commit()
    flash('Course deleted, with its examinations.')
    return redirect(url_for('admin_page'))


@app.route('/admin/exam/save', methods=['POST'])
def admin_exam_save():
    if not is_role('admin'):
        return redirect(url_for('login'))
    exam_id = to_int(request.form.get('id', ''))
    course_id = to_int(request.form.get('course_id', ''))
    name = request.form.get('name', '').strip()
    exam_type = request.form.get('exam_type', '')
    duration = to_int(request.form.get('duration', ''))
    max_marks = to_int(request.form.get('max_marks', ''))
    slot_start = to_date(request.form.get('slot_start', ''))
    slot_end = to_date(request.form.get('slot_end', ''))
    book_start = to_date(request.form.get('book_start', ''))
    book_end = to_date(request.form.get('book_end', ''))
    slot_open = 'slot_creation_open' in request.form
    book_open = 'booking_open' in request.form
    completed = 'completed' in request.form
    examiner_ids = request.form.getlist('examiner_ids')

    if None in (course_id, duration, max_marks, slot_start, slot_end, book_start, book_end) or name == '':
        flash('Fill in every field with a valid value.')
    elif db.session.get(Course, course_id) is None:
        flash('Choose a valid course.')
    elif exam_type not in EXAM_TYPES:
        flash('Choose a valid exam type.')
    elif duration < 1 or max_marks < 1:
        flash('Duration and max marks must be more than 0.')
    elif slot_end < slot_start or book_end < book_start:
        flash('An end date cannot be before its start date.')
    else:
        exam = db.session.get(Exam, exam_id) if exam_id else None
        if exam is None:
            exam = Exam()
            db.session.add(exam)
        exam.course_id = course_id
        exam.name = name
        exam.exam_type = exam_type
        exam.duration = duration
        exam.max_marks = max_marks
        exam.slot_start = slot_start
        exam.slot_end = slot_end
        exam.book_start = book_start
        exam.book_end = book_end
        exam.slot_creation_open = slot_open
        exam.booking_open = book_open
        exam.status = make_status(exam.status, slot_open, book_open, completed)
        db.session.commit()

        # Replace the examiner list for this examination
        Assignment.query.filter_by(exam_id=exam.id).delete()
        for examiner_id in examiner_ids:
            if to_int(examiner_id) is not None:
                db.session.add(Assignment(exam_id=exam.id, examiner_id=to_int(examiner_id)))
        db.session.commit()
        flash('Examination saved.')
    return redirect(url_for('admin_page'))


@app.route('/admin/exam/<int:exam_id>/delete', methods=['POST'])
def admin_exam_delete(exam_id):
    if not is_role('admin'):
        return redirect(url_for('login'))
    db.session.delete(db.get_or_404(Exam, exam_id))
    db.session.commit()
    flash('Examination deleted.')
    return redirect(url_for('admin_page'))


@app.route('/admin/rubric/save', methods=['POST'])
def admin_rubric_save():
    if not is_role('admin'):
        return redirect(url_for('login'))
    rubric_id = to_int(request.form.get('id', ''))
    exam_id = to_int(request.form.get('exam_id', ''))
    criterion = request.form.get('criterion', '').strip()
    max_marks = to_int(request.form.get('max_marks', ''))
    weightage = to_float(request.form.get('weightage', ''))
    description = request.form.get('description', '').strip()
    exam = db.session.get(Exam, exam_id) if exam_id else None
    if exam is None or criterion == '' or max_marks is None or max_marks < 1 or not (weightage and weightage > 0):
        flash('Enter a criterion name, max marks above 0 and a weightage above 0.')
        return redirect(url_for('admin_page'))
    rubric = db.session.get(Rubric, rubric_id) if rubric_id else None
    if rubric is None:
        rubric = Rubric(exam_id=exam.id)
        db.session.add(rubric)
    rubric.criterion = criterion
    rubric.max_marks = max_marks
    rubric.weightage = weightage
    rubric.description = description
    db.session.commit()
    flash('Rubric criterion saved.')
    return redirect(url_for('admin_page', rubrics=exam.id))


@app.route('/admin/rubric/<int:rubric_id>/delete', methods=['POST'])
def admin_rubric_delete(rubric_id):
    if not is_role('admin'):
        return redirect(url_for('login'))
    rubric = db.get_or_404(Rubric, rubric_id)
    exam_id = rubric.exam_id
    Score.query.filter_by(rubric_id=rubric.id).delete()
    db.session.delete(rubric)
    db.session.commit()
    flash('Rubric criterion deleted.')
    return redirect(url_for('admin_page', rubrics=exam_id))


@app.route('/admin/examiner/add', methods=['POST'])
def admin_examiner_add():
    if not is_role('admin'):
        return redirect(url_for('login'))
    name = request.form.get('name', '').strip()
    email = request.form.get('email', '').strip().lower()
    password = request.form.get('password', '')
    if name == '' or email == '' or password == '':
        flash('Name, email and password are required.')
    elif User.query.filter_by(email=email).first() is not None:
        flash('This email is already registered.')
    else:
        db.session.add(User(name=name, email=email, password=generate_password_hash(password),
                            phone=request.form.get('phone', '').strip(),
                            department=request.form.get('department', '').strip(),
                            role='examiner', status='approved'))
        db.session.commit()
        flash('Examiner added and approved.')
    return redirect(url_for('admin_page'))


@app.route('/admin/examiner/<int:user_id>/status', methods=['POST'])
def admin_examiner_status(user_id):
    if not is_role('admin'):
        return redirect(url_for('login'))
    user = db.get_or_404(User, user_id)
    action = request.form.get('action', '')
    if user.role != 'examiner':
        flash('Only examiners can be approved or deactivated here.')
    elif action in ('approve', 'activate'):
        user.status = 'approved'
        db.session.commit()
        flash('Examiner approved.')
    elif action == 'deactivate':
        user.status = 'deactivated'
        db.session.commit()
        flash('Examiner deactivated.')
    return redirect(url_for('admin_page'))


@app.route('/admin/slot/<int:slot_id>/examiner', methods=['POST'])
def admin_slot_examiner(slot_id):
    if not is_role('admin'):
        return redirect(url_for('login'))
    slot = db.get_or_404(Slot, slot_id)
    new_id = to_int(request.form.get('examiner_id', ''))
    new_examiner = db.session.get(User, new_id) if new_id else None
    if new_examiner is None or new_examiner.role != 'examiner' or new_examiner.status != 'approved':
        flash('Choose an approved examiner.')
    else:
        slot.examiner_id = new_examiner.id
        if Assignment.query.filter_by(exam_id=slot.exam_id, examiner_id=new_examiner.id).first() is None:
            db.session.add(Assignment(exam_id=slot.exam_id, examiner_id=new_examiner.id))
        db.session.commit()
        flash('Examiner changed for this slot.')
    return redirect(url_for('admin_page'))


@app.route('/admin/slot/<int:slot_id>/cancel', methods=['POST'])
def admin_slot_cancel(slot_id):
    if not is_role('admin'):
        return redirect(url_for('login'))
    slot = db.get_or_404(Slot, slot_id)
    slot.cancelled = True
    for booking in slot.bookings:
        if booking.status == 'Booked':
            booking.status = 'Cancelled'
    db.session.commit()
    flash('Slot cancelled. Its active bookings were cancelled too.')
    return redirect(url_for('admin_page'))


@app.route('/admin/booking/<int:booking_id>/reschedule', methods=['POST'])
def admin_booking_reschedule(booking_id):
    if not is_role('admin'):
        return redirect(url_for('login'))
    booking = db.get_or_404(Booking, booking_id)
    new_slot_id = to_int(request.form.get('new_slot_id', ''))
    new_slot = db.session.get(Slot, new_slot_id) if new_slot_id else None
    if booking.status != 'Booked':
        flash('Only active bookings can be moved.')
    elif new_slot is None or new_slot.exam_id != booking.slot.exam_id:
        flash('Choose a slot of the same examination.')
    elif seats_left(new_slot) <= 0:
        flash('That slot is full.')
    else:
        booking.slot_id = new_slot.id
        db.session.commit()
        flash('Booking moved to the new slot.')
    return redirect(url_for('admin_page'))


# ---------------- Examiner ----------------

@app.route('/examiner')
def examiner_page():
    if not is_role('examiner'):
        return redirect(url_for('login'))
    me = current_user()
    assigned_exams = [a.exam for a in Assignment.query.filter_by(examiner_id=me.id).all()]
    my_slots = Slot.query.filter_by(examiner_id=me.id).order_by(Slot.slot_date, Slot.start_time).all()
    my_bookings = []
    for slot in my_slots:
        for booking in slot.bookings:
            if booking.status != 'Cancelled':
                my_bookings.append(booking)
    pending = len([b for b in my_bookings if b.status == 'Booked'])
    edit_id = to_int(request.args.get('edit_slot', ''))
    edit_slot = db.session.get(Slot, edit_id) if edit_id else None
    if edit_slot is not None and edit_slot.examiner_id != me.id:
        edit_slot = None
    return render_template('examiner.html', assigned_exams=assigned_exams, my_slots=my_slots,
                           my_bookings=my_bookings, pending=pending, edit_slot=edit_slot)


@app.route('/examiner/slot/save', methods=['POST'])
def examiner_slot_save():
    if not is_role('examiner'):
        return redirect(url_for('login'))
    me = current_user()
    slot_id = to_int(request.form.get('id', ''))
    slot = db.session.get(Slot, slot_id) if slot_id else None
    if slot is not None:
        exam = slot.exam  # editing keeps the same examination
    else:
        exam_id = to_int(request.form.get('exam_id', ''))
        exam = db.session.get(Exam, exam_id) if exam_id else None
    slot_date = to_date(request.form.get('slot_date', ''))
    start = to_time(request.form.get('start_time', ''))
    end = to_time(request.form.get('end_time', ''))
    capacity = to_int(request.form.get('capacity', ''))

    if slot_id and (slot is None or slot.examiner_id != me.id):
        flash('That slot is not yours.')
    elif exam is None or Assignment.query.filter_by(exam_id=exam.id, examiner_id=me.id).first() is None:
        flash('You are not assigned to this examination.')
    elif None in (slot_date, start, end, capacity):
        flash('Enter a valid date, times and number of seats.')
    elif start >= end or capacity < 1:
        flash('End time must be after start time, and seats must be at least 1.')
    elif slot is None and not can_create_slots(exam):
        flash('Slot creation is not open for this examination right now.')
    elif slot is not None and (slot.cancelled or date.today() >= exam.book_start or seats_taken(slot) > 0):
        flash('This slot can no longer be changed.')
    else:
        if slot is None:
            slot = Slot(exam_id=exam.id, examiner_id=me.id)
            db.session.add(slot)
        slot.slot_date = slot_date
        slot.start_time = start
        slot.end_time = end
        slot.capacity = capacity
        db.session.commit()
        flash('Slot saved.')
    return redirect(url_for('examiner_page'))


@app.route('/examiner/slot/<int:slot_id>/delete', methods=['POST'])
def examiner_slot_delete(slot_id):
    if not is_role('examiner'):
        return redirect(url_for('login'))
    me = current_user()
    slot = db.get_or_404(Slot, slot_id)
    if slot.examiner_id != me.id:
        flash('That slot is not yours.')
    elif date.today() >= slot.exam.book_start or seats_taken(slot) > 0:
        flash('A slot can be removed only before booking starts and when nobody has booked it.')
    else:
        db.session.delete(slot)
        db.session.commit()
        flash('Slot removed.')
    return redirect(url_for('examiner_page'))


@app.route('/examiner/evaluate/<int:booking_id>', methods=['GET', 'POST'])
def examiner_evaluate(booking_id):
    if not is_role('examiner'):
        return redirect(url_for('login'))
    me = current_user()
    booking = db.get_or_404(Booking, booking_id)
    if booking.slot.examiner_id != me.id or booking.status == 'Cancelled':
        flash('You can only evaluate students booked in your own slots.')
        return redirect(url_for('examiner_page'))

    exam = booking.slot.exam
    if request.method == 'POST':
        total = 0
        marks_list = []
        for rubric in exam.rubrics:
            marks = to_float(request.form.get('mark_' + str(rubric.id), ''))
            if marks is None or not 0 <= marks <= rubric.max_marks:
                flash(f'Enter marks from 0 to {rubric.max_marks} for {rubric.criterion}.')
                return redirect(url_for('examiner_evaluate', booking_id=booking.id))
            marks_list.append((rubric, marks))
            total += marks

        if booking.evaluation is None:
            booking.evaluation = Evaluation()
        evaluation = booking.evaluation
        evaluation.total = total
        evaluation.remarks = request.form.get('remarks', '').strip()
        evaluation.published = 'publish' in request.form
        evaluation.scores = []
        for rubric, marks in marks_list:
            evaluation.scores.append(Score(rubric_id=rubric.id, marks=marks))
        booking.status = 'Completed'
        db.session.commit()
        flash('Evaluation saved.')
        return redirect(url_for('examiner_page'))

    evaluation = booking.evaluation
    existing = {}
    if evaluation is not None:
        for score in evaluation.scores:
            existing[score.rubric_id] = score.marks
    return render_template('evaluate.html', booking=booking, exam=exam, existing=existing,
                           remarks=evaluation.remarks if evaluation else '',
                           published=evaluation.published if evaluation else True)


# ---------------- Student ----------------

@app.route('/student')
def student_page():
    if not is_role('student'):
        return redirect(url_for('login'))
    me = current_user()
    today = date.today()
    q = request.args.get('q', '').strip()
    exam_type = request.args.get('exam_type', '')
    exam_status = request.args.get('exam_status', '')

    shown_exams = []
    for exam in Exam.query.order_by(Exam.id).all():
        if q and q.lower() not in exam.name.lower():
            continue
        if exam_type and exam.exam_type != exam_type:
            continue
        if exam_status and exam.status != exam_status:
            continue
        shown_exams.append(exam)

    available_slots = []
    for slot in Slot.query.order_by(Slot.slot_date, Slot.start_time).all():
        if slot.slot_date >= today and not slot.cancelled and can_book(slot.exam) and seats_left(slot) > 0:
            available_slots.append(slot)

    my_bookings = Booking.query.filter_by(student_id=me.id).all()
    upcoming = [b for b in my_bookings if b.status == 'Booked' and b.slot.slot_date >= today]
    results = [b for b in my_bookings if b.evaluation is not None and b.evaluation.published]
    return render_template('student.html', exams=shown_exams, available_slots=available_slots,
                           open_exams=[e for e in Exam.query.order_by(Exam.id).all() if can_book(e)],
                           my_bookings=my_bookings, upcoming=upcoming, results=results, today=today,
                           q=q, exam_type=exam_type, exam_status=exam_status,
                           exam_types=EXAM_TYPES, exam_statuses=EXAM_STATUSES)


@app.route('/student/book/<int:slot_id>', methods=['POST'])
def student_book(slot_id):
    if not is_role('student'):
        return redirect(url_for('login'))
    me = current_user()
    slot = db.get_or_404(Slot, slot_id)
    exam = slot.exam
    if not can_book(exam):
        flash('Booking is not open for this examination.')
    elif slot.slot_date < date.today():
        flash('This slot date has already passed.')
    elif slot.cancelled:
        flash('This slot was cancelled.')
    elif seats_left(slot) <= 0:
        flash('Sorry, this slot is full.')
    elif already_booked(me.id, exam.id):
        flash('You already have a booking for this examination.')
    else:
        db.session.add(Booking(student_id=me.id, slot_id=slot.id, booked_on=date.today()))
        db.session.commit()
        flash('Slot booked successfully.')
    return redirect(url_for('student_page'))


@app.route('/student/cancel/<int:booking_id>', methods=['POST'])
def student_cancel(booking_id):
    if not is_role('student'):
        return redirect(url_for('login'))
    me = current_user()
    booking = db.get_or_404(Booking, booking_id)
    if booking.student_id != me.id:
        flash('That is not your booking.')
    elif booking.status != 'Booked':
        flash('This booking cannot be cancelled.')
    elif date.today() > booking.slot.exam.book_end:
        flash('The cancellation deadline has passed.')
    else:
        booking.status = 'Cancelled'
        db.session.commit()
        flash('Booking cancelled. The seat is free again.')
    return redirect(url_for('student_page'))


@app.route('/student/profile', methods=['GET', 'POST'])
def student_profile():
    if not is_role('student'):
        return redirect(url_for('login'))
    me = current_user()
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        if name == '':
            flash('Name cannot be empty.')
        else:
            me.name = name
            me.phone = request.form.get('phone', '').strip()
            me.department = request.form.get('department', '').strip()
            new_password = request.form.get('new_password', '')
            if new_password != '':
                me.password = generate_password_hash(new_password)
            db.session.commit()
            flash('Profile updated.')
            return redirect(url_for('student_profile'))
    return render_template('profile.html')


# ---------------- JSON API (described in api.yaml) ----------------

def api_user():
    # The logged-in user, if the account is allowed to use the system
    me = current_user()
    if me is None or me.status not in ('approved', 'active'):
        return None
    return me


@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        data = {}
    email = str(data.get('email', '')).strip().lower()
    password = str(data.get('password', ''))
    user = User.query.filter_by(email=email).first()
    if user is None or not check_password_hash(user.password, password):
        return jsonify({'error': 'Wrong email or password'}), 401
    if user.status not in ('approved', 'active'):
        return jsonify({'error': 'This account is not allowed to log in'}), 403
    session['user_id'] = user.id
    return jsonify({'name': user.name, 'role': user.role})


@app.route('/api/exams')
def api_exams():
    if api_user() is None:
        return jsonify({'error': 'Please log in first'}), 401
    result = []
    for exam in Exam.query.order_by(Exam.id).all():
        result.append({'id': exam.id, 'name': exam.name, 'course': exam.course.code,
                       'type': exam.exam_type, 'max_marks': exam.max_marks, 'status': exam.status})
    return jsonify(result)


@app.route('/api/slots')
def api_slots():
    if api_user() is None:
        return jsonify({'error': 'Please log in first'}), 401
    result = []
    for slot in Slot.query.order_by(Slot.slot_date, Slot.start_time).all():
        result.append({'id': slot.id, 'exam': slot.exam.name, 'date': slot.slot_date.isoformat(),
                       'start': slot.start_time.strftime('%H:%M'), 'end': slot.end_time.strftime('%H:%M'),
                       'seats_left': seats_left(slot), 'status': slot_status(slot)})
    return jsonify(result)


@app.route('/api/bookings')
def api_bookings():
    me = api_user()
    if me is None:
        return jsonify({'error': 'Please log in first'}), 401
    if me.role != 'student':
        return jsonify({'error': 'Students only'}), 403
    result = []
    for booking in Booking.query.filter_by(student_id=me.id).all():
        marks = None
        if booking.evaluation is not None and booking.evaluation.published:
            marks = booking.evaluation.total
        result.append({'id': booking.id, 'exam': booking.slot.exam.name,
                       'date': booking.slot.slot_date.isoformat(), 'status': booking.status, 'marks': marks})
    return jsonify(result)


@app.route('/api/summary')
def api_summary():
    me = api_user()
    if me is None:
        return jsonify({'error': 'Please log in first'}), 401
    if me.role != 'admin':
        return jsonify({'error': 'Admins only'}), 403
    return jsonify({'courses': Course.query.count(), 'exams': Exam.query.count(),
                    'examiners': User.query.filter_by(role='examiner').count(),
                    'students': User.query.filter_by(role='student').count(),
                    'slots': Slot.query.count(), 'bookings': Booking.query.count()})


# ---------------- Demo data ----------------

def seed_demo_data():
    # Runs only on an empty database, so the admin is created once
    if User.query.filter_by(role='admin').first() is not None:
        return
    today = date.today()

    admin = User(name='System Admin', email='admin@emp.com', password=generate_password_hash(os.environ.get('ADMIN_PASSWORD', 'admin123')),
                 role='admin', status='active')
    anil = User(name='Dr. Anil Sharma', email='anil@emp.com', password=generate_password_hash('examiner123'),
                phone='9810011111', department='Computer Science', role='examiner', status='approved')
    priya = User(name='Prof. Priya Nair', email='priya@emp.com', password=generate_password_hash('examiner123'),
                 phone='9820022222', department='Information Technology', role='examiner', status='approved')
    suresh = User(name='Dr. Suresh Iyer', email='suresh@emp.com', password=generate_password_hash('examiner123'),
                  phone='9830033333', department='Computer Science', role='examiner', status='pending')
    aarav = User(name='Aarav Patel', email='aarav@emp.com', password=generate_password_hash('student123'),
                 phone='9840044444', department='Computer Science', role='student', status='active')
    ananya = User(name='Ananya Gupta', email='ananya@emp.com', password=generate_password_hash('student123'),
                  phone='9850055555', department='Information Technology', role='student', status='active')
    rohan = User(name='Rohan Verma', email='rohan@emp.com', password=generate_password_hash('student123'),
                 phone='9860066666', department='Computer Science', role='student', status='active')
    db.session.add_all([admin, anil, priya, suresh, aarav, ananya, rohan])

    dsa = Course(code='CS201', name='Data Structures', description='Core data structures')
    dbms = Course(code='CS305', name='Database Management Systems', description='Databases and SQL')
    db.session.add_all([dsa, dbms])
    db.session.commit()

    viva = Exam(course_id=dsa.id, name='DSA Viva', exam_type='Viva', duration=30, max_marks=50,
                slot_start=today - timedelta(days=5), slot_end=today + timedelta(days=20),
                book_start=today - timedelta(days=1), book_end=today + timedelta(days=15),
                status='Booking Open', booking_open=True)
    demo = Exam(course_id=dbms.id, name='DBMS Project Demo', exam_type='Project Demo', duration=20, max_marks=40,
                slot_start=today - timedelta(days=2), slot_end=today + timedelta(days=20),
                book_start=today + timedelta(days=21), book_end=today + timedelta(days=30),
                status='Slot Creation', slot_creation_open=True)
    db.session.add_all([viva, demo])
    db.session.commit()

    db.session.add(Assignment(exam_id=viva.id, examiner_id=anil.id))
    db.session.add(Assignment(exam_id=demo.id, examiner_id=priya.id))
    db.session.add_all([
        Rubric(exam_id=viva.id, criterion='Problem solving', max_marks=20),
        Rubric(exam_id=viva.id, criterion='Code explanation', max_marks=15),
        Rubric(exam_id=viva.id, criterion='Communication', max_marks=15),
    ])
    slot1 = Slot(exam_id=viva.id, examiner_id=anil.id, slot_date=today + timedelta(days=1),
                 start_time=time(10, 0), end_time=time(10, 30), capacity=2)
    slot2 = Slot(exam_id=viva.id, examiner_id=anil.id, slot_date=today + timedelta(days=2),
                 start_time=time(11, 0), end_time=time(11, 30), capacity=1)
    db.session.add_all([slot1, slot2])
    db.session.commit()

    db.session.add(Booking(student_id=aarav.id, slot_id=slot1.id, booked_on=today))
    db.session.commit()


with app.app_context():
    db.create_all()   # tables are created from the models in this file
    seed_demo_data()


if __name__ == '__main__':
    app.run(debug=True)
