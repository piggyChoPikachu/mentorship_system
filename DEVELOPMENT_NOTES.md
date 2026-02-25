# Mentorship System - Development Notes

**Current Date:** 2026-02-25  
**Status:** Profile System Complete ✅

---

## 📊 Project Overview

A Flask-based mentorship system that connects students with alumni.

**Main Features:**
- User registration (Student/Alumni)
- User authentication (Login/Logout)
- Profile management (6 containers)
- Matching system (TODO)
- Preferences (TODO)

---

## ✅ Completed Features

### 1. Authentication System

**Routes:**
- `POST /api/auth/register` - Register new user
- `POST /api/auth/login` - Login user
- `GET /logout` - Logout user

**Features:**
- Username & email validation
- Password hashing (werkzeug)
- Session management
- Role-based (student/alumni)
- Register only needs: username, email, password, role

**Database Tables:**
- `person` - Basic user info
- `student` - Student-specific data
- `alumni` - Alumni-specific data

---

### 2. Profile System (MAIN FEATURE)

**Status:** ✅ Complete with modals

**Frontend:**
- Single HTML file: `templates/profile.html`
- 6 Containers:
  1. **Personal Information** - username, email, name, phone, address, country, role
  2. **Education** - study level, programme, institute, department, faculty, dates
  3. **Career** (Alumni only) - job title, company, location, dates, description
  4. **Skills** - skill tags with add/remove
  5. **Interests** - interest tags with add/remove
  6. **Expertise** (Alumni only) - expertise tags with add/remove

**Design:**
- View mode (read-only display)
- Edit mode (forms + modals)
- Modals for adding items (no page navigation)
- Empty states with helpful messages
- Responsive design (Bootstrap 5)

**Views (SQL):**
- `v_student_profile` - Student view with all data as JSON
- `v_alumni_profile` - Alumni view with career & expertise

---

### 3. Backend Routes (Flask)

#### Profile Routes

**GET /profile**
- Shows profile in view/edit mode
- Parses JSON from views
- Gets countries for dropdown
- Parameters: `mode=view|edit`

**POST /profile/personal/save**
- Updates: first_name, last_name, phone_number, address, home_country
- JSON request
- Returns: `{"ok": true}`

---

#### Education Routes

**POST /profile/education/add**
- Adds education record
- Parameters: study_level_id, programme_id, start_date, end_date
- JSON request
- Returns: `{"ok": true, "education_id": 123}`

**DELETE /profile/education/<id>**
- Deletes education record
- Ownership verification
- Returns: `{"ok": true}`

---

#### Career Routes (Alumni only)

**POST /profile/career/add**
- Adds career record
- Parameters: job_title, company_name, city, work_country_code, start_date, end_date, job_description
- JSON request
- Returns: `{"ok": true, "career_id": 123}`

**DELETE /profile/career/<id>**
- Deletes career record
- Ownership verification
- Returns: `{"ok": true}`

---

#### Skills Routes

**POST /profile/skill/add**
- Adds or links skill
- Auto-creates skill if not exists
- Parameters: skill_name
- JSON request
- Returns: `{"ok": true, "skill_id": 123}`

**DELETE /profile/skill/<id>**
- Removes skill from person
- Ownership verification
- Returns: `{"ok": true}`

---

#### Interests Routes

**POST /profile/interest/add**
- Adds or links interest
- Auto-creates interest if not exists
- Parameters: interest_name
- JSON request
- Returns: `{"ok": true, "interest_id": 123}`

**DELETE /profile/interest/<id>**
- Removes interest from person
- Ownership verification
- Returns: `{"ok": true}`

---

#### Expertise Routes (Alumni only)

**POST /profile/expertise/add**
- Adds or links expertise
- Auto-creates expertise if not exists
- Parameters: expertise_name
- JSON request
- Returns: `{"ok": true, "expertise_id": 123}`

**DELETE /profile/expertise/<id>**
- Removes expertise from alumni
- Ownership verification
- Returns: `{"ok": true}`

---

### 4. Database Schema

#### Views (Automatically Generated)

**v_student_profile**
```sql
Columns:
- person_id (INT)
- username (VARCHAR)
- email (VARCHAR)
- phone_number (VARCHAR)
- address (VARCHAR)
- first_name (VARCHAR)
- last_name (VARCHAR)
- home_country_code (VARCHAR)
- home_country_name (VARCHAR)
- role (VARCHAR) = 'student'
- education (JSON array)
- skills (JSON array)
- interests (JSON array)