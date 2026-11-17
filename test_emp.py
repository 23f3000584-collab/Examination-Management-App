import os, sys, shutil
from datetime import date, timedelta, time
import tempfile
SRC = os.path.dirname(os.path.abspath(__file__))
DST = os.path.join(tempfile.mkdtemp(), 'EMP_Simple')
shutil.copytree(SRC, DST, ignore=shutil.ignore_patterns('__pycache__', 'instance', 'emp.db', '*.zip', '*.pyc'))
os.chdir(DST); sys.path.insert(0, DST)
if os.path.exists('instance/emp.db'):
    os.remove('instance/emp.db')
import app as emp
from app import app, db, User, Course, Exam, Assignment, Rubric, Slot, Booking, Evaluation
app.config['TESTING'] = True
today = date.today()
results = []

def check(label, ok):
    results.append(ok)
    print(('PASS ' if ok else 'FAIL ') + label)

def login(email, pw):
    c = app.test_client()
    c.post('/login', data={'email': email, 'password': pw})
    return c

def uid(email):
    with app.app_context():
        return User.query.filter_by(email=email).first().id

def eid(name):
    with app.app_context():
        return Exam.query.filter_by(name=name).first().id

def slot_of(exam_name, index=0):
    with app.app_context():
        e = Exam.query.filter_by(name=exam_name).first()
        return Slot.query.filter_by(exam_id=e.id).order_by(Slot.id).all()[index].id

def count(model, **kw):
    with app.app_context():
        return model.query.filter_by(**kw).count()

def get_row(model, **kw):
    with app.app_context():
        row = model.query.filter_by(**kw).first()
        return {c.name: getattr(row, c.name) for c in model.__table__.columns} if row else None

# ---------- 1. Access control ----------
anon = app.test_client()
admin = login('admin@emp.com', 'admin123')
anil = login('anil@emp.com', 'examiner123')
priya = login('priya@emp.com', 'examiner123')
aarav = login('aarav@emp.com', 'student123')
rohan = login('rohan@emp.com', 'student123')
ananya = login('ananya@emp.com', 'student123')
check('anonymous user is sent to login for /admin', anon.get('/admin').status_code == 302)
check('student cannot open /admin', aarav.get('/admin').status_code == 302)
check('examiner cannot open /student', anil.get('/student').status_code == 302)
check('pending examiner cannot log in', login('suresh@emp.com', 'examiner123').get('/examiner').status_code == 302)

# ---------- 2. Every page loads without an error ----------
pages = {
    admin: ['/admin', '/admin?q=aarav', '/admin?q=2', '/admin?edit_course=1', '/admin?edit_exam=1',
            '/admin?rubrics=1', '/admin?edit_exam=1&rubrics=1', '/admin?rubrics=1&edit_rubric=1'],
    anil: ['/examiner', '/examiner?edit_slot=1'],
    aarav: ['/student', '/student?q=DSA&exam_type=Viva&exam_status=Booking+Open', '/student/profile'],
    anon: ['/login', '/register', '/static/css/bootstrap.min.css'],
}
for client, paths in pages.items():
    for p in paths:
        r = client.get(p)
        check(f'page {p} loads (HTTP {r.status_code})', r.status_code == 200)

# ---------- 3. Registration ----------
c = app.test_client()
c.post('/register', data={'role': 'student', 'name': 'Meena Krishnan', 'email': 'meena@emp.com',
                          'password': 'student123', 'phone': '9870077777', 'department': 'Computer Science'})
check('student can register', count(User, email='meena@emp.com') == 1)
c.post('/register', data={'role': 'admin', 'name': 'Hacker', 'email': 'h@emp.com', 'password': 'x'})
check('admin cannot register', count(User, email='h@emp.com') == 0)
c.post('/register', data={'role': 'student', 'name': 'Dup', 'email': 'meena@emp.com', 'password': 'x'})
check('duplicate email is refused', count(User, email='meena@emp.com') == 1)
c.post('/register', data={'role': 'examiner', 'name': 'Kavya Menon', 'email': 'kavya@emp.com',
                          'password': 'examiner123', 'department': 'Computer Science'})
