from django.contrib import admin
from unfold.admin import ModelAdmin
from .models import Comment

from django.contrib.contenttypes.admin import GenericStackedInline
from django.urls import path, reverse
from django.http import JsonResponse
from django.contrib.contenttypes.models import ContentType

from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from unfold.decorators import display

class CommentAdminMixin:
    #inlines = [CommentInline]
    change_form_template = "admin/change_form_with_comments.html"
    
    def get_urls(self):
        # Get default admin URLs first
        urls = super().get_urls()
        # Get model metadata for namespacing
        app_label = self.model._meta.app_label
        model_name = self.model._meta.model_name
        
        # Create custom URL pattern
        custom_urls = [
            path(
                '<uuid:object_id>/save-comment/',
                self.admin_site.admin_view(self.save_comment),
                name=f'{app_label}_{model_name}_save_comment'
            ),
        ]
        return custom_urls + urls

    def save_comment(self, request, object_id):
        if request.method == 'POST':
            #object_id = request.POST.get('object_id')
            #content_type_id = request.POST.get('content_type_id')
            text = request.POST.get('text')

            if not text:
                return JsonResponse({'success': False, 'error': 'Comment text is required'}, status=400)
            
            """if not all([object_id, content_type_id, text]):
                return JsonResponse({'success': False, 'error': 'Missing parameters'}, status=400)"""
            
            try:
                #content_type = ContentType.objects.get_for_id(content_type_id)
                content_type = ContentType.objects.get_for_model(self.model)
                comment = Comment.objects.create(
                    content_type=content_type,
                    object_id=object_id,
                    author=request.user,
                    text=text
                )
                return JsonResponse({
                    'success': True,
                    'comment': {
                        'text': comment.text,
                        'author': comment.author.get_full_name() or comment.author.username,
                        'created_at': comment.created_at.strftime("%Y-%m-%d %H:%M:%S")
                    }
                })
            except Exception as e:
                return JsonResponse({'success': False, 'error': str(e)}, status=400)
        return JsonResponse({'success': False, 'error': 'Invalid method'}, status=405)
    
    # Add this method to pass content_type to template context
    """def render_change_form(self, request, context, add=False, change=False, form_url='', obj=None):
        if obj:
            context['content_type'] = ContentType.objects.get_for_model(obj)
        return super().render_change_form(request, context, add, change, form_url, obj)"""
    
    def render_change_form(self, request, context, add=False, change=False, form_url='', obj=None):
        """Add custom context variables to the template"""
        if obj:
            # Generate save comment URL for this object
            model_name = self.model._meta.model_name
            app_label = self.model._meta.app_label
            context['save_comment_url'] = reverse(
                f'admin:{app_label}_{model_name}_save_comment',
                args=[obj.uuid]
            )
            
            # Get comments for this object
            content_type = ContentType.objects.get_for_model(obj)
            context['comments'] = Comment.objects.filter(
                content_type=content_type,
                object_id=obj.uuid
            ).order_by('-created_at')[:10]

        context = super().render_change_form(request, context, add, change, form_url, obj)
        return context