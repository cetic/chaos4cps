from django.contrib import admin
from .models import User
from django.contrib.auth.models import Group
from unfold.admin import ModelAdmin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm


# Register your models here.
class UserAdmin(BaseUserAdmin, ModelAdmin):
    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm

    list_display = ["username", "first_name", "last_name", "email"]
    list_display_links = ["username"]
    # Fields that you want to search by (can't search by foreign key)
    search_fields = ["username", "first_name", "last_name", "email"]

    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Personal info', {'fields': ('first_name', 'last_name', 'email')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'password1', 'password2', 'first_name', 'last_name', 'email'),
        }),
    )
    
# Disable group on admin page
admin.site.unregister(Group)
admin.site.register(User, UserAdmin)

