import os
import tempfile
from datetime import datetime, timedelta
from django.test import TestCase, override_settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone
from ..models import Client, Case, Document
from ..forms import ClientRegistrationForm, ClientProfileForm, CaseForm, DocumentForm

User = get_user_model()

class ClientRegistrationFormTest(TestCase):
    def setUp(self):
        self.valid_data = {
            'username': 'testuser',
            'email': 'test@example.com',
            'name': 'Test User',
            'password1': 'ComplexPass123!',
            'password2': 'ComplexPass123!',
            'phone': '+1234567890',
            'address': '123 Test St',
            'date_of_birth': '1990-01-01',
        }
    
    def test_valid_registration(self):
        form = ClientRegistrationForm(data=self.valid_data)
        self.assertTrue(form.is_valid())
        
        user = form.save()
        self.assertEqual(user.email, 'test@example.com')
        self.assertEqual(user.client.name, 'Test User')
        self.assertTrue(user.groups.filter(name='Clients').exists())
    
    def test_duplicate_email(self):
        # Create a user with the same email first
        User.objects.create_user(
            username='existing',
            email='test@example.com',
            password='testpass123'
        )
        
        form = ClientRegistrationForm(data=self.valid_data)
        self.assertFalse(form.is_valid())
        self.assertIn('email', form.errors)
    
    def test_invalid_email(self):
        data = self.valid_data.copy()
        data['email'] = 'invalid-email'
        form = ClientRegistrationForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('email', form.errors)
    
    def test_underage_user(self):
        data = self.valid_data.copy()
        data['date_of_birth'] = (timezone.now().date() - timedelta(days=365*15)).isoformat()
        form = ClientRegistrationForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('date_of_birth', form.errors)

class ClientProfileFormTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.client_profile = Client.objects.create(
            user=self.user,
            name='Test User',
            email='test@example.com'
        )
        
        self.valid_data = {
            'name': 'Updated Name',
            'email': 'updated@example.com',
            'phone': '+1234567890',
            'address': '456 New St',
            'date_of_birth': '1990-01-01',
        }
    
    def test_valid_profile_update(self):
        form = ClientProfileForm(instance=self.client_profile, data=self.valid_data)
        self.assertTrue(form.is_valid())
        
        client = form.save()
        self.assertEqual(client.name, 'Updated Name')
        self.assertEqual(client.email, 'updated@example.com')
        self.assertEqual(client.user.email, 'updated@example.com')
    
    def test_duplicate_email(self):
        # Create another user with email we'll try to use
        User.objects.create_user(
            username='otheruser',
            email='taken@example.com',
            password='testpass123'
        )
        
        data = self.valid_data.copy()
        data['email'] = 'taken@example.com'
        form = ClientProfileForm(instance=self.client_profile, data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('email', form.errors)
    
    def test_name_validation(self):
        data = self.valid_data.copy()
        data['name'] = ''  # Empty name
        form = ClientProfileForm(instance=self.client_profile, data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('name', form.errors)

class CaseFormTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.client_profile = Client.objects.create(
            user=self.user,
            name='Test User',
            email='test@example.com'
        )
        
        self.valid_data = {
            'title': 'Test Case',
            'client': self.client_profile.id,
            'description': 'Test case description',
            'status': 'open',
        }
    
    def test_valid_case_creation(self):
        form = CaseForm(data=self.valid_data)
        self.assertTrue(form.is_valid())
        
        case = form.save(commit=False)
        case.save()
        self.assertEqual(case.title, 'Test Case')
        self.assertEqual(case.client, self.client_profile)

@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class DocumentFormTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.client_profile = Client.objects.create(
            user=self.user,
            name='Test User',
            email='test@example.com'
        )
        self.case = Case.objects.create(
            title='Test Case',
            client=self.client_profile,
            status='open',
            description='Test case'
        )
        
        self.test_file = SimpleUploadedFile(
            'test_document.txt',
            b'This is a test document',
            content_type='text/plain'
        )
        
        self.valid_data = {
            'title': 'Test Document',
            'file': self.test_file,
        }
    
    def test_valid_document_upload(self):
        form = DocumentForm(data={'title': 'Test Document'}, files={'file': self.test_file})
        self.assertTrue(form.is_valid())
        
        document = form.save(commit=False)
        document.case = self.case
        document.uploaded_by = self.user
        document.save()
        
        self.assertEqual(document.title, 'Test Document')
        self.assertTrue(document.file.name.endswith('test_document.txt'))
        
        # Clean up the test file
        if os.path.exists(document.file.path):
            os.remove(document.file.path)
    
    def test_missing_file(self):
        data = {'title': 'No File'}
        form = DocumentForm(data=data, files={})
        self.assertFalse(form.is_valid())
        self.assertIn('file', form.errors)
