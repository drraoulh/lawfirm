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
from .forms import ClientRegistrationForm, ClientProfileForm, CaseForm, DocumentForm, VisitorForm
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
                    username = form.cleaned_data.get('username')
                    email = form.cleaned_data.get('email')
                    
                    # Check if username already exists
                    if User.objects.filter(username=username).exists():
                        form.add_error('username', 'This username is already taken. Please choose a different one.')
                        return render(request, 'registration/register.html', {'form': form})
                    
                    # Check if email already exists
                    if User.objects.filter(email=email).exists():
                        form.add_error('email', 'This email is already registered. Please use a different email or log in.')
                        return render(request, 'registration/register.html', {'form': form})
                    
                    # Create the user
                    user = User.objects.create_user(
                        username=username,
                        email=email,
                        password=form.cleaned_data['password1'],
                        first_name=form.cleaned_data['name'].split(' ')[0],
                        last_name=' '.join(form.cleaned_data['name'].split(' ')[1:]) if ' ' in form.cleaned_data['name'] else ''
                    )
                    
                    # Create the client profile
                    client = Client(
                        user=user,
                        name=form.cleaned_data['name'],
                        email=email.lower(),
                        phone=form.cleaned_data.get('phone', ''),
                        address=form.cleaned_data.get('address', ''),
                        date_of_birth=form.cleaned_data.get('date_of_birth')
                    )
                    client.full_clean()
                    client.save()
                    
                    # Log the user in
                    login(request, user)
                    messages.success(request, 'Registration successful! Welcome to your dashboard.')
                    return redirect('dashboard')
                    
            except ValidationError as e:
                # Handle model validation errors
                for field, errors in e.message_dict.items():
                    for error in errors:
                        form.add_error(field, error)
            except Exception as e:
                # Log the exception for debugging
                import logging
                logger = logging.getLogger(__name__)
                logger.exception("Error during registration")
                
                # User-friendly error message
                error_message = 'An error occurred during registration. '
                if 'duplicate' in str(e).lower():
                    if 'username' in str(e).lower():
                        error_message += 'This username is already taken.'
                    elif 'email' in str(e).lower():
                        error_message += 'This email is already registered.'
                    else:
                        error_message += 'The provided information conflicts with an existing account.'
                else:
                    error_message += 'Please check your information and try again.'
                
                messages.error(request, error_message)
                
            # If we get here, there was an error
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

@login_required
def dashboard(request):
    query = request.GET.get('q')
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

    context = {
        'cases': cases,
        'clients': clients,
    }
    return render(request, 'dashboard.html', context)

@login_required
@group_required('Admin', 'Lawyer')
def client_create(request):
    if request.method == 'POST':
        form = ClientForm(request.POST)
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
        form = ClientForm()
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
    case = Case.objects.get(pk=pk)
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
    client = Client.objects.get(pk=pk)
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
        form = ClientForm(request.POST, instance=client)
        if form.is_valid():
            form.save()
            messages.success(request, f'Client "{client.name}" has been updated successfully.')
            return redirect('client_detail', pk=client.pk)
    else:
        form = ClientForm(instance=client)
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
