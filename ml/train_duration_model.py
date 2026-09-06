import os
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.ensemble import RandomForestRegressor
from sklearn.pipeline import Pipeline
from sklearn.metrics import mean_absolute_error, r2_score
import joblib

def generate_consultation_data(num_samples=2500, random_state=42):
    np.random.seed(random_state)
    
    departments = ['Cardiology', 'Pediatrics', 'Dermatology', 'General Medicine', 'Orthopedics', 'Neurology', 'ENT', 'Gynecology']
    visit_types = ['first_visit', 'follow_up', 'routine_checkup', 'urgent']
    severities = ['mild', 'moderate', 'severe']
    genders = ['M', 'F', 'O']
    
    dept_base_minutes = {
        'Cardiology': 26.0,
        'Neurology': 28.0,
        'Orthopedics': 22.0,
        'Gynecology': 24.0,
        'General Medicine': 18.0,
        'Pediatrics': 20.0,
        'Dermatology': 15.0,
        'ENT': 16.0
    }
    
    data = []
    for _ in range(num_samples):
        dept = np.random.choice(departments, p=[0.18, 0.15, 0.12, 0.22, 0.13, 0.08, 0.06, 0.06])
        age = int(np.random.randint(2, 85))
        gender = np.random.choice(genders, p=[0.48, 0.48, 0.04])
        visit_type = np.random.choice(visit_types, p=[0.35, 0.35, 0.20, 0.10])
        severity = np.random.choice(severities, p=[0.55, 0.32, 0.13])
        chronic = int(np.random.choice([0, 1], p=[0.65, 0.35]))
        doc_exp = int(np.random.randint(1, 30))
        
        # Calculate duration with realistic medical factors
        duration = dept_base_minutes[dept]
        
        # Visit type influence
        if visit_type == 'first_visit':
            duration += 7.5  # Need full medical history taking
        elif visit_type == 'routine_checkup':
            duration -= 3.0
        elif visit_type == 'urgent':
            duration += 9.0  # Immediate stabilization / acute assessment
        elif visit_type == 'follow_up':
            duration -= 4.0  # Review previous tests and adjust meds
            
        # Severity influence
        if severity == 'moderate':
            duration += 4.5
        elif severity == 'severe':
            duration += 11.0
            
        # Chronic condition
        if chronic == 1:
            duration += 4.0
            
        # Age factors (elderly > 65 and young children < 5 require more handling time)
        if age > 65:
            duration += 3.5
        elif age < 5:
            duration += 3.0
            
        # Doctor experience (experienced doctors are slightly faster and more decisive)
        duration -= (doc_exp * 0.15)
        
        # Random natural clinical variability (Gaussian noise)
        duration += np.random.normal(0, 2.5)
        
        # Clip to realistic consultation duration limits [8, 60] minutes
        duration = float(np.clip(duration, 8.0, 60.0))
        
        data.append({
            'patient_age': age,
            'patient_gender': gender,
            'department': dept,
            'visit_type': visit_type,
            'symptom_severity': severity,
            'has_chronic_condition': chronic,
            'doctor_experience_years': doc_exp,
            'consultation_duration_minutes': round(duration, 1)
        })
        
    return pd.DataFrame(data)

def train_and_save_duration_model(csv_path="ml/consultation_dataset.csv", model_path="ml/consultation_duration_model.joblib"):
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    df = generate_consultation_data(num_samples=3000)
    df.to_csv(csv_path, index=False)
    print(f"Saved synthetic dataset to {csv_path} with {len(df)} rows.")
    
    X = df.drop(columns=['consultation_duration_minutes'])
    y = df['consultation_duration_minutes']
    
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    numeric_features = ['patient_age', 'has_chronic_condition', 'doctor_experience_years']
    categorical_features = ['patient_gender', 'department', 'visit_type', 'symptom_severity']
    
    preprocessor = ColumnTransformer(
        transformers=[
            ('num', StandardScaler(), numeric_features),
            ('cat', OneHotEncoder(handle_unknown='ignore'), categorical_features)
        ]
    )
    
    pipeline = Pipeline(steps=[
        ('preprocessor', preprocessor),
        ('regressor', RandomForestRegressor(n_estimators=120, max_depth=12, random_state=42, n_jobs=-1))
    ])
    
    pipeline.fit(X_train, y_train)
    y_pred = pipeline.predict(X_test)
    
    mae = mean_absolute_error(y_test, y_pred)
    r2 = r2_score(y_test, y_pred)
    
    print(f"Duration Model Evaluation:")
    print(f"  Mean Absolute Error: {mae:.2f} minutes")
    print(f"  R2 Score: {r2:.4f}")
    
    joblib.dump(pipeline, model_path)
    print(f"Saved trained duration model pipeline to {model_path}")

if __name__ == "__main__":
    train_and_save_duration_model()

