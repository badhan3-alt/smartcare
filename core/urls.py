from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('', views.home_view, name='home'),
    path('search-suggestions/', views.search_suggestions_view, name='search_suggestions'),
]
