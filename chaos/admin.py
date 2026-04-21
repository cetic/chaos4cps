from django.contrib import admin, messages
from .models import *
from django.utils.html import format_html
from django.urls import reverse
from django import forms
from django.http import JsonResponse
from django.urls import path
from uuid6 import uuid7
from django.core.files.base import ContentFile
import os
from django.shortcuts import redirect
from django.utils.safestring import mark_safe
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.views import View
from django.core.exceptions import ObjectDoesNotExist

from unfold.admin import ModelAdmin
from unfold.admin import StackedInline, TabularInline
from unfold.decorators import display
from unfold.contrib.forms.widgets import WysiwygWidget
from unfold.widgets import UnfoldAdminSelectWidget
from common.admin import CommentAdminMixin
from common.models import Comment
from unfold.decorators import display
from django.contrib.auth import get_user_model
from django.contrib.admin import RelatedFieldListFilter
from django.db.models import Q

User = get_user_model()


class UserFilteredRelatedFieldListFilter(RelatedFieldListFilter):
    """Custom RelatedFieldListFilter that filters querysets based on user permissions."""
    
    def field_choices(self, field, request, model_admin):
        """Override to filter choices based on user permissions."""
        # Get the related model
        related_model = field.remote_field.model
        
        # Get the base queryset
        if request.user.is_superuser:
            queryset = related_model.objects.all()
        else:
            # Filter based on the model type
            if hasattr(related_model, 'created_by') and hasattr(related_model, 'shared'):
                # Tag, Script, Tool: own + shared
                queryset = related_model.objects.filter(
                    Q(created_by=request.user) | Q(shared=True)
                )
            elif hasattr(related_model, 'created_by'):
                queryset = related_model.objects.filter(created_by=request.user)
            elif related_model == Execution:
                queryset = Execution.objects.filter(experiment__created_by=request.user)
            elif related_model == Recovery:
                queryset = Recovery.objects.filter(execution__experiment__created_by=request.user)
            else:
                queryset = related_model.objects.all()
        
        # Return choices in the format Django expects
        order_field = 'name' if hasattr(related_model, 'name') else 'pk'
        try:
            return [(obj.pk, str(obj)) for obj in queryset.order_by(order_field)]
        except:
            return [(obj.pk, str(obj)) for obj in queryset]


# Register the custom filter for ForeignKey fields
from django.contrib.admin.filters import FieldListFilter

# Register our custom filter to be used for ForeignKey fields
FieldListFilter.register(lambda f: f.many_to_one and f.related_model, UserFilteredRelatedFieldListFilter, take_priority=True)


class UserFilteredAdminMixin:
    """
    Mixin to filter admin data based on the logged-in user.
    - Superusers see all data
    - Non-superusers only see records they created
    - Automatically sets created_by field when saving new records
    """

    def get_readonly_fields(self, request, obj=None):
        """Make created_by field readonly if it exists."""
        readonly_fields = super().get_readonly_fields(request, obj) if hasattr(super(), 'get_readonly_fields') else []
        if hasattr(self.model, 'created_by'):
            readonly_fields = list(readonly_fields) if readonly_fields else []
            if 'created_by' not in readonly_fields:
                readonly_fields.append('created_by')
        return readonly_fields

    def get_queryset(self, request):
        """Filter queryset to show only records created by the current user (unless superuser)."""
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs

        # Models with 'shared' (Tag, Script, Tool) are filtered by SharedReadOnlyAdminMixin (own | shared)
        if hasattr(self.model, 'created_by') and hasattr(self.model, 'shared'):
            return qs

        # Filter by created_by field if it exists on the model
        if hasattr(self.model, 'created_by'):
            return qs.filter(created_by=request.user)

        # Special handling for models that don't have direct created_by but inherit ownership
        model_name = self.model._meta.model_name
        if model_name == 'execution':
            # Filter executions by their experiment's created_by
            return qs.filter(experiment__created_by=request.user)
        elif model_name == 'recovery':
            # Filter recoveries by their execution's experiment's created_by
            return qs.filter(execution__experiment__created_by=request.user)

        return qs

    def has_change_permission(self, request, obj=None):
        """Check if user can change this object."""
        if request.user.is_superuser:
            return True
        if obj is None:
            # Can add new objects
            return True
        # Can only change objects they created or own through relationships
        if hasattr(obj, 'created_by'):
            return obj.created_by == request.user

        # Special handling for models that don't have direct created_by
        model_name = obj._meta.model_name
        if model_name == 'execution':
            return obj.experiment.created_by == request.user
        elif model_name == 'recovery':
            return obj.execution.experiment.created_by == request.user

        return True

    def has_delete_permission(self, request, obj=None):
        """Check if user can delete this object."""
        if request.user.is_superuser:
            return True
        if obj is None:
            # Can delete objects in general (will be filtered by queryset)
            return True
        # Can only delete objects they created or own through relationships
        if hasattr(obj, 'created_by'):
            return obj.created_by == request.user

        # Special handling for models that don't have direct created_by
        model_name = obj._meta.model_name
        if model_name == 'execution':
            return obj.experiment.created_by == request.user
        elif model_name == 'recovery':
            return obj.execution.experiment.created_by == request.user

        return True

    def has_view_permission(self, request, obj=None):
        """Check if user can view this object."""
        if request.user.is_superuser:
            return True
        if obj is None:
            # Can view objects in general (will be filtered by queryset)
            return True
        # Can only view objects they created or own through relationships
        if hasattr(obj, 'created_by'):
            return obj.created_by == request.user

        # Special handling for models that don't have direct created_by
        model_name = obj._meta.model_name
        if model_name == 'execution':
            return obj.experiment.created_by == request.user
        elif model_name == 'recovery':
            return obj.execution.experiment.created_by == request.user

        return True

    def save_model(self, request, obj, form, change):
        """Automatically set created_by field for new objects and prevent changes to existing ones."""
        if not change and hasattr(obj, 'created_by'):
            # For new objects, set created_by to current user
            obj.created_by = request.user
        elif change and hasattr(obj, 'created_by'):
            # For existing objects, preserve the original created_by value
            # Get the original object from database
            original_obj = self.model.objects.get(pk=obj.pk)
            obj.created_by = original_obj.created_by
        super().save_model(request, obj, form, change)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Filter foreign key choices based on user's permissions."""
        if not request.user.is_superuser:
            # For related fields, only show objects the user can access
            if db_field.name == 'customer' and hasattr(self.model, 'created_by'):
                # Only show customers created by the user
                kwargs['queryset'] = Customer.objects.filter(created_by=request.user)
            elif db_field.name == 'sut' and hasattr(self.model, 'created_by'):
                # Only show SUTs created by the user
                kwargs['queryset'] = Sut.objects.filter(created_by=request.user)
            elif db_field.name == 'version' and hasattr(self.model, 'created_by'):
                # Only show versions created by the user
                kwargs['queryset'] = Version.objects.filter(created_by=request.user)
            elif db_field.name == 'script' and hasattr(self.model, 'created_by'):
                # Show scripts created by the user or shared
                kwargs['queryset'] = Script.objects.filter(
                    Q(created_by=request.user) | Q(shared=True)
                )
            elif db_field.name == 'hypothesis' and hasattr(self.model, 'created_by'):
                # Only show hypotheses created by the user
                kwargs['queryset'] = Hypothesis.objects.filter(created_by=request.user)
            elif db_field.name == 'experiment' and hasattr(self.model, 'created_by'):
                # Only show experiments created by the user
                kwargs['queryset'] = Experiment.objects.filter(created_by=request.user)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        """Filter M2M choices: for Tag, show user's tags and shared tags."""
        if not request.user.is_superuser and db_field.name == 'tags':
            related_model = db_field.remote_field.model
            if hasattr(related_model, 'shared') and hasattr(related_model, 'created_by'):
                kwargs['queryset'] = related_model.objects.filter(
                    Q(created_by=request.user) | Q(shared=True)
                )
        return super().formfield_for_manytomany(db_field, request, **kwargs)

    def get_changelist(self, request, **kwargs):
        """Override to inject user-aware filter querysets."""
        from django.contrib.admin.views.main import ChangeList
        
        class UserFilteredChangeList(ChangeList):
            def get_filters(self, request):
                """Override to filter filter querysets based on user."""
                filter_specs, has_filters, lookup_params, use_distinct = super().get_filters(request)
                
                if not request.user.is_superuser:
                    # Filter the querysets used by RelatedFieldListFilter
                    for filter_spec in filter_specs:
                        if isinstance(filter_spec, RelatedFieldListFilter):
                            # Get the field and related model
                            field = filter_spec.field
                            if hasattr(field, 'remote_field') and field.remote_field:
                                related_model = field.remote_field.model
                                
                                # Store original field_choices
                                original_field_choices = filter_spec.field_choices
                                
                                # Create a wrapper that filters the queryset
                                def make_filtered_choices(related_model, user, original_method):
                                    def filtered_field_choices(field_param, request_param, model_admin_param):
                                        # Get the original choices
                                        choices = original_method(field_param, request_param, model_admin_param)
                                        
                                        if user.is_superuser:
                                            return choices
                                        
                                        # Filter choices based on user permissions
                                        filtered_choices = []
                                        for choice_pk, choice_label in choices:
                                            try:
                                                # Get the object
                                                obj = related_model.objects.get(pk=choice_pk)
                                                
                                                # Check if user has access
                                                if hasattr(related_model, 'shared') and hasattr(related_model, 'created_by'):
                                                    if obj.created_by == user or getattr(obj, 'shared', False):
                                                        filtered_choices.append((choice_pk, choice_label))
                                                elif hasattr(related_model, 'created_by'):
                                                    if obj.created_by == user:
                                                        filtered_choices.append((choice_pk, choice_label))
                                                elif related_model == Execution:
                                                    if obj.experiment.created_by == user:
                                                        filtered_choices.append((choice_pk, choice_label))
                                                elif related_model == Recovery:
                                                    if obj.execution.experiment.created_by == user:
                                                        filtered_choices.append((choice_pk, choice_label))
                                                else:
                                                    # If no filtering logic, include it
                                                    filtered_choices.append((choice_pk, choice_label))
                                            except related_model.DoesNotExist:
                                                # Skip if object doesn't exist
                                                continue
                                        
                                        return filtered_choices
                                    
                                    return filtered_field_choices
                                
                                # Replace the field_choices method
                                filter_spec.field_choices = make_filtered_choices(related_model, request.user, original_field_choices)
                
                return filter_specs, has_filters, lookup_params, use_distinct
        
        kwargs['list_class'] = UserFilteredChangeList
        return super().get_changelist(request, **kwargs)


class SharedReadOnlyAdminMixin:
    """
    Mixin for Tag, Tool, and Script admins.
    - Superusers: full access.
    - Non-superusers: can add/read/list/edit/delete their own data;
      can read and list shared data (can open detail page but not edit);
      cannot edit or delete other users' data.
    """

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        if hasattr(self.model, 'created_by') and hasattr(self.model, 'shared'):
            return qs.filter(Q(created_by=request.user) | Q(shared=True))
        return qs

    def has_view_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        if obj is None:
            return True
        if hasattr(obj, 'shared'):
            return obj.created_by == request.user or getattr(obj, 'shared', False)
        return super().has_view_permission(request, obj)

    def has_change_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        if obj is None:
            return True
        # Non-superusers can open change view for own or shared (edit blocked via readonly)
        if hasattr(obj, 'created_by') and hasattr(obj, 'shared'):
            return obj.created_by == request.user or getattr(obj, 'shared', False)
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        if obj is None:
            return True
        if hasattr(obj, 'created_by'):
            return obj.created_by == request.user
        return super().has_delete_permission(request, obj)

    def get_readonly_fields(self, request, obj=None):
        # Avoid recursion: get_fieldsets can trigger get_readonly_fields when building the form
        if getattr(request, '_shared_readonly_guard', False):
            return list(super().get_readonly_fields(request, obj))
        readonly = list(super().get_readonly_fields(request, obj))
        # For shared items not owned by this user: make all fields readonly (view only)
        if (
            obj is not None
            and hasattr(obj, 'shared')
            and getattr(obj, 'shared', False)
            and obj.created_by != request.user
        ):
            request._shared_readonly_guard = True
            try:
                all_field_names = set()
                for fieldset in self.get_fieldsets(request, obj):
                    for field_name in fieldset[1]['fields']:
                        if isinstance(field_name, str):
                            all_field_names.add(field_name)
                        else:
                            all_field_names.update(field_name)
                readonly = list(all_field_names)
            finally:
                request._shared_readonly_guard = False
        return readonly

    def get_inline_instances(self, request, obj=None):
        """Hide inlines when viewing shared items (non-owner): no add/edit related data."""
        if (
            obj is not None
            and not request.user.is_superuser
            and getattr(obj, 'shared', False)
            and obj.created_by != request.user
        ):
            return []
        return super().get_inline_instances(request, obj)

    def change_view(self, request, object_id, form_url='', extra_context=None):
        extra_context = extra_context or {}
        if not request.user.is_superuser and object_id:
            try:
                obj = self.get_object(request, object_id)
                if obj and getattr(obj, 'shared', False) and obj.created_by != request.user:
                    extra_context['show_save'] = False
                    extra_context['show_save_and_continue'] = False
                    extra_context['show_save_and_add_another'] = False
                    extra_context['show_save_as_new'] = False
                    extra_context['show_delete'] = False
                    extra_context['is_view_only_shared'] = True
            except self.model.DoesNotExist:
                pass
        return super().change_view(request, object_id, form_url, extra_context=extra_context)


