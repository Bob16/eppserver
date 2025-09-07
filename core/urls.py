from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='home'),  # This makes / show the dashboard
    path('dashboard/', views.dashboard, name='dashboard'),
]
