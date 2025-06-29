from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login, logout, authenticate
from django.db import transaction
from django.db.models import Q
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import UpdateView
from django.urls import reverse_lazy
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.contrib.auth.password_validation import validate_password

from .models import Client, Case, Document, Visitor, Lawyer, Appointment
from .forms import (
    ClientRegistrationForm, ClientProfileForm, CaseForm, DocumentForm, VisitorForm, 
    AppointmentForm, LawyerRegistrationForm, LawyerProfileForm, AppointmentResponseForm,
    AppointmentRescheduleForm, ClientDocumentForm
)
from .decorators import group_required

def landing_page(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        form = VisitorForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Your message has been sent successfully! We will get back to you shortly.')
            return redirect('landing_page')
    else:
        form = VisitorForm()
    return render(request, 'landing.html', {'form': form})

def register(request):
    if request.user.is_authenticated:
        messages.info(request, 'You are already logged in.')
        return redirect('dashboard')

    if request.method == 'POST':
        form = ClientRegistrationForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    user = form.save(commit=False)
                    user.is_active = False  # Require admin validation
                    user.save()
                    # Create the client profile
                    if not hasattr(user, 'client_profile'):
                        Client.objects.create(
                            user=user,
                            name=form.cleaned_data['name'],
                            email=form.cleaned_data['email']
                        )
                    from django.contrib.auth.models import Group
                    clients_group, created = Group.objects.get_or_create(name='Clients')
                    user.groups.add(clients_group)
                    messages.success(request, 'Your account has been created and is pending admin approval. You will be able to log in once an admin activates your account.')
                    return redirect('login')
            except ValidationError as e:
                for field, errors in e.message_dict.items():
                    for error in errors:
                        form.add_error(field, error)
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.exception("Error during registration")
                messages.error(request, 'An unexpected error occurred during registration. Please try again or contact support.')
        return render(request, 'registration/register.html', {'form': form})
    else:
        form = ClientRegistrationForm()

    return render(request, 'registration/register.html', {
        'form': form,
        'title': 'Client Registration'
    })

class ClientProfileView(LoginRequiredMixin, UpdateView):
    model = Client
    form_class = ClientProfileForm
    template_name = 'profile.html'
    success_url = reverse_lazy('dashboard')

    def get_object(self, queryset=None):
        """Return Client profile for the logged-in user, creating one if missing."""
        user = self.request.user
        try:
            return user.client_profile
        except Client.DoesNotExist:
            # Create a minimal client profile on first access
            name = (user.get_full_name() or user.username or user.email.split('@')[0]).strip()
            if not user.email:
                # Ensure an email value (use placeholder)
                user.email = f"{user.username}@example.com"
                user.save(update_fields=["email"])
            client = Client.objects.create(
                user=user,
                name=name,
                email=user.email,
            )
            return client

    def form_valid(self, form):
        messages.success(self.request, 'Profile updated successfully!')
        return super().form_valid(form)

def dashboard(request):
    query = request.GET.get('q')
    # If user is admin or lawyer, show all cases/clients
    if request.user.is_superuser or request.user.groups.filter(name__in=['Admin', 'Lawyer']).exists():
        cases = Case.objects.order_by('-opened_on')
        clients = Client.objects.order_by('name')
        if query:
            cases = cases.filter(
                Q(title__icontains=query) |
                Q(description__icontains=query) |
                Q(client__name__icontains=query)
            ).distinct()
            clients = clients.filter(
                Q(name__icontains=query) |
                Q(email__icontains=query)
            ).distinct()
    else:
        # If user is a client, only show their own cases and profile
        try:
            client = request.user.client_profile
            cases = Case.objects.filter(client=client).order_by('-opened_on')
            clients = Client.objects.filter(pk=client.pk)
            if query:
                cases = cases.filter(
                    Q(title__icontains=query) |
                    Q(description__icontains=query)
                ).distinct()
        except Client.DoesNotExist:
            cases = Case.objects.none()
            clients = Client.objects.none()
    
    # Add appointment statistics for lawyers
    appointment_stats = {}
    if request.user.groups.filter(name='Lawyer').exists():
        appointments = Appointment.objects.filter(lawyer=request.user)
        appointment_stats = {
            'total_appointments': appointments.count(),
            'pending_appointments': appointments.filter(status='pending').count(),
            'accepted_appointments': appointments.filter(status='accepted').count(),
            'rejected_appointments': appointments.filter(status='rejected').count(),
            'rescheduled_appointments': appointments.filter(status='rescheduled').count(),
        }
    
    context = {
        'cases': cases,
        'clients': clients,
        'appointment_stats': appointment_stats,
    }
    return render(request, 'dashboard.html', context)

@login_required
@group_required('Admin', 'Lawyer')
def client_create(request):
    if request.method == 'POST':
        form = ClientProfileForm(request.POST)
        if form.is_valid():
            try:
                client = form.save()
                messages.success(request, f'Client "{client.name}" has been created successfully.')
                return redirect('dashboard')
            except Exception as e:
                if 'email' in str(e):
                    messages.error(request, 'A client with this email already exists. Please use a different email address.')
                else:
                    messages.error(request, f'An error occurred: {str(e)}')
    else:
        form = ClientProfileForm()
    return render(request, 'form_template.html', {'form': form, 'title': 'Add New Client'})

@login_required
@group_required('Admin', 'Lawyer')
def case_create(request):
    if request.method == 'POST':
        form = CaseForm(request.POST)
        if form.is_valid():
            case = form.save()
            messages.success(request, f'Case "{case.title}" has been created successfully.')
            return redirect('dashboard')
    else:
        form = CaseForm()
    return render(request, 'form_template.html', {'form': form, 'title': 'Add New Case'})

@login_required
def case_detail(request, pk):
    case = get_object_or_404(Case, pk=pk)
    # Only allow access if admin/lawyer or the client owns the case
    if not (request.user.is_superuser or request.user.groups.filter(name__in=['Admin', 'Lawyer']).exists() or (hasattr(request.user, 'client_profile') and case.client == request.user.client_profile)):
        messages.error(request, 'You do not have permission to view this case.')
        return redirect('dashboard')
    documents = Document.objects.filter(case=case)
    form = DocumentForm() # Initialize form for GET request

    if request.method == 'POST':
        # Ensure only authorized users can upload
        if request.user.is_superuser or request.user.groups.filter(name__in=['Admin', 'Lawyer']).exists():
            form = DocumentForm(request.POST, request.FILES)
            if form.is_valid():
                document = form.save(commit=False)
                document.case = case
                document.save()
                messages.success(request, f'Document "{document.title}" has been uploaded successfully.')
                return redirect('case_detail', pk=case.pk)
    
    context = {
        'case': case,
        'documents': documents,
        'form': form,
    }
    return render(request, 'case_detail.html', context)

@login_required
def client_detail(request, pk):
    client = get_object_or_404(Client, pk=pk)
    # Only allow access if admin/lawyer or the client is viewing their own profile
    if not (request.user.is_superuser or request.user.groups.filter(name__in=['Admin', 'Lawyer']).exists() or (hasattr(request.user, 'client_profile') and request.user.client_profile.pk == client.pk)):
        messages.error(request, 'You do not have permission to view this client.')
        return redirect('dashboard')
    cases = Case.objects.filter(client=client)
    context = {
        'client': client,
        'cases': cases
    }
    return render(request, 'client_detail.html', context)

@login_required
@group_required('Admin', 'Lawyer')
def client_update(request, pk):
    client = get_object_or_404(Client, pk=pk)
    if request.method == 'POST':
        form = ClientProfileForm(request.POST, instance=client)
        if form.is_valid():
            form.save()
            messages.success(request, f'Client "{client.name}" has been updated successfully.')
            return redirect('client_detail', pk=client.pk)
    else:
        form = ClientProfileForm(instance=client)
    return render(request, 'form_template.html', {'form': form, 'title': 'Edit Client'})

@login_required
@group_required('Admin', 'Lawyer')
def case_update(request, pk):
    case = get_object_or_404(Case, pk=pk)
    if request.method == 'POST':
        form = CaseForm(request.POST, instance=case)
        if form.is_valid():
            form.save()
            messages.success(request, f'Case "{case.title}" has been updated successfully.')
            return redirect('case_detail', pk=case.pk)
    else:
        form = CaseForm(instance=case)
    return render(request, 'form_template.html', {'form': form, 'title': 'Edit Case'})

@login_required
def book_appointment(request):
    # Only allow clients to book appointments
    if not hasattr(request.user, 'client_profile'):
        messages.error(request, 'Only clients can book appointments.')
        return redirect('dashboard')
    if request.method == 'POST':
        form = AppointmentForm(request.POST)
        if form.is_valid():
            appointment = form.save(commit=False)
            appointment.client = request.user.client_profile
            appointment.save()
            messages.success(request, 'Your appointment has been booked!')
            return redirect('dashboard')
    else:
        form = AppointmentForm()
    return render(request, 'book_appointment.html', {'form': form})

def lawyer_register(request):
    if request.user.is_authenticated:
        messages.info(request, 'You are already logged in.')
        return redirect('dashboard')

    if request.method == 'POST':
        form = LawyerRegistrationForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    user = form.save(commit=False)
                    user.is_active = False  # Require admin validation
                    user.save()
                    # Create the lawyer profile
                    if not hasattr(user, 'lawyer_profile'):
                        Lawyer.objects.create(
                            user=user,
                            name=form.cleaned_data['name'],
                            email=form.cleaned_data['email'],
                            phone=form.cleaned_data['phone'],
                            specialization=form.cleaned_data['specialization'],
                            bar_number=form.cleaned_data['bar_number'],
                            years_experience=form.cleaned_data['years_experience'],
                            bio=form.cleaned_data['bio']
                        )
                    from django.contrib.auth.models import Group
                    lawyers_group, created = Group.objects.get_or_create(name='Lawyers')
                    user.groups.add(lawyers_group)
                    messages.success(request, 'Your lawyer account has been created and is pending admin approval. You will be able to log in once an admin activates your account.')
                    return redirect('login')
            except ValidationError as e:
                for field, errors in e.message_dict.items():
                    for error in errors:
                        form.add_error(field, error)
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.exception("Error during lawyer registration")
                messages.error(request, 'An unexpected error occurred during registration. Please try again or contact support.')
        return render(request, 'registration/lawyer_register.html', {'form': form})
    else:
        form = LawyerRegistrationForm()

    return render(request, 'registration/lawyer_register.html', {
        'form': form,
        'title': 'Lawyer Registration'
    })

class LawyerProfileView(LoginRequiredMixin, UpdateView):
    model = Lawyer
    form_class = LawyerProfileForm
    template_name = 'lawyer_profile.html'
    success_url = reverse_lazy('dashboard')

    def get_object(self, queryset=None):
        """Return Lawyer profile for the logged-in user, creating one if missing."""
        user = self.request.user
        try:
            return user.lawyer_profile
        except Lawyer.DoesNotExist:
            # Create a minimal lawyer profile on first access
            name = (user.get_full_name() or user.username or user.email.split('@')[0]).strip()
            if not user.email:
                # Ensure an email value (use placeholder)
                user.email = f"{user.username}@example.com"
                user.save(update_fields=["email"])
            lawyer = Lawyer.objects.create(
                user=user,
                name=name,
                email=user.email,
            )
            return lawyer

    def form_valid(self, form):
        messages.success(self.request, 'Profile updated successfully!')
        return super().form_valid(form)

@login_required
@group_required('Admin', 'Lawyer')
def appointment_list(request):
    """View for lawyers and admins to see all appointments."""
    if request.user.groups.filter(name='Lawyers').exists():
        # Lawyers see appointments assigned to them or unassigned ones
        appointments = Appointment.objects.filter(
            Q(lawyer=request.user) | Q(lawyer__isnull=True)
        ).order_by('-created_at')
    else:
        # Admins see all appointments
        appointments = Appointment.objects.all().order_by('-created_at')
    
    context = {
        'appointments': appointments,
        'is_lawyer': request.user.groups.filter(name='Lawyers').exists(),
    }
    return render(request, 'appointment_list.html', context)

@login_required
def client_appointments(request):
    """View for clients to see their own appointments."""
    if not hasattr(request.user, 'client_profile'):
        messages.error(request, 'Only clients can view appointments.')
        return redirect('dashboard')
    
    appointments = Appointment.objects.filter(
        client=request.user.client_profile
    ).order_by('-created_at')
    
    context = {
        'appointments': appointments,
    }
    return render(request, 'client_appointments.html', context)

@login_required
@group_required('Admin', 'Lawyer')
def appointment_detail(request, pk):
    """View for lawyers and admins to see appointment details and respond."""
    appointment = get_object_or_404(Appointment, pk=pk)
    
    # Check if user has permission to view this appointment
    if request.user.groups.filter(name='Lawyers').exists() and appointment.lawyer and appointment.lawyer != request.user:
        messages.error(request, 'You do not have permission to view this appointment.')
        return redirect('appointment_list')
    
    if request.method == 'POST':
        form = AppointmentResponseForm(request.POST, instance=appointment)
        if form.is_valid():
            appointment = form.save(commit=False)
            if request.user.groups.filter(name='Lawyers').exists():
                appointment.lawyer = request.user
            appointment.save()
            messages.success(request, f'Appointment {appointment.get_status_display().lower()}.')
            return redirect('appointment_list')
    else:
        form = AppointmentResponseForm(instance=appointment)
    
    context = {
        'appointment': appointment,
        'form': form,
        'is_lawyer': request.user.groups.filter(name='Lawyers').exists(),
    }
    return render(request, 'appointment_detail.html', context)

@login_required
@group_required('Admin', 'Lawyer')
def appointment_reschedule(request, pk):
    """View for lawyers and admins to reschedule appointments."""
    appointment = get_object_or_404(Appointment, pk=pk)
    
    # Check if user has permission to reschedule this appointment
    if request.user.groups.filter(name='Lawyers').exists() and appointment.lawyer and appointment.lawyer != request.user:
        messages.error(request, 'You do not have permission to reschedule this appointment.')
        return redirect('appointment_list')
    
    if request.method == 'POST':
        form = AppointmentRescheduleForm(request.POST, instance=appointment)
        if form.is_valid():
            appointment = form.save(commit=False)
            appointment.status = 'rescheduled'
            if request.user.groups.filter(name='Lawyers').exists():
                appointment.lawyer = request.user
            appointment.save()
            messages.success(request, 'Appointment has been rescheduled.')
            return redirect('appointment_list')
    else:
        form = AppointmentRescheduleForm(instance=appointment)
    
    context = {
        'appointment': appointment,
        'form': form,
    }
    return render(request, 'appointment_reschedule.html', context)

@login_required
def client_document_upload(request, case_pk):
    """View for clients to upload documents related to their cases."""
    case = get_object_or_404(Case, pk=case_pk)
    
    # Only allow clients to upload documents for their own cases
    if not hasattr(request.user, 'client_profile') or case.client != request.user.client_profile:
        messages.error(request, 'You do not have permission to upload documents for this case.')
        return redirect('dashboard')
    
    if request.method == 'POST':
        form = ClientDocumentForm(request.POST, request.FILES)
        if form.is_valid():
            document = form.save(commit=False)
            document.case = case
            document.save()
            messages.success(request, f'Document "{document.title}" has been uploaded successfully.')
            return redirect('case_detail', pk=case.pk)
    else:
        form = ClientDocumentForm()
    
    context = {
        'case': case,
        'form': form,
    }
    return render(request, 'client_document_upload.html', context)

@login_required
@group_required('Admin', 'Lawyer')
def lawyer_list(request):
    """View for admins to see all lawyers."""
    lawyers = Lawyer.objects.all().order_by('name')
    context = {
        'lawyers': lawyers,
    }
    return render(request, 'lawyer_list.html', context)

@login_required
@group_required('Admin', 'Lawyer')
def lawyer_detail(request, pk):
    """View for admins to see lawyer details."""
    lawyer = get_object_or_404(Lawyer, pk=pk)
    appointments = Appointment.objects.filter(lawyer=lawyer.user).order_by('-created_at')
    cases = Case.objects.filter(lawyer=lawyer.user).order_by('-opened_on')
    
    context = {
        'lawyer': lawyer,
        'appointments': appointments,
        'cases': cases,
    }
    return render(request, 'lawyer_detail.html', context)

def lawyer_login(request):
    """Dedicated login view for lawyers."""
    if request.user.is_authenticated:
        if request.user.groups.filter(name='Lawyers').exists():
            return redirect('lawyer_dashboard')
        else:
            messages.warning(request, 'This login is for lawyers only. Please use the regular login.')
            return redirect('dashboard')
    
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            if user.groups.filter(name='Lawyers').exists():
                login(request, user)
                messages.success(request, f'Welcome back, {user.get_full_name() or user.username}!')
                return redirect('lawyer_dashboard')
            else:
                messages.error(request, 'This login is for lawyers only. Please use the regular login.')
        else:
            messages.error(request, 'Invalid username or password.')
    
    return render(request, 'registration/lawyer_login.html')

def lawyer_dashboard(request):
    """Dedicated dashboard for lawyers."""
    if not request.user.is_authenticated:
        return redirect('lawyer_login')
    
    if not request.user.groups.filter(name='Lawyers').exists():
        messages.error(request, 'Access denied. This area is for lawyers only.')
        return redirect('dashboard')
    
    # Get lawyer-specific data
    lawyer = request.user.lawyer_profile
    appointments = Appointment.objects.filter(lawyer=request.user).order_by('-created_at')
    cases = Case.objects.filter(lawyer=request.user).order_by('-opened_on')
    clients = Client.objects.filter(case__lawyer=request.user).distinct().order_by('name')
    
    # Appointment statistics
    appointment_stats = {
        'total_appointments': appointments.count(),
        'pending_appointments': appointments.filter(status='pending').count(),
        'accepted_appointments': appointments.filter(status='accepted').count(),
        'rejected_appointments': appointments.filter(status='rejected').count(),
        'rescheduled_appointments': appointments.filter(status='rescheduled').count(),
        'completed_appointments': appointments.filter(status='completed').count(),
    }
    
    # Case statistics
    case_stats = {
        'total_cases': cases.count(),
        'open_cases': cases.filter(status='open').count(),
        'pending_cases': cases.filter(status='pending').count(),
        'closed_cases': cases.filter(status='closed').count(),
    }
    
    context = {
        'lawyer': lawyer,
        'appointments': appointments[:5],  # Recent 5 appointments
        'cases': cases[:5],  # Recent 5 cases
        'clients': clients[:5],  # Recent 5 clients
        'appointment_stats': appointment_stats,
        'case_stats': case_stats,
    }
    return render(request, 'lawyer_dashboard.html', context)