# Custom Forms for Dynamic Field Filtering
class ElementForm(forms.ModelForm):
    """Enhanced form for Element with dynamic customer -> SUT -> Version filtering."""
    customer = forms.ModelChoiceField(
        queryset=Customer.objects.all(),
        required=False,
        empty_label="Select a customer",
        help_text="Select a customer to filter available SUTs and versions",
        widget=UnfoldAdminSelectWidget
    )
    sut = forms.ModelChoiceField(
        queryset=Sut.objects.none(),
        required=False,
        empty_label="Select a SUT",
        help_text="Select a System Under Test (filtered by customer)",
        widget=UnfoldAdminSelectWidget
    )
    
    class Meta:
        model = Element
        fields = '__all__'
        exclude = ['uuid', 'created_at', 'updated_at', 'created_by']

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        # Filter customer queryset based on user if not superuser
        if user and not user.is_superuser:
            self.fields['customer'].queryset = Customer.objects.filter(created_by=user)
        else:
            self.fields['customer'].queryset = Customer.objects.all()

        # Set up initial states for dynamic fields
        if self.instance and self.instance.pk:
            # Editing existing element - set initial values if relationships exist
            try:
                # Check if element has a version
                if hasattr(self.instance, 'version') and self.instance.version_id:
                    version = self.instance.version
                    print(f"Setting up edit form for Element {self.instance.pk}, version: {version}")
                    
                    # Set up customer field - keep all customers available but set initial
                    #self.fields['customer'].queryset = Customer.objects.all()
                    if version.sut and version.sut.customer:
                        # Set initial values using both initial and data attributes
                        self.fields['customer'].initial = version.sut.customer
                        self.initial['customer'] = version.sut.customer.pk
                        print(f"Set customer initial to: {version.sut.customer}")
                        
                        # Set up SUT field - show SUTs for the customer
                        self.fields['sut'].queryset = Sut.objects.filter(customer=version.sut.customer)
                        self.fields['sut'].initial = version.sut
                        self.initial['sut'] = version.sut.pk
                        print(f"Set SUT initial to: {version.sut}")
                        
                        # Set up version field - show versions for the SUT
                        self.fields['version'].queryset = Version.objects.filter(sut=version.sut)
                        self.fields['version'].initial = version
                        self.initial['version'] = version.pk
                        print(f"Set version initial to: {version}")
                        
                        # Set up parent field - elements in same version excluding self
                        self.fields['parent'].queryset = Element.objects.filter(version=version).exclude(pk=self.instance.pk)
                        
                        print("Successfully set up edit form")
                        # Successfully set up edit form, return early
                        return
                        
            except Exception as e:
                # Log the error for debugging (you can remove this in production)
                print(f"Error setting up edit form for Element {self.instance.pk}: {e}")
                # Fall through to default setup
        
        # Default setup for new elements or when relationships don't exist
        print("Setting up default form (new element or missing relationships)")
        #self.fields['customer'].queryset = Customer.objects.all()
        self.fields['sut'].queryset = Sut.objects.none()
        self.fields['version'].queryset = Version.objects.none()
        self.fields['parent'].queryset = Element.objects.none()

    def clean(self):
        cleaned_data = super().clean()
        customer = cleaned_data.get('customer')
        sut = cleaned_data.get('sut')
        version = cleaned_data.get('version')
        
        # Validate cascading relationships
        if customer and sut and sut.customer != customer:
            raise forms.ValidationError("Selected SUT does not belong to the selected customer.")
        
        if sut and version and version.sut != sut:
            raise forms.ValidationError("Selected version does not belong to the selected SUT.")
        
        # Remove custom fields that are not part of the model
        # These fields are only used for dynamic filtering in the UI
        cleaned_data.pop('customer', None)
        cleaned_data.pop('sut', None)
        
        return cleaned_data

    def clean_sut(self):
        """Ensure sut field validation doesn't fail due to filtered queryset."""
        sut = self.cleaned_data.get('sut')
        if sut:
            try:
                # Verify the sut exists in the database
                Sut.objects.get(pk=sut.pk)
                # Temporarily expand the queryset to include this sut
                if hasattr(self.fields['sut'], 'queryset') and sut not in self.fields['sut'].queryset:
                    self.fields['sut'].queryset = self.fields['sut'].queryset | Sut.objects.filter(pk=sut.pk)
                return sut
            except Sut.DoesNotExist:
                raise forms.ValidationError("Selected SUT does not exist.")
        return sut

    def clean_version(self):
        """Ensure version field validation doesn't fail due to filtered queryset."""
        version = self.cleaned_data.get('version')
        if version:
            try:
                # Verify the version exists in the database
                Version.objects.get(pk=version.pk)
                # Temporarily expand the queryset to include this version
                if hasattr(self.fields['version'], 'queryset') and version not in self.fields['version'].queryset:
                    self.fields['version'].queryset = self.fields['version'].queryset | Version.objects.filter(pk=version.pk)
                return version
            except Version.DoesNotExist:
                raise forms.ValidationError("Selected version does not exist.")
        return version

    def clean_parent(self):
        """Ensure parent field validation doesn't fail due to filtered queryset."""
        parent = self.cleaned_data.get('parent')
        if parent:
            try:
                # Verify the parent exists in the database
                Element.objects.get(pk=parent.pk)
                # Temporarily expand the queryset to include this parent
                if hasattr(self.fields['parent'], 'queryset') and parent not in self.fields['parent'].queryset:
                    self.fields['parent'].queryset = self.fields['parent'].queryset | Element.objects.filter(pk=parent.pk)
                return parent
            except Element.DoesNotExist:
                raise forms.ValidationError("Selected parent element does not exist.")
        return parent

    def full_clean(self):
        """Override to expand querysets before field validation."""
        # First, expand querysets based on submitted data
        if self.data:
            # Helper function to get field value considering form prefix
            def get_field_value(field_name):
                if hasattr(self, 'prefix') and self.prefix:
                    prefixed_name = f"{self.prefix}-{field_name}"
                    value = self.data.get(prefixed_name)
                    if value is None:
                        value = self.data.get(field_name)
                    return value
                return self.data.get(field_name)
            
            # Expand customer queryset before validation (if needed)
            customer_id = get_field_value('customer')
            if customer_id and customer_id != '' and 'customer' in self.fields:
                try:
                    customer = Customer.objects.get(pk=customer_id)
                    if hasattr(self.fields['customer'], 'queryset') and customer not in self.fields['customer'].queryset:
                        self.fields['customer'].queryset = self.fields['customer'].queryset | Customer.objects.filter(pk=customer_id)
                except (Customer.DoesNotExist, ValueError):
                    pass
            
            # Expand sut queryset before validation
            sut_id = get_field_value('sut')
            if sut_id and sut_id != '' and 'sut' in self.fields:
                try:
                    sut = Sut.objects.get(pk=sut_id)
                    if hasattr(self.fields['sut'], 'queryset') and sut not in self.fields['sut'].queryset:
                        self.fields['sut'].queryset = self.fields['sut'].queryset | Sut.objects.filter(pk=sut_id)
                except (Sut.DoesNotExist, ValueError):
                    pass
            
            # Expand version queryset before validation
            version_id = get_field_value('version')
            if version_id and version_id != '' and 'version' in self.fields:
                try:
                    version = Version.objects.get(pk=version_id)
                    if hasattr(self.fields['version'], 'queryset') and version not in self.fields['version'].queryset:
                        self.fields['version'].queryset = self.fields['version'].queryset | Version.objects.filter(pk=version_id)
                except (Version.DoesNotExist, ValueError):
                    pass
            
            # Expand parent queryset before validation
            parent_id = get_field_value('parent')
            if parent_id and parent_id != '' and 'parent' in self.fields:
                try:
                    parent = Element.objects.get(pk=parent_id)
                    if hasattr(self.fields['parent'], 'queryset') and parent not in self.fields['parent'].queryset:
                        self.fields['parent'].queryset = self.fields['parent'].queryset | Element.objects.filter(pk=parent_id)
                except (Element.DoesNotExist, ValueError):
                    pass
        
        # Call parent full_clean after expanding querysets
        super().full_clean()


class SteadyStateScriptParameterInlineForm(forms.ModelForm):
    """Simple form for SteadyStateScriptParameter."""
    
    class Meta:
        model = SteadyStateScriptParameter
        fields = ('script', 'parameter', 'parameter_value')


class SteadyStateForm(forms.ModelForm):
    """Enhanced form for SteadyState with dynamic customer -> SUT -> Version filtering."""
    customer = forms.ModelChoiceField(
        queryset=Customer.objects.all(),
        required=False,
        empty_label="Select a customer",
        help_text="Select a customer to filter available SUTs and versions",
        widget=UnfoldAdminSelectWidget
    )
    sut = forms.ModelChoiceField(
        queryset=Sut.objects.none(),
        required=False,
        empty_label="Select a SUT",
        help_text="Select a System Under Test (filtered by customer)",
        widget=UnfoldAdminSelectWidget
    )
    script = forms.ModelChoiceField(
        queryset=Script.objects.all(),
        required=False,
        empty_label="Select a script",
        help_text="Select a script to configure parameters for this steady state",
        widget=UnfoldAdminSelectWidget
    )
    
    class Meta:
        model = SteadyState
        fields = '__all__'
        exclude = ['uuid', 'created_at', 'updated_at', 'created_by']

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        # Filter customer queryset based on user if not superuser
        if user and not user.is_superuser:
            self.fields['customer'].queryset = Customer.objects.filter(created_by=user)
        else:
            self.fields['customer'].queryset = Customer.objects.all()

        # Set up initial states for dynamic fields
        if self.instance and self.instance.pk:
            # Editing existing steady state - set initial values if relationships exist
            try:
                # Check if steady state has a version
                if hasattr(self.instance, 'version') and self.instance.version_id:
                    version = self.instance.version
                    print(f"Setting up edit form for SteadyState {self.instance.pk}, version: {version}")
                    
                    # Set up customer field - keep all customers available but set initial
                    #self.fields['customer'].queryset = Customer.objects.all()
                    if version.sut and version.sut.customer:
                        # Set initial values using both initial and data attributes
                        self.fields['customer'].initial = version.sut.customer
                        self.initial['customer'] = version.sut.customer.pk
                        print(f"Set customer initial to: {version.sut.customer}")
                        
                        # Set up SUT field - show SUTs for the customer
                        self.fields['sut'].queryset = Sut.objects.filter(customer=version.sut.customer)
                        self.fields['sut'].initial = version.sut
                        self.initial['sut'] = version.sut.pk
                        print(f"Set SUT initial to: {version.sut}")
                        
                        # Set up version field - show versions for the SUT
                        self.fields['version'].queryset = Version.objects.filter(sut=version.sut)
                        self.fields['version'].initial = version
                        self.initial['version'] = version.pk
                        print(f"Set version initial to: {version}")
                        
                        print("Successfully set up SteadyState edit form")
                        # Successfully set up edit form, return early
                        return
                        
            except Exception as e:
                # Log the error for debugging (you can remove this in production)
                print(f"Error setting up edit form for SteadyState {self.instance.pk}: {e}")
                # Fall through to default setup
        
        # Default setup for new steady states or when relationships don't exist
        print("Setting up default SteadyState form (new or missing relationships)")
        #self.fields['customer'].queryset = Customer.objects.all()
        self.fields['sut'].queryset = Sut.objects.none()
        self.fields['version'].queryset = Version.objects.none()

    def clean(self):
        cleaned_data = super().clean()
        
        # Remove custom fields that are not part of the model
        # These fields are only used for dynamic filtering in the UI
        cleaned_data.pop('customer', None)
        cleaned_data.pop('sut', None)
        cleaned_data.pop('script', None)
        
        return cleaned_data

    def clean_sut(self):
        """Ensure sut field validation doesn't fail due to filtered queryset."""
        sut = self.cleaned_data.get('sut')
        if sut:
            try:
                # Verify the sut exists in the database
                Sut.objects.get(pk=sut.pk)
                # Temporarily expand the queryset to include this sut
                if hasattr(self.fields['sut'], 'queryset') and sut not in self.fields['sut'].queryset:
                    self.fields['sut'].queryset = self.fields['sut'].queryset | Sut.objects.filter(pk=sut.pk)
                return sut
            except Sut.DoesNotExist:
                raise forms.ValidationError("Selected SUT does not exist.")
        return sut

    def clean_version(self):
        """Ensure version field validation doesn't fail due to filtered queryset."""
        version = self.cleaned_data.get('version')
        if version:
            try:
                # Verify the version exists in the database
                Version.objects.get(pk=version.pk)
                # Temporarily expand the queryset to include this version
                if hasattr(self.fields['version'], 'queryset') and version not in self.fields['version'].queryset:
                    self.fields['version'].queryset = self.fields['version'].queryset | Version.objects.filter(pk=version.pk)
                return version
            except Version.DoesNotExist:
                raise forms.ValidationError("Selected version does not exist.")
        return version

    def full_clean(self):
        """Override to expand querysets before field validation."""
        # First, expand querysets based on submitted data
        if self.data:
            # Helper function to get field value considering form prefix
            def get_field_value(field_name):
                if hasattr(self, 'prefix') and self.prefix:
                    prefixed_name = f"{self.prefix}-{field_name}"
                    value = self.data.get(prefixed_name)
                    if value is None:
                        value = self.data.get(field_name)
                    return value
                return self.data.get(field_name)
            
            # Expand customer queryset before validation (if needed)
            customer_id = get_field_value('customer')
            if customer_id and customer_id != '' and 'customer' in self.fields:
                try:
                    customer = Customer.objects.get(pk=customer_id)
                    if hasattr(self.fields['customer'], 'queryset') and customer not in self.fields['customer'].queryset:
                        self.fields['customer'].queryset = self.fields['customer'].queryset | Customer.objects.filter(pk=customer_id)
                except (Customer.DoesNotExist, ValueError):
                    pass
            
            # Expand sut queryset before validation
            sut_id = get_field_value('sut')
            if sut_id and sut_id != '' and 'sut' in self.fields:
                try:
                    sut = Sut.objects.get(pk=sut_id)
                    if hasattr(self.fields['sut'], 'queryset') and sut not in self.fields['sut'].queryset:
                        self.fields['sut'].queryset = self.fields['sut'].queryset | Sut.objects.filter(pk=sut_id)
                except (Sut.DoesNotExist, ValueError):
                    pass
            
            # Expand version queryset before validation
            version_id = get_field_value('version')
            if version_id and version_id != '' and 'version' in self.fields:
                try:
                    version = Version.objects.get(pk=version_id)
                    if hasattr(self.fields['version'], 'queryset') and version not in self.fields['version'].queryset:
                        self.fields['version'].queryset = self.fields['version'].queryset | Version.objects.filter(pk=version_id)
                except (Version.DoesNotExist, ValueError):
                    pass
        
        # Call parent full_clean after expanding querysets
        super().full_clean()


