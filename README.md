<<<<<<< HEAD
# SmartCare: ML-Based Healthcare Appointment Scheduling and Queue Management System

**Course Code:** CSE-06133230  
**Course Name:** Project Work II  
**Institution:** North East University Bangladesh (NEUB)  
**Submitted to:** Mr. Rana M Luthfur Rahman Pir  

**Prepared by:**
- **Joyashis Das** (ID: 0562410005101003)
- **F. Tabassum Haq Khan** (ID: 0562410005101016)
- **Atiya Mahjabin Maishah** (ID: 0562410005101023)

---

## 1. Project Overview

Traditional healthcare appointment systems rely on static, fixed-duration slots (e.g., rigid 15-minute blocks). However, actual clinical consultations vary widely depending on patient age, visit type (first consultation vs routine follow-up), symptom severity, and chronic conditions. Fixed scheduling often leads to severe clinic overcrowding, unpredictable delays, and frustrated patients.

**SmartCare** addresses these challenges by integrating **Machine Learning** with an end-to-end Django web application:
1. **Consultation Duration Prediction:** Uses a Scikit-Learn Random Forest Regressor to predict the exact expected consultation duration for each patient upon booking.
2. **Dynamic Live Queue Management:** Computes live queue positions and real-time waiting times by summing the ML-predicted durations of preceding patients.
3. **Appointment Demand Forecasting:** Uses a Scikit-Learn Gradient Boosting Regressor to forecast daily patient loads by clinical specialty, assisting hospital administration in staffing and capacity planning.

---

## 2. Proposed Technology Stack

| Layer | Technology |
|---|---|
| **Frontend** | HTML5, CSS3, Bootstrap 5.3, Bootstrap Icons, JavaScript (ES6+), Chart.js |
| **Backend** | Python 3.13, Django 6.1 |
| **Database** | SQLite (Production-ready via Django ORM) |
| **Machine Learning** | Scikit-Learn 1.9, Joblib |
| **Data Processing** | Pandas 3.0, NumPy 2.5 |
| **Version Control** | Git & GitHub |
| **Development** | VS Code |

---

## 3. System Architecture & Machine Learning Pipelines

```
+---------------------------------------------------------------------------------------+
|                                    SmartCare Platform                                 |
+---------------------------------------------------------------------------------------+
|  Frontend (Bootstrap 5, Responsive Medical UI, Chart.js, Live Queue Tracker)         |
+---------------------------------------------------------------------------------------+
|  Django Web Layer (Auth & Role-Based Views: Patient, Doctor, Administrator)           |
+---------------------------------------------------------------------------------------+
|  Business & Queue Engine (Token allocation, Dynamic queue wait-time calculator)       |
+---------------------------------------------------------------------------------------+
|  Machine Learning Layer (Scikit-Learn Pipelines & Trained Models)                     |
|   1. Consultation Duration Predictor (RandomForest / Preprocessing Pipeline)          |
|   2. Appointment Demand Forecaster (Time-Series & Specialty Volume Forecaster)        |
+---------------------------------------------------------------------------------------+
|  Database Layer (SQLite / Django ORM Models: Users, Profiles, Doctors, Schedules,     |
|                   Appointments, Feedback)                                             |
+---------------------------------------------------------------------------------------+
```

### ML Model 1: Consultation Duration Predictor
- **Target:** `consultation_duration_minutes` (Continuous float: 8 to 60 minutes)
- **Features:** `patient_age`, `patient_gender`, `department`, `visit_type`, `symptom_severity`, `has_chronic_condition`, `doctor_experience_years`
- **Model:** `Pipeline(ColumnTransformer(StandardScaler + OneHotEncoder) + RandomForestRegressor)`
- **Evaluation:** Mean Absolute Error (MAE) ~ 2.3 minutes, $R^2 \approx 0.89$
- **Artifact:** `ml/consultation_duration_model.joblib`

### ML Model 2: Appointment Demand Forecaster
- **Target:** `daily_appointment_demand` (Count of patient visits per day/specialty)
- **Features:** `day_of_week`, `day_of_month`, `month`, `is_weekend`, `department`
- **Model:** `Pipeline(ColumnTransformer(StandardScaler + OneHotEncoder) + GradientBoostingRegressor)`
- **Evaluation:** MAE ~ 1.7 appointments, $R^2 \approx 0.95$
- **Artifact:** `ml/demand_forecast_model.joblib`

---

## 4. Key Portals & Features

### Patient Portal
- **Registration & Profile Management:** Demographic and medical details (gender, DOB, blood group, contact).
- **Specialist Directory & Search:** Filter doctors by specialty, qualification, consultation fee, and rating.
- **Smart Booking with Real-time ML Duration Estimation:** Interactive AJAX calculates expected consultation duration live as symptoms and visit types are selected.
- **Live Queue Tracker:** Dedicated tracker displaying:
  - Patient's Token Number
  - Token currently in consultation
  - Number of patients ahead
  - Real-time estimated waiting time (dynamically updated)
  - Consultation room number
- **Rescheduling & Cancellation:** Move appointment to another date or cancel with reason.
- **Feedback & Rating:** Star ratings (1-5) and reviews for completed consultations.

### Doctor Portal
- **Doctor Dashboard:** Daily schedule overview, completed visits, waiting patients, and workload forecast.
- **Live Queue Console:**
  - "Call Patient to Room"
  - "Start Consultation" (begins live timer)
  - "Finish Consultation & Save Rx" (records actual duration and clinical notes)
  - "Mark No-Show"
