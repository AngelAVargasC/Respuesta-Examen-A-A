from django.urls import path
from . import views

urlpatterns = [
 
    path('', views.dashboard, name='dashboard'),
    path('dashboard-mas/', views.dashboard_mas, name='dashboard-mas'),
]