import os
import datetime
import joblib
import pandas as pd
from django.conf import settings

_DURATION_MODEL = None
_DEMAND_MODEL = None

def get_duration_model():
    global _DURATION_MODEL
    if _DURATION_MODEL is None:
        model_path = os.path.join(settings.BASE_DIR, 'ml', 'consultation_duration_model.joblib')
        if os.path.exists(model_path):
            _DURATION_MODEL = joblib.load(model_path)
    return _DURATION_MODEL

def get_demand_model():
    global _DEMAND_MODEL
    if _DEMAND_MODEL is None:
        model_path = os.path.join(settings.BASE_DIR, 'ml', 'demand_forecast_model.joblib')
        if os.path.exists(model_path):
            _DEMAND_MODEL = joblib.load(model_path)
    return _DEMAND_MODEL

def predict_consultation_duration(
    patient_age: int,
    patient_gender: str,
    department: str,
    visit_type: str,
    symptom_severity: str,
    has_chronic_condition: bool,
    doctor_experience_years: int
) -> float:
    """
    Predicts expected consultation duration in minutes using trained RandomForestRegressor.
    Returns bounded float between 5.0 and 60.0 mins.
    """
    model = get_duration_model()
    if model is None:
        # Graceful fallback heuristic
        base = 15.0
        if visit_type == 'first_visit': base += 6.0
        if symptom_severity == 'severe': base += 8.0
        elif symptom_severity == 'moderate': base += 4.0
        if has_chronic_condition: base += 3.0
        return round(base, 1)

    df_input = pd.DataFrame([{
        'patient_age': int(patient_age),
        'patient_gender': str(patient_gender),
        'department': str(department),
        'visit_type': str(visit_type),
        'symptom_severity': str(symptom_severity),
        'has_chronic_condition': int(has_chronic_condition),
        'doctor_experience_years': int(doctor_experience_years)
    }])

    try:
        pred = float(model.predict(df_input)[0])
        return round(max(5.0, min(60.0, pred)), 1)
    except Exception as e:
        return 20.0

def forecast_appointment_demand(start_date=None, days_ahead=7):
    """
    Predicts expected appointment demand per department over the next `days_ahead` days.
    """
    model = get_demand_model()
    if start_date is None:
        start_date = datetime.date.today()

    departments = [
        'Cardiology', 'Pediatrics', 'Dermatology', 'Orthopedics',
        'Neurology', 'General Medicine', 'ENT', 'Gynecology'
    ]

    forecasts = []
    daily_summaries = {}

    for i in range(days_ahead):
        curr_date = start_date + datetime.timedelta(days=i)
        day_of_week = curr_date.weekday()
        month = curr_date.month
        is_weekend = 1 if day_of_week in [4, 5] else 0 # Fri/Sat in BD context

        date_str = curr_date.strftime('%Y-%m-%d')
        daily_summaries[date_str] = {
            'date': curr_date,
            'day_name': curr_date.strftime('%A'),
            'total_projected_visits': 0,
            'dept_breakdown': {}
        }

        for dept in departments:
            if model:
                row = pd.DataFrame([{
                    'department': dept,
                    'day_of_week': day_of_week,
                    'month': month,
                    'is_weekend': is_weekend
                }])
                try:
                    predicted_count = max(0, int(round(float(model.predict(row)[0]))))
                except Exception:
                    predicted_count = 12 if is_weekend else 22
            else:
                predicted_count = 14 if is_weekend else 24

            daily_summaries[date_str]['total_projected_visits'] += predicted_count
            daily_summaries[date_str]['dept_breakdown'][dept] = predicted_count
            
            forecasts.append({
                'date': curr_date,
                'department': dept,
                'predicted_visits': predicted_count
            })

    return {
        'forecasts': forecasts,
        'daily_summaries': daily_summaries,
        'total_projected': sum(d['total_projected_visits'] for d in daily_summaries.values())
    }