check('new examiner starts as pending', get_row(User, email='kavya@emp.com')['status'] == 'pending')
meena = login('meena@emp.com', 'student123')
check('registered student can log in', meena.get('/student').status_code == 200)

# ---------- 4. Admin: courses ----------
admin.post('/admin/course/save', data={'id': '', 'code': 'CS201', 'name': 'Duplicate', 'status': 'Active'})
check('duplicate course code is refused', count(Course, name='Duplicate') == 0)
admin.post('/admin/course/save', data={'id': '', 'code': 'cs410', 'name': 'Machine Learning', 'status': 'Active'})
ml_id = get_row(Course, code='CS410')['id']
check('admin adds a course', ml_id is not None)
admin.post('/admin/course/save', data={'id': str(ml_id), 'code': 'CS410', 'name': 'ML Basics', 'status': 'Active'})
check('admin edits a course', get_row(Course, code='CS410')['name'] == 'ML Basics')
admin.post(f'/admin/course/{ml_id}/delete')
check('admin deletes a course', count(Course, code='CS410') == 0)

# ---------- 5. Admin: examinations and timelines ----------
cs305 = get_row(Course, code='CS305')['id']
base = {'id': '', 'course_id': str(cs305), 'name': 'Lab Test', 'exam_type': 'Practical', 'duration': '60',
        'max_marks': '30', 'slot_creation_open': 'on', 'examiner_ids': [str(uid('anil@emp.com'))]}
bad = dict(base, slot_start=str(today), slot_end=str(today - timedelta(days=3)),
           book_start=str(today + timedelta(days=11)), book_end=str(today + timedelta(days=20)))
admin.post('/admin/exam/save', data=bad)
check('exam with end date before start date is refused', count(Exam, name='Lab Test') == 0)
good = dict(base, slot_start=str(today - timedelta(days=1)), slot_end=str(today + timedelta(days=10)),
            book_start=str(today + timedelta(days=11)), book_end=str(today + timedelta(days=20)))
admin.post('/admin/exam/save', data=good)
lab = eid('Lab Test')
check('admin creates an examination', lab is not None)
check('examiner is assigned to the examination', count(Assignment, exam_id=lab, examiner_id=uid('anil@emp.com')) == 1)
admin.post('/admin/rubric/save', data={'exam_id': str(lab), 'criterion': 'Lab work', 'max_marks': '30', 'weightage': '1', 'description': ''})
lab_rubric = get_row(Rubric, exam_id=lab)['id']
check('admin adds a rubric criterion', lab_rubric is not None)
admin.post(f'/admin/rubric/{lab_rubric}/delete')
check('admin deletes a rubric criterion', count(Rubric, exam_id=lab) == 0)
admin.post('/admin/rubric/save', data={'exam_id': str(lab), 'criterion': 'Lab work', 'max_marks': '30', 'weightage': '1', 'description': ''})

# ---------- 6. Admin: examiners ----------
admin.post('/admin/examiner/add', data={'name': 'Kiran Rao', 'email': 'kiran@emp.com', 'password': 'examiner123',
                                        'phone': '9880088888', 'department': 'IT'})
kiran = uid('kiran@emp.com')
check('lab examination is created with status Slot Creation', get_row(Exam, name='Lab Test')['status'] == 'Slot Creation')
check('admin adds an approved examiner', get_row(User, email='kiran@emp.com')['status'] == 'approved')
admin.post(f'/admin/examiner/{kiran}/status', data={'action': 'deactivate'})
check('deactivated examiner cannot log in', login('kiran@emp.com', 'examiner123').get('/examiner').status_code == 302)
admin.post(f'/admin/examiner/{kiran}/status', data={'action': 'activate'})
check('reactivated examiner can log in', login('kiran@emp.com', 'examiner123').get('/examiner').status_code == 200)
admin.post(f'/admin/examiner/{uid("kavya@emp.com")}/status', data={'action': 'approve'})
check('admin approves a pending examiner', get_row(User, email='kavya@emp.com')['status'] == 'approved')