- **Schedule Management:** Toggle daily clinic availability and working hours.

### Administrator Portal
- **Executive Analytics:** High-level KPIs, total revenue/consultation load, status breakdown doughnut chart, department workload bar chart.
- **ML Demand Forecasting Dashboard:** 7-day and 14-day forward projections with automated staffing recommendations (e.g. alert when high volume requires multiple doctors on duty).

---

## 5. Quick Start & Execution Guide

### Step 1: Activate Virtual Environment
Windows (PowerShell):
```powershell
venv\Scripts\activate
```

macOS / Linux:
```bash
source venv/bin/activate
```

### Step 2: (Optional) Retrain Machine Learning Models
Pre-trained models are already included, but can be retrained at any time:
```bash
python ml/train_duration_model.py
python ml/train_demand_model.py
```

### Step 3: Run Migrations & Seed Sample Data
```bash
python manage.py makemigrations
python manage.py migrate
python manage.py seed_smartcare
```

### Step 4: Run Automated Tests
```bash
python manage.py test smartcare
```

### Step 5: Start the Development Server
```bash
python manage.py runserver
```
Open **[http://127.0.0.1:8000/](http://127.0.0.1:8000/)** in your web browser.

---

## 6. Pre-Configured Accounts & Registration

Users can register new accounts with any role (**Patient**, **Doctor / Specialist**, or **Administrator**) directly on the [Registration Page](http://127.0.0.1:8000/register/).

### Email OTP Configuration

Registration verification and password reset codes are delivered through Gmail
SMTP. Use a Google **App Password**, not your normal Gmail password:

1. Enable 2-Step Verification on the Gmail account.
2. Create an App Password in the Google account security settings.
3. Copy `.env.example` to `.env`, then replace `EMAIL_HOST_USER`,
   `EMAIL_HOST_PASSWORD`, and `DEFAULT_FROM_EMAIL` with your own values:

```powershell
Copy-Item .env.example .env
```

The application reads `.env` from the project root; `.env.example` is only a
template and is not loaded automatically. Restart the development server after
creating or changing `.env`. OTP emails will be sent from that Gmail account.
Never commit `.env` or the app password to the repository.

For testing existing clinical queues and historical charts, pre-seeded accounts are also available:

| Role | Username | Password | Notes |
|---|---|---|---|
| **Patient** | `patient1` | `patient123` | Joyashis Das (Has active Token #3 in Dr. Rahim's live queue today!) |
| **Doctor** | `dr.rahim` | `doctor123` | Dr. Abdur Rahim (Cardiologist with active live queue and console) |
| **Administrator** | `admin` | `admin123` | System Administrator (Full access to ML Demand Forecaster and Django Admin) |

---

## 7. Modular Multi-App Architecture

The project is structured into **5 dedicated, decoupled Django applications** following best enterprise practices for **NEUB Project Work II**:

```
smartcare/
├── config/                  # Django project configuration (settings.py, urls.py)
├── ml/                      # Pre-trained ML models & dataset generation scripts
│   ├── train_duration_model.py
│   ├── train_demand_model.py
│   ├── consultation_duration_model.joblib
│   ├── demand_forecast_model.joblib
│   ├── consultation_dataset.csv
│   └── appointment_demand_dataset.csv
├── core/                    # Core landing page, navigation, shared base layout
│   ├── views.py             # Home landing page with live stats
│   ├── urls.py              # Root routing
│   ├── templatetags/        # Custom template filters
│   └── templates/core/      # base.html, home.html
├── accounts/                # User authentication, role profiles, and registration
│   ├── models.py            # UserProfile (Patient / Doctor / Admin roles)
│   ├── forms.py             # UserRegistrationForm (dynamic role dropdown selector)
│   ├── views.py             # Login, Register, Logout, Role Dispatcher
│   ├── urls.py
│   └── templates/accounts/  # login.html, register.html
├── doctors/                 # Doctor directories, departments, and consultation console
│   ├── models.py            # Department, DoctorProfile, DoctorSchedule
│   ├── forms.py             # DoctorConsultationForm
│   ├── views.py             # Directory, Profile, Queue Console, Shift Manager
│   ├── urls.py
│   └── templates/doctors/   # doctor_list, doctor_detail, dashboard, queue_console, manage_schedule
├── appointments/            # Booking, queue sequencing, dynamic wait-time calculator
│   ├── models.py            # Appointment, PatientFeedback
│   ├── queue_service.py     # Dynamic ML queue calculation & Token sequencing
│   ├── forms.py             # Booking, Reschedule, Cancel, Feedback forms
│   ├── views.py             # Patient dashboard, booking, live queue tracker
│   ├── urls.py
│   └── templates/appointments/ # patient_dashboard, book, queue_tracker, cancel, reschedule, feedback
├── ml_engine/               # ML inference services, admin analytics & forecasting
│   ├── ml_service.py        # Safe model loading & prediction pipelines
│   ├── views.py             # Admin KPIs, 7/14-day demand forecast dashboard
│   ├── urls.py
│   ├── management/commands/
│   │   └── seed_smartcare.py# Pre-seeder with doctors, patients, and today's live queue
│   └── templates/ml_engine/ # admin_dashboard.html, demand_forecast.html
└── README.md
```
=======
# smartcare
>>>>>>> 4997f2e17535b1b9a0032a6510193d1e012560f9
