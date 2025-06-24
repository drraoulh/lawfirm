import re
from django import forms
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth.password_validation import password_validators_help_text_html
from .models import Visitor, Client, Case, Document, Appointment

User = get_user_model()

class VisitorForm(forms.ModelForm):
    class Meta:
        model = Visitor
        fields = ['name', 'email', 'message']
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'Your Name'}),
            'email': forms.EmailInput(attrs={'placeholder': 'Your Email'}),
            'message': forms.Textarea(attrs={'placeholder': 'Your Message', 'rows': 4}),
        }

class ClientRegistrationForm(UserCreationForm):
    name = forms.CharField(
        max_length=255,
        required=True,
        help_text='Your full name',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'John Doe',
            'autofocus': 'autofocus'
        })
    )
    email = forms.EmailField(
        required=True,
        help_text='A valid email address',
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'your.email@example.com',
            'autocomplete': 'email'
        })
    )
    phone = forms.CharField(
        max_length=20,
        required=True,
        help_text='Your phone number',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': '+1 (555) 123-4567'
        })
    )
    username = forms.CharField(
        max_length=150,
        required=True,
        help_text='Required. 150 characters or fewer. Letters, digits and @/./+/-/_ only.',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'johndoe',
            'autocomplete': 'username',
        })
    )
    password1 = forms.CharField(
        label='Password',
        strip=False,
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'autocomplete': 'new-password',
            'placeholder': 'Create a password'
        })
    )
    password2 = forms.CharField(
        label='Password confirmation',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'autocomplete': 'new-password',
            'placeholder': 'Enter the same password again'
        }),
        strip=False,
        help_text='Enter the same password as before, for verification.',
    )

    class Meta:
        model = User
        fields = ('username', 'email', 'name', 'phone', 'password1', 'password2')

    def clean_username(self):
        username = self.cleaned_data.get('username').strip()
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError('This username is already taken.')
        return username

    def clean_email(self):
        email = self.cleaned_data.get('email', '').lower().strip()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('This email is already registered.')
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        name_parts = self.cleaned_data['name'].split(' ', 1)
        user.first_name = name_parts[0]
        if len(name_parts) > 1:
            user.last_name = name_parts[1]
        if commit:
            user.save()
            client = Client.objects.create(
                user=user,
                name=self.cleaned_data['name'],
                email=self.cleaned_data['email'],
                phone=self.cleaned_data['phone']
            )
            from django.contrib.auth.models import Group
            clients_group, created = Group.objects.get_or_create(name='Clients')
            user.groups.add(clients_group)
        return user

class ClientProfileForm(forms.ModelForm):
    """
    Form for updating client profile information.
    Updates both the Client and associated User model.
    """
    email = forms.EmailField(
        required=True,
        help_text='Your email address',
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'your.email@example.com',
            'autocomplete': 'email'
        }),
        error_messages={
            'required': 'Please enter your email address.',
            'invalid': 'Please enter a valid email address.'
        }
    )
    
    name = forms.CharField(
        max_length=255,
        required=True,
        help_text='Your full name',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'John Doe'
        }),
        error_messages={
            'required': 'Please enter your full name.',
            'max_length': 'Name is too long (max 255 characters).'
        }
    )
    
    phone = forms.CharField(
        max_length=20,
        required=False,
        help_text='Contact phone number (optional)',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': '+1 (555) 123-4567'
        }),
        error_messages={
            'max_length': 'Phone number is too long.'
        }
    )
    
    address = forms.CharField(
        required=False,
        help_text='Your mailing address (optional)',
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': '123 Main St, City, State, ZIP'
        })
    )
    
    date_of_birth = forms.DateField(
        required=False,
        help_text='Date of birth (YYYY-MM-DD)',
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'form-control',
            'max': str(timezone.now().date() - timezone.timedelta(days=365*18))  # At least 18 years old
        }),
        error_messages={
            'invalid': 'Please enter a valid date (YYYY-MM-DD).'
        }
    )

    class Meta:
        model = Client
        fields = ['name', 'email', 'phone', 'address', 'date_of_birth']
        error_messages = {
            'email': {
                'unique': 'This email is already in use by another account.'
            }
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set initial values from the user model
        if self.instance and hasattr(self.instance, 'user'):
            self.fields['email'].initial = self.instance.user.email
            self.fields['name'].initial = self.instance.name

    def clean_email(self):
        email = self.cleaned_data.get('email', '').lower().strip()
        if not email:
            raise forms.ValidationError('Please enter your email address.')
            
        # Check for valid email format
        try:
            validate_email(email)
        except ValidationError:
            raise forms.ValidationError('Please enter a valid email address.')
        
        # Check if email is already in use by another user
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.user.pk).exists():
            raise forms.ValidationError('This email is already in use by another account.')
            
        return email
    
    def clean_name(self):
        name = self.cleaned_data.get('name', '').strip()
        if not name:
            raise forms.ValidationError('Please enter your full name.')
            
        # Clean up name formatting
        return ' '.join(part.capitalize() for part in name.split() if part)
    
    def clean(self):
        cleaned_data = super().clean()
        
        # Validate date of birth if provided
        date_of_birth = cleaned_data.get('date_of_birth')
        if date_of_birth:
            today = timezone.now().date()
            age = today.year - date_of_birth.year - ((today.month, today.day) < (date_of_birth.month, date_of_birth.day))
            if age < 18:
                self.add_error('date_of_birth', 'You must be at least 18 years old.')
                
        return cleaned_data

    def save(self, commit=True):
        """
        Save the client profile and update the associated User model.
        """
        client = super().save(commit=False)
        
        # Update the associated user's email if it changed
        if client.user.email != self.cleaned_data['email']:
            client.user.email = self.cleaned_data['email']
            
            # Update username if it was based on the old email
            if client.user.username.lower() == client.user.email.lower():
                client.user.username = self.cleaned_data['email']
            
            if commit:
                client.user.save()
        
        # Update the client's name
        if hasattr(client, 'user'):
            name_parts = self.cleaned_data['name'].split(' ', 1)
            client.user.first_name = name_parts[0]
            client.user.last_name = name_parts[1] if len(name_parts) > 1 else ''
            if commit:
                client.user.save()
        
        if commit:
            client.save()
            
        return client

class CaseForm(forms.ModelForm):
    class Meta:
        model = Case
        fields = ['title', 'client', 'description', 'status']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }

class DocumentForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = ['title', 'file']

class AppointmentForm(forms.ModelForm):
    class Meta:
        model = Appointment
        fields = ['date', 'time', 'message']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'time': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'message': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Reason for appointment (optional)'}),
        }