class HypothesisForm(forms.ModelForm):
    """Enhanced form for Hypothesis with dynamic customer -> SUT -> Version filtering."""
    customer = forms.ModelChoiceField(
        queryset=Customer.objects.all(),
        required=False,
        empty_label="Select a customer",
        help_text="Select a customer to filter available SUTs and versions",
        widget=UnfoldAdminSelectWidget
    )
    sut = forms.ModelChoiceField(
        queryset=Sut.objects.none(),
        required=False,
        empty_label="Select a SUT",
        help_text="Select a System Under Test (filtered by customer)",
        widget=UnfoldAdminSelectWidget
    )
    
    class Meta:
        model = Hypothesis
        fields = '__all__'
        exclude = ['uuid', 'created_at', 'updated_at', 'elements', 'steady_states', 'created_by']

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        # Filter customer queryset based on user if not superuser
        if user and not user.is_superuser:
            self.fields['customer'].queryset = Customer.objects.filter(created_by=user)
        else:
            self.fields['customer'].queryset = Customer.objects.all()

        # Set up initial states for dynamic fields
        if self.instance and self.instance.pk:
            # Editing existing hypothesis - set initial values if relationships exist
            try:
                # Check if hypothesis has a version
                if hasattr(self.instance, 'version') and self.instance.version_id:
                    version = self.instance.version
                    print(f"Setting up edit form for Hypothesis {self.instance.pk}, version: {version}")
                    
                    # Set up customer field - keep all customers available but set initial
                    #self.fields['customer'].queryset = Customer.objects.all()
                    if version.sut and version.sut.customer:
                        # Set initial values using both initial and data attributes
                        self.fields['customer'].initial = version.sut.customer
                        self.initial['customer'] = version.sut.customer.pk
                        print(f"Set customer initial to: {version.sut.customer}")
                        
                        # Set up SUT field - show SUTs for the customer
                        self.fields['sut'].queryset = Sut.objects.filter(customer=version.sut.customer)
                        self.fields['sut'].initial = version.sut
                        self.initial['sut'] = version.sut.pk
                        print(f"Set SUT initial to: {version.sut}")
                        
                        # Set up version field - show versions for the SUT
                        self.fields['version'].queryset = Version.objects.filter(sut=version.sut)
                        self.fields['version'].initial = version
                        self.initial['version'] = version.pk
                        print(f"Set version initial to: {version}")
                        
                        # Note: elements and steady_states fields are hidden from the interface
                        
                        print("Successfully set up Hypothesis edit form")
                        # Successfully set up edit form, return early
                        return
                        
            except Exception as e:
                # Log the error for debugging (you can remove this in production)
                print(f"Error setting up edit form for Hypothesis {self.instance.pk}: {e}")
                # Fall through to default setup
        
        # Default setup for new hypotheses or when relationships don't exist
        print("Setting up default Hypothesis form (new or missing relationships)")
        #self.fields['customer'].queryset = Customer.objects.all()
        self.fields['sut'].queryset = Sut.objects.none()
        self.fields['version'].queryset = Version.objects.none()
        # Note: elements and steady_states fields are hidden from the interface

    def clean(self):
        cleaned_data = super().clean()
        
        # Remove custom fields that are not part of the model
        # These fields are only used for dynamic filtering in the UI
        cleaned_data.pop('customer', None)
        cleaned_data.pop('sut', None)
        
        return cleaned_data
    
    def full_clean(self):
        """Override to expand querysets before validation to prevent 'choice not available' errors."""
        # Expand querysets to include submitted values before validation
        if self.data:
            # Expand version queryset if version is submitted
            version_id = self.data.get('version')
            if version_id and hasattr(self.fields.get('version'), 'queryset'):
                try:
                    version = Version.objects.get(pk=version_id)
                    current_queryset = self.fields['version'].queryset
                    if version not in current_queryset:
                        self.fields['version'].queryset = current_queryset | Version.objects.filter(pk=version_id)
                except (Version.DoesNotExist, ValueError):
                    pass
            
            # Expand SUT queryset if SUT is submitted
            sut_id = self.data.get('sut')
            if sut_id and hasattr(self.fields.get('sut'), 'queryset'):
                try:
                    sut = Sut.objects.get(pk=sut_id)
                    current_queryset = self.fields['sut'].queryset
                    if sut not in current_queryset:
                        self.fields['sut'].queryset = current_queryset | Sut.objects.filter(pk=sut_id)
                except (Sut.DoesNotExist, ValueError):
                    pass
            
            # Expand customer queryset if customer is submitted
            customer_id = self.data.get('customer')
            if customer_id and hasattr(self.fields.get('customer'), 'queryset'):
                try:
                    customer = Customer.objects.get(pk=customer_id)
                    current_queryset = self.fields['customer'].queryset
                    if customer not in current_queryset:
                        self.fields['customer'].queryset = current_queryset | Customer.objects.filter(pk=customer_id)
                except (Customer.DoesNotExist, ValueError):
                    pass
        
        # Call parent full_clean after expanding querysets
        super().full_clean()


class VersionForm(forms.ModelForm):
    """Enhanced form for Version with dynamic customer -> SUT filtering."""
    customer = forms.ModelChoiceField(
        queryset=Customer.objects.all(),
        required=False,
        empty_label="Select a customer",
        help_text="Select a customer to filter available SUTs",
        widget=UnfoldAdminSelectWidget
    )
    
    class Meta:
        model = Version
        fields = '__all__'
        exclude = ['uuid', 'created_at', 'updated_at', 'created_by']

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        # Filter customer queryset based on user if not superuser
        if user and not user.is_superuser:
            self.fields['customer'].queryset = Customer.objects.filter(created_by=user)
        else:
            self.fields['customer'].queryset = Customer.objects.all()
        
        # Set up initial querysets
        if self.instance and self.instance.pk:
            # Editing existing version
            try:
                if hasattr(self.instance, 'sut') and self.instance.sut:
                    self.fields['customer'].initial = self.instance.sut.customer
                    self.fields['sut'].queryset = Sut.objects.filter(
                            customer=self.instance.sut.customer
                        )
                    self.fields['sut'].initial = self.instance.sut
            except (AttributeError, Sut.DoesNotExist):
                # Handle case where sut relationship doesn't exist
                pass
        else:
            # Creating new version
            self.fields['sut'].queryset = Sut.objects.none()

    def clean(self):
        cleaned_data = super().clean()
        customer = cleaned_data.get('customer')
        sut = cleaned_data.get('sut')
        
        # Validate cascading relationships
        if customer and sut and sut.customer != customer:
            raise forms.ValidationError("Selected SUT does not belong to the selected customer.")
        
        # Remove custom fields that are not part of the model
        # These fields are only used for dynamic filtering in the UI
        cleaned_data.pop('customer', None)
        
        return cleaned_data

    def full_clean(self):
        """Override to expand querysets before validation to prevent 'choice not available' errors."""
        # Expand querysets to include submitted values before validation
        if self.data:
            # Expand SUT queryset if SUT is submitted
            sut_id = self.data.get('sut')
            if sut_id and hasattr(self.fields.get('sut'), 'queryset'):
                try:
                    sut = Sut.objects.get(pk=sut_id)
                    current_queryset = self.fields['sut'].queryset
                    if sut not in current_queryset:
                        self.fields['sut'].queryset = current_queryset | Sut.objects.filter(pk=sut_id)
                except (Sut.DoesNotExist, ValueError):
                    pass
        
        # Call parent full_clean after expanding querysets
        super().full_clean()


class ExperimentForm(forms.ModelForm):
    """Enhanced form for Experiment with dynamic filtering."""
    customer = forms.ModelChoiceField(
        queryset=Customer.objects.all(),
        required=False,
        empty_label="Select a customer",
        help_text="Select a customer to filter available SUTs, versions, and hypotheses",
        widget=UnfoldAdminSelectWidget
    )
    sut = forms.ModelChoiceField(
        queryset=Sut.objects.none(),
        required=False,
        empty_label="Select a SUT",
        help_text="Select a System Under Test (filtered by customer)",
        widget=UnfoldAdminSelectWidget
    )
    version = forms.ModelChoiceField(
        queryset=Version.objects.none(),
        required=False,
        empty_label="Select a version",
        help_text="Select a version (filtered by SUT)",
        widget=UnfoldAdminSelectWidget
    )
    script_for_parameters = forms.ModelChoiceField(
        queryset=Script.objects.all(),
        required=False,
        empty_label="Select a script to configure parameters",
        help_text="Select a script to view and configure its parameters for this experiment",
        widget=UnfoldAdminSelectWidget
    )
    
    class Meta:
        model = Experiment
        fields = '__all__'
        exclude = ['uuid', 'created_at', 'updated_at', 'created_by']

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        # Filter customer queryset based on user if not superuser
        if user and not user.is_superuser:
            self.fields['customer'].queryset = Customer.objects.filter(created_by=user)
        else:
            self.fields['customer'].queryset = Customer.objects.all()

        # Set up initial querysets
        if self.instance and self.instance.pk:
            # Editing existing experiment
            try:
                if hasattr(self.instance, 'hypothesis') and self.instance.hypothesis_id:
                    hypothesis = self.instance.hypothesis
                    print(f"Setting up edit form for Experiment {self.instance.pk}, hypothesis: {hypothesis}")
                    
                    if hypothesis.version and hypothesis.version.sut and hypothesis.version.sut.customer:
                        version = hypothesis.version
                        
                        # Set up customer field - keep all customers available but set initial
                        #self.fields['customer'].queryset = Customer.objects.all()
                        self.fields['customer'].initial = version.sut.customer
                        self.initial['customer'] = version.sut.customer.pk
                        print(f"Set customer initial to: {version.sut.customer}")
                        
                        # Set up SUT field - show SUTs for the customer
                        self.fields['sut'].queryset = Sut.objects.filter(customer=version.sut.customer)
                        self.fields['sut'].initial = version.sut
                        self.initial['sut'] = version.sut.pk
                        print(f"Set SUT initial to: {version.sut}")
                        
                        # Set up version field - show versions for the SUT
                        self.fields['version'].queryset = Version.objects.filter(sut=version.sut)
                        self.fields['version'].initial = version
                        self.initial['version'] = version.pk
                        print(f"Set version initial to: {version}")
                        
                        # Set up hypothesis field - show hypotheses for the version
                        self.fields['hypothesis'].queryset = Hypothesis.objects.filter(version=version)
                        self.fields['hypothesis'].initial = hypothesis
                        self.initial['hypothesis'] = hypothesis.pk
                        print(f"Set hypothesis initial to: {hypothesis}")
                
                        # Filter elements and steady states by version
                        self.fields['elements'].queryset = version.elements.all()
                        self.fields['steady_states'].queryset = version.steady_states.all()
                        print("Successfully set up edit form")
                        return
            except Exception as e:
                print(f"Error setting up edit form for Experiment {self.instance.pk}: {e}")
        
        # Default setup for new experiment or when relationships are missing
        print("Setting up default form (new experiment or missing relationships)")
        #self.fields['customer'].queryset = Customer.objects.all()
        self.fields['sut'].queryset = Sut.objects.none()
        self.fields['version'].queryset = Version.objects.none()
        self.fields['hypothesis'].queryset = Hypothesis.objects.none()
        self.fields['elements'].queryset = Element.objects.none()
        self.fields['steady_states'].queryset = SteadyState.objects.none()

    def clean(self):
        cleaned_data = super().clean()
        
        # Remove custom fields that are not part of the model
        # These fields are only used for dynamic filtering in the UI
        cleaned_data.pop('customer', None)
        cleaned_data.pop('sut', None)
        cleaned_data.pop('version', None)
        cleaned_data.pop('script_for_parameters', None)

        return cleaned_data

    def clean_customer(self):
        """Clean customer field - allow empty values."""
        customer = self.cleaned_data.get('customer')
        if customer == '':
            return None
        return customer

    def clean_sut(self):
        """Clean SUT field - allow empty values."""
        sut = self.cleaned_data.get('sut')
        if sut == '':
            return None
        return sut

    def clean_version(self):
        """Clean version field - allow empty values."""
        version = self.cleaned_data.get('version')
        if version == '':
            return None
        return version

    def clean_script_for_parameters(self):
        """Clean script_for_parameters field - allow empty values."""
        script = self.cleaned_data.get('script_for_parameters')
        if script == '':
            return None
        return script

    def full_clean(self):
        """Override to expand querysets before validation to prevent 'choice not available' errors."""
        # Expand querysets to include submitted values before validation
        if self.data:
            # Expand customer queryset if customer is submitted
            customer_id = self.data.get('customer')
            if customer_id and customer_id.strip() and hasattr(self.fields.get('customer'), 'queryset'):
                try:
                    customer = Customer.objects.get(pk=customer_id)
                    current_queryset = self.fields['customer'].queryset
                    if customer not in current_queryset:
                        self.fields['customer'].queryset = current_queryset | Customer.objects.filter(pk=customer_id)
                except (Customer.DoesNotExist, ValueError):
                    pass

            # Expand SUT queryset if SUT is submitted
            sut_id = self.data.get('sut')
            if sut_id and sut_id.strip() and hasattr(self.fields.get('sut'), 'queryset'):
                try:
                    sut = Sut.objects.get(pk=sut_id)
                    current_queryset = self.fields['sut'].queryset
                    if sut not in current_queryset:
                        self.fields['sut'].queryset = current_queryset | Sut.objects.filter(pk=sut_id)
                except (Sut.DoesNotExist, ValueError):
                    pass

            # Expand version queryset if version is submitted
            version_id = self.data.get('version')
            if version_id and version_id.strip() and hasattr(self.fields.get('version'), 'queryset'):
                try:
                    version = Version.objects.get(pk=version_id)
                    current_queryset = self.fields['version'].queryset
                    if version not in current_queryset:
                        self.fields['version'].queryset = current_queryset | Version.objects.filter(pk=version_id)
                except (Version.DoesNotExist, ValueError):
                    pass

            # Expand hypothesis queryset if hypothesis is submitted
            hypothesis_id = self.data.get('hypothesis')
            if hypothesis_id and hasattr(self.fields.get('hypothesis'), 'queryset'):
                try:
                    hypothesis = Hypothesis.objects.get(pk=hypothesis_id)
                    current_queryset = self.fields['hypothesis'].queryset
                    if hypothesis not in current_queryset:
                        self.fields['hypothesis'].queryset = current_queryset | Hypothesis.objects.filter(pk=hypothesis_id)
                except (Hypothesis.DoesNotExist, ValueError):
                    pass

            # Expand script_for_parameters queryset if script is submitted
            script_id = self.data.get('script_for_parameters')
            if script_id and script_id.strip() and hasattr(self.fields.get('script_for_parameters'), 'queryset'):
                try:
                    script = Script.objects.get(pk=script_id)
                    current_queryset = self.fields['script_for_parameters'].queryset
                    if script not in current_queryset:
                        self.fields['script_for_parameters'].queryset = current_queryset | Script.objects.filter(pk=script_id)
                except (Script.DoesNotExist, ValueError):
                    pass
            
            # Expand elements queryset for many-to-many field
            element_ids = self.data.getlist('elements')
            if element_ids and hasattr(self.fields.get('elements'), 'queryset'):
                try:
                    # Filter valid element IDs
                    valid_element_ids = []
                    for element_id in element_ids:
                        if Element.objects.filter(pk=element_id).exists():
                            valid_element_ids.append(element_id)
                    
                    if valid_element_ids:
                        current_queryset = self.fields['elements'].queryset
                        additional_elements = Element.objects.filter(pk__in=valid_element_ids)
                        self.fields['elements'].queryset = current_queryset | additional_elements
                except (ValueError, TypeError):
                    pass
            
            # Expand steady_states queryset for many-to-many field
            steady_state_ids = self.data.getlist('steady_states')
            if steady_state_ids and hasattr(self.fields.get('steady_states'), 'queryset'):
                try:
                    # Filter valid steady state IDs
                    valid_steady_state_ids = []
                    for steady_state_id in steady_state_ids:
                        if SteadyState.objects.filter(pk=steady_state_id).exists():
                            valid_steady_state_ids.append(steady_state_id)
                    
                    if valid_steady_state_ids:
                        current_queryset = self.fields['steady_states'].queryset
                        additional_steady_states = SteadyState.objects.filter(pk__in=valid_steady_state_ids)
                        self.fields['steady_states'].queryset = current_queryset | additional_steady_states
                except (ValueError, TypeError):
                    pass
        
        # Call parent full_clean after expanding querysets
        super().full_clean()


