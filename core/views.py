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

from .models import Client, Case, Document, Visitor
from .forms import ClientRegistrationForm, ClientProfileForm, CaseForm, DocumentForm, VisitorForm, AppointmentForm
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
    context = {
        'cases': cases,
        'clients': clients,
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
