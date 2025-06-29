from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    # Authentication URLs
    path('register/', views.register, name='register'),
    path('lawyer/register/', views.lawyer_register, name='lawyer_register'),
    path('login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('lawyer/login/', views.lawyer_login, name='lawyer_login'),
    path('profile/', views.ClientProfileView.as_view(), name='profile'),
    path('lawyer/profile/', views.LawyerProfileView.as_view(), name='lawyer_profile'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    
    # Application URLs
    path('', views.landing_page, name='landing_page'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('lawyer/dashboard/', views.lawyer_dashboard, name='lawyer_dashboard'),
    
    # Client and Case Management
    path('clients/add/', views.client_create, name='client_create'),
    path('cases/add/', views.case_create, name='case_create'),
    path('client/<int:pk>/', views.client_detail, name='client_detail'),
    path('client/<int:pk>/edit/', views.client_update, name='client_update'),
    path('case/<int:pk>/', views.case_detail, name='case_detail'),
    path('case/<int:pk>/edit/', views.case_update, name='case_update'),
    
    # Appointment Management
    path('book-appointment/', views.book_appointment, name='book_appointment'),
    path('appointments/', views.client_appointments, name='client_appointments'),
    path('manage/appointments/', views.appointment_list, name='appointment_list'),
    path('manage/appointments/<int:pk>/', views.appointment_detail, name='appointment_detail'),
    path('manage/appointments/<int:pk>/reschedule/', views.appointment_reschedule, name='appointment_reschedule'),
    
    # Document Management
    path('case/<int:case_pk>/upload-document/', views.client_document_upload, name='client_document_upload'),
    
    # Lawyer Management
    path('manage/lawyers/', views.lawyer_list, name='lawyer_list'),
    path('manage/lawyers/<int:pk>/', views.lawyer_detail, name='lawyer_detail'),
]
