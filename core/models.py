from django.contrib.auth.models import AbstractUser
from django.db import models
from django.core.exceptions import ValidationError

class User(AbstractUser):
    """Custom user for future role tweaks (leave empty for now)."""

    @property
    def client(self):
        """Return related Client instance if present for backward compatibility."""
        return getattr(self, 'client_profile', None)


class Client(models.Model):
    user = models.OneToOneField(
        User, 
        on_delete=models.CASCADE, 
        related_name='client_profile',
        verbose_name='User Account',
        null=True,  # Make nullable for existing data
        blank=True  # Allow blank in forms
    )
    name = models.CharField(
        max_length=100,
        help_text="Client's full name"
    )
    email = models.EmailField(
        unique=True,
        help_text="Primary email address (must be unique)"
    )
    phone = models.CharField(
        max_length=20, 
        blank=True, 
        null=True,
        help_text="Contact phone number"
    )
    address = models.TextField(
        blank=True, 
        null=True,
        help_text="Full mailing address"
    )
    date_of_birth = models.DateField(
        blank=True, 
        null=True,
        help_text="Date of birth (YYYY-MM-DD)",
        verbose_name="Date of Birth"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this client was created",
        null=True,  # Make nullable for existing data
        blank=True  # Allow blank in forms
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="When this client was last updated",
        null=True,  # Make nullable for existing data
        blank=True  # Allow blank in forms
    )

    class Meta:
        ordering = ['name']
        verbose_name = 'Client'
        verbose_name_plural = 'Clients'
        indexes = [
            models.Index(fields=['email'], name='client_email_idx'),
            models.Index(fields=['name'], name='client_name_idx'),
        ]

    def __str__(self):
        return f"{self.name} ({self.email})"
    
    def clean(self):
        """
        Ensure data integrity and proper formatting.
        """
        # Clean and validate email
        if not self.email:
            raise ValidationError({'email': 'Email is required.'})
            
        self.email = self.email.lower().strip()
        
        # Validate email format
        from django.core.validators import validate_email
        try:
            validate_email(self.email)
        except ValidationError:
            raise ValidationError({'email': 'Enter a valid email address.'})
        
        # Check for duplicate email (excluding self)
        query = Client.objects.filter(email=self.email)
        if self.pk:
            query = query.exclude(pk=self.pk)
            
        if query.exists():
            raise ValidationError({'email': 'A client with this email already exists.'})
        
        # Validate name
        if not self.name or not self.name.strip():
            raise ValidationError({'name': 'Name is required.'})
            
        # Clean name
        self.name = ' '.join(part.capitalize() for part in self.name.strip().split())
        
        # Sync with User model if user exists
        if hasattr(self, 'user') and self.user:
            if self.email != self.user.email:
                # Check if new email is already used by another user
                if User.objects.filter(email=self.email).exclude(pk=self.user.pk).exists():
                    raise ValidationError({'email': 'This email is already in use by another account.'})
                self.user.email = self.email
                
            # Update user's first and last name if they exist
            if not self.user.first_name and not self.user.last_name:
                name_parts = self.name.split(' ', 1)
                self.user.first_name = name_parts[0]
                if len(name_parts) > 1:
                    self.user.last_name = name_parts[1]
    
    def save(self, *args, **kwargs):
        """
        Save the client and ensure the associated User is kept in sync.
        Uses transaction to ensure data consistency.
        """
        from django.db import transaction
        
        # Run model validation
        self.full_clean()
        
        is_new = self._state.adding
        
        try:
            with transaction.atomic():
                # If this is a new client, create the User first
                if is_new and not hasattr(self, 'user'):
                    base_username = self.email.split('@')[0]
                    username = base_username
                    counter = 1
                    
                    # Ensure username is unique
                    while User.objects.filter(username=username).exists():
                        username = f"{base_username}_{counter}"
                        counter += 1
                    
                    # Create the user with the cleaned data
                    user = User.objects.create_user(
                        username=username,
                        email=self.email,
                        password=User.objects.make_random_password(),  # Temporary password, will be set by the form
                        is_active=True
                    )
                    
                    # Set names from the client's name
                    name_parts = self.name.split(' ', 1)
                    user.first_name = name_parts[0]
                    if len(name_parts) > 1:
                        user.last_name = name_parts[1]
                    user.save()
                    
                    self.user = user
                
                # Save the client
                super().save(*args, **kwargs)
                
                # Update the User model if needed
                if hasattr(self, 'user') and self.user:
                    needs_save = False
                    
                    # Update email if changed
                    if self.email != self.user.email:
                        self.user.email = self.email
                        needs_save = True
                    
                    # Update names if they're empty
                    if not self.user.first_name and not self.user.last_name:
                        name_parts = self.name.split(' ', 1)
                        self.user.first_name = name_parts[0]
                        if len(name_parts) > 1:
                            self.user.last_name = name_parts[1]
                        needs_save = True
                    
                    if needs_save:
                        self.user.save()
                        
        except Exception as e:
            # Log the error with stack trace
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error saving client: {str(e)}", exc_info=True)
            
            # Re-raise the exception with a more descriptive message
            raise ValidationError(
                f"An error occurred while saving the client: {str(e)}"
            ) from e
    
    def delete(self, *args, **kwargs):
        """
        Delete the client and associated User if no other related objects exist.
        """
        user = self.user
        super().delete(*args, **kwargs)
        
        # Delete the User if no other related objects exist
        if user and not hasattr(user, 'client_profile'):
            user.delete()


class Case(models.Model):
    STATUS = [
        ('open',    'Open'),
        ('pending', 'Pending'),
        ('closed',  'Closed'),
    ]
    title       = models.CharField(max_length=255)
    client      = models.ForeignKey(Client, on_delete=models.CASCADE)
    description = models.TextField(blank=True)
    lawyer      = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    status    = models.CharField(max_length=20, choices=STATUS, default='open')
    opened_on = models.DateField(auto_now_add=True)
    due_date  = models.DateField(null=True, blank=True)

    def __str__(self):
        return self.title


class Document(models.Model):
    title       = models.CharField(max_length=255, default='Untitled Document')
    case        = models.ForeignKey(Case, on_delete=models.CASCADE)
    file        = models.FileField(upload_to='docs/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class Visitor(models.Model):
    name = models.CharField(max_length=255)
    email = models.EmailField()
    message = models.TextField()
    submitted_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Inquiry from {self.name} on {self.submitted_at.strftime('%Y-%m-%d')}"
