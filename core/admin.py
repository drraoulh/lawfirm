from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html
from django.urls import reverse
from django.db.models import Q
from .models import User, Client, Case, Document, Visitor, Lawyer, Appointment
from django.contrib.auth.models import Group
from django.contrib.auth import get_user_model

User = get_user_model()

# Customize the admin site
admin.site.site_header = 'Law Firm Administration'
admin.site.site_title = 'Law Firm Admin'
admin.site.index_title = 'Welcome to Law Firm Admin'

# Unregister the default Group model
# admin.site.unregister(Group)

@admin.register(User)
class CustomUserAdmin(BaseUserAdmin):
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_active', 'is_staff', 'date_joined')
    list_filter = ('is_active', 'is_staff', 'is_superuser', 'groups', 'date_joined')
    search_fields = ('username', 'email', 'first_name', 'last_name')
    ordering = ('-date_joined',)
    
    fieldsets = BaseUserAdmin.fieldsets
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('client_profile', 'lawyer_profile')

@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'phone', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('name', 'email', 'phone')
    ordering = ('name',)
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('user', 'name', 'email', 'phone')
        }),
        ('Additional Information', {
            'fields': ('address', 'date_of_birth'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

@admin.register(Lawyer)
class LawyerAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'specialization', 'years_experience', 'is_available', 'created_at')
    list_filter = ('specialization', 'is_available', 'created_at')
    search_fields = ('name', 'email', 'bar_number')
    ordering = ('name',)
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('user', 'name', 'email', 'phone')
        }),
        ('Professional Information', {
            'fields': ('specialization', 'bar_number', 'years_experience', 'bio', 'is_available')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

@admin.register(Case)
class CaseAdmin(admin.ModelAdmin):
    list_display = ('title', 'client', 'lawyer', 'status', 'opened_on', 'due_date')
    list_filter = ('status', 'opened_on', 'due_date')
    search_fields = ('title', 'description', 'client__name', 'lawyer__username')
    ordering = ('-opened_on',)
    readonly_fields = ('opened_on',)
    
    fieldsets = (
        ('Case Information', {
            'fields': ('title', 'description', 'client', 'lawyer')
        }),
        ('Status', {
            'fields': ('status', 'opened_on', 'due_date')
        }),
    )

@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ('title', 'case', 'uploaded_at')
    list_filter = ('uploaded_at',)
    search_fields = ('title', 'case__title')
    ordering = ('-uploaded_at',)
    readonly_fields = ('uploaded_at',)

@admin.register(Visitor)
class VisitorAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'submitted_at')
    list_filter = ('submitted_at',)
    search_fields = ('name', 'email', 'message')
    ordering = ('-submitted_at',)
    readonly_fields = ('submitted_at',)

@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ('client', 'lawyer', 'date', 'time', 'status', 'created_at')
    list_filter = ('status', 'date', 'created_at')
    search_fields = ('client__name', 'lawyer__username', 'message')
    ordering = ('-date', '-time')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('Appointment Details', {
            'fields': ('client', 'lawyer', 'date', 'time', 'message')
        }),
        ('Status Management', {
            'fields': ('status', 'lawyer_notes', 'rejection_reason', 'reschedule_reason')
        }),
        ('Rescheduling Information', {
            'fields': ('original_date', 'original_time'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('client', 'lawyer')

class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True

class MultipleFileField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single_file_clean = super().clean
        if isinstance(data, (list, tuple)):
            return [single_file_clean(d, initial) for d in data]
        return [single_file_clean(data, initial)]

class DocumentForm(forms.ModelForm):
    files = MultipleFileField(
        required=False,
        help_text='Upload multiple files at once.'
    )
    
    class Meta:
        model = Document
        fields = '__all__'
    
    def save(self, commit=True):
        # Handle single file upload via the regular file field
        return super().save(commit=commit)

    def get_urls(self):
        from django.urls import path
        urls = super().get_urls()
        custom_urls = [
            path('upload/', self.admin_site.admin_view(self.upload_document), name='document_upload'),
        ]
        return custom_urls + urls
    
    def upload_document(self, request):
        """Handle AJAX file uploads"""
        from django.http import JsonResponse
        if request.method == 'POST' and request.FILES:
            try:
                file = request.FILES['file']
                document = Document(
                    title=file.name,
                    file=file,
                    uploaded_by=request.user
                )
                document.save()
                return JsonResponse({
                    'success': True,
                    'id': document.id,
                    'name': document.file.name,
                    'url': document.file.url,
                    'size': document.file.size
                })
            except Exception as e:
                return JsonResponse({'success': False, 'error': str(e)})
        return JsonResponse({'success': False, 'error': 'No file provided'})

    def get_readonly_fields(self, request, obj=None):
        # Make user field read-only if not a superuser
        if not request.user.is_superuser:
            return self.readonly_fields + ('user',)
        return self.readonly_fields

    def user_link(self, obj):
        if obj.user:
            url = reverse('admin:core_user_change', args=[obj.user.id])
            return format_html('<a href="{0}">{1}</a>', url, obj.user.username)
        return 'No user account'
    user_link.short_description = 'User Account'

    def case_count(self, obj):
        count = obj.case_set.count()
        url = reverse('admin:core_case_changelist') + f'?client__id__exact={obj.id}'
        return format_html('<a href="{0}">{1}</a>', url, count)
    case_count.short_description = 'Cases'

    def case_display(self, obj):
        if obj.case:
            return obj.case.title
        return 'No case'
    case_display.short_description = 'Case'
    case_display.admin_order_field = 'case__title'
    
    def file_type_display(self, obj):
        if obj.file:
            return obj.file.name.split('.')[-1].upper()
        return 'N/A'
    file_type_display.short_description = 'File Type'
    
    def file_size_display(self, obj):
        if obj.file:
            size = obj.file.size
            if size < 1024:
                return f"{size} B"
            elif size < 1024 * 1024:
                return f"{size / 1024:.1f} KB"
            else:
                return f"{size / (1024 * 1024):.1f} MB"
        return 'N/A'
    file_size_display.short_description = 'Size'
    
    def preview(self, obj):
        if obj.file:
            if obj.file_type.lower() in ['jpg', 'jpeg', 'png', 'gif']:
                return format_html(
                    '<div style="max-width: 200px; max-height: 200px; overflow: hidden;">'
                    '<img src="{}" style="max-width: 100%; height: auto;" />'
                    '</div>',
                    obj.file.url
                )
            elif obj.file_type.lower() == 'pdf':
                return format_html(
                    '<iframe src="{}" width="100%" height="300" style="border: 1px solid #ddd;"></iframe>',
                    obj.file.url
                )
        return 'No preview available'
    preview.short_description = 'Preview'
    
    def file_actions(self, obj):
        if obj.file:
            return format_html(
                '<div class="actions">'
                '<a href="{}" class="button" target="_blank">View</a> '
                '<a href="{}" class="button" download>Download</a>'
                '</div>',
                obj.file.url,
                obj.file.url
            )
        return 'No file'
    file_actions.short_description = 'Actions'
    file_actions.allow_tags = True
    
    def save_model(self, request, obj, form, change):
        # Handle multiple file uploads
        files = request.FILES.getlist('files')
        if files:
            for file in files:
                Document.objects.create(
                    title=file.name,
                    file=file,
                    case=obj.case,
                    uploaded_by=request.user
                )
        super().save_model(request, obj, form, change)
    
    def download_selected_documents(self, request, queryset):
        """
        Download selected documents as a zip file
        """
        import zipfile
        import os
        from django.http import HttpResponse
        import tempfile
        
        # Create a temporary file to store the zip
        temp_file = tempfile.NamedTemporaryFile(delete=False)
        
        with zipfile.ZipFile(temp_file.name, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for document in queryset:
                if document.file and os.path.exists(document.file.path):
                    # Add file to zip with a subfolder structure
                    arcname = f"{document.case.title}/{document.file.name.split('/')[-1]}"
                    zipf.write(document.file.path, arcname)
        
        # Prepare the response
        response = HttpResponse(open(temp_file.name, 'rb'), content_type='application/zip')
        response['Content-Disposition'] = 'attachment; filename="documents.zip"'
        response['Content-Length'] = os.path.getsize(temp_file.name)
        
        # Clean up
        os.unlink(temp_file.name)
        
        return response
    download_selected_documents.short_description = 'Download selected documents (ZIP)'
    
    class Media:
        css = {
            'all': ('admin/css/document_admin.css',)
        }
        js = ('admin/js/documents.js',)