# ---------- 7. Examiner: slot rules ----------
viva = eid('DSA Viva')
dbms = eid('DBMS Project Demo')
slot_day = lambda n: str(today + timedelta(days=n))
n_before = count(Slot, exam_id=viva)
anil.post('/examiner/slot/save', data={'id': '', 'exam_id': str(viva), 'slot_date': slot_day(5),
          'start_time': '09:00', 'end_time': '09:30', 'capacity': '2'})
check('examiner cannot create slot when status is Booking Open', count(Slot, exam_id=viva) == n_before)
anil.post('/examiner/slot/save', data={'id': '', 'exam_id': str(lab), 'slot_date': slot_day(2),
          'start_time': '12:00', 'end_time': '11:00', 'capacity': '2'})
check('examiner cannot save a slot where end is before start', count(Slot, exam_id=lab) == 0)
anil.post('/examiner/slot/save', data={'id': '', 'exam_id': str(lab), 'slot_date': slot_day(2),
          'start_time': '12:00', 'end_time': '13:00', 'capacity': '3'})
check('examiner creates a slot in an open slot creation period', count(Slot, exam_id=lab) == 1)
anil.post('/examiner/slot/save', data={'id': '', 'exam_id': str(dbms), 'slot_date': slot_day(3),
          'start_time': '10:00', 'end_time': '11:00', 'capacity': '1'})
check('examiner cannot create a slot for an exam not assigned to them', count(Slot, exam_id=dbms) == 0)
priya.post('/examiner/slot/save', data={'id': '', 'exam_id': str(dbms), 'slot_date': slot_day(3),
           'start_time': '10:00', 'end_time': '11:00', 'capacity': '1'})
check('assigned examiner creates a slot', count(Slot, exam_id=dbms) == 1)
priya_slot = slot_of('DBMS Project Demo')
priya.post('/examiner/slot/save', data={'id': str(priya_slot), 'slot_date': slot_day(4),
           'start_time': '10:00', 'end_time': '11:00', 'capacity': '1'})
check('examiner edits own slot before booking starts', get_row(Slot, id=priya_slot)['slot_date'] == today + timedelta(days=4))
priya.post(f'/examiner/slot/{priya_slot}/delete')
check('examiner removes own slot before booking starts', count(Slot, id=priya_slot) == 0)
viva_slot1, viva_slot2 = slot_of('DSA Viva', 0), slot_of('DSA Viva', 1)
anil.post('/examiner/slot/save', data={'id': str(viva_slot1), 'slot_date': slot_day(9),
          'start_time': '10:00', 'end_time': '10:30', 'capacity': '2'})
check('examiner cannot edit a slot that already has a booking', get_row(Slot, id=viva_slot1)['slot_date'] == today + timedelta(days=1))
anil.post(f'/examiner/slot/{viva_slot2}/delete')
check('examiner cannot remove a slot after booking has started', count(Slot, id=viva_slot2) == 1)

# ---------- 8. Student booking rules ----------
rohan.post(f'/student/book/{viva_slot1}')
check('student books a slot in the booking period', count(Booking, student_id=uid('rohan@emp.com')) == 1)
rohan.post(f'/student/book/{viva_slot1}')
check('student cannot book the same examination twice', count(Booking, student_id=uid('rohan@emp.com')) == 1)
ananya.post(f'/student/book/{viva_slot2}')
ananya_booking = get_row(Booking, student_id=uid('ananya@emp.com'))['id']
check('student books the last seat', count(Booking, slot_id=viva_slot2, status='Booked') == 1)
meena.post(f'/student/book/{viva_slot2}')
check('student cannot book a full slot (no overbooking)', count(Booking, student_id=uid('meena@emp.com')) == 0)
meena.post(f'/student/book/{slot_of("Lab Test")}')
check('student cannot book while status is Slot Creation', count(Booking, student_id=uid('meena@emp.com')) == 0)
ananya.post(f'/student/cancel/{ananya_booking}')
check('student cancels before the deadline', get_row(Booking, id=ananya_booking)['status'] == 'Cancelled')
meena.post(f'/student/book/{viva_slot2}')
check('cancelled seat becomes free again', count(Booking, student_id=uid('meena@emp.com'), status='Booked') == 1)
meena_booking = get_row(Booking, student_id=uid('meena@emp.com'))['id']

