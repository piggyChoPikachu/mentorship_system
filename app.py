from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash
import psycopg2
import psycopg2.errors
import os
from dotenv import load_dotenv
import json

load_dotenv() 
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret")


def get_conn():
    """Get database connection"""
    return psycopg2.connect(os.getenv("DATABASE_URL"))


def login_required(f):
    """Decorator to check if user is logged in"""
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login_page"))
        return f(*args, **kwargs)
    wrapper.__name__ = f.__name__
    return wrapper


# ============================================================
# AUTH ROUTES
# ============================================================

@app.route("/")
def home():
    """Show register page - ALWAYS, no redirects"""
    return render_template("register.html")


@app.route("/login")
def login_page():
    """Show login page - ALWAYS, no redirects"""
    return render_template("login.html")


@app.post("/api/auth/register")
def api_register():
    """Register new user"""
    data = request.get_json(silent=True) or {}

    username = (data.get("username") or "").strip()
    email = (data.get("email") or "").strip()
    password = data.get("password") or ""
    role = (data.get("identity_role") or "").strip().lower()

    if not username or not email or not password or role not in ("student", "alumni"):
        return jsonify({"error": "Invalid input"}), 400

    password_hash = generate_password_hash(password)

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO person (username, email, password_hash, identity_role, first_name, last_name)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (username, email, password_hash, role, "", "")
                )
                person_id = cur.fetchone()[0]

                if role == "student":
                    cur.execute("INSERT INTO student (person_id) VALUES (%s)", (person_id,))
                else:
                    cur.execute("INSERT INTO alumni (person_id) VALUES (%s)", (person_id,))

            conn.commit()
            return jsonify({"ok": True, "person_id": person_id}), 201

    except psycopg2.errors.UniqueViolation:
        return jsonify({"error": "Username or email already exists"}), 409
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.post("/api/auth/login")
def api_login():
    """Login user"""
    data = request.get_json() or {}

    identifier = (data.get("identifier") or "").strip()
    password = data.get("password") or ""

    if not identifier or not password:
        return jsonify({"error": "Invalid input"}), 400

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, password_hash, identity_role FROM person WHERE username=%s OR email=%s",
                    (identifier, identifier)
                )
                user = cur.fetchone()
                
                if not user:
                    return jsonify({"error": "Invalid credentials"}), 401
                
                user_id, password_hash, role = user
                if not check_password_hash(password_hash, password):
                    return jsonify({"error": "Invalid credentials"}), 401
        
        session["user_id"] = user_id
        session["identity_role"] = role
        return jsonify({"ok": True}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.get("/logout")
def logout():
    """Logout user"""
    session.clear()
    return redirect(url_for("home"))


# ============================================================
# PROFILE ROUTES
# ============================================================

@app.get("/profile")
@login_required
def profile_page():
    """Show user profile (view mode) - PROTECTED"""
    user_id = session.get("user_id")
    mode = request.args.get("mode", "view")
    
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                # Get person info
                cur.execute(
                    """
                    SELECT id, username, email, identity_role, first_name, last_name, 
                           phone_number, address, home_country
                    FROM person
                    WHERE id = %s
                    """,
                    (user_id,)
                )
                row = cur.fetchone()
                
                if not row:
                    return jsonify({"error": "User not found"}), 404
                
                # Convert to DICTIONARY
                user = {
                    "id": row[0],
                    "username": row[1],
                    "email": row[2],
                    "identity_role": row[3],
                    "first_name": row[4],
                    "last_name": row[5],
                    "phone_number": row[6],
                    "address": row[7],
                    "home_country": row[8]
                }

        return render_template("profile.html", user=user, mode=mode)
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ============================================================
# API: COUNTRIES
# ============================================================

@app.get("/api/countries")
def get_countries():
    """Get all countries"""
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT code, name FROM country ORDER BY name")
                countries = [{"code": row[0], "name": row[1]} for row in cur.fetchall()]
                return jsonify({"countries": countries}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ============================================================
# API: STUDY LEVELS
# ============================================================

@app.get("/api/study-levels")
def get_study_levels():
    """Get all study levels"""
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, name FROM study_level ORDER BY id"
                )
                study_levels = [{"id": row[0], "name": row[1]} for row in cur.fetchall()]
                return jsonify({"study_levels": study_levels}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ============================================================
# API: PROGRAMMES
# ============================================================

@app.get("/api/programmes")
def get_programmes():
    """Get all programmes"""
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT p.id, p.name, p.study_level_id, p.faculty_id, p.institute_id,
                           sl.name as study_level_name,
                           f.name as faculty_name,
                           i.name as institute_name
                    FROM programme p
                    JOIN study_level sl ON p.study_level_id = sl.id
                    JOIN faculty f ON p.faculty_id = f.id
                    LEFT JOIN institute i ON p.institute_id = i.id
                    ORDER BY p.name
                    """
                )
                programmes = []
                for row in cur.fetchall():
                    programmes.append({
                        "id": row[0],
                        "name": row[1],
                        "study_level_id": row[2],
                        "faculty_id": row[3],
                        "institute_id": row[4],
                        "study_level_name": row[5],
                        "faculty_name": row[6],
                        "institute_name": row[7]
                    })
                return jsonify({"programmes": programmes}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.get("/api/programmes/<int:study_level_id>")
def get_programmes_by_level(study_level_id):
    """Get programmes filtered by study level"""
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT p.id, p.name, p.study_level_id, p.faculty_id, p.institute_id,
                           sl.name as study_level_name,
                           f.name as faculty_name,
                           i.name as institute_name
                    FROM programme p
                    JOIN study_level sl ON p.study_level_id = sl.id
                    JOIN faculty f ON p.faculty_id = f.id
                    LEFT JOIN institute i ON p.institute_id = i.id
                    WHERE p.study_level_id = %s
                    ORDER BY p.name
                    """,
                    (study_level_id,)
                )
                programmes = []
                for row in cur.fetchall():
                    programmes.append({
                        "id": row[0],
                        "name": row[1],
                        "study_level_id": row[2],
                        "faculty_id": row[3],
                        "institute_id": row[4],
                        "study_level_name": row[5],
                        "faculty_name": row[6],
                        "institute_name": row[7]
                    })
                return jsonify({"programmes": programmes}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ============================================================
# API: PERSONAL INFO
# ============================================================

@app.post("/api/profile/personal")
@login_required
def save_personal():
    """Save personal information"""
    user_id = session.get("user_id")
    data = request.get_json() or {}

    first_name = (data.get("first_name") or "").strip()
    last_name = (data.get("last_name") or "").strip()
    phone_number = (data.get("phone_number") or "").strip() or None
    address = (data.get("address") or "").strip() or None
    home_country = (data.get("home_country") or "").strip() or None

    if not first_name or not last_name:
        return jsonify({"error": "First name and last name required"}), 400

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE person
                    SET first_name=%s, last_name=%s, phone_number=%s, address=%s, home_country=%s
                    WHERE id=%s
                    """,
                    (first_name, last_name, phone_number, address, home_country, user_id)
                )
            conn.commit()
            return jsonify({"ok": True}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ============================================================
# API: EDUCATION
# ============================================================

@app.get("/api/education")
@login_required
def get_education():
    """Get user education records"""
    user_id = session.get("user_id")

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT 
                        e.id,
                        e.programme_id,
                        e.study_level_id,
                        e.start_date,
                        e.end_date,
                        sl.name as study_level,
                        p.name as programme,
                        i.name as institute,
                        f.name as faculty
                    FROM education e
                    JOIN study_level sl ON e.study_level_id = sl.id
                    JOIN programme p ON e.programme_id = p.id
                    LEFT JOIN institute i ON p.institute_id = i.id
                    JOIN faculty f ON p.faculty_id = f.id
                    WHERE e.person_id = %s
                    ORDER BY e.start_date DESC
                    """,
                    (user_id,)
                )

                education = []
                for row in cur.fetchall():
                    education.append({
                        "id": row[0],
                        "programme_id": row[1],
                        "study_level_id": row[2],
                        "start_date": str(row[3]) if row[3] else None,
                        "end_date": str(row[4]) if row[4] else None,
                        "study_level": row[5],
                        "programme": row[6],
                        "institute": row[7],
                        "faculty": row[8],
                    })

                return jsonify({"education": education}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.post("/api/education")
@login_required
def add_education():
    """Add education record"""
    user_id = session.get("user_id")
    data = request.get_json() or {}

    programme_id = data.get("programme_id")
    study_level_id = data.get("study_level_id")
    start_date = data.get("start_date") or None
    end_date = data.get("end_date") or None

    if not programme_id or not study_level_id:
        return jsonify({"error": "Programme and study level required"}), 400

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO education (person_id, programme_id, study_level_id, start_date, end_date)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (user_id, programme_id, study_level_id, start_date, end_date)
                )
                edu_id = cur.fetchone()[0]
            conn.commit()
            return jsonify({"ok": True, "id": edu_id}), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.put("/api/education/<int:edu_id>")
@login_required
def update_education(edu_id):
    """Update education record"""
    user_id = session.get("user_id")
    data = request.get_json() or {}

    programme_id = data.get("programme_id")
    study_level_id = data.get("study_level_id")
    start_date = data.get("start_date") or None
    end_date = data.get("end_date") or None

    if not programme_id or not study_level_id:
        return jsonify({"error": "Programme and study level required"}), 400

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                # Check if education belongs to user
                cur.execute("SELECT person_id FROM education WHERE id=%s", (edu_id,))
                result = cur.fetchone()
                
                if not result or result[0] != user_id:
                    return jsonify({"error": "Unauthorized"}), 403
                
                # Update education
                cur.execute(
                    """
                    UPDATE education
                    SET programme_id=%s, study_level_id=%s, start_date=%s, end_date=%s
                    WHERE id=%s
                    """,
                    (programme_id, study_level_id, start_date, end_date, edu_id)
                )
            conn.commit()
            return jsonify({"ok": True}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.delete("/api/education/<int:edu_id>")
@login_required
def delete_education(edu_id):
    """Delete education record"""
    user_id = session.get("user_id")

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT person_id FROM education WHERE id=%s", (edu_id,))
                result = cur.fetchone()
                
                if not result or result[0] != user_id:
                    return jsonify({"error": "Unauthorized"}), 403
                
                cur.execute("DELETE FROM education WHERE id=%s", (edu_id,))
            conn.commit()
            return jsonify({"ok": True}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ============================================================
# API: CAREER (Alumni Only)
# ============================================================

@app.get("/api/career")
@login_required
def get_career():
    """Get user career records (alumni only)"""
    user_id = session.get("user_id")
    role = session.get("identity_role")

    if role != "alumni":
        return jsonify({"error": "Alumni only"}), 403

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT 
                        c.id,
                        c.job_title,
                        c.company_name,
                        c.country_code,
                        c.start_date,
                        c.end_date,
                        c.job_description,
                        co.name as country_name
                    FROM career c
                    LEFT JOIN country co ON c.country_code = co.code
                    WHERE c.person_id = %s
                    ORDER BY c.start_date DESC
                    """,
                    (user_id,)
                )

                career = []
                for row in cur.fetchall():
                    career.append({
                        "id": row[0],
                        "job_title": row[1],
                        "company_name": row[2],
                        "country_code": row[3],
                        "start_date": str(row[4]) if row[4] else None,
                        "end_date": str(row[5]) if row[5] else None,
                        "job_description": row[6],
                        "country_name": row[7] or "",
                    })

                return jsonify({"career": career}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.post("/api/career")
@login_required
def add_career():
    """Add career record (alumni only)"""
    user_id = session.get("user_id")
    role = session.get("identity_role")

    if role != "alumni":
        return jsonify({"error": "Alumni only"}), 403

    data = request.get_json() or {}

    job_title = (data.get("job_title") or "").strip()
    company_name = (data.get("company_name") or "").strip()
    country_code = (data.get("work_country_code") or "").strip() or None
    start_date = data.get("start_date")
    end_date = data.get("end_date") or None
    job_description = (data.get("job_description") or "").strip() or None

    if not job_title or not company_name or not start_date:
        return jsonify({"error": "Job title, company, and start date required"}), 400

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO career (person_id, job_title, company_name, country_code, start_date, end_date, job_description)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (user_id, job_title, company_name, country_code, start_date, end_date, job_description)
                )
                career_id = cur.fetchone()[0]
            conn.commit()
            return jsonify({"ok": True, "id": career_id}), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.put("/api/career/<int:career_id>")
@login_required
def update_career(career_id):
    """Update career record (alumni only)"""
    user_id = session.get("user_id")
    role = session.get("identity_role")

    if role != "alumni":
        return jsonify({"error": "Alumni only"}), 403

    data = request.get_json() or {}

    job_title = (data.get("job_title") or "").strip()
    company_name = (data.get("company_name") or "").strip()
    country_code = (data.get("work_country_code") or "").strip() or None
    start_date = data.get("start_date")
    end_date = data.get("end_date") or None
    job_description = (data.get("job_description") or "").strip() or None

    if not job_title or not company_name or not start_date:
        return jsonify({"error": "Job title, company, and start date required"}), 400

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                # Check if career belongs to user
                cur.execute("SELECT person_id FROM career WHERE id=%s", (career_id,))
                result = cur.fetchone()
                
                if not result or result[0] != user_id:
                    return jsonify({"error": "Unauthorized"}), 403
                
                # Update career
                cur.execute(
                    """
                    UPDATE career
                    SET job_title=%s, company_name=%s, country_code=%s, start_date=%s, end_date=%s, job_description=%s
                    WHERE id=%s
                    """,
                    (job_title, company_name, country_code, start_date, end_date, job_description, career_id)
                )
            conn.commit()
            return jsonify({"ok": True}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.delete("/api/career/<int:career_id>")
@login_required
def delete_career(career_id):
    """Delete career record (alumni only)"""
    user_id = session.get("user_id")
    role = session.get("identity_role")

    if role != "alumni":
        return jsonify({"error": "Alumni only"}), 403

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT person_id FROM career WHERE id=%s", (career_id,))
                result = cur.fetchone()
                
                if not result or result[0] != user_id:
                    return jsonify({"error": "Unauthorized"}), 403
                
                cur.execute("DELETE FROM career WHERE id=%s", (career_id,))
            conn.commit()
            return jsonify({"ok": True}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ============================================================
# ERROR HANDLERS
# ============================================================

@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Not found"}), 404


@app.errorhandler(500)
def server_error(error):
    return jsonify({"error": "Server error"}), 500


# ============================================================
# PREFERENCE ROUTES
# ============================================================

@app.get("/preference")
@login_required
def preference_page():
    """Show user preference page"""
    user_id = session.get("user_id")
    mode = request.args.get("mode", "view")
    
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                # Get user info
                cur.execute(
                    """
                    SELECT id, first_name, last_name FROM person WHERE id=%s
                    """,
                    (user_id,)
                )
                row = cur.fetchone()
                
                if not row:
                    return jsonify({"error": "User not found"}), 404
                
                user = {
                    "id": row[0],
                    "first_name": row[1],
                    "last_name": row[2]
                }
        
        return render_template("preference.html", user=user, mode=mode)
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.get("/api/topics")
def get_topics():
    """Get all available topics"""
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, name FROM topic ORDER BY name"
                )
                topics = [{"id": row[0], "name": row[1]} for row in cur.fetchall()]
                return jsonify({"topics": topics}), 200
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.get("/api/user-preferences")
@login_required
def get_user_preferences():
    """Get logged-in user's current preferences"""
    user_id = session.get("user_id")
    
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT p.topic_id, t.name, p.preference_role
                    FROM preference p
                    JOIN topic t ON p.topic_id = t.id
                    WHERE p.person_id = %s
                    ORDER BY t.name
                    """,
                    (user_id,)
                )
                preferences = [
                    {
                        "topic_id": row[0],
                        "topic_name": row[1],
                        "preference_role": row[2]
                    }
                    for row in cur.fetchall()
                ]
                return jsonify({"preferences": preferences}), 200
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.post("/api/preference/save")
@login_required
def save_preferences():
    """Save user preferences (delete old, insert new)"""
    user_id = session.get("user_id")
    data = request.get_json() or {}
    
    preferences = data.get("preferences") or []
    
    # Validate preferences
    for pref in preferences:
        if not pref.get("topic_id") or not pref.get("preference_role"):
            return jsonify({"error": "Invalid preference data"}), 400
        
        if pref.get("preference_role") not in ("mentor", "mentee", "two_way"):
            return jsonify({"error": "Invalid preference role"}), 400
    
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                # Step 1: Delete all existing preferences for this user
                cur.execute(
                    "DELETE FROM preference WHERE person_id=%s",
                    (user_id,)
                )
                
                # Step 2: Insert new preferences
                for pref in preferences:
                    cur.execute(
                        """
                        INSERT INTO preference (person_id, topic_id, preference_role)
                        VALUES (%s, %s, %s)
                        """,
                        (user_id, pref.get("topic_id"), pref.get("preference_role"))
                    )
            
            conn.commit()
            return jsonify({"ok": True}), 200
    
    except Exception as e:
        try:
            conn.rollback()
        except:
            pass
        return jsonify({"error": str(e)}), 500


# ============================================================
# PUBLISH ROUTES
# ============================================================

@app.get("/published-profile")
@login_required
def published_profile_page():
    """Show user's published profile (their own view)"""
    user_id = session.get("user_id")
    
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                # Get person info with publish status
                cur.execute(
                    """
                    SELECT id, first_name, last_name, identity_role, home_country, 
                           phone_number, address, profile_published, preferences_published
                    FROM person 
                    WHERE id = %s
                    """,
                    (user_id,)
                )
                row = cur.fetchone()
                
                if not row:
                    return jsonify({"error": "User not found"}), 404
                
                person = {
                    "id": row[0],
                    "first_name": row[1],
                    "last_name": row[2],
                    "identity_role": row[3],
                    "home_country": row[4],
                    "phone_number": row[5],
                    "address": row[6],
                    "profile_published": row[7],
                    "preferences_published": row[8]
                }
                
                profile_published = person["profile_published"]
                preferences_published = person["preferences_published"]
                
                profile_data = None
                preferences_data = None
                
                # Get profile data if published
                if profile_published:
                    # Get education
                    cur.execute(
                        """
                        SELECT e.id, e.start_date, e.end_date, 
                               sl.name as study_level,
                               p.name as programme,
                               i.name as institute,
                               f.name as faculty
                        FROM education e
                        JOIN study_level sl ON e.study_level_id = sl.id
                        JOIN programme p ON e.programme_id = p.id
                        LEFT JOIN institute i ON p.institute_id = i.id
                        JOIN faculty f ON p.faculty_id = f.id
                        WHERE e.person_id = %s
                        ORDER BY e.start_date DESC
                        """,
                        (user_id,)
                    )
                    
                    # Convert education tuples to dictionaries
                    education = []
                    for edu_row in cur.fetchall():
                        education.append({
                            "id": edu_row[0],
                            "start_date": edu_row[1],
                            "end_date": edu_row[2],
                            "study_level": edu_row[3],
                            "programme": edu_row[4],
                            "institute": edu_row[5],
                            "faculty": edu_row[6]
                        })
                    
                    # Get career if alumni
                    career = []
                    if person["identity_role"] == 'alumni':
                        cur.execute(
                            """
                            SELECT c.id, c.job_title, c.company_name, c.start_date, 
                                   c.end_date, c.job_description, co.name as country_name
                            FROM career c
                            LEFT JOIN country co ON c.country_code = co.code
                            WHERE c.person_id = %s
                            ORDER BY c.start_date DESC
                            """,
                            (user_id,)
                        )
                        
                        # Convert career tuples to dictionaries
                        for car_row in cur.fetchall():
                            career.append({
                                "id": car_row[0],
                                "job_title": car_row[1],
                                "company_name": car_row[2],
                                "start_date": car_row[3],
                                "end_date": car_row[4],
                                "job_description": car_row[5],
                                "country_name": car_row[6]
                            })
                    
                    profile_data = {
                        "first_name": person["first_name"],
                        "last_name": person["last_name"],
                        "identity_role": person["identity_role"],
                        "home_country": person["home_country"],
                        "phone_number": person["phone_number"],
                        "address": person["address"],
                        "education": education,
                        "career": career
                    }
                
                # Get preferences if published
                if preferences_published:
                    cur.execute(
                        """
                        SELECT pr.topic_id, t.name, pr.preference_role
                        FROM preference pr
                        JOIN topic t ON pr.topic_id = t.id
                        WHERE pr.person_id = %s
                        ORDER BY t.name
                        """,
                        (user_id,)
                    )
                    preferences_data = [
                        {
                            "topic_id": row[0],
                            "topic_name": row[1],
                            "preference_role": row[2]
                        }
                        for row in cur.fetchall()
                    ]
        
        return render_template(
            "published_profile.html",
            profile_published=profile_published,
            preferences_published=preferences_published,
            profile=profile_data,
            preferences=preferences_data
        )
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.get("/api/profile/publish-status")
@login_required
def get_publish_status():
    """Get profile and preferences publish status"""
    user_id = session.get("user_id")
    
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT profile_published, preferences_published
                    FROM person WHERE id = %s
                    """,
                    (user_id,)
                )
                result = cur.fetchone()
                
                if not result:
                    return jsonify({"error": "User not found"}), 404
                
                profile_published, preferences_published = result
                
                return jsonify({
                    "profile_published": profile_published,
                    "preferences_published": preferences_published
                }), 200
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.post("/api/profile/publish")
@login_required
def publish_profile():
    """Publish user profile"""
    user_id = session.get("user_id")
    
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                # Check if profile has required fields
                cur.execute(
                    """
                    SELECT first_name, last_name, email
                    FROM person WHERE id = %s
                    """,
                    (user_id,)
                )
                person = cur.fetchone()
                
                if not person:
                    return jsonify({"error": "User not found"}), 404
                
                first_name, last_name, email = person
                
                if not first_name or not last_name:
                    return jsonify({"error": "Profile incomplete - first name and last name required"}), 400
                
                # Publish profile
                cur.execute(
                    """
                    UPDATE person
                    SET profile_published = TRUE
                    WHERE id = %s
                    """,
                    (user_id,)
                )
            
            conn.commit()
            return jsonify({"ok": True, "message": "Profile published successfully"}), 200
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.post("/api/preferences/publish")
@login_required
def publish_preferences():
    """Publish user preferences"""
    user_id = session.get("user_id")
    
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                # Check if user has preferences
                cur.execute(
                    "SELECT COUNT(*) FROM preference WHERE person_id = %s",
                    (user_id,)
                )
                pref_count = cur.fetchone()[0]
                
                if pref_count == 0:
                    return jsonify({"error": "No preferences to publish"}), 400
                
                # Publish preferences
                cur.execute(
                    """
                    UPDATE person
                    SET preferences_published = TRUE
                    WHERE id = %s
                    """,
                    (user_id,)
                )
            
            conn.commit()
            return jsonify({"ok": True, "message": "Preferences published successfully"}), 200
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.post("/api/profile/unpublish")
@login_required
def unpublish_profile():
    """Unpublish user profile (optional - based on your requirements)"""
    user_id = session.get("user_id")
    
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE person
                    SET profile_published = FALSE
                    WHERE id = %s
                    """,
                    (user_id,)
                )
            
            conn.commit()
            return jsonify({"ok": True, "message": "Profile unpublished"}), 200
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.post("/api/preferences/unpublish")
@login_required
def unpublish_preferences():
    """Unpublish user preferences (optional - based on your requirements)"""
    user_id = session.get("user_id")
    
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE person
                    SET preferences_published = FALSE
                    WHERE id = %s
                    """,
                    (user_id,)
                )
            
            conn.commit()
            return jsonify({"ok": True, "message": "Preferences unpublished"}), 200
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500



# ============================================================
# MATCHING ROUTES
# ============================================================

# ============================================================
# MATCHING ROUTES - CORRECTED VERSION
# ============================================================

@app.get("/matching")
@login_required
def matching_page():
    """Show matching page - find mentors/mentees"""
    return render_template("matching.html")



@app.get("/api/matching/search")
@login_required
def api_matching_search():
    """Search for strict topic-role matches from published preferences only."""
    user_id = session.get("user_id")

    topic_id = request.args.get("topic_id", type=int)
    role_filter = request.args.get("role", type=str)
    location_code = request.args.get("location", type=str)

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                # Check current user + publication status
                cur.execute(
                    """
                    SELECT id, identity_role, preferences_published
                    FROM person
                    WHERE id = %s
                    """,
                    (user_id,)
                )
                me = cur.fetchone()

                if not me:
                    return jsonify({"error": "User not found"}), 404

                my_identity_role = me[1]
                preferences_published = me[2]

                if not preferences_published:
                    return jsonify({
                        "results": [],
                        "message": "Please publish your preferences first to see matches."
                    }), 200

                opposite_role = "alumni" if my_identity_role == "student" else "student"

                params = [user_id, user_id, opposite_role]
                extra_filters = []

                if topic_id:
                    extra_filters.append("my_pref.topic_id = %s")
                    params.append(topic_id)

                if role_filter:
                    extra_filters.append("my_pref.preference_role = %s")
                    params.append(role_filter)

                if location_code:
                    extra_filters.append("other.home_country = %s")
                    params.append(location_code)

                extra_sql = ""
                if extra_filters:
                    extra_sql = " AND " + " AND ".join(extra_filters)

                cur.execute(
                    f"""
                    SELECT
                        other.id AS person_id,
                        COALESCE(NULLIF(other.first_name, ''), other.username) AS first_name,
                        COALESCE(NULLIF(other.last_name, ''), '') AS last_name,
                        other.identity_role,
                        other.home_country,
                        my_pref.topic_id,
                        t.name AS topic_name,
                        my_pref.preference_role AS my_role,
                        other_pref.preference_role AS other_role,
                        mr.status AS request_status
                    FROM preference my_pref
                    JOIN person me
                      ON me.id = my_pref.person_id
                    JOIN topic t
                      ON t.id = my_pref.topic_id
                    JOIN preference other_pref
                      ON other_pref.topic_id = my_pref.topic_id
                    JOIN person other
                      ON other.id = other_pref.person_id
                    LEFT JOIN mentorship_request mr
                      ON mr.topic_id = my_pref.topic_id
                     AND LEAST(mr.sender_id, mr.receiver_id) = LEAST(%s, other.id)
                     AND GREATEST(mr.sender_id, mr.receiver_id) = GREATEST(%s, other.id)
                    WHERE my_pref.person_id = %s
                      AND other.id <> %s
                      AND other.identity_role = %s
                      AND me.preferences_published = TRUE
                      AND other.preferences_published = TRUE
                      AND (
                            (my_pref.preference_role = 'mentee' AND other_pref.preference_role = 'mentor')
                         OR (my_pref.preference_role = 'mentor' AND other_pref.preference_role = 'mentee')
                         OR (my_pref.preference_role = 'two_way' AND other_pref.preference_role = 'two_way')
                      )
                      {extra_sql}
                    ORDER BY t.name, first_name, last_name
                    """,
                    [user_id, user_id, user_id, user_id, opposite_role, *params[3:]]
                )

                rows = cur.fetchall()

                results = []
                for row in rows:
                    results.append({
                        "person_id": row[0],
                        "first_name": row[1],
                        "last_name": row[2],
                        "identity_role": row[3],
                        "home_country": row[4] or "Not specified",
                        "topic_id": row[5],
                        "topic_name": row[6],
                        "my_role": row[7],
                        "other_role": row[8],
                        "request_status": row[9]
                    })

                return jsonify({"results": results}), 200

    except Exception as e:
        print(f"Error in matching search: {str(e)}")
        return jsonify({"error": str(e)}), 500
        
        
@app.get("/api/matching/filter-options")
@login_required
def api_matching_filter_options():
    """Load topic and location dropdown options for matching page."""
    user_id = session.get("user_id")

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:

                # check if user has published preferences
                cur.execute(
                    "SELECT preferences_published FROM person WHERE id=%s",
                    (user_id,)
                )
                row = cur.fetchone()

                if not row:
                    return jsonify({"error": "User not found"}), 404

                preferences_published = row[0]

                # topics = only user's own preferences
                cur.execute(
                    """
                    SELECT p.topic_id, t.name, p.preference_role
                    FROM preference p
                    JOIN topic t ON p.topic_id = t.id
                    WHERE p.person_id = %s
                    ORDER BY t.name
                    """,
                    (user_id,)
                )

                topic_options = [
                    {
                        "topic_id": r[0],
                        "topic_name": r[1],
                        "preference_role": r[2]
                    }
                    for r in cur.fetchall()
                ]

                # countries
                cur.execute(
                    "SELECT code, name FROM country ORDER BY name"
                )

                countries = [
                    {"code": r[0], "name": r[1]}
                    for r in cur.fetchall()
                ]

                return jsonify({
                    "preferences_published": preferences_published,
                    "topic_options": topic_options,
                    "countries": countries
                }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500        
        
@app.get("/api/matching/public-profile/<int:person_id>")
@login_required
def api_matching_public_profile(person_id):
    """Return simplified published profile for modal view."""

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:

                cur.execute(
                    """
                    SELECT first_name, last_name, identity_role, home_country,
                           preferences_published
                    FROM person
                    WHERE id = %s
                    """,
                    (person_id,)
                )

                row = cur.fetchone()

                if not row:
                    return jsonify({"error": "User not found"}), 404

                first_name, last_name, role, home_country, pref_pub = row

                preferences = []

                if pref_pub:
                    cur.execute(
                        """
                        SELECT t.name, p.preference_role
                        FROM preference p
                        JOIN topic t ON p.topic_id = t.id
                        WHERE p.person_id = %s
                        ORDER BY t.name
                        """,
                        (person_id,)
                    )

                    preferences = [
                        {
                            "topic_name": r[0],
                            "preference_role": r[1]
                        }
                        for r in cur.fetchall()
                    ]

                return jsonify({
                    "first_name": first_name,
                    "last_name": last_name,
                    "identity_role": role,
                    "home_country": home_country,
                    "preferences": preferences
                }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500        
        
@app.post("/api/matching/request")
@login_required
def api_matching_request():
    """Send a matching request for one exact topic match."""
    sender_id = session.get("user_id")
    data = request.get_json() or {}

    receiver_id = data.get("receiver_id")
    topic_id = data.get("topic_id")

    if not receiver_id or not topic_id:
        return jsonify({"error": "receiver_id and topic_id are required"}), 400

    if sender_id == receiver_id:
        return jsonify({"error": "Cannot send request to yourself"}), 400

    try:
        receiver_id = int(receiver_id)
        topic_id = int(topic_id)
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid request data"}), 400

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                # Validate strict match on this exact topic
                cur.execute(
                    """
                    SELECT 1
                    FROM preference my_pref
                    JOIN person me ON me.id = my_pref.person_id
                    JOIN preference other_pref ON other_pref.topic_id = my_pref.topic_id
                    JOIN person other ON other.id = other_pref.person_id
                    WHERE my_pref.person_id = %s
                      AND other.id = %s
                      AND my_pref.topic_id = %s
                      AND other.id <> %s
                      AND me.preferences_published = TRUE
                      AND other.preferences_published = TRUE
                      AND (
                            (me.identity_role = 'student' AND other.identity_role = 'alumni')
                         OR (me.identity_role = 'alumni' AND other.identity_role = 'student')
                      )
                      AND (
                            (my_pref.preference_role = 'mentee' AND other_pref.preference_role = 'mentor')
                         OR (my_pref.preference_role = 'mentor' AND other_pref.preference_role = 'mentee')
                         OR (my_pref.preference_role = 'two_way' AND other_pref.preference_role = 'two_way')
                      )
                    LIMIT 1
                    """,
                    (sender_id, receiver_id, topic_id, sender_id)
                )
                valid_match = cur.fetchone()

                if not valid_match:
                    return jsonify({"error": "This request does not match the current strict topic-role rules."}), 400

                # Check existing request for same pair + same topic, any direction
                cur.execute(
                    """
                    SELECT id, status
                    FROM mentorship_request
                    WHERE topic_id = %s
                      AND LEAST(sender_id, receiver_id) = LEAST(%s, %s)
                      AND GREATEST(sender_id, receiver_id) = GREATEST(%s, %s)
                    LIMIT 1
                    """,
                    (topic_id, sender_id, receiver_id, sender_id, receiver_id)
                )
                existing = cur.fetchone()

                if existing:
                    return jsonify({
                        "error": f"Request already exists with status: {existing[1]}"
                    }), 409

                cur.execute(
                    """
                    INSERT INTO mentorship_request (sender_id, receiver_id, topic_id, status)
                    VALUES (%s, %s, %s, 'pending')
                    RETURNING id
                    """,
                    (sender_id, receiver_id, topic_id)
                )
                request_id = cur.fetchone()[0]

            conn.commit()
            return jsonify({
                "ok": True,
                "request_id": request_id,
                "message": "Request sent successfully!"
            }), 201

    except Exception as e:
        print(f"Error sending request: {str(e)}")
        return jsonify({"error": str(e)}), 500




@app.get("/requests-management")
@login_required
def requests_management_page():
    """Show incoming pending requests page"""
    return render_template("requests_management.html")
    
@app.get("/api/requests-management/overview")
@login_required
def api_requests_management_overview():
    """Get current user's received and sent requests grouped by status"""
    user_id = session.get("user_id")

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                # current user info for header
                cur.execute(
                    """
                    SELECT id, username, first_name, last_name, identity_role
                    FROM person
                    WHERE id = %s
                    """,
                    (user_id,)
                )
                me = cur.fetchone()

                if not me:
                    return jsonify({"error": "User not found"}), 404

                current_user = {
                    "id": me[0],
                    "username": me[1],
                    "first_name": me[2],
                    "last_name": me[3],
                    "identity_role": me[4]
                }

                # received requests
                cur.execute(
                    """
                    SELECT
                        mr.id AS request_id,
                        mr.sender_id,
                        mr.receiver_id,
                        COALESCE(NULLIF(sender.first_name, ''), sender.username) AS sender_first_name,
                        COALESCE(NULLIF(sender.last_name, ''), '') AS sender_last_name,
                        sender.identity_role AS sender_identity_role,
                        COALESCE(NULLIF(receiver.first_name, ''), receiver.username) AS receiver_first_name,
                        COALESCE(NULLIF(receiver.last_name, ''), '') AS receiver_last_name,
                        receiver.identity_role AS receiver_identity_role,
                        mr.topic_id,
                        t.name AS topic_name,
                        mr.status,
                        mr.created_at,
                        mr.updated_at
                    FROM mentorship_request mr
                    JOIN person sender
                      ON sender.id = mr.sender_id
                    JOIN person receiver
                      ON receiver.id = mr.receiver_id
                    JOIN topic t
                      ON t.id = mr.topic_id
                    WHERE mr.receiver_id = %s
                    ORDER BY
                        CASE mr.status
                            WHEN 'pending' THEN 1
                            WHEN 'accepted' THEN 2
                            WHEN 'rejected' THEN 3
                            ELSE 4
                        END,
                        mr.updated_at DESC,
                        mr.created_at DESC,
                        mr.id DESC
                    """,
                    (user_id,)
                )

                received_pending = []
                received_accepted = []
                received_rejected = []

                for row in cur.fetchall():
                    item = {
                        "request_id": row[0],
                        "sender_id": row[1],
                        "receiver_id": row[2],
                        "sender_first_name": row[3],
                        "sender_last_name": row[4],
                        "sender_identity_role": row[5],
                        "receiver_first_name": row[6],
                        "receiver_last_name": row[7],
                        "receiver_identity_role": row[8],
                        "topic_id": row[9],
                        "topic_name": row[10],
                        "status": row[11],
                        "created_at": str(row[12]) if row[12] else None,
                        "updated_at": str(row[13]) if row[13] else None
                    }

                    if row[11] == "pending":
                        received_pending.append(item)
                    elif row[11] == "accepted":
                        received_accepted.append(item)
                    elif row[11] == "rejected":
                        received_rejected.append(item)

                # sent requests
                cur.execute(
                    """
                    SELECT
                        mr.id AS request_id,
                        mr.sender_id,
                        mr.receiver_id,
                        COALESCE(NULLIF(sender.first_name, ''), sender.username) AS sender_first_name,
                        COALESCE(NULLIF(sender.last_name, ''), '') AS sender_last_name,
                        sender.identity_role AS sender_identity_role,
                        COALESCE(NULLIF(receiver.first_name, ''), receiver.username) AS receiver_first_name,
                        COALESCE(NULLIF(receiver.last_name, ''), '') AS receiver_last_name,
                        receiver.identity_role AS receiver_identity_role,
                        mr.topic_id,
                        t.name AS topic_name,
                        mr.status,
                        mr.created_at,
                        mr.updated_at
                    FROM mentorship_request mr
                    JOIN person sender
                      ON sender.id = mr.sender_id
                    JOIN person receiver
                      ON receiver.id = mr.receiver_id
                    JOIN topic t
                      ON t.id = mr.topic_id
                    WHERE mr.sender_id = %s
                    ORDER BY
                        CASE mr.status
                            WHEN 'pending' THEN 1
                            WHEN 'accepted' THEN 2
                            WHEN 'rejected' THEN 3
                            ELSE 4
                        END,
                        mr.updated_at DESC,
                        mr.created_at DESC,
                        mr.id DESC
                    """,
                    (user_id,)
                )

                sent_pending = []
                sent_accepted = []
                sent_rejected = []

                for row in cur.fetchall():
                    item = {
                        "request_id": row[0],
                        "sender_id": row[1],
                        "receiver_id": row[2],
                        "sender_first_name": row[3],
                        "sender_last_name": row[4],
                        "sender_identity_role": row[5],
                        "receiver_first_name": row[6],
                        "receiver_last_name": row[7],
                        "receiver_identity_role": row[8],
                        "topic_id": row[9],
                        "topic_name": row[10],
                        "status": row[11],
                        "created_at": str(row[12]) if row[12] else None,
                        "updated_at": str(row[13]) if row[13] else None
                    }

                    if row[11] == "pending":
                        sent_pending.append(item)
                    elif row[11] == "accepted":
                        sent_accepted.append(item)
                    elif row[11] == "rejected":
                        sent_rejected.append(item)

        return jsonify({
            "ok": True,
            "current_user": current_user,
            "received_pending": received_pending,
            "received_accepted": received_accepted,
            "received_rejected": received_rejected,
            "sent_pending": sent_pending,
            "sent_accepted": sent_accepted,
            "sent_rejected": sent_rejected
        }), 200

    except Exception as e:
        print(f"Error loading requests overview: {str(e)}")
        return jsonify({"error": str(e)}), 500



@app.post("/api/requests-management/request/<int:request_id>/status")
@login_required
def api_requests_management_update_status(request_id):
    """Receiver accepts or rejects a pending request"""
    user_id = session.get("user_id")
    data = request.get_json() or {}
    new_status = (data.get("status") or "").strip().lower()

    if new_status not in ("accepted", "rejected"):
        return jsonify({"error": "Status must be 'accepted' or 'rejected'"}), 400

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                # 1. Find request and ensure current user is the receiver
                cur.execute(
                    """
                    SELECT id, sender_id, receiver_id, topic_id, status, mentorship_id
                    FROM mentorship_request
                    WHERE id = %s
                      AND receiver_id = %s
                    """,
                    (request_id, user_id)
                )
                request_row = cur.fetchone()

                if not request_row:
                    return jsonify({"error": "Request not found"}), 404

                req_id, sender_id, receiver_id, topic_id, current_status, existing_mentorship_id = request_row

                if current_status != "pending":
                    return jsonify({"error": "Only pending requests can be updated"}), 400

                # ------------------------------------------------------------
                # REJECT branch
                # ------------------------------------------------------------
                if new_status == "rejected":
                    cur.execute(
                        """
                        UPDATE mentorship_request
                        SET status = 'rejected',
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = %s
                        """,
                        (request_id,)
                    )

                    conn.commit()
                    return jsonify({
                        "ok": True,
                        "message": "Request rejected successfully."
                    }), 200

                # ------------------------------------------------------------
                # ACCEPT branch
                # ------------------------------------------------------------

                # 2. Get sender and receiver identity roles
                cur.execute(
                    """
                    SELECT id, identity_role
                    FROM person
                    WHERE id IN (%s, %s)
                    """,
                    (sender_id, receiver_id)
                )
                people = cur.fetchall()

                if len(people) != 2:
                    return jsonify({"error": "Sender or receiver not found"}), 400

                role_map = {row[0]: row[1] for row in people}
                sender_identity = role_map.get(sender_id)
                receiver_identity = role_map.get(receiver_id)

                # 3. Determine student_id and alumni_id
                if sender_identity == "student" and receiver_identity == "alumni":
                    student_id = sender_id
                    alumni_id = receiver_id
                elif sender_identity == "alumni" and receiver_identity == "student":
                    student_id = receiver_id
                    alumni_id = sender_id
                else:
                    return jsonify({
                        "error": "Invalid request identities. One user must be student and the other must be alumni."
                    }), 400

                # 4. Confirm subtype rows exist
                cur.execute("SELECT person_id FROM student WHERE person_id = %s", (student_id,))
                if not cur.fetchone():
                    return jsonify({"error": "Student subtype record not found"}), 400

                cur.execute("SELECT person_id FROM alumni WHERE person_id = %s", (alumni_id,))
                if not cur.fetchone():
                    return jsonify({"error": "Alumni subtype record not found"}), 400

                # 5. Get preference roles for both users on this topic
                cur.execute(
                    """
                    SELECT person_id, preference_role
                    FROM preference
                    WHERE topic_id = %s
                      AND person_id IN (%s, %s)
                    """,
                    (topic_id, student_id, alumni_id)
                )
                pref_rows = cur.fetchall()

                if len(pref_rows) != 2:
                    return jsonify({"error": "Missing preference records for this topic"}), 400

                pref_map = {row[0]: row[1] for row in pref_rows}
                student_pref = pref_map.get(student_id)
                alumni_pref = pref_map.get(alumni_id)

                # 6. Derive mentorship_type
                if alumni_pref == "mentor" and student_pref == "mentee":
                    mentorship_type = "traditional"
                elif alumni_pref == "mentee" and student_pref == "mentor":
                    mentorship_type = "reverse"
                elif alumni_pref == "two_way" and student_pref == "two_way":
                    mentorship_type = "two_way"
                else:
                    return jsonify({
                        "error": "Preference roles do not form a valid mentorship type"
                    }), 400

                # 7. Avoid duplicate mentorship for same topic + student + alumni
                cur.execute(
                    """
                    SELECT id
                    FROM mentorship
                    WHERE topic_id = %s
                      AND student_id = %s
                      AND alumni_id = %s
                    """,
                    (topic_id, student_id, alumni_id)
                )
                existing_mentorship = cur.fetchone()

                if existing_mentorship:
                    mentorship_id = existing_mentorship[0]
                else:
                    # 8. Insert mentorship
                    cur.execute(
                        """
                        INSERT INTO mentorship (
                            student_id,
                            alumni_id,
                            topic_id,
                            mentorship_type,
                            status,
                            start_date
                        )
                        VALUES (%s, %s, %s, %s, 'active', CURRENT_DATE)
                        RETURNING id
                        """,
                        (student_id, alumni_id, topic_id, mentorship_type)
                    )
                    mentorship_id = cur.fetchone()[0]

                # 9. Update request
                cur.execute(
                    """
                    UPDATE mentorship_request
                    SET status = 'accepted',
                        mentorship_id = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                    """,
                    (mentorship_id, request_id)
                )

            conn.commit()

        return jsonify({
            "ok": True,
            "message": "Request accepted and mentorship created successfully.",
            "mentorship_id": mentorship_id
        }), 200

    except Exception as e:
        print(f"Error updating request status: {str(e)}")
        return jsonify({"error": str(e)}), 500



@app.get("/mentorship-management")
@login_required
def mentorship_management_page():
    """Show mentorship management page"""
    return render_template("mentorship_management.html")


@app.get("/api/mentorship-management/active")
@login_required
def api_mentorship_management_active():
    """Get active mentorships for current user"""
    user_id = session.get("user_id")

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                # current user info for header
                cur.execute(
                    """
                    SELECT id, username, first_name, last_name, identity_role
                    FROM person
                    WHERE id = %s
                    """,
                    (user_id,)
                )
                me = cur.fetchone()

                if not me:
                    return jsonify({"error": "User not found"}), 404

                current_user = {
                    "id": me[0],
                    "username": me[1],
                    "first_name": me[2],
                    "last_name": me[3],
                    "identity_role": me[4]
                }

                # active mentorships where current user is student or alumni
                cur.execute(
                    """
                    SELECT
                        m.id AS mentorship_id,
                        m.student_id,
                        m.alumni_id,
                        m.topic_id,
                        m.mentorship_type,
                        m.status,
                        m.start_date,
                        m.end_date,
                        t.name AS topic_name,
                        p.id AS other_person_id,
                        COALESCE(NULLIF(p.first_name, ''), p.username) AS other_first_name,
                        COALESCE(NULLIF(p.last_name, ''), '') AS other_last_name,
                        p.identity_role AS other_identity_role
                    FROM mentorship m
                    JOIN topic t
                      ON t.id = m.topic_id
                    JOIN person p
                      ON p.id = CASE
                          WHEN m.student_id = %s THEN m.alumni_id
                          ELSE m.student_id
                      END
                    WHERE (m.student_id = %s OR m.alumni_id = %s)
                      AND m.status = 'active'
                    ORDER BY m.start_date DESC, m.id DESC
                    """,
                    (user_id, user_id, user_id)
                )

                mentorships = []
                for row in cur.fetchall():
                    mentorships.append({
                        "mentorship_id": row[0],
                        "student_id": row[1],
                        "alumni_id": row[2],
                        "topic_id": row[3],
                        "mentorship_type": row[4],
                        "status": row[5],
                        "start_date": str(row[6]) if row[6] else None,
                        "end_date": str(row[7]) if row[7] else None,
                        "topic_name": row[8],
                        "other_person_id": row[9],
                        "other_first_name": row[10],
                        "other_last_name": row[11],
                        "other_identity_role": row[12]
                    })

        return jsonify({
            "ok": True,
            "current_user": current_user,
            "mentorships": mentorships
        }), 200

    except Exception as e:
        print(f"Error loading mentorships: {str(e)}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True)