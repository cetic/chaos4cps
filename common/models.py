from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
import uuid6 as uuid

from accounts.models import User
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey

class Comment(models.Model):
    """Generic comment model that can be attached to any model"""
    uuid = models.CharField(max_length=100, primary_key=True, default=uuid.uuid7)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.UUIDField()
    content_object = GenericForeignKey('content_type', 'object_id')
    
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    text = models.TextField()
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'comment'
        verbose_name = 'Comment'
        verbose_name_plural = 'Comments'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
        ]
    
    def __str__(self):
        return f"Comment by {self.author.username} on {self.content_object} at {self.created_at}"