class ExecutionForm(forms.ModelForm):
    """Enhanced form for Execution with dynamic filtering."""
    customer = forms.ModelChoiceField(
        queryset=Customer.objects.all(),
        required=False,
        empty_label="Select a customer",
        help_text="Select a customer to filter available SUTs, versions, hypotheses, and experiments",
        widget=UnfoldAdminSelectWidget
    )
    sut = forms.ModelChoiceField(
        queryset=Sut.objects.none(),
        required=False,
        empty_label="Select a SUT",
        help_text="Select a System Under Test (filtered by customer)",
        widget=UnfoldAdminSelectWidget
    )
    version = forms.ModelChoiceField(
        queryset=Version.objects.none(),
        required=False,
        empty_label="Select a version",
        help_text="Select a version (filtered by SUT)",
        widget=UnfoldAdminSelectWidget
    )
    hypothesis = forms.ModelChoiceField(
        queryset=Hypothesis.objects.none(),
        required=False,
        empty_label="Select a hypothesis",
        help_text="Select a hypothesis (filtered by version)",
        widget=UnfoldAdminSelectWidget
    )
    script = forms.ModelChoiceField(
        queryset=Script.objects.all(),
        required=False,
        empty_label="Select a script",
        help_text="Select a script to view its parameters for execution configuration",
        widget=UnfoldAdminSelectWidget
    )
    
    class Meta:
        model = Execution
        fields = '__all__'
        exclude = ['uuid', 'created_at', 'updated_at', 'created_by']

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        # Filter customer queryset based on user if not superuser
        if user and not user.is_superuser:
            self.fields['customer'].queryset = Customer.objects.filter(created_by=user)
        else:
            self.fields['customer'].queryset = Customer.objects.all()

        # Set up initial querysets
        if self.instance and self.instance.pk:
            # Editing existing execution
            try:
                if hasattr(self.instance, 'experiment') and self.instance.experiment_id:
                    experiment = self.instance.experiment
                    print(f"Setting up edit form for Execution {self.instance.pk}, experiment: {experiment}")
                    
                    if (experiment.hypothesis and experiment.hypothesis.version and 
                        experiment.hypothesis.version.sut and experiment.hypothesis.version.sut.customer):
                        hypothesis = experiment.hypothesis
                        version = hypothesis.version
                        
                        # Set up customer field - keep all customers available but set initial
                        #self.fields['customer'].queryset = Customer.objects.all()
                        self.fields['customer'].initial = version.sut.customer
                        self.initial['customer'] = version.sut.customer.pk
                        print(f"Set customer initial to: {version.sut.customer}")
                        
                        # Set up SUT field - show SUTs for the customer
                        self.fields['sut'].queryset = Sut.objects.filter(customer=version.sut.customer)
                        self.fields['sut'].initial = version.sut
                        self.initial['sut'] = version.sut.pk
                        print(f"Set SUT initial to: {version.sut}")
                        
                        # Set up version field - show versions for the SUT
                        self.fields['version'].queryset = Version.objects.filter(sut=version.sut)
                        self.fields['version'].initial = version
                        self.initial['version'] = version.pk
                        print(f"Set version initial to: {version}")
                        
                        # Set up hypothesis field - show hypotheses for the version
                        self.fields['hypothesis'].queryset = Hypothesis.objects.filter(version=version)
                        self.fields['hypothesis'].initial = hypothesis
                        self.initial['hypothesis'] = hypothesis.pk
                        print(f"Set hypothesis initial to: {hypothesis}")
                        
                        # Set up experiment field - show experiments for the hypothesis
                        self.fields['experiment'].queryset = Experiment.objects.filter(hypothesis=hypothesis)
                        print("Successfully set up edit form")
                        return
            except Exception as e:
                print(f"Error setting up edit form for Execution {self.instance.pk}: {e}")
        
        # Default setup for new execution or when relationships are missing
        print("Setting up default form (new execution or missing relationships)")
        #self.fields['customer'].queryset = Customer.objects.all()
        self.fields['sut'].queryset = Sut.objects.none()
        self.fields['version'].queryset = Version.objects.none()
        self.fields['hypothesis'].queryset = Hypothesis.objects.none()
        # For new executions, show all experiments to allow selection
        self.fields['experiment'].queryset = Experiment.objects.all()

    def clean(self):
        cleaned_data = super().clean()
        
        # Validate that experiment is selected
        experiment = cleaned_data.get('experiment')
        if not experiment:
            raise forms.ValidationError("Please select an experiment for this execution.")
        
        # Clean dynamic fields - ensure they are None if empty
        for field_name in ['customer', 'sut', 'version', 'hypothesis', 'script']:
            if field_name in cleaned_data and not cleaned_data[field_name]:
                cleaned_data[field_name] = None
        
        # Remove custom fields that are not part of the model
        # These fields are only used for dynamic filtering in the UI
        cleaned_data.pop('customer', None)
        cleaned_data.pop('sut', None)
        cleaned_data.pop('version', None)
        cleaned_data.pop('hypothesis', None)
        cleaned_data.pop('script', None)
        
        return cleaned_data

    def clean_customer(self):
        """Clean customer field - allow empty values."""
        customer = self.cleaned_data.get('customer')
        if customer == '':
            return None
        return customer

    def clean_sut(self):
        """Clean SUT field - allow empty values."""
        sut = self.cleaned_data.get('sut')
        if sut == '':
            return None
        return sut

    def clean_version(self):
        """Clean version field - allow empty values."""
        version = self.cleaned_data.get('version')
        if version == '':
            return None
        return version

    def clean_hypothesis(self):
        """Clean hypothesis field - allow empty values."""
        hypothesis = self.cleaned_data.get('hypothesis')
        if hypothesis == '':
            return None
        return hypothesis

    def clean_script(self):
        """Clean script field - allow empty values."""
        script = self.cleaned_data.get('script')
        if script == '':
            return None
        return script

    def full_clean(self):
        """Override to expand querysets before validation to prevent 'choice not available' errors."""
        # Expand querysets to include submitted values before validation
        if self.data:
            # Expand customer queryset if customer is submitted
            customer_id = self.data.get('customer')
            if customer_id and customer_id.strip() and hasattr(self.fields.get('customer'), 'queryset'):
                try:
                    customer = Customer.objects.get(pk=customer_id)
                    current_queryset = self.fields['customer'].queryset
                    if customer not in current_queryset:
                        self.fields['customer'].queryset = current_queryset | Customer.objects.filter(pk=customer_id)
                except (Customer.DoesNotExist, ValueError):
                    pass
            
            # Expand SUT queryset if SUT is submitted
            sut_id = self.data.get('sut')
            if sut_id and sut_id.strip() and hasattr(self.fields.get('sut'), 'queryset'):
                try:
                    sut = Sut.objects.get(pk=sut_id)
                    current_queryset = self.fields['sut'].queryset
                    if sut not in current_queryset:
                        self.fields['sut'].queryset = current_queryset | Sut.objects.filter(pk=sut_id)
                except (Sut.DoesNotExist, ValueError):
                    pass
            
            # Expand version queryset if version is submitted
            version_id = self.data.get('version')
            if version_id and version_id.strip() and hasattr(self.fields.get('version'), 'queryset'):
                try:
                    version = Version.objects.get(pk=version_id)
                    current_queryset = self.fields['version'].queryset
                    if version not in current_queryset:
                        self.fields['version'].queryset = current_queryset | Version.objects.filter(pk=version_id)
                except (Version.DoesNotExist, ValueError):
                    pass
            
            # Expand hypothesis queryset if hypothesis is submitted
            hypothesis_id = self.data.get('hypothesis')
            if hypothesis_id and hypothesis_id.strip() and hasattr(self.fields.get('hypothesis'), 'queryset'):
                try:
                    hypothesis = Hypothesis.objects.get(pk=hypothesis_id)
                    current_queryset = self.fields['hypothesis'].queryset
                    if hypothesis not in current_queryset:
                        self.fields['hypothesis'].queryset = current_queryset | Hypothesis.objects.filter(pk=hypothesis_id)
                except (Hypothesis.DoesNotExist, ValueError):
                    pass
            
            # Expand experiment queryset if experiment is submitted
            experiment_id = self.data.get('experiment')
            if experiment_id and experiment_id.strip() and hasattr(self.fields.get('experiment'), 'queryset'):
                try:
                    experiment = Experiment.objects.get(pk=experiment_id)
                    current_queryset = self.fields['experiment'].queryset
                    if experiment not in current_queryset:
                        self.fields['experiment'].queryset = current_queryset | Experiment.objects.filter(pk=experiment_id)
                except (Experiment.DoesNotExist, ValueError):
                    pass
            
            # Expand script queryset if script is submitted
            script_id = self.data.get('script')
            if script_id and script_id.strip() and hasattr(self.fields.get('script'), 'queryset'):
                try:
                    script = Script.objects.get(pk=script_id)
                    current_queryset = self.fields['script'].queryset
                    if script not in current_queryset:
                        self.fields['script'].queryset = current_queryset | Script.objects.filter(pk=script_id)
                except (Script.DoesNotExist, ValueError):
                    pass
        
        # Temporarily disable validation for dynamic fields to prevent choice errors
        original_required = {}
        for field_name in ['customer', 'sut', 'version', 'hypothesis', 'script']:
            if field_name in self.fields:
                original_required[field_name] = self.fields[field_name].required
                self.fields[field_name].required = False
        
        try:
            # Call parent full_clean after expanding querysets
            super().full_clean()
        finally:
            # Restore original required settings
            for field_name, required in original_required.items():
                if field_name in self.fields:
                    self.fields[field_name].required = required


