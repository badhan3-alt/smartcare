from django.urls import path

from .views import (
    home,
    predict_insurance
)


urlpatterns = [

    path(
        "",
        home,
        name="insurance_home"
    ),

    path(
        "predict/",
        predict_insurance,
        name="predict"
    ),
]