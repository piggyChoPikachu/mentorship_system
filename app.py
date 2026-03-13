from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from werkzeug.security import generate_password_hash
from werkzeug.security import check_password_hash
import psycopg2
import psycopg2.errors
import os
from dotenv import load_dotenv
from datetime import datetime
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
# HOME & AUTHENTICATION ROUTES
# ============================================================

@app.route("/")
def home():
    """Show register page"""
    return render_template("register.html")


@app.post("/api/auth/register")
def api_register():
    """Register new user"""
    data = request.get_json(silent=True) or {}

    username = (data.get("username") or "").strip()
    email = (data.get("email") or "").strip()
    password = data.get("password") or ""
    role = (data.get("role") or "").strip().lower()   # expect "student" or "alumni"

    if not username or not email or not password or role not in ("student", "alumni"):
        return jsonify({"error": "username, email, password, and role (student|alumni) are required"}), 400

    password_hash = generate_password_hash(password)

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                # 1) insert into person
                cur.execute(
                    """
                    INSERT INTO person (username, email, password_hash, first_name, last_name)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (username, email, password_hash, "", "")
                )
                person_id = cur.fetchone()[0]

                # 2) insert into subtype
                if role == "student":
                    cur.execute("INSERT INTO student (person_id) VALUES (%s)", (person_id,))
                else:
                    cur.execute("INSERT INTO alumni (person_id) VALUES (%s)", (person_id,))

            conn.commit()
            return jsonify({"ok": True, "person_id": person_id}), 201

    except psycopg2.errors.UniqueViolation:
        return jsonify({"error": "username or email already exists"}), 409
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    
@app.route("/login")
def login_page():
    """Show login page"""
    return render_template("login.html")
    
    
@app.post("/api/auth/login")
def api_login():
    """Login user"""
    data = request.get_json() or {}

    identifier = (data.get("identifier") or "").strip()
    password = data.get("password") or ""

    if not identifier or not password:
        return jsonify({"error": "Username/email and password are required"}), 400

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                # Query person by username or email
                cur.execute(
                    "SELECT id, password_hash FROM person WHERE username=%s OR email=%s",
                    (identifier, identifier)
                )
                user = cur.fetchone()
                
                if not user:
                    return jsonify({"error": "Invalid credentials"}), 401
                
                user_id, password_hash = user
                if not check_password_hash(password_hash, password):
                    return jsonify({"error": "Invalid credentials"}), 401
                
                # Get role
                cur.execute("SELECT 1 FROM alumni WHERE person_id=%s", (user_id,))
                role = "alumni" if cur.fetchone() else "student"
        
        # Only now, AFTER successful queries
        session["user_id"] = user_id
        session["role"] = role
        return jsonify({"ok": True})

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
    """Show user profile (view mode)"""
    user_id = session.get("user_id")
    role = session.get("role")
    mode = request.args.get("mode", "view")
    
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                # Get profile data from view
                if role == "student":
                    cur.execute("SELECT * FROM v_student_profile_1 WHERE person_id = %s", (user_id,))
                else:  # alumni
                    cur.execute("SELECT * FROM v_alumni_profile WHERE person_id = %s", (user_id,))
                
                profile_row = cur.fetchone()
                
                if not profile_row:
                    return jsonify({"error": "Profile not found"}), 404
                
                col_names = [desc[0] for desc in cur.description]
                profile_data = dict(zip(col_names, profile_row))
                
                # ✅ FIX: Handle JSON arrays that come from json_agg
                # These are already lists, not strings
                for key in ["education", "skills", "interests"]:
                    value = profile_data.get(key)
                    if value is None:
                        profile_data[key] = []
                    elif isinstance(value, list):
                        # Already a list (from json_agg)
                        profile_data[key] = value
                    elif isinstance(value, str):
                        # String needs parsing
                        try:
                            profile_data[key] = json.loads(value)
                        except:
                            profile_data[key] = []
                    else:
                        profile_data[key] = []
                
                # Alumni only fields
                if role == "alumni":
                    for key in ["career", "expertise"]:
                        value = profile_data.get(key)
                        if value is None:
                            profile_data[key] = []
                        elif isinstance(value, list):
                            profile_data[key] = value
                        elif isinstance(value, str):
                            try:
                                profile_data[key] = json.loads(value)
                            except:
                                profile_data[key] = []
                        else:
                            profile_data[key] = []
                
                # Get countries for dropdown (edit mode)
                countries = []
                if mode == "edit":
                    cur.execute("SELECT code, name FROM country ORDER BY name")
                    countries = [{"code": row[0], "name": row[1]} for row in cur.fetchall()]
        
        return render_template(
            "profile.html", 
            profile=profile_data, 
            mode=mode,
            countries=countries
        )
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.post("/profile/personal/save")
@login_required
def profile_personal_save():
    """Save personal info (Person Info Container)"""
    user_id = session.get("user_id")
    
    data = request.get_json() or {}
    first_name = (data.get("first_name") or "").strip()
    last_name = (data.get("last_name") or "").strip()
    phone_number = (data.get("phone_number") or "").strip() or None
    address = (data.get("address") or "").strip() or None
    home_country = (data.get("home_country") or "").strip() or None

    if not first_name or not last_name:
        return jsonify({"error": "First name and last name are required"}), 400

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
            return jsonify({"ok": True})
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500





@app.post("/profile/education/add")
@login_required
def education_add():
    """Add education record"""
    user_id = session.get("user_id")
    
    data = request.get_json() or {}
    programme_id = data.get("programme_id")
    study_level_id = data.get("study_level_id")
    start_date = data.get("start_date") or None
    end_date = data.get("end_date") or None

    if not programme_id or not study_level_id:
        return jsonify({"error": "Programme and study level are required"}), 400

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
            return jsonify({"ok": True, "education_id": edu_id}), 201
    
    except psycopg2.errors.UniqueViolation:
        return jsonify({"error": "This education record already exists"}), 409
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.delete("/profile/education/<int:education_id>")
@login_required
def education_delete(education_id):
    """Delete education record"""
    user_id = session.get("user_id")
    
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                # Verify ownership
                cur.execute("SELECT person_id FROM education WHERE id=%s", (education_id,))
                result = cur.fetchone()
                if not result or result[0] != user_id:
                    return jsonify({"error": "Unauthorized"}), 403
                
                # Delete
                cur.execute("DELETE FROM education WHERE id=%s", (education_id,))
            conn.commit()
            return jsonify({"ok": True})
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.post("/profile/career/add")
@login_required
def career_add():
    """Add career record (alumni only)"""
    user_id = session.get("user_id")
    role = session.get("role")
    
    if role != "alumni":
        return jsonify({"error": "Only alumni can add career records"}), 403
    
    data = request.get_json() or {}
    job_title = (data.get("job_title") or "").strip()
    company_name = (data.get("company_name") or "").strip()
    city = (data.get("city") or "").strip() or None
    work_country_code = (data.get("work_country_code") or "").strip() or None
    start_date = data.get("start_date") or None
    end_date = data.get("end_date") or None
    job_description = (data.get("job_description") or "").strip() or None

    if not job_title or not company_name or not start_date:
        return jsonify({"error": "Job title, company name, and start date are required"}), 400

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO career (alumni_id, job_title, company_name, city, work_country_code, start_date, end_date, job_description)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (user_id, job_title, company_name, city, work_country_code, start_date, end_date, job_description)
                )
                career_id = cur.fetchone()[0]
            conn.commit()
            return jsonify({"ok": True, "career_id": career_id}), 201
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.delete("/profile/career/<int:career_id>")
@login_required
def career_delete(career_id):
    """Delete career record"""
    user_id = session.get("user_id")
    
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                # Verify ownership
                cur.execute("SELECT alumni_id FROM career WHERE id=%s", (career_id,))
                result = cur.fetchone()
                if not result or result[0] != user_id:
                    return jsonify({"error": "Unauthorized"}), 403
                
                # Delete
                cur.execute("DELETE FROM career WHERE id=%s", (career_id,))
            conn.commit()
            return jsonify({"ok": True})
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.post("/profile/skill/add")
@login_required
def skill_add():
    """Add skill"""
    user_id = session.get("user_id")
    
    data = request.get_json() or {}
    skill_name = (data.get("skill_name") or "").strip()

    if not skill_name:
        return jsonify({"error": "Skill name is required"}), 400

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                # Get or create skill
                cur.execute(
                    "SELECT id FROM skill WHERE LOWER(name)=LOWER(%s)",
                    (skill_name,)
                )
                skill_result = cur.fetchone()
                
                if skill_result:
                    skill_id = skill_result[0]
                else:
                    cur.execute(
                        "INSERT INTO skill (name) VALUES (%s) RETURNING id",
                        (skill_name,)
                    )
                    skill_id = cur.fetchone()[0]
                
                # Add to person_skill
                cur.execute(
                    "INSERT INTO person_skill (person_id, skill_id) VALUES (%s, %s)",
                    (user_id, skill_id)
                )
            conn.commit()
            return jsonify({"ok": True, "skill_id": skill_id}), 201
    
    except psycopg2.errors.UniqueViolation:
        return jsonify({"error": "You already have this skill"}), 409
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.delete("/profile/skill/<int:skill_id>")
@login_required
def skill_delete(skill_id):
    """Delete skill"""
    user_id = session.get("user_id")
    
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                # Verify ownership
                cur.execute("SELECT person_id FROM person_skill WHERE skill_id=%s AND person_id=%s", (skill_id, user_id))
                if not cur.fetchone():
                    return jsonify({"error": "Unauthorized"}), 403
                
                # Delete
                cur.execute("DELETE FROM person_skill WHERE skill_id=%s AND person_id=%s", (skill_id, user_id))
            conn.commit()
            return jsonify({"ok": True})
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.post("/profile/interest/add")
@login_required
def interest_add():
    """Add interest"""
    user_id = session.get("user_id")
    
    data = request.get_json() or {}
    interest_name = (data.get("interest_name") or "").strip()

    if not interest_name:
        return jsonify({"error": "Interest name is required"}), 400

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                # Get or create interest
                cur.execute(
                    "SELECT id FROM interest WHERE LOWER(name)=LOWER(%s)",
                    (interest_name,)
                )
                interest_result = cur.fetchone()
                
                if interest_result:
                    interest_id = interest_result[0]
                else:
                    cur.execute(
                        "INSERT INTO interest (name) VALUES (%s) RETURNING id",
                        (interest_name,)
                    )
                    interest_id = cur.fetchone()[0]
                
                # Add to person_interest
                cur.execute(
                    "INSERT INTO person_interest (person_id, interest_id) VALUES (%s, %s)",
                    (user_id, interest_id)
                )
            conn.commit()
            return jsonify({"ok": True, "interest_id": interest_id}), 201
    
    except psycopg2.errors.UniqueViolation:
        return jsonify({"error": "You already have this interest"}), 409
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.delete("/profile/interest/<int:interest_id>")
@login_required
def interest_delete(interest_id):
    """Delete interest"""
    user_id = session.get("user_id")
    
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                # Verify ownership
                cur.execute("SELECT person_id FROM person_interest WHERE interest_id=%s AND person_id=%s", (interest_id, user_id))
                if not cur.fetchone():
                    return jsonify({"error": "Unauthorized"}), 403
                
                # Delete
                cur.execute("DELETE FROM person_interest WHERE interest_id=%s AND person_id=%s", (interest_id, user_id))
            conn.commit()
            return jsonify({"ok": True})
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.post("/profile/expertise/add")
@login_required
def expertise_add():
    """Add expertise (alumni only)"""
    user_id = session.get("user_id")
    role = session.get("role")
    
    if role != "alumni":
        return jsonify({"error": "Only alumni can add expertise"}), 403
    
    data = request.get_json() or {}
    expertise_name = (data.get("expertise_name") or "").strip()

    if not expertise_name:
        return jsonify({"error": "Expertise name is required"}), 400

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                # Get or create expertise
                cur.execute(
                    "SELECT id FROM expertise WHERE LOWER(name)=LOWER(%s)",
                    (expertise_name,)
                )
                expertise_result = cur.fetchone()
                
                if expertise_result:
                    expertise_id = expertise_result[0]
                else:
                    cur.execute(
                        "INSERT INTO expertise (name) VALUES (%s) RETURNING id",
                        (expertise_name,)
                    )
                    expertise_id = cur.fetchone()[0]
                
                # Add to alumni_expertise
                cur.execute(
                    "INSERT INTO alumni_expertise (alumni_id, expertise_id) VALUES (%s, %s)",
                    (user_id, expertise_id)
                )
            conn.commit()
            return jsonify({"ok": True, "expertise_id": expertise_id}), 201
    
    except psycopg2.errors.UniqueViolation:
        return jsonify({"error": "You already have this expertise"}), 409
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.delete("/profile/expertise/<int:expertise_id>")
@login_required
def expertise_delete(expertise_id):
    """Delete expertise"""
    user_id = session.get("user_id")
    
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                # Verify ownership
                cur.execute("SELECT alumni_id FROM alumni_expertise WHERE expertise_id=%s AND alumni_id=%s", (expertise_id, user_id))
                if not cur.fetchone():
                    return jsonify({"error": "Unauthorized"}), 403
                
                # Delete
                cur.execute("DELETE FROM alumni_expertise WHERE expertise_id=%s AND alumni_id=%s", (expertise_id, user_id))
            conn.commit()
            return jsonify({"ok": True})
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ============================================================
# MATCHING ROUTES
# ============================================================

@app.get("/matching")
@login_required
def matching_page():
    """Show matching/search page"""
    return render_template("matching.html")


@app.get("/api/topics")
@login_required
def api_topics():
    """Return all topics for filter dropdown"""
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id, name FROM topic ORDER BY name")
                topics = [{"id": row[0], "name": row[1]} for row in cur.fetchall()]
                return jsonify({"topics": topics}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.get("/api/countries")
@login_required
def api_countries():
    """Return all countries for filter dropdown"""
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT code, name FROM country ORDER BY name")
                countries = [{"code": row[0], "name": row[1]} for row in cur.fetchall()]
                return jsonify({"countries": countries}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.get("/api/matching/filter-options")
@login_required
def api_matching_filter_options():
    """Return filter dropdown data (topics and countries)"""
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id, name FROM topic ORDER BY name")
                topics = [{"id": row[0], "name": row[1]} for row in cur.fetchall()]

                cur.execute("SELECT code, name FROM country ORDER BY name")
                countries = [{"code": row[0], "name": row[1]} for row in cur.fetchall()]

                return jsonify({"topics": topics, "countries": countries}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.get("/api/matching/search")
@login_required
def api_matching_search():
    """Search for matching mentors/mentees using strict topic-role matching"""
    user_id = session.get("user_id")

    topic_id = request.args.get("topic_id", type=int)
    role_filter = request.args.get("role", type=str)
    location_code = request.args.get("location", type=str)

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                # Use the PostgreSQL matching function
                cur.execute("SELECT * FROM get_matching_users(%s)", (user_id,))
                rows = cur.fetchall()
                col_names = [desc[0] for desc in cur.description]

                # Fetch all request statuses involving the current user
                cur.execute(
                    """
                    SELECT
                        CASE WHEN from_person_id = %s THEN to_person_id ELSE from_person_id END,
                        status
                    FROM mentorship_request
                    WHERE from_person_id = %s OR to_person_id = %s
                    ORDER BY created_at DESC
                    """,
                    (user_id, user_id, user_id),
                )
                request_status_map = {}
                for req_row in cur.fetchall():
                    other_id = req_row[0]
                    # Keep the most recent status per user pair
                    if other_id not in request_status_map:
                        request_status_map[other_id] = req_row[1]

                results = []
                for row in rows:
                    row_dict = dict(zip(col_names, row))
                    to_user_id = row_dict.get("to_user_id")
                    topics_data = row_dict.get("topics_with_roles") or []

                    if isinstance(topics_data, str):
                        try:
                            topics_data = json.loads(topics_data)
                        except Exception:
                            topics_data = []

                    # Apply topic filter
                    if topic_id:
                        if not any(t.get("topic_id") == topic_id for t in topics_data):
                            continue

                    # Apply role filter (their preference_role)
                    if role_filter:
                        if not any(t.get("preference_role") == role_filter for t in topics_data):
                            continue

                    # Apply location filter
                    if location_code:
                        if row_dict.get("to_user_home_country") != location_code:
                            continue

                    match = {
                        "id": to_user_id,
                        "first_name": row_dict.get("to_user_first_name", ""),
                        "last_name": row_dict.get("to_user_last_name", ""),
                        "home_country": row_dict.get("to_user_home_country") or "Not specified",
                        "identity_role": row_dict.get("to_user_identity_role", ""),
                        "topics_with_roles": topics_data,
                        "request_status": request_status_map.get(to_user_id),
                    }
                    results.append(match)

                return jsonify({"results": results}), 200

    except Exception as e:
        print(f"Error in matching search: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.get("/api/matching/public-profile/<int:target_user_id>")
@login_required
def api_matching_public_profile(target_user_id):
    """Return public profile info for a matched user"""
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        p.id,
                        p.first_name,
                        p.last_name,
                        p.home_country,
                        CASE WHEN a.person_id IS NOT NULL THEN 'alumni' ELSE 'student' END AS identity_role,
                        c.name AS country_name
                    FROM person p
                    LEFT JOIN alumni a ON a.person_id = p.id
                    LEFT JOIN country c ON c.code = p.home_country
                    WHERE p.id = %s
                    """,
                    (target_user_id,),
                )
                user = cur.fetchone()
                if not user:
                    return jsonify({"error": "User not found"}), 404

                col_names = ["id", "first_name", "last_name", "home_country", "identity_role", "country_name"]
                profile = dict(zip(col_names, user))
                return jsonify({"profile": profile}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.post("/api/matching/request")
@login_required
def api_matching_request():
    """Send a mentorship request after validating the match"""
    user_id = session.get("user_id")
    data = request.get_json(silent=True) or {}
    to_person_id = data.get("to_person_id")

    if not to_person_id:
        return jsonify({"error": "to_person_id is required"}), 400

    if to_person_id == user_id:
        return jsonify({"error": "Cannot send request to yourself"}), 400

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                # Prevent duplicate requests
                cur.execute(
                    """
                    SELECT id, status FROM mentorship_request
                    WHERE (from_person_id = %s AND to_person_id = %s)
                       OR (from_person_id = %s AND to_person_id = %s)
                    """,
                    (user_id, to_person_id, to_person_id, user_id),
                )
                existing = cur.fetchone()
                if existing:
                    return jsonify({"error": "Request already exists", "status": existing[1]}), 409

                # Validate that the two users are a strict match
                cur.execute(
                    "SELECT COUNT(*) FROM get_matching_users(%s) WHERE to_user_id = %s",
                    (user_id, to_person_id),
                )
                count = cur.fetchone()[0]
                if count == 0:
                    return jsonify({"error": "Users are not a valid match"}), 400

                # Insert the request
                cur.execute(
                    """
                    INSERT INTO mentorship_request (from_person_id, to_person_id, status)
                    VALUES (%s, %s, 'pending')
                    RETURNING id
                    """,
                    (user_id, to_person_id),
                )
                request_id = cur.fetchone()[0]
            conn.commit()
            return jsonify({"ok": True, "request_id": request_id}), 201

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


if __name__ == "__main__":
    app.run(debug=True)