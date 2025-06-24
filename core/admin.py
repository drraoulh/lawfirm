from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html
from django.urls import reverse
from django.db.models import Q
from .models import User, Client, Case, Document, Visitor
from django.contrib.auth.models import Group

# Customize the admin site
admin.site.site_header = 'Law Firm Administration'
admin.site.site_title = 'Law Firm Admin'
admin.site.index_title = 'Welcome to Law Firm Admin'

# Unregister the default Group model
# admin.site.unregister(Group)

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_staff', 'is_active')
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'groups')
    search_fields = ('username', 'first_name', 'last_name', 'email')
    ordering = ('username',)
    filter_horizontal = ('groups', 'user_permissions',)

@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'phone', 'case_count', 'created_at', 'user_link')
    search_fields = ('name', 'email', 'phone', 'user__username', 'user__email')
    list_filter = ('created_at',)
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)
    readonly_fields = ('created_at', 'user_link')
    filter_horizontal = ('cases',) if 'cases' in [f.name for f in Client._meta.get_fields()] else ()
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if not request.user.is_superuser:
            # For non-superusers, only show clients they're associated with
            qs = qs.filter(Q(user=request.user) | Q(case__lawyer=request.user)).distinct()
        return qs
        
    def get_readonly_fields(self, request, obj=None):
        # Make user field read-only if not a superuser
        if not request.user.is_superuser:
            return self.readonly_fields + ('user',)
        return self.readonly_fields
    
    def user_link(self, obj):
        if obj.user:
            url = reverse('admin:auth_user_change', args=[obj.user.id])
            return format_html('<a href="{0}">{1}</a>', url, obj.user.username)
        return 'No user account'
    user_link.short_description = 'User Account'
    
    def case_count(self, obj):
        count = obj.case_set.count()
        url = reverse('admin:core_case_changelist') + f'?client__id__exact={obj.id}'
        return format_html('<a href="{0}">{1}</a>', url, count)
    case_count.short_description = 'Cases'

@admin.register(Case)
class CaseAdmin(admin.ModelAdmin):
    list_display = ('title', 'client_link', 'status', 'status_badge', 'lawyer', 'opened_on', 'due_date', 'is_active')
    list_display_links = ('title',)
    list_filter = ('status', 'opened_on', 'due_date', 'lawyer')
    search_fields = ('title', 'description', 'client__name')
    date_hierarchy = 'opened_on'
    ordering = ('-opened_on',)
    list_editable = ('status', 'lawyer')
    list_display_links = ('title',)
    readonly_fields = ('opened_on',)
    filter_horizontal = ('lawyers',) if 'lawyers' in [f.name for f in Case._meta.get_fields()] else ()
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if not request.user.is_superuser:
            # For non-superusers, only show their cases or cases they're assigned to
            qs = qs.filter(Q(client__user=request.user) | Q(lawyer=request.user))
        return qs
        
    def get_readonly_fields(self, request, obj=None):
        # Make certain fields read-only based on user permissions
        if not request.user.is_superuser:
            return self.readonly_fields + ('client', 'opened_on')
        return self.readonly_fields
        
    def is_active(self, obj):
        if obj.status == 'closed':
            return format_html(
                '<img src="/static/admin/img/icon-no.svg" alt="False">'
            )
        return format_html(
            '<img src="/static/admin/img/icon-yes.svg" alt="True">'
        )
    is_active.short_description = 'Active'
    is_active.allow_tags = True
    
    def client_link(self, obj):
        if obj.client:
            url = reverse('admin:core_client_change', args=[obj.client.id])
            return format_html('<a href="{0}">{1}</a>', url, obj.client.name)
        return 'No client'
    client_link.short_description = 'Client'
    client_link.admin_order_field = 'client__name'
    
    def status_badge(self, obj):
        status_config = {
            'open': {'color': '#28a745', 'text_color': 'white'},    # Green
            'pending': {'color': '#ffc107', 'text_color': '#212529'}, # Yellow
            'closed': {'color': '#6c757d', 'text_color': 'white'},  # Gray
        }
        config = status_config.get(obj.status, {'color': '#6c757d', 'text_color': 'white'})
        
        return format_html(
            '<span style="display: inline-block; min-width: 70px; text-align: center; '
            'background-color: {bg_color}; color: {text_color}; padding: 4px 10px; '
            'border-radius: 12px; font-size: 12px; font-weight: 500; text-transform: uppercase; '
            'letter-spacing: 0.5px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">'
            '{status}</span>',
            status=obj.get_status_display().upper(),
            bg_color=config['color'],
            text_color=config['text_color']
        )
    status_badge.allow_tags = True
    status_badge.short_description = 'Status'
    status_badge.admin_order_field = 'status'

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

@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    form = DocumentForm
    list_display = ('title', 'case_display', 'file_type_display', 'file_size_display', 'uploaded_at', 'file_actions')
    list_filter = ('uploaded_at', 'case')
    search_fields = ('title', 'case__title', 'description')
    date_hierarchy = 'uploaded_at'
    readonly_fields = ('uploaded_at', 'file_type_display', 'file_size_display', 'preview')
    list_per_page = 25
    actions = ['download_selected_documents']
    
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
    
    fieldsets = (
        (None, {
            'fields': ('title', 'description', 'case')
        }),
        ('File', {
            'fields': ('file', 'files'),
            'description': 'Upload a single file or multiple files at once.'
        }),
        ('Metadata', {
            'fields': ('file_type', 'file_size', 'uploaded_at', 'preview'),
            'classes': ('collapse',)
        }),
    )
    

    
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

@admin.register(Visitor)
class VisitorAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'submitted_at', 'message_preview')
    list_filter = ('submitted_at',)
    search_fields = ('name', 'email', 'message')
    date_hierarchy = 'submitted_at'
    readonly_fields = ('submitted_at',)
    
    def message_preview(self, obj):
        return f"{obj.message[:50]}..." if obj.message else ""
    message_preview.short_description = 'Message Preview'
