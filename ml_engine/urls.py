from django.urls import path
from . import views

app_name = 'ml_engine'

urlpatterns = [
    path('dashboard/', views.admin_dashboard_view, name='admin_dashboard'),
    path('demand-forecast/', views.admin_demand_forecast_view, name='admin_demand_forecast'),
    path('api/predict-duration/', views.api_predict_duration, name='api_predict_duration'),
]