class RecoveryForm(forms.ModelForm):
    """Enhanced form for Recovery with dynamic filtering."""
    customer = forms.ModelChoiceField(
        queryset=Customer.objects.all(),
        required=False,
        empty_label="Select a customer",
        help_text="Select a customer to filter available SUTs, versions, hypotheses, experiments, and executions",
        widget=UnfoldAdminSelectWidget
    )
    sut = forms.ModelChoiceField(
        queryset=Sut.objects.none(),
        required=False,
        empty_label="Select a SUT",
        help_text="Select a System Under Test (filtered by customer)",
        widget=UnfoldAdminSelectWidget
    )
    version = forms.ModelChoiceField(
        queryset=Version.objects.none(),
        required=False,
        empty_label="Select a version",
        help_text="Select a version (filtered by SUT)",
        widget=UnfoldAdminSelectWidget
    )
    hypothesis = forms.ModelChoiceField(
        queryset=Hypothesis.objects.none(),
        required=False,
        empty_label="Select a hypothesis",
        help_text="Select a hypothesis (filtered by version)",
        widget=UnfoldAdminSelectWidget
    )
    experiment = forms.ModelChoiceField(
        queryset=Experiment.objects.none(),
        required=False,
        empty_label="Select an experiment",
        help_text="Select an experiment (filtered by hypothesis)",
        widget=UnfoldAdminSelectWidget
    )
    script = forms.ModelChoiceField(
        queryset=Script.objects.all(),
        required=False,
        empty_label="Select a script",
        help_text="Select a script to configure parameters for this recovery process",
        widget=UnfoldAdminSelectWidget
    )
    
    class Meta:
        model = Recovery
        fields = '__all__'
        exclude = ['uuid', 'created_at', 'updated_at', 'created_by']

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        # Filter customer queryset based on user if not superuser
        if user and not user.is_superuser:
            self.fields['customer'].queryset = Customer.objects.filter(created_by=user)
        else:
            self.fields['customer'].queryset = Customer.objects.all()

        # Set up initial querysets
        if self.instance and self.instance.pk:
            # Editing existing recovery
            try:
                if hasattr(self.instance, 'execution') and self.instance.execution_id:
                    execution = self.instance.execution
                    print(f"Setting up edit form for Recovery {self.instance.pk}, execution: {execution}")
                    
                    if (execution.experiment and execution.experiment.hypothesis and 
                        execution.experiment.hypothesis.version and execution.experiment.hypothesis.version.sut and 
                        execution.experiment.hypothesis.version.sut.customer):
                        experiment = execution.experiment
                        hypothesis = experiment.hypothesis
                        version = hypothesis.version
                        
                        # Set up customer field - keep all customers available but set initial
                        #self.fields['customer'].queryset = Customer.objects.all()
                        self.fields['customer'].initial = version.sut.customer
                        self.initial['customer'] = version.sut.customer.pk
                        print(f"Set customer initial to: {version.sut.customer}")
                        
                        # Set up SUT field - show SUTs for the customer
                        self.fields['sut'].queryset = Sut.objects.filter(customer=version.sut.customer)
                        self.fields['sut'].initial = version.sut
                        self.initial['sut'] = version.sut.pk
                        print(f"Set SUT initial to: {version.sut}")
                        
                        # Set up version field - show versions for the SUT
                        self.fields['version'].queryset = Version.objects.filter(sut=version.sut)
                        self.fields['version'].initial = version
                        self.initial['version'] = version.pk
                        print(f"Set version initial to: {version}")
                        
                        # Set up hypothesis field - show hypotheses for the version
                        self.fields['hypothesis'].queryset = Hypothesis.objects.filter(version=version)
                        self.fields['hypothesis'].initial = hypothesis
                        self.initial['hypothesis'] = hypothesis.pk
                        print(f"Set hypothesis initial to: {hypothesis}")
                        
                        # Set up experiment field - show experiments for the hypothesis
                        self.fields['experiment'].queryset = Experiment.objects.filter(hypothesis=hypothesis)
                        self.fields['experiment'].initial = experiment
                        self.initial['experiment'] = experiment.pk
                        print(f"Set experiment initial to: {experiment}")
                        
                        # Set up execution field - show executions for the experiment
                        self.fields['execution'].queryset = Execution.objects.filter(experiment=experiment)
                        print("Successfully set up edit form")
                        return
            except Exception as e:
                print(f"Error setting up edit form for Recovery {self.instance.pk}: {e}")
        
        # Default setup for new recovery or when relationships are missing
        print("Setting up default form (new recovery or missing relationships)")
        #self.fields['customer'].queryset = Customer.objects.all()
        self.fields['sut'].queryset = Sut.objects.none()
        self.fields['version'].queryset = Version.objects.none()
        self.fields['hypothesis'].queryset = Hypothesis.objects.none()
        self.fields['experiment'].queryset = Experiment.objects.none()
        # For new recoveries, show all executions to allow selection
        self.fields['execution'].queryset = Execution.objects.all()

    def clean(self):
        cleaned_data = super().clean()
        
        # Validate that execution is selected
        execution = cleaned_data.get('execution')
        if not execution:
            raise forms.ValidationError("Please select an execution for this recovery.")
        
        # Clean dynamic fields - ensure they are None if empty
        for field_name in ['customer', 'sut', 'version', 'hypothesis', 'experiment', 'script']:
            if field_name in cleaned_data and not cleaned_data[field_name]:
                cleaned_data[field_name] = None
        
        # Remove custom fields that are not part of the model
        # These fields are only used for dynamic filtering in the UI
        cleaned_data.pop('customer', None)
        cleaned_data.pop('sut', None)
        cleaned_data.pop('version', None)
        cleaned_data.pop('hypothesis', None)
        cleaned_data.pop('experiment', None)
        cleaned_data.pop('script', None)
        
        return cleaned_data

    def clean_customer(self):
        """Clean customer field - allow empty values."""
        customer = self.cleaned_data.get('customer')
        if customer == '':
            return None
        return customer

    def clean_sut(self):
        """Clean SUT field - allow empty values."""
        sut = self.cleaned_data.get('sut')
        if sut == '':
            return None
        return sut

    def clean_version(self):
        """Clean version field - allow empty values."""
        version = self.cleaned_data.get('version')
        if version == '':
            return None
        return version

    def clean_hypothesis(self):
        """Clean hypothesis field - allow empty values."""
        hypothesis = self.cleaned_data.get('hypothesis')
        if hypothesis == '':
            return None
        return hypothesis

    def clean_experiment(self):
        """Clean experiment field - allow empty values."""
        experiment = self.cleaned_data.get('experiment')
        if experiment == '':
            return None
        return experiment

    def clean_script(self):
        """Clean script field - allow empty values."""
        script = self.cleaned_data.get('script')
        if script == '':
            return None
        return script

    def full_clean(self):
        """Override to expand querysets before validation to prevent 'choice not available' errors."""
        # Expand querysets to include submitted values before validation
        if self.data:
            # Expand customer queryset if customer is submitted
            customer_id = self.data.get('customer')
            if customer_id and customer_id.strip() and hasattr(self.fields.get('customer'), 'queryset'):
                try:
                    customer = Customer.objects.get(pk=customer_id)
                    current_queryset = self.fields['customer'].queryset
                    if customer not in current_queryset:
                        self.fields['customer'].queryset = current_queryset | Customer.objects.filter(pk=customer_id)
                except (Customer.DoesNotExist, ValueError):
                    pass
            
            # Expand SUT queryset if SUT is submitted
            sut_id = self.data.get('sut')
            if sut_id and sut_id.strip() and hasattr(self.fields.get('sut'), 'queryset'):
                try:
                    sut = Sut.objects.get(pk=sut_id)
                    current_queryset = self.fields['sut'].queryset
                    if sut not in current_queryset:
                        self.fields['sut'].queryset = current_queryset | Sut.objects.filter(pk=sut_id)
                except (Sut.DoesNotExist, ValueError):
                    pass
            
            # Expand version queryset if version is submitted
            version_id = self.data.get('version')
            if version_id and version_id.strip() and hasattr(self.fields.get('version'), 'queryset'):
                try:
                    version = Version.objects.get(pk=version_id)
                    current_queryset = self.fields['version'].queryset
                    if version not in current_queryset:
                        self.fields['version'].queryset = current_queryset | Version.objects.filter(pk=version_id)
                except (Version.DoesNotExist, ValueError):
                    pass
            
            # Expand hypothesis queryset if hypothesis is submitted
            hypothesis_id = self.data.get('hypothesis')
            if hypothesis_id and hypothesis_id.strip() and hasattr(self.fields.get('hypothesis'), 'queryset'):
                try:
                    hypothesis = Hypothesis.objects.get(pk=hypothesis_id)
                    current_queryset = self.fields['hypothesis'].queryset
                    if hypothesis not in current_queryset:
                        self.fields['hypothesis'].queryset = current_queryset | Hypothesis.objects.filter(pk=hypothesis_id)
                except (Hypothesis.DoesNotExist, ValueError):
                    pass
            
            # Expand experiment queryset if experiment is submitted
            experiment_id = self.data.get('experiment')
            if experiment_id and experiment_id.strip() and hasattr(self.fields.get('experiment'), 'queryset'):
                try:
                    experiment = Experiment.objects.get(pk=experiment_id)
                    current_queryset = self.fields['experiment'].queryset
                    if experiment not in current_queryset:
                        self.fields['experiment'].queryset = current_queryset | Experiment.objects.filter(pk=experiment_id)
                except (Experiment.DoesNotExist, ValueError):
                    pass
            
            # Expand execution queryset if execution is submitted
            execution_id = self.data.get('execution')
            if execution_id and execution_id.strip() and hasattr(self.fields.get('execution'), 'queryset'):
                try:
                    execution = Execution.objects.get(pk=execution_id)
                    current_queryset = self.fields['execution'].queryset
                    if execution not in current_queryset:
                        self.fields['execution'].queryset = current_queryset | Execution.objects.filter(pk=execution_id)
                except (Execution.DoesNotExist, ValueError):
                    pass
            
            # Expand script queryset if script is submitted
            script_id = self.data.get('script')
            if script_id and script_id.strip() and hasattr(self.fields.get('script'), 'queryset'):
                try:
                    script = Script.objects.get(pk=script_id)
                    current_queryset = self.fields['script'].queryset
                    if script not in current_queryset:
                        self.fields['script'].queryset = current_queryset | Script.objects.filter(pk=script_id)
                except (Script.DoesNotExist, ValueError):
                    pass
        
        # Temporarily disable validation for dynamic fields to prevent choice errors
        original_required = {}
        for field_name in ['customer', 'sut', 'version', 'hypothesis', 'experiment', 'script']:
            if field_name in self.fields:
                original_required[field_name] = self.fields[field_name].required
                self.fields[field_name].required = False
        
        try:
            # Call parent full_clean after expanding querysets
            super().full_clean()
        finally:
            # Restore original required settings
            for field_name, required in original_required.items():
                if field_name in self.fields:
                    self.fields[field_name].required = required


# AJAX View for Dynamic Data Loading
@method_decorator(csrf_exempt, name='dispatch')
class DynamicDataView(View):
    """AJAX view for loading dynamic data based on selections."""

    def get(self, request):
        data_type = request.GET.get('type')
        customer_id = request.GET.get('customer')
        sut_id = request.GET.get('sut')
        version_id = request.GET.get('version')
        hypothesis_id = request.GET.get('hypothesis')
        experiment_id = request.GET.get('experiment')

        response_data = {}

        if not request.user.is_superuser:
            # For non-superusers, apply ownership filtering
            if data_type == 'suts' and customer_id:
                # Get SUTs for a customer - customer must belong to user
                suts = Sut.objects.filter(
                    customer_id=customer_id,
                    customer__created_by=request.user,
                    created_by=request.user
                ).values('uuid', 'name')
                response_data['suts'] = list(suts)

            elif data_type == 'versions' and sut_id:
                # Get versions for a SUT - SUT must belong to user
                versions = Version.objects.filter(
                    sut_id=sut_id,
                    sut__created_by=request.user,
                    created_by=request.user
                ).values('uuid', 'name')
                response_data['versions'] = list(versions)

            elif data_type == 'elements' and version_id:
                # Get elements for a version - version must belong to user
                elements = Element.objects.filter(
                    version_id=version_id,
                    version__created_by=request.user,
                    created_by=request.user
                ).values('uuid', 'name', 'description')
                response_data['elements'] = list(elements)

            elif data_type == 'steady_states' and version_id:
                # Get steady states for a version - version must belong to user
                steady_states = SteadyState.objects.filter(
                    version_id=version_id,
                    version__created_by=request.user,
                    created_by=request.user
                ).values('uuid', 'metric_name', 'normal_behavior')
                response_data['steady_states'] = list(steady_states)

            elif data_type == 'hypotheses' and version_id:
                # Get hypotheses for a version - version must belong to user
                hypotheses = Hypothesis.objects.filter(
                    version_id=version_id,
                    version__created_by=request.user,
                    created_by=request.user
                ).values('uuid', 'name', 'description')
                response_data['hypotheses'] = list(hypotheses)

            elif data_type == 'parents' and version_id:
                # Get parent elements for a version (excluding self if editing)
                element_id = request.GET.get('element_id')
                parents = Element.objects.filter(
                    version_id=version_id,
                    version__created_by=request.user,
                    created_by=request.user
                )
                if element_id:
                    parents = parents.exclude(uuid=element_id)
                response_data['parents'] = list(parents.values('uuid', 'name'))

            elif data_type == 'experiments' and hypothesis_id:
                # Get experiments for a hypothesis - hypothesis must belong to user
                experiments = Experiment.objects.filter(
                    hypothesis_id=hypothesis_id,
                    hypothesis__created_by=request.user,
                    created_by=request.user
                ).values('uuid', 'name', 'description')
                response_data['experiments'] = list(experiments)

            elif data_type == 'executions' and experiment_id:
                # Get executions for an experiment - experiment must belong to user
                executions = Execution.objects.filter(
                    experiment_id=experiment_id,
                    experiment__created_by=request.user
                ).values('uuid', 'status', 'execution_date')
                response_data['executions'] = list(executions)

            elif data_type == 'script_parameters':
                # Get parameters for a specific script - script must belong to user
                script_id = request.GET.get('script')
                if script_id:
                    parameters = Parameter.objects.filter(
                        script_id=script_id,
                        script__created_by=request.user,
                        created_by=request.user
                    ).values(
                        'uuid', 'name', 'description', 'parameter_type', 'default_value', 'required', 'script_id'
                    )
                    response_data['parameters'] = list(parameters)
        else:
            # For superusers, show all data
            if data_type == 'suts' and customer_id:
                suts = Sut.objects.filter(customer_id=customer_id).values('uuid', 'name')
                response_data['suts'] = list(suts)

            elif data_type == 'versions' and sut_id:
                versions = Version.objects.filter(sut_id=sut_id).values('uuid', 'name')
                response_data['versions'] = list(versions)

            elif data_type == 'elements' and version_id:
                elements = Element.objects.filter(version_id=version_id).values('uuid', 'name', 'description')
                response_data['elements'] = list(elements)

            elif data_type == 'steady_states' and version_id:
                steady_states = SteadyState.objects.filter(version_id=version_id).values('uuid', 'metric_name', 'normal_behavior')
                response_data['steady_states'] = list(steady_states)

            elif data_type == 'hypotheses' and version_id:
                hypotheses = Hypothesis.objects.filter(version_id=version_id).values('uuid', 'name', 'description')
                response_data['hypotheses'] = list(hypotheses)

            elif data_type == 'parents' and version_id:
                element_id = request.GET.get('element_id')
                parents = Element.objects.filter(version_id=version_id)
                if element_id:
                    parents = parents.exclude(uuid=element_id)
                response_data['parents'] = list(parents.values('uuid', 'name'))

            elif data_type == 'experiments' and hypothesis_id:
                experiments = Experiment.objects.filter(hypothesis_id=hypothesis_id).values('uuid', 'name', 'description')
                response_data['experiments'] = list(experiments)

            elif data_type == 'executions' and experiment_id:
                executions = Execution.objects.filter(experiment_id=experiment_id).values('uuid', 'status', 'execution_date')
                response_data['executions'] = list(executions)

            elif data_type == 'script_parameters':
                script_id = request.GET.get('script')
                if script_id:
                    parameters = Parameter.objects.filter(script_id=script_id).values(
                        'uuid', 'name', 'description', 'parameter_type', 'default_value', 'required', 'script_id'
                    )
                    response_data['parameters'] = list(parameters)

        return JsonResponse(response_data)


#region Inlines for ForeignKey relationships
class SutInline(TabularInline):
    model = Sut
    extra = 1
    show_change_link = True
    tab = True

class VersionInline(TabularInline):
    model = Version
    extra = 1
    show_change_link = True
    tab = True

class ElementInline(TabularInline):
    model = Element
    extra = 1
    show_change_link = True
    tab = True
    exclude = ['created_by']
    
    def get_formset(self, request, obj=None, **kwargs):
        """Override to ensure proper parent queryset setup for inline forms."""
        formset = super().get_formset(request, obj, **kwargs)
        
        class ElementFormSetWithParentFiltering(formset):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                # Filter parent elements based on the current version
                if obj:  # obj is the Version instance
                    for form in self.forms:
                        if hasattr(form, 'fields') and 'parent' in form.fields:
                            # For new forms, set up parent filtering
                            if not form.instance.pk:  # New element
                                # Show only elements in the same version, excluding any future self-reference
                                form.fields['parent'].queryset = Element.objects.filter(version=obj)
                            else:
                                # For existing forms, ensure the current parent is available and exclude self
                                current_queryset = Element.objects.filter(version=obj).exclude(pk=form.instance.pk)
                                # If there's a current parent, make sure it's in the queryset
                                try:
                                    if form.instance.parent:
                                        if form.instance.parent not in current_queryset:
                                            current_queryset = current_queryset | Element.objects.filter(pk=form.instance.parent.pk)
                                except ObjectDoesNotExist:
                                    # Element has no parent, which is fine
                                    pass
                                form.fields['parent'].queryset = current_queryset
        
        return ElementFormSetWithParentFiltering

class SteadyStateInline(TabularInline):
    model = SteadyState
    extra = 1
    show_change_link = True
    tab = True
    exclude = ['created_by']

class HypothesisInlineForm(forms.ModelForm):
    """Simplified form for Hypothesis inline that hides customer and SUT fields."""
    
    class Meta:
        model = Hypothesis
        fields = ['name', 'description', 'justification']
        exclude = ['uuid', 'created_at', 'updated_at', 'elements', 'steady_states', 'version', 'created_by']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # This form is used in inline context where version is set automatically

    def save(self, commit=True):
        # The version will be set by the parent formset
        return super().save(commit=commit)

class HypothesisInline(TabularInline):
    model = Hypothesis
    form = HypothesisInlineForm
    extra = 1
    show_change_link = True
    tab = True
    
    def get_formset(self, request, obj=None, **kwargs):
        """Override to ensure proper version setup for inline forms."""
        formset = super().get_formset(request, obj, **kwargs)
        
        class HypothesisFormSetWithVersion(formset):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                # Set the version automatically from the parent version
                if obj:  # obj is the Version instance
                    for form in self.forms:
                        # Set the version instance for new forms
                        if not form.instance.pk:  # New hypothesis
                            form.instance.version = obj
                        # For existing forms, ensure they belong to the current version
                        else:
                            # Check if version exists before comparing
                            try:
                                current_version = form.instance.version
                                if current_version != obj:
                                    # This shouldn't happen, but just in case
                                    form.instance.version = obj
                            except ObjectDoesNotExist:
                                # Hypothesis has no version, set it
                                form.instance.version = obj
        
        return HypothesisFormSetWithVersion

class ElementChildInlineForm(forms.ModelForm):
    """Simplified form for Element child inline that hides customer field."""
    
    class Meta:
        model = Element
        fields = ['name', 'description', 'justification', 'dependencies', 'image']
        exclude = ['uuid', 'created_at', 'updated_at', 'version', 'parent', 'created_by']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # This form is used in inline context where version and parent are set automatically

    def save(self, commit=True):
        # The version and parent will be set by the parent formset
        return super().save(commit=commit)

class ElementChildInline(TabularInline):
    model = Element
    fk_name = 'parent'
    form = ElementChildInlineForm
    extra = 1
    show_change_link = True
    tab = True
    
    def get_formset(self, request, obj=None, **kwargs):
        """Override to ensure proper version and parent setup for inline forms."""
        formset = super().get_formset(request, obj, **kwargs)
        
        class ElementChildFormSetWithVersion(formset):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                # Set the version and parent automatically from the parent element
                if obj:  # obj is the parent Element instance
                    for form in self.forms:
                        # Set the version instance for new forms
                        if not form.instance.pk:  # New child element
                            form.instance.version = obj.version
                            form.instance.parent = obj
                        # For existing forms, ensure they belong to the current version and parent
                        else:
                            # Check if version exists before comparing
                            try:
                                current_version = form.instance.version
                                current_parent = form.instance.parent
                                if current_version != obj.version or current_parent != obj:
                                    # This shouldn't happen, but just in case
                                    form.instance.version = obj.version
                                    form.instance.parent = obj
                            except ObjectDoesNotExist:
                                # Element has no version, set it
                                form.instance.version = obj.version
                                form.instance.parent = obj
        
        return ElementChildFormSetWithVersion

class ParameterInline(TabularInline):
    model = Parameter
    extra = 1
    show_change_link = True
    tab = True


class ObservationForm(forms.ModelForm):
    class Meta:
        model = Observation
        fields = '__all__'
        exclude = ['created_by']
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Get the execution instance to filter steady states by experiment
        if 'instance' in kwargs and kwargs['instance'] and hasattr(kwargs['instance'], 'execution'):
            # Existing observation - filter by its execution's experiment
            execution = kwargs['instance'].execution
            if execution and execution.experiment:
                self.fields['steady_state'].queryset = execution.experiment.steady_states.all()
        elif hasattr(self, 'instance') and self.instance and hasattr(self.instance, 'execution'):
            # Alternative way to get execution
            execution = self.instance.execution
            if execution and execution.experiment:
                self.fields['steady_state'].queryset = execution.experiment.steady_states.all()
        else:
            # Try to get execution from parent form data or initial data
            execution_id = None
            if 'initial' in kwargs and 'execution' in kwargs['initial']:
                execution_id = kwargs['initial']['execution']
            elif hasattr(self, 'instance') and self.instance.pk is None:
                # New observation - try to get from request or context
                # For now, show all steady states for new observations
                self.fields['steady_state'].queryset = SteadyState.objects.all()
            
            if execution_id:
                try:
                    execution = Execution.objects.get(pk=execution_id)
                    if execution.experiment:
                        self.fields['steady_state'].queryset = execution.experiment.steady_states.all()
                except Execution.DoesNotExist:
                    pass


class ObservationInline(TabularInline):
    model = Observation
    form = ObservationForm
    extra = 1
    show_change_link = True
    tab = True
    fields = ('steady_state', 'observed_value', 'observation_date')
    readonly_fields = []
    
    def get_extra(self, request, obj=None, **kwargs):
        """Return the number of extra forms to display."""
        if obj:  # If editing existing object
            return 1
        return 2  # If creating new object
    
    def get_formset(self, request, obj=None, **kwargs):
        """Override to pass execution context to forms."""
        formset = super().get_formset(request, obj, **kwargs)
        
        class ObservationFormSetWithExecution(formset):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                # Pass the execution (obj) to each form
                if obj:  # obj is the Execution instance
                    for form in self.forms:
                        if hasattr(form, 'fields') and 'steady_state' in form.fields:
                            if obj.experiment:
                                form.fields['steady_state'].queryset = obj.experiment.steady_states.all()
                            else:
                                form.fields['steady_state'].queryset = SteadyState.objects.none()
        
        return ObservationFormSetWithExecution
    

class EvaluationInline(TabularInline):
    model = Evaluation
    extra = 1
    show_change_link = True
    tab = True
    exclude = ['created_by']

class RecoveryInline(TabularInline):
    model = Recovery
    extra = 0
    max_num = 1
    can_delete = True
    show_change_link = True
    tab = True
    exclude = ['created_by']

class ExperimentScriptParameterInline(TabularInline):
    model = ExperimentScriptParameter
    extra = 1
    show_change_link = True
    tab = True
    exclude = ['created_by']

class RecoveryScriptParameterInline(TabularInline):
    model = RecoveryScriptParameter
    extra = 1
    show_change_link = True
    tab = True
    exclude = ['created_by']

class SteadyStateScriptParameterInline(TabularInline):
    model = SteadyStateScriptParameter
    form = SteadyStateScriptParameterInlineForm
    extra = 1
    show_change_link = True
    tab = True
    fields = ('script', 'parameter', 'parameter_value')

@admin.register(Customer)
class CustomerAdmin(UserFilteredAdminMixin, CommentAdminMixin, ModelAdmin):
    list_display = ['name', 'description_short', 'comment_count']
    list_display_links = ["name"]
    search_fields = ['name', 'description']
    inlines = [SutInline]

    def description_short(self, obj):
        if obj.description:
            return obj.description[:100] + '...' if len(obj.description) > 100 else obj.description
        return '-'
    description_short.short_description = 'Description'

    
    @display(description="Comments")
    def comment_count(self, obj):
        count = Comment.objects.filter(
            content_type__model=self.model._meta.model_name,
            object_id=obj.uuid
        ).count()
        if count > 0:
            return str(count)+' comments'
        return '0 comments'


@admin.register(Sut)
class SutAdmin(UserFilteredAdminMixin, CommentAdminMixin, ModelAdmin):
    list_display = ('name', 'customer', 'description_short', 'comment_count')
    search_fields = ['name', 'description']
    list_filter = ('customer',)
    inlines = [VersionInline]

    def description_short(self, obj):
        if obj.description:
            return obj.description[:100] + '...' if len(obj.description) > 100 else obj.description
        return '-'
    description_short.short_description = 'Description'

    
    @display(description="Comments")
    def comment_count(self, obj):
        count = Comment.objects.filter(
            content_type__model=self.model._meta.model_name,
            object_id=obj.uuid
        ).count()
        if count > 0:
            return str(count)+' comments'
        return '0 comments'

