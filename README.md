# Examination Management Portal (Simple Version)

Built with Python, Flask, SQLite, Jinja2 and Bootstrap. No JavaScript is used.
Bootstrap is included in the `static` folder, so the app works without internet.

## How to run

1. Open a terminal in the `EMP_Simple` folder.
2. Install the packages: `pip install -r requirements.txt`
3. Start the app: `python app.py`
4. Open `http://127.0.0.1:5000` in your browser.

The database file `emp.db` is created automatically the first time you run the app, with demo data.

## Run the tests

Run `python test_emp.py`. It copies the project to a temporary folder, runs 118 checks (every rule, the refused cases, every page and the API), and prints PASS or FAIL for each one. Your own `emp.db` is not touched.

## JSON API

The endpoints are described in `api.yaml` (OpenAPI 3.0), which is in the submission zip.

- `POST /api/login` with JSON `{"email": ..., "password": ...}` starts a session.
- `GET /api/exams` and `GET /api/slots` return examinations and slots to any logged-in user.
- `GET /api/bookings` returns the student's own bookings and published marks.
- `GET /api/summary` returns the admin dashboard counts.

Anyone who is not logged in gets 401, and a role that is not allowed gets 403.

## Before you submit

**1. Change the SECRET_KEY.** Flask uses this key to sign the cookie that remembers who is logged in. The code is public, so anyone who knows the key could make a login cookie for the admin. Make a random key:

    python -c "import secrets; print(secrets.token_hex(32))"

Paste the result into `app.py` in place of `PASTE-YOUR-OWN-LONG-RANDOM-KEY-HERE`, or set it as an environment variable called `SECRET_KEY` before you start the app.

**2. Change the admin password.** The admin password `admin123` is written in this README, so anyone can use it. Log in as admin, then use the "Change admin password" form at the top of the admin page. The new password must have at least 6 characters.

If you delete `emp.db` and start again, the admin password is reset to `admin123`, or to the value of the `ADMIN_PASSWORD` environment variable if you set one.

## Demo accounts

| Role | Email | Password | Notes |
| --- | --- | --- | --- |
| Admin | admin@emp.com | admin123 | Change it (see above). No admin registration. |
| Examiner | anil@emp.com | examiner123 | Approved. Assigned to DSA Viva. |
| Examiner | priya@emp.com | examiner123 | Approved. Assigned to DBMS Project Demo. |
| Examiner | suresh@emp.com | examiner123 | Pending. Cannot log in until the admin approves. |
| Student | aarav@emp.com | student123 | Has a booked slot. |
| Student | ananya@emp.com | student123 | Can book slots. |
| Student | rohan@emp.com | student123 | Can book slots. |

New examiners and students can register from the Register link.

## What each role can do

**Admin:** manage courses; create, edit and delete examinations with their timelines; open or close examiner slot creation and student booking with two separate switches; mark an examination completed; add rubric criteria with weightage and description, and edit or delete them; add, approve and deactivate examiners; change the examiner of a slot; cancel a slot; move a booking to another slot of the same examination; search students, examiners, examinations and bookings by name or ID.

**Examiner:** see assigned examinations; create slots only while slot creation is open and today is inside the slot creation dates; edit or remove own slots only before booking starts and while nobody has booked them; see booked students; give marks for each rubric criterion, with remarks, and choose whether to publish them.

**Student:** see examinations open for booking; search and filter all examinations; book a slot only while booking is open and today is inside the booking dates; one booking per examination; no booking of full or cancelled slots; cancel a booking up to the last booking date; see booking history, upcoming examinations and published results; edit the profile.

## Rules built in

- A slot is shown as Available, Full (all seats taken), Cancelled (by the admin) or Completed (the date has passed).
- The examination status (Draft, Slot Creation, Booking Open, Closed, Completed) is worked out from the admin's switches.
- A student cannot book the same examination twice.
- An examiner can only evaluate students booked in their own slots.
- Marks must be numbers from 0 up to the maximum for each criterion. The total is the sum of the marks.

## Files

- `app.py`: database tables, login, all pages, the JSON API and the demo data
- `templates/`: the web pages (Jinja2 with Bootstrap)
- `static/css/bootstrap.min.css`: Bootstrap 5.3.3, stored locally
- `requirements.txt`: the packages to install
- `test_emp.py`: the automated tests