# ---------- 9. Evaluation rules ----------
aarav_booking = get_row(Booking, student_id=uid('aarav@emp.com'))['id']
anil.post(f'/examiner/evaluate/{aarav_booking}', data={'mark_1': '-5', 'mark_2': '3', 'mark_3': '3'})
check('negative marks are refused', get_row(Booking, id=aarav_booking)['status'] == 'Booked')
anil.post(f'/examiner/evaluate/{aarav_booking}', data={'mark_1': 'abc', 'mark_2': '3', 'mark_3': '3'})
check('non-numeric marks are refused', get_row(Booking, id=aarav_booking)['status'] == 'Booked')
anil.post(f'/examiner/evaluate/{aarav_booking}', data={'mark_1': '25', 'mark_2': '3', 'mark_3': '3'})
check('marks above the maximum are refused', get_row(Booking, id=aarav_booking)['status'] == 'Booked')
priya.post(f'/examiner/evaluate/{aarav_booking}', data={'mark_1': '20', 'mark_2': '15', 'mark_3': '15'})
check('examiner cannot evaluate a student from another examiner slot', get_row(Booking, id=aarav_booking)['status'] == 'Booked')
anil.post(f'/examiner/evaluate/{aarav_booking}', data={'mark_1': '18', 'mark_2': '12', 'mark_3': '10', 'publish': 'on', 'remarks': 'Good work'})
check('valid evaluation completes the booking', get_row(Booking, id=aarav_booking)['status'] == 'Completed')
check('total marks are saved', get_row(Evaluation, booking_id=aarav_booking)['total'] == 40)
anil.post(f'/examiner/evaluate/{ananya_booking}', data={'mark_1': '10', 'mark_2': '10', 'mark_3': '10'})
check('cancelled booking cannot be evaluated', get_row(Booking, id=ananya_booking)['status'] == 'Cancelled')
anil.post(f'/examiner/evaluate/{meena_booking}', data={'mark_1': '10', 'mark_2': '10', 'mark_3': '10'})
check('unpublished evaluation is saved', get_row(Booking, id=meena_booking)['status'] == 'Completed')
check('student sees published marks', b'40.0 / 50' in aarav.get('/student').data)
check('student does not see unpublished marks', b'10.0 / 50' not in meena.get('/student').data)

# ---------- 10. Admin: reschedule and change examiner ----------
admin.post(f'/admin/booking/{meena_booking}/reschedule', data={'new_slot_id': str(viva_slot1)})
check('admin cannot move a booking to a full slot', get_row(Booking, id=meena_booking)['slot_id'] == viva_slot2)
anil.post('/examiner/slot/save', data={'id': '', 'exam_id': str(lab), 'slot_date': slot_day(2),
          'start_time': '14:00', 'end_time': '15:00', 'capacity': '1'})
anil.post('/examiner/slot/save', data={'id': '', 'exam_id': str(viva), 'slot_date': slot_day(5),
          'start_time': '09:00', 'end_time': '09:30', 'capacity': '1'})