@admin.register(Version)
class VersionAdmin(UserFilteredAdminMixin, CommentAdminMixin, ModelAdmin):
    form = VersionForm

    def get_form(self, request, obj=None, **kwargs):
        """Pass the current user to the form for customer filtering."""
        form = super().get_form(request, obj, **kwargs)
        # Create a new form class that passes the user
        class FormWithUser(form):
            def __init__(self, *args, **kwargs_inner):
                kwargs_inner['user'] = request.user
                super().__init__(*args, **kwargs_inner)
        return FormWithUser
    list_display = ('name', 'report_url', 'sut', 'description_short', 'duplicate_link', 'comment_count')
    list_filter = ('sut__customer', 'sut')
    search_fields = ['name', 'description']
    inlines = [ElementInline, SteadyStateInline, HypothesisInline]
    actions = ['duplicate_version']
    readonly_fields = ('uuid', 'created_at', 'updated_at', 'architecture_preview')
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('customer', 'sut', 'name', 'description', 'notes', 'architecture', 'architecture_preview'),
            'description': 'Basic information and relationships - select customer to filter available SUTs',
            'classes': ('tab',)
        }),
        ('System Information', {
            'fields': ('uuid', 'created_at', 'updated_at'),
            'classes': ('tab',)
        })
    )

    
    @display(description="Comments")
    def comment_count(self, obj):
        count = Comment.objects.filter(
            content_type__model=self.model._meta.model_name,
            object_id=obj.uuid
        ).count()
        if count > 0:
            return str(count)+' comments'
        return '0 comments'

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('dynamic-data/', self.admin_site.admin_view(DynamicDataView.as_view()), name='dynamic-data'),
            path(
                '<uuid:version_uuid>/duplicate/',
                self.admin_site.admin_view(self.duplicate_version_view),
                name='duplicate-version',
            ),
        ]
        return custom_urls + urls

    class Media:
        js = ('js/dynamic_admin.js',)

    def duplicate_link(self, obj):
        url = f"/admin/chaos/version/{obj.uuid}/duplicate/"
        return format_html('<a href="{}">Duplicate</a>', url)

    duplicate_link.short_description = "Duplicate"
    duplicate_link.allow_tags = True

    def description_short(self, obj):
        if obj.description:
            return obj.description[:100] + '...' if len(obj.description) > 100 else obj.description
        return '-'
    description_short.short_description = 'Description'

    def architecture_preview(self, obj):
        if obj.architecture:
            file_name = obj.architecture.name.lower()
            if any(file_name.endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.svg']):
                return format_html(
                    '<div style="display: flex; flex-direction: column; align-items: center;">'
                    '<img src="{}" style="max-width: 500px; max-height: 500px; border: 1px solid #ddd; margin-bottom: 5px;" />'
                    '<a href="{}" target="_blank" style="font-size: 12px; color: #007bff;">View Full Size</a>'
                    '</div>',
                    obj.architecture.url, obj.architecture.url
                )
            else:
                return format_html('<a href="{}" target="_blank">View Architecture</a>', obj.architecture.url)
        return '-'
    architecture_preview.short_description = 'Architecture Preview'


    def report_url(self, obj):
        url = reverse('version_report', args=[obj.uuid])
        return format_html('<a href="{}" target="_blank">Report</a>', url)

    report_url.short_description = "Report"
    report_url.allow_tags = True

    def duplicate_version_view(self, request, version_uuid):
        try:
            original = Version.objects.get(uuid=version_uuid)
            new_version = Version.objects.get(pk=original.pk)
            new_version.pk = None
            new_version.uuid = uuid7()
            new_version.name = f"{original.name} (copy)"

            # Copy architecture file if it exists
            if original.architecture:
                original.architecture.open()
                new_version.architecture.save(
                    f"copy_{os.path.basename(original.architecture.name)}",
                    ContentFile(original.architecture.read())
                )
            new_version.save()

            element_map = {}
            steady_state_map = {}

            for elem in original.elements.all():
                orig_elem_file = elem.image.read() if elem.image else None

                new_elem = Element.objects.get(pk=elem.pk)
                new_elem.pk = None
                new_elem.uuid = uuid7()
                new_elem.version = new_version
                new_elem.parent = None
                new_elem.save()

                if elem.image and orig_elem_file:
                    new_elem.image.save(
                        f"copy_{os.path.basename(elem.image.name)}",
                        ContentFile(orig_elem_file)
                    )

                element_map[elem.pk] = new_elem

            for elem in original.elements.all():
                if elem.parent_id:
                    new_elem = element_map[elem.pk]
                    new_elem.parent = element_map.get(elem.parent_id)
                    new_elem.save()

            for ss in original.steady_states.all():
                new_ss = SteadyState.objects.get(pk=ss.pk)
                new_ss.pk = None
                new_ss.uuid = uuid7()
                new_ss.version = new_version
                new_ss.save()

                steady_state_map[ss.pk] = new_ss

                for param in ss.steadystatescriptparameters.all():
                    SteadyStateScriptParameter.objects.create(
                        steady_state=new_ss,
                        script=param.script,
                        parameter=param.parameter,
                        parameter_value=param.parameter_value
                    )

            for hypo in original.hypotheses.all():
                new_hypo = Hypothesis.objects.get(pk=hypo.pk)
                new_hypo.pk = None
                new_hypo.uuid = uuid7()
                new_hypo.version = new_version
                new_hypo.save()

                # Set hypothesis relationships to elements and steady states
                new_hypo.elements.set([element_map[el.pk] for el in hypo.elements.all()])
                new_hypo.steady_states.set([steady_state_map[ss.pk] for ss in hypo.steady_states.all()])

                for exp in hypo.experiments.all():
                    new_exp = Experiment.objects.get(pk=exp.pk)
                    new_exp.pk = None
                    new_exp.uuid = uuid7()
                    new_exp.hypothesis = new_hypo
                    new_exp.save()

                    new_exp.elements.set([element_map[el.pk] for el in exp.elements.all()])
                    new_exp.steady_states.set([steady_state_map[ss.pk] for ss in exp.steady_states.all()])

                    # Duplicate experiment script parameters
                    for param in exp.experimentscriptparameters.all():
                        ExperimentScriptParameter.objects.create(
                            experiment=new_exp,
                            script=param.script,
                            parameter=param.parameter,
                            parameter_value=param.parameter_value
                        )

            self.message_user(request, "Version duplicated successfully.", level=messages.SUCCESS)
        except Exception as e:
            self.message_user(request, f"Error duplicating version: {e}", level=messages.ERROR)

        return redirect(request.META.get('HTTP_REFERER', '/admin/'))

    def duplicate_version(self, request, queryset):
        for original in queryset:
            # Duplicate Version
            new_version = Version.objects.get(pk=original.pk)
            new_version.pk = None
            new_version.uuid = uuid7()
            new_version.name = f"{original.name} (copy)"

            # Copy architecture file if exists
            if original.architecture:
                original.architecture.open()
                new_version.architecture.save(
                    f"copy_{os.path.basename(original.architecture.name)}",
                    ContentFile(original.architecture.read())
                )

            new_version.save()

            # Map of old -> new elements and steady states
            element_map = {}
            steady_state_map = {}

            # Duplicate Elements
            for elem in original.elements.all():
                orig_elem_file = elem.image.read() if elem.image else None

                new_elem = Element.objects.get(pk=elem.pk)
                new_elem.pk = None
                new_elem.uuid = uuid7()
                new_elem.version = new_version
                new_elem.parent = None  # temporarily unset to avoid issues
                new_elem.save()

                if elem.image and orig_elem_file:
                    new_elem.image.save(
                        f"copy_{os.path.basename(elem.image.name)}",
                        ContentFile(orig_elem_file)
                    )

                element_map[elem.pk] = new_elem

            # Restore parent relationships
            for elem in original.elements.all():
                if elem.parent_id:
                    new_elem = element_map[elem.pk]
                    new_elem.parent = element_map.get(elem.parent_id)
                    new_elem.save()

            # Duplicate SteadyStates and Parameters
            for ss in original.steady_states.all():
                new_ss = SteadyState.objects.get(pk=ss.pk)
                new_ss.pk = None
                new_ss.uuid = uuid7()
                new_ss.version = new_version
                new_ss.save()

                steady_state_map[ss.pk] = new_ss

                for param in ss.steadystatescriptparameters.all():
                    SteadyStateScriptParameter.objects.create(
                        steady_state=new_ss,
                        script=param.script,
                        parameter=param.parameter,
                        parameter_value=param.parameter_value
                    )

            # Duplicate Hypotheses and Experiments
            for hypo in original.hypotheses.all():
                new_hypo = Hypothesis.objects.get(pk=hypo.pk)
                new_hypo.pk = None
                new_hypo.uuid = uuid7()
                new_hypo.version = new_version
                new_hypo.save()

                # Set hypothesis relationships to elements and steady states
                new_hypo.elements.set([element_map[el.pk] for el in hypo.elements.all()])
                new_hypo.steady_states.set([steady_state_map[ss.pk] for ss in hypo.steady_states.all()])

                for exp in hypo.experiments.all():
                    new_exp = Experiment.objects.get(pk=exp.pk)
                    new_exp.pk = None
                    new_exp.uuid = uuid7()
                    new_exp.hypothesis = new_hypo
                    new_exp.save()

                    new_exp.elements.set([element_map[el.pk] for el in exp.elements.all()])
                    new_exp.steady_states.set([steady_state_map[ss.pk] for ss in exp.steady_states.all()])

                    # Duplicate experiment script parameters
                    for param in exp.experimentscriptparameters.all():
                        ExperimentScriptParameter.objects.create(
                            experiment=new_exp,
                            script=param.script,
                            parameter=param.parameter,
                            parameter_value=param.parameter_value
                        )
        
        self.message_user(request, "Selected versions were duplicated successfully.")

    duplicate_version.short_description = "Duplicate selected versions"

@admin.register(Element)
class ElementAdmin(UserFilteredAdminMixin, CommentAdminMixin, ModelAdmin):
    form = ElementForm

    def get_form(self, request, obj=None, **kwargs):
        """Pass the current user to the form for customer filtering."""
        form = super().get_form(request, obj, **kwargs)
        # Create a new form class that passes the user
        class FormWithUser(form):
            def __init__(self, *args, **kwargs_inner):
                kwargs_inner['user'] = request.user
                super().__init__(*args, **kwargs_inner)
        return FormWithUser
    list_display = ('name', 'version', 'parent', 'description_short', 'comment_count')
    search_fields = ['name', 'description']
    list_filter = ('version__sut__customer', 'version__sut', 'version')
    inlines = [ElementChildInline]
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('customer', 'sut', 'version', 'parent', 'name', 'description', 'justification', 'dependencies', 'image'),
            'description': 'Basic information and relationships - select customer, SUT, and version to filter available options',
            'classes': ('tab',)
        }),
    )

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('dynamic-data/', self.admin_site.admin_view(DynamicDataView.as_view()), name='dynamic-data'),
        ]
        return custom_urls + urls

    class Media:
        js = ('js/dynamic_admin.js',)

    def description_short(self, obj):
        if obj.description:
            return obj.description[:100] + '...' if len(obj.description) > 100 else obj.description
        return '-'
    description_short.short_description = 'Description'
    
    @display(description="Comments")
    def comment_count(self, obj):
        count = Comment.objects.filter(
            content_type__model=self.model._meta.model_name,
            object_id=obj.uuid
        ).count()
        if count > 0:
            return str(count)+' comments'
        return '0 comments'

@admin.register(SteadyState)
class SteadyStateAdmin(UserFilteredAdminMixin, CommentAdminMixin, ModelAdmin):
    form = SteadyStateForm

    def get_form(self, request, obj=None, **kwargs):
        """Pass the current user to the form for customer filtering."""
        form = super().get_form(request, obj, **kwargs)
        # Create a new form class that passes the user
        class FormWithUser(form):
            def __init__(self, *args, **kwargs_inner):
                kwargs_inner['user'] = request.user
                super().__init__(*args, **kwargs_inner)
        return FormWithUser
    list_display = ('metric_name', 'version', 'normal_behavior', 'comment_count')
    search_fields = ['metric_name', 'normal_behavior']
    list_filter = ('version__sut__customer', 'version__sut', 'version')
    inlines = [SteadyStateScriptParameterInline]
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('customer', 'sut', 'version', 'metric_name', 'category', 'normal_behavior', 'deviation_indicators', 'justification'),
            'description': 'Basic information and relationships - select customer, SUT, and version to filter available options',
            'classes': ('tab',)
        }),
        ('Script Configuration', {
            'fields': ('script',),
            'description': 'Select a script to configure its parameters for this steady state',
            'classes': ('tab',)
        }),
    )

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('dynamic-data/', self.admin_site.admin_view(DynamicDataView.as_view()), name='dynamic-data'),
        ]
        return custom_urls + urls

    class Media:
        js = ('js/dynamic_admin.js',)
    
    @display(description="Comments")
    def comment_count(self, obj):
        count = Comment.objects.filter(
            content_type__model=self.model._meta.model_name,
            object_id=obj.uuid
        ).count()
        if count > 0:
            return str(count)+' comments'
        return '0 comments'

@admin.register(Hypothesis)
class HypothesisAdmin(UserFilteredAdminMixin, CommentAdminMixin, ModelAdmin):
    form = HypothesisForm

    def get_form(self, request, obj=None, **kwargs):
        """Pass the current user to the form for customer filtering."""
        form = super().get_form(request, obj, **kwargs)
        # Create a new form class that passes the user
        class FormWithUser(form):
            def __init__(self, *args, **kwargs_inner):
                kwargs_inner['user'] = request.user
                super().__init__(*args, **kwargs_inner)
        return FormWithUser
    list_display = ('name', 'version', 'description_short', 'comment_count')
    search_fields = ['name', 'description']
    list_filter = ('version__sut__customer', 'version__sut', 'version')
    # filter_horizontal = ('elements', 'steady_states')  # Hidden from interface

    fieldsets = (
        ('Basic Information', {
            'fields': ('customer', 'sut', 'version', 'name', 'description', 'justification'),
            'description': 'Basic information and relationships - select customer, SUT, and version to filter available options',
            'classes': ('tab',)
        }),
    )

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('dynamic-data/', self.admin_site.admin_view(DynamicDataView.as_view()), name='dynamic-data'),
        ]
        return custom_urls + urls

    class Media:
        js = ('js/dynamic_admin.js',)

    def description_short(self, obj):
        if obj.description:
            return obj.description[:100] + '...' if len(obj.description) > 100 else obj.description
        return '-'
    description_short.short_description = 'Description'

    
    @display(description="Comments")
    def comment_count(self, obj):
        count = Comment.objects.filter(
            content_type__model=self.model._meta.model_name,
            object_id=obj.uuid
        ).count()
        if count > 0:
            return str(count)+' comments'
        return '0 comments'

