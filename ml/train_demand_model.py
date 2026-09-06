import os
import datetime
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.pipeline import Pipeline
from sklearn.metrics import mean_absolute_error, r2_score
import joblib

def generate_demand_data(start_date="2025-01-01", days=365, random_state=42):
    np.random.seed(random_state)
    departments = ['Cardiology', 'Pediatrics', 'Dermatology', 'General Medicine', 'Orthopedics', 'Neurology', 'ENT', 'Gynecology']
    
    dept_base_demand = {
        'General Medicine': 32,
        'Cardiology': 24,
        'Pediatrics': 26,
        'Orthopedics': 20,
        'Dermatology': 18,
        'Gynecology': 16,
        'Neurology': 14,
        'ENT': 12
    }
    
    base = datetime.datetime.strptime(start_date, "%Y-%m-%d")
    data = []
    
    for d in range(days):
        curr_date = base + datetime.timedelta(days=d)
        dow = curr_date.weekday() # 0 = Monday, 6 = Sunday
        dom = curr_date.day
        month = curr_date.month
        is_weekend = 1 if dow in [5, 6] else 0 # Saturday/Sunday
        
        # Day of week multiplier (Monday=peak, weekend=low)
        dow_multipliers = [1.25, 1.15, 1.05, 1.0, 0.95, 0.55, 0.40]
        dow_mult = dow_multipliers[dow]
        
        for dept in departments:
            base_count = dept_base_demand[dept]
            
            # Seasonal adjustments
            seasonal_mult = 1.0
            if dept in ['General Medicine', 'Pediatrics', 'ENT'] and month in [11, 12, 1, 2]:
                seasonal_mult = 1.25  # Winter respiratory / flu surge
            elif dept == 'Dermatology' and month in [5, 6, 7, 8]:
                seasonal_mult = 1.20  # Summer skin condition surge
            elif dept == 'Cardiology' and month in [12, 1]:
                seasonal_mult = 1.15  # Winter cardiovascular load
                
            expected = base_count * dow_mult * seasonal_mult
            noise = np.random.normal(0, 2.0)
            final_count = max(2, int(round(expected + noise)))
            
            data.append({
                'date': curr_date.strftime("%Y-%m-%d"),
                'day_of_week': dow,
                'day_of_month': dom,
                'month': month,
                'is_weekend': is_weekend,
                'department': dept,
                'daily_appointment_demand': final_count
            })
            
    return pd.DataFrame(data)

def train_and_save_demand_model(csv_path="ml/appointment_demand_dataset.csv", model_path="ml/demand_forecast_model.joblib"):
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    df = generate_demand_data(days=400)
    df.to_csv(csv_path, index=False)
    print(f"Saved demand dataset to {csv_path} with {len(df)} rows.")
    
    X = df[['day_of_week', 'day_of_month', 'month', 'is_weekend', 'department']]
    y = df['daily_appointment_demand']
    
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    preprocessor = ColumnTransformer(
        transformers=[
            ('num', StandardScaler(), ['day_of_week', 'day_of_month', 'month', 'is_weekend']),
            ('cat', OneHotEncoder(handle_unknown='ignore'), ['department'])
        ]
    )
    
    pipeline = Pipeline(steps=[
        ('preprocessor', preprocessor),
        ('regressor', GradientBoostingRegressor(n_estimators=150, max_depth=5, learning_rate=0.08, random_state=42))
    ])
    
    pipeline.fit(X_train, y_train)
    y_pred = pipeline.predict(X_test)
    
    mae = mean_absolute_error(y_test, y_pred)
    r2 = r2_score(y_test, y_pred)
    
    print(f"Demand Model Evaluation:")
    print(f"  Mean Absolute Error: {mae:.2f} appointments")
    print(f"  R2 Score: {r2:.4f}")
    
    joblib.dump(pipeline, model_path)
    print(f"Saved trained demand forecast model to {model_path}")

if __name__ == "__main__":
    train_and_save_demand_model()