check('examiner cannot create a Viva slot while booking is open', count(Slot, exam_id=viva) == 2)
new_viva_slot = slot_of('DSA Viva', 2) if count(Slot, exam_id=viva) == 3 else viva_slot2
admin.post(f'/admin/booking/{meena_booking}/reschedule', data={'new_slot_id': str(lab_slot := slot_of('Lab Test'))})
check('admin cannot move a booking to another examination', get_row(Booking, id=meena_booking)['slot_id'] == viva_slot2)
admin.post(f'/admin/slot/{viva_slot2}/examiner', data={'examiner_id': str(uid('priya@emp.com'))})
check('admin changes the examiner of a slot', get_row(Slot, id=viva_slot2)['examiner_id'] == uid('priya@emp.com'))
admin.post(f'/admin/slot/{viva_slot2}/examiner', data={'examiner_id': str(uid('anil@emp.com'))})

# ---------- 11. Student cancel rules, profile, search and filter ----------
with app.app_context():
    old = Exam(course_id=cs305, name='Old Exam', exam_type='Assessment', duration=30, max_marks=10,
               slot_start=today - timedelta(days=20), slot_end=today - timedelta(days=10),
               book_start=today - timedelta(days=9), book_end=today - timedelta(days=1), status='Booking Open')
    db.session.add(old); db.session.commit()
    s = Slot(exam_id=old.id, examiner_id=uid('anil@emp.com'), slot_date=today + timedelta(days=1),
             start_time=time(9, 0), end_time=time(9, 30), capacity=5)
    db.session.add(s); db.session.commit()
    b = Booking(student_id=uid('meena@emp.com'), slot_id=s.id, booked_on=today)
    db.session.add(b); db.session.commit()
    old_booking = b.id
meena.post(f'/student/cancel/{old_booking}')
check('student cannot cancel after the deadline', get_row(Booking, id=old_booking)['status'] == 'Booked')
check('student cannot cancel a completed (evaluated) booking', get_row(Booking, id=meena_booking)['status'] == 'Completed')
rohan_booking = get_row(Booking, student_id=uid('rohan@emp.com'))['id']
rohan.post(f'/student/cancel/{rohan_booking}')
check('student cancels a booking before the deadline', get_row(Booking, id=rohan_booking)['status'] == 'Cancelled')
meena.post('/student/profile', data={'name': 'Meena Krishnan Iyer', 'phone': '9870077799', 'department': 'CS', 'new_password': ''})
check('student edits profile', get_row(User, email='meena@emp.com')['name'] == 'Meena Krishnan Iyer')
check('student search finds an examination by name', b'DSA Viva' in meena.get('/student?q=dsa').data)
check('student search returns nothing for a wrong name', b'Lab Test' not in meena.get('/student?q=zzz').data)
r = meena.get('/student?exam_type=Project+Demo')
check('student filter by type hides other types', b'<td>Viva</td>' not in r.data and b'DBMS Project Demo' in r.data)
check('admin search finds a student by name', b'Aarav Patel' in admin.get('/admin?q=aarav').data)
check('admin search finds a booking by student ID', b'Aarav Patel' in admin.get(f'/admin?q={uid("aarav@emp.com")}').data)

# ---------- 12. Admin deletes an examination (cascade) ----------
admin.post(f'/admin/exam/{eid("Old Exam")}/delete')
check('deleting an examination removes its slots and bookings', count(Booking, id=old_booking) == 0)

# ---------- 12b. New features ----------
admin.post('/admin/exam/save', data=dict(good, id=str(lab), booking_open='on', slot_creation_open='on'))
check('opening booking shows status Booking Open', get_row(Exam, id=lab)['status'] == 'Booking Open')
check('both switches stay on together', get_row(Exam, id=lab)['slot_creation_open'] and get_row(Exam, id=lab)['booking_open'])
anil.post('/examiner/slot/save', data={'id': '', 'exam_id': str(lab), 'slot_date': slot_day(3),
          'start_time': '16:00', 'end_time': '16:30', 'capacity': '1'})
check('examiner can still create slots while booking is open', count(Slot, exam_id=lab) == 3)
admin.post('/admin/exam/save', data=dict(good, id=str(lab), slot_creation_open='on'))
check('closing booking leaves slot creation open and status Slot Creation',
      get_row(Exam, id=lab)['status'] == 'Slot Creation' and get_row(Exam, id=lab)['slot_creation_open'])
admin.post('/admin/exam/save', data={k: v for k, v in good.items() if k != 'slot_creation_open'} | {'id': str(lab)})
check('closing both switches gives status Closed', get_row(Exam, id=lab)['status'] == 'Closed')
admin.post('/admin/exam/save', data=dict(good, id=str(lab), slot_creation_open='on'))
admin.post('/admin/rubric/save', data={'id': str(lab_rubric), 'exam_id': str(lab), 'criterion': 'Lab viva',
           'max_marks': '20', 'weightage': '2.5', 'description': 'Viva on the lab work'})
check('admin edits a rubric criterion with weightage and description',
      get_row(Rubric, id=lab_rubric)['criterion'] == 'Lab viva' and get_row(Rubric, id=lab_rubric)['weightage'] == 2.5)
admin.post('/admin/rubric/save', data={'id': '', 'exam_id': str(lab), 'criterion': 'Bad', 'max_marks': '5', 'weightage': '0'})
check('rubric with weightage 0 is refused', count(Rubric, criterion='Bad') == 0)
admin.post(f'/admin/slot/{slot_of("Lab Test")}/cancel')
check('admin cancels a slot', get_row(Slot, id=slot_of('Lab Test'))['cancelled'] is True or get_row(Slot, id=slot_of('Lab Test'))['cancelled'] == 1)
check('cancelled slot shows status Cancelled to the examiner', b'Cancelled' in anil.get('/examiner').data)
check('student sees open examinations list', b'Available examinations' in aarav.get('/student').data)
check('admin password is changed', admin.post('/admin/password', data={'new_password': 'newadmin1'}).status_code == 302)
check('new admin password works', login('admin@emp.com', 'newadmin1').get('/admin').status_code == 200)
check('old admin password no longer works', login('admin@emp.com', 'admin123').get('/admin').status_code == 302)
admin = login('admin@emp.com', 'newadmin1')

# ---------- 12c. JSON API ----------
api_anon = app.test_client()
check('API: anonymous request is refused', api_anon.get('/api/exams').status_code == 401)
check('API: wrong password is refused', api_anon.post('/api/login', json={'email': 'anil@emp.com', 'password': 'x'}).status_code == 401)
check('API: pending examiner is refused', api_anon.post('/api/login', json={'email': 'suresh@emp.com', 'password': 'examiner123'}).status_code == 403)
api_st = app.test_client()
r = api_st.post('/api/login', json={'email': 'aarav@emp.com', 'password': 'student123'})
check('API: student logs in', r.status_code == 200 and r.get_json()['role'] == 'student')
check('API: student lists examinations', api_st.get('/api/exams').status_code == 200 and len(api_st.get('/api/exams').get_json()) > 0)
check('API: slots include a status', 'status' in api_st.get('/api/slots').get_json()[0])
bookings = api_st.get('/api/bookings').get_json()
check('API: student sees own bookings with published marks', any(b['marks'] == 40.0 for b in bookings))
check('API: student cannot read the admin summary', api_st.get('/api/summary').status_code == 403)
api_ad = app.test_client()
api_ad.post('/api/login', json={'email': 'admin@emp.com', 'password': 'newadmin1'})
summary = api_ad.get('/api/summary')
check('API: admin reads the summary', summary.status_code == 200 and summary.get_json()['students'] >= 1)
check('API: bad JSON body does not crash', api_anon.post('/api/login', data='not json', content_type='application/json').status_code == 401)

# ---------- 13. Final pass: every page still loads ----------
for client, paths in pages.items():
    for p in paths:
        check(f'final: {p} loads', client.get(p).status_code == 200)

print()
print(f'{sum(results)} of {len(results)} checks passed')