@admin.register(Tag)
class TagAdmin(SharedReadOnlyAdminMixin, UserFilteredAdminMixin, ModelAdmin):
    list_display = ('name', 'description_short', 'shared')
    search_fields = ['name', 'description', 'shared']

    def description_short(self, obj):
        if obj.description:
            return obj.description[:100] + '...' if len(obj.description) > 100 else obj.description
        return '-'
    description_short.short_description = 'Description'

@admin.register(Script)
class ScriptAdmin(SharedReadOnlyAdminMixin, UserFilteredAdminMixin, CommentAdminMixin, ModelAdmin):
    list_display = ('name', 'tags_string', 'comment_count',"shared")
    search_fields = ['name', 'shared']
    list_filter = ('tags',)
    filter_horizontal = ('tags',)
    inlines = [ParameterInline]
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'description', 'tags', 'shared'),
            'classes': ('tab',)
        }),
        ('Script Content', {
            'fields': ('code', 'script_file', 'script_git_link'),
            'description': 'Provide at least one of: inline code, script file, or git repository link',
            'classes': ('tab',)
        }),
    )

    @display(description="Tags")
    def tags_string(self, obj):
        """Return tags as a comma-separated string."""
        return ", ".join([tag.name for tag in obj.tags.all()]) or "-"
    
    @display(description="Comments")
    def comment_count(self, obj):
        count = Comment.objects.filter(
            content_type__model=self.model._meta.model_name,
            object_id=obj.uuid
        ).count()
        if count > 0:
            return str(count)+' comments'
        return '0 comments'


@admin.register(Tool)
class ToolAdmin(SharedReadOnlyAdminMixin, UserFilteredAdminMixin, CommentAdminMixin, ModelAdmin):
    list_display = ('name', 'tags_string', 'shared', 'comment_count')
    search_fields = ['name', 'shared']
    list_filter = ('tags',)
    filter_horizontal = ('tags',)
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'description', 'tags', 'shared'),
            'classes': ('tab',)
        }),
        ('Tool Content', {
            'fields': ('tool_file', 'tool_git_link'),
            'description': 'Provide at least one of: tool file or git repository link',
            'classes': ('tab',)
        }),
    )
    
    @display(description="Tags")
    def tags_string(self, obj):
        """Return tags as a comma-separated string."""
        return ", ".join([tag.name for tag in obj.tags.all()]) or "-"
    
    @display(description="Comments")
    def comment_count(self, obj):
        count = Comment.objects.filter(
            content_type__model=self.model._meta.model_name,
            object_id=obj.uuid
        ).count()
        if count > 0:
            return str(count)+' comments'
        return '0 comments'


@admin.register(Experiment)
class ExperimentAdmin(UserFilteredAdminMixin, CommentAdminMixin, ModelAdmin):
    form = ExperimentForm

    def get_form(self, request, obj=None, **kwargs):
        """Pass the current user to the form for customer filtering."""
        form = super().get_form(request, obj, **kwargs)
        # Create a new form class that passes the user
        class FormWithUser(form):
            def __init__(self, *args, **kwargs_inner):
                kwargs_inner['user'] = request.user
                super().__init__(*args, **kwargs_inner)
        return FormWithUser
    list_display = ('name', 'hypothesis', 'comment_count')
    list_filter = ('hypothesis__version__sut__customer', 'hypothesis__version__sut', 'hypothesis__version', 'hypothesis')
    search_fields = ['name']
    filter_vertical = ('elements', 'steady_states', 'scripts')
    inlines = [ExperimentScriptParameterInline]

    fieldsets = (
        ('Basic Information', {
            'fields': ('customer', 'sut', 'version', 'hypothesis', 'name', 'description', 'justification'),
            'description': 'Basic information and relationships - select customer, SUT, and version to filter available hypotheses',
            'classes': ('tab',)
        }),
        ('Relationships', {
            'fields': ('elements', 'steady_states', 'scripts'),
            'description': 'Elements and steady states will be filtered based on the selected version',
            'classes': ('tab',)
        }),
        ('Script Configuration', {
            'fields': ('script_for_parameters',),
            'description': 'Select a script to configure its parameters for this experiment',
            'classes': ('tab',)
        }),
    )

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('dynamic-data/', self.admin_site.admin_view(DynamicDataView.as_view()), name='dynamic-data'),
            path('load-data/', self.admin_site.admin_view(self.load_experiment_data), name='load_experiment_data')
        ]
        return custom_urls + urls

    class Media:
        js = ('js/dynamic_admin.js', 'js/experiment_admin.js')
    
    @display(description="Comments")
    def comment_count(self, obj):
        count = Comment.objects.filter(
            content_type__model=self.model._meta.model_name,
            object_id=obj.uuid
        ).count()
        if count > 0:
            return str(count)+' comments'
        return '0 comments'

    def load_experiment_data(self, request):
        hypothesis_id = request.GET.get('hypothesis')
        elements = []
        steady_states = []

        if hypothesis_id:
            try:
                hypothesis = Hypothesis.objects.get(pk=hypothesis_id)
                version = hypothesis.version

                # Use actual objects to get __str__()
                elements = [
                    {'uuid': str(element.uuid), 'name': str(element)}
                    for element in version.elements.all()
                ]

                steady_states = [
                    {'uuid': str(state.uuid), 'name': str(state)}
                    for state in version.steady_states.all()
                ]
            except Hypothesis.DoesNotExist:
                pass
            
        return JsonResponse({
            'elements': elements,
            'steady_states': steady_states,
        })

@admin.register(Execution)
class ExecutionAdmin(UserFilteredAdminMixin, CommentAdminMixin, ModelAdmin):
    form = ExecutionForm

    def get_form(self, request, obj=None, **kwargs):
        """Pass the current user to the form for customer filtering."""
        form = super().get_form(request, obj, **kwargs)
        # Create a new form class that passes the user
        class FormWithUser(form):
            def __init__(self, *args, **kwargs_inner):
                kwargs_inner['user'] = request.user
                super().__init__(*args, **kwargs_inner)
        return FormWithUser
    list_display = ('experiment', 'status', 'execution_date', 'comment_count')
    list_filter = ('status', 'experiment', 'experiment__hypothesis', 'experiment__hypothesis__version__sut', 'experiment__hypothesis__version', 'execution_date')
    readonly_fields = ('log_preview',)
    inlines = [ObservationInline, EvaluationInline, RecoveryInline]

    fieldsets = (
        ('Basic Information', {
            'fields': ('customer', 'sut', 'version', 'hypothesis', 'experiment', 'status', 'execution_date'),
            'classes': ('tab',)
        }),
        ('Execution Details', {
            'fields': ('started_at', 'completed_at', 'log', 'log_preview', 'error_message'),
            'classes': ('tab',)
        }),
        ('Script Configuration', {
            'fields': ('script',),
            'description': 'Select a script to view its parameters for execution configuration',
            'classes': ('tab',)
        }),
    )

    class Media:
        js = ('js/dynamic_admin.js',)

    def get_urls(self):
        urls = super().get_urls()
        my_urls = [
            path('dynamic-data/', self.admin_site.admin_view(DynamicDataView.as_view()), name='chaos_execution_dynamic_data'),
        ]
        return my_urls + urls

    @display(description="Comments")
    def comment_count(self, obj):
        count = Comment.objects.filter(
            content_type__model=self.model._meta.model_name,
            object_id=obj.uuid
        ).count()
        if count > 0:
            return str(count)+' comments'
        return '0 comments'

    def log_preview(self, obj):
        if obj.log:
            file_name = obj.log.name.lower()
            if any(file_name.endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.svg', '.gif', '.bmp']):
                return format_html(
                    '<div style="display: flex; flex-direction: column; align-items: center;">'
                    '<img src="{}" style="max-width: 500px; max-height: 500px; border: 1px solid #ddd; margin-bottom: 5px;" />'
                    '<a href="{}" target="_blank" style="font-size: 12px; color: #007bff;">View Full Size</a>'
                    '</div>',
                    obj.log.url, obj.log.url
                )
            else:
                return format_html('<a href="{}" target="_blank">Download Log</a>', obj.log.url)
        return '-'
    log_preview.short_description = 'Log Preview'

@admin.register(Recovery)
class RecoveryAdmin(UserFilteredAdminMixin, CommentAdminMixin, ModelAdmin):
    form = RecoveryForm

    def get_form(self, request, obj=None, **kwargs):
        """Pass the current user to the form for customer filtering."""
        form = super().get_form(request, obj, **kwargs)
        # Create a new form class that passes the user
        class FormWithUser(form):
            def __init__(self, *args, **kwargs_inner):
                kwargs_inner['user'] = request.user
                super().__init__(*args, **kwargs_inner)
        return FormWithUser
    list_display = ('execution', 'name', 'outcome', 'comment_count')
    list_filter = ('outcome', 'execution__experiment', 'execution__experiment__hypothesis', 'execution__experiment__hypothesis__version__sut', 'execution__experiment__hypothesis__version')
    inlines = [RecoveryScriptParameterInline]

    fieldsets = (
        ('Basic Information', {
            'fields': ('customer', 'sut', 'version', 'hypothesis', 'experiment', 'execution', 'name', 'outcome'),
            'classes': ('tab',)
        }),
        ('Recovery Details', {
            'fields': ('recovery_process', 'notes', 'recovery_date'),
            'classes': ('tab',)
        }),
        ('Script Configuration', {
            'fields': ('script',),
            'description': 'Select a script to configure its parameters for this recovery process',
            'classes': ('tab',)
        }),
    )

    class Media:
        js = ('js/dynamic_admin.js',)

    def get_urls(self):
        urls = super().get_urls()
        my_urls = [
            path('dynamic-data/', self.admin_site.admin_view(DynamicDataView.as_view()), name='chaos_recovery_dynamic_data'),
        ]
        return my_urls + urls
    
    @display(description="Comments")
    def comment_count(self, obj):
        count = Comment.objects.filter(
            content_type__model=self.model._meta.model_name,
            object_id=obj.uuid
        ).count()
        if count > 0:
            return str(count)+' comments'
        return '0 comments'


#@admin.register(SteadyStateScriptParameter)
class SteadyStateScriptParameterAdmin(UserFilteredAdminMixin, ModelAdmin):
    list_display = ('steady_state', 'script', 'parameter', 'parameter_value_short')
    list_filter = ('steady_state__version__sut__customer', 'steady_state__version__sut', 'steady_state__version', 'script', 'script__tags')
    search_fields = ('steady_state__metric_name', 'script__name', 'parameter__name', 'parameter_value')

    fieldsets = (
        ('Configuration', {
            'fields': ('steady_state', 'script', 'parameter', 'parameter_value'),
            'description': 'Configure script parameters for this steady state',
            'classes': ('tab',)
        }),
    )

    def parameter_value_short(self, obj):
        if obj.parameter_value:
            return obj.parameter_value[:50] + '...' if len(obj.parameter_value) > 50 else obj.parameter_value
        return '-'
    parameter_value_short.short_description = 'Parameter Value'

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Filter parameters based on selected script."""
        if db_field.name == "parameter":
            # This will be enhanced with JavaScript for dynamic filtering
            kwargs["queryset"] = Parameter.objects.select_related('script')
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


#@admin.register(RecoveryScriptParameter)
class RecoveryScriptParameterAdmin(UserFilteredAdminMixin, ModelAdmin):
    list_display = ('recovery', 'script', 'parameter', 'parameter_value_short')
    list_filter = ('recovery__execution__experiment__hypothesis__version__sut__customer', 'script', 'script__tags')
    search_fields = ('recovery__name', 'script__name', 'parameter__name', 'parameter_value')

    fieldsets = (
        ('Configuration', {
            'fields': ('recovery', 'script', 'parameter', 'parameter_value'),
            'description': 'Configure script parameters for this recovery process',
            'classes': ('tab',)
        }),
    )

    def parameter_value_short(self, obj):
        if obj.parameter_value:
            return obj.parameter_value[:50] + '...' if len(obj.parameter_value) > 50 else obj.parameter_value
        return '-'
    parameter_value_short.short_description = 'Parameter Value'

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Filter parameters based on selected script."""
        if db_field.name == "parameter":
            kwargs["queryset"] = Parameter.objects.select_related('script')
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


#@admin.register(ExperimentScriptParameter)
class ExperimentScriptParameterAdmin(UserFilteredAdminMixin, ModelAdmin):
    list_display = ('experiment', 'script', 'parameter', 'parameter_value_short')
    list_filter = ('experiment__hypothesis__version__sut__customer', 'experiment__hypothesis__version__sut', 'experiment__hypothesis__version', 'script', 'script__tags')
    search_fields = ('experiment__name', 'script__name', 'parameter__name', 'parameter_value')

    fieldsets = (
        ('Configuration', {
            'fields': ('experiment', 'script', 'parameter', 'parameter_value'),
            'description': 'Configure script parameters for this experiment',
            'classes': ('tab',)
        }),
    )

    def parameter_value_short(self, obj):
        if obj.parameter_value:
            return obj.parameter_value[:50] + '...' if len(obj.parameter_value) > 50 else obj.parameter_value
        return '-'
    parameter_value_short.short_description = 'Parameter Value'

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Filter parameters based on selected script."""
        if db_field.name == "parameter":
            kwargs["queryset"] = Parameter.objects.select_related('script')
        return super().formfield_for_foreignkey(db_field, request, **kwargs)