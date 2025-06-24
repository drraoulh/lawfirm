from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    # Authentication URLs
    path('register/', views.register, name='register'),
    path('profile/', views.ClientProfileView.as_view(), name='profile'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    
    # Application URLs
    path('', views.landing_page, name='landing_page'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('clients/add/', views.client_create, name='client_create'),
    path('cases/add/', views.case_create, name='case_create'),
    path('client/<int:pk>/', views.client_detail, name='client_detail'),
    path('client/<int:pk>/edit/', views.client_update, name='client_update'),
    path('case/<int:pk>/', views.case_detail, name='case_detail'),
    path('case/<int:pk>/edit/', views.case_update, name='case_update'),
    path('book-appointment/', views.book_appointment, name='book_appointment'),
]
