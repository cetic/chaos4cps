from django.db import models
from django.core.validators import FileExtensionValidator
from django.utils import timezone
from uuid6 import uuid7
from django.contrib.auth import get_user_model
import re
import os

User = get_user_model()


def clean_string(input_string, special_chars="-_."):
    """
    Clean file name by keeping only alphanumeric characters and specified special characters.
    
    Args:
        input_string (str): The string to clean
        special_chars (str): Special characters to allow in the cleaned string
        
    Returns:
        str: Cleaned string with only allowed characters
    """
    if not input_string:
        return ""
    
    # Create a regex pattern that includes alphanumeric and allowed special characters
    pattern = f"[a-zA-Z0-9{re.escape(special_chars)}]+"
    
    # Find all matches of the pattern in the input string and join them
    cleaned_string = ''.join(re.findall(pattern, input_string))
    
    return cleaned_string


def path_architecture(instance, filename):
    """Generate upload path for architecture files."""
    head, tail = os.path.split(filename)
    cleaned_filename = clean_string(tail)
    return os.path.join('architectures', cleaned_filename)


def path_script(instance, filename):
    """Generate upload path for script files."""
    head, tail = os.path.split(filename)
    cleaned_filename = clean_string(tail)
    return os.path.join('scripts', cleaned_filename)


def path_element(instance, filename):
    """Generate upload path for element files."""
    head, tail = os.path.split(filename)
    cleaned_filename = clean_string(tail)
    return os.path.join('elements', cleaned_filename)


def path_log(instance, filename):
    """Generate upload path for log files."""
    head, tail = os.path.split(filename)
    cleaned_filename = clean_string(tail)
    return os.path.join('logs', cleaned_filename)


def path_tool(instance, filename):
    """Generate upload path for tool files."""
    head, tail = os.path.split(filename)
    cleaned_filename = clean_string(tail)
    return os.path.join('tools', cleaned_filename)


class TimeStampedModel(models.Model):
    """Abstract base class that provides created_at and updated_at fields."""
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        abstract = True


class Customer(TimeStampedModel):
    """Represents a customer who owns systems under test."""
    uuid = models.UUIDField(primary_key=True, editable=False, default=uuid7)
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='customers',
        null=True,
        blank=True,
        help_text="User who created this customer"
    )

    class Meta:
        ordering = ['name']
        verbose_name = "Customer"
        verbose_name_plural = "Customers"

    def __str__(self):
        return self.name


class Sut(TimeStampedModel):
    """System Under Test - represents a system that will be tested."""
    uuid = models.UUIDField(primary_key=True, editable=False, default=uuid7)
    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name="suts"
    )
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='suts',
        null=True,
        blank=True,
        help_text="User who created this system under test"
    )

    class Meta:
        ordering = ['customer__name', 'name']
        verbose_name = "System Under Test"
        verbose_name_plural = "Systems Under Test"
        unique_together = ['customer', 'name']

    def __str__(self):
        return f"{self.customer.name} - {self.name}"


class Version(TimeStampedModel):
    """Represents a specific version of a System Under Test."""
    uuid = models.UUIDField(primary_key=True, editable=False, default=uuid7)
    sut = models.ForeignKey(
        Sut,
        on_delete=models.CASCADE,
        related_name='versions'
    )
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    notes = models.TextField(
        blank=True,
        null=True,
        verbose_name="Additional Information",
        help_text="Any additional information about the version (useful for the agent)"
    )
    architecture = models.FileField(
        upload_to=path_architecture,
        null=True,
        blank=True,
        validators=[FileExtensionValidator(allowed_extensions=['pdf', 'png', 'jpg', 'jpeg', 'svg'])]
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='versions',
        null=True,
        blank=True,
        help_text="User who created this version"
    )

    class Meta:
        ordering = ['sut__name', 'name']
        verbose_name = "Version"
        verbose_name_plural = "Versions"
        unique_together = ['sut', 'name']

    def __str__(self):
        return f"{self.sut.name} - {self.name}"


class Element(TimeStampedModel):
    """Represents a component or element within a system version."""
    uuid = models.UUIDField(primary_key=True, editable=False, default=uuid7)
    version = models.ForeignKey(
        Version,
        on_delete=models.CASCADE,
        related_name='elements'
    )
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        related_name='children',
        null=True,
        blank=True,
        verbose_name="Parent Element"
    )
    dependencies = models.TextField(
        blank=True,
        null=True,
        help_text="Dependencies of this element on other elements"
    )
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    justification = models.TextField(
        blank=True,
        null=True,
        verbose_name="Justification (from Agent)",
        help_text="Justification for the element's existence in the system, provided by the agent"
    )
    image = models.FileField(
        upload_to=path_element,
        null=True,
        blank=True,
        validators=[FileExtensionValidator(allowed_extensions=['png', 'jpg', 'jpeg', 'svg'])]
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='elements',
        null=True,
        blank=True,
        help_text="User who created this element"
    )

    class Meta:
        ordering = ['version__sut__name', 'version__name', 'name']
        verbose_name = "Element"
        verbose_name_plural = "Elements"
        # Note: unique_together with nullable version field commented out to avoid admin issues
        # unique_together = ['version', 'name']

    def __str__(self):
        if hasattr(self, 'version') and self.version:
            return f"{self.version} - {self.name}"
        return self.name or "New Element"


class SteadyState(TimeStampedModel):
    """Represents a metric that indicates the steady state of a system."""
    uuid = models.UUIDField(primary_key=True, editable=False, default=uuid7)
    version = models.ForeignKey(
        Version,
        on_delete=models.CASCADE,
        related_name='steady_states'
    )
    metric_name = models.CharField(max_length=512)
    category = models.CharField(max_length=512, blank=True, null=True)
    normal_behavior = models.TextField(
        verbose_name="Normal Behavior Description",
        help_text="Description of the metric that indicates normal behavior of the system"
    )
    deviation_indicators = models.TextField(
        blank=True,
        null=True,
        help_text="Indicators of deviation from normal behavior"
    )
    justification = models.TextField(
        blank=True,
        null=True,
        verbose_name="Justification (from Agent)",
        help_text="Why this signal is crucial for determining system health, provided by the agent"
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='steady_states',
        null=True,
        blank=True,
        help_text="User who created this steady state"
    )

    class Meta:
        ordering = ['version__sut__name', 'version__name', 'metric_name']
        verbose_name = "Steady State"
        verbose_name_plural = "Steady States"
        unique_together = ['version', 'metric_name']

    def __str__(self):
        if self.normal_behavior:
            if len(self.normal_behavior) > 50:
                return f"{self.metric_name} - {self.normal_behavior[:50]}..."
            else:
                return f"{self.metric_name} - {self.normal_behavior}"
        else:
            return self.metric_name


class Tag(TimeStampedModel):
    """Represents tags that can be applied to scripts for categorization."""
    uuid = models.UUIDField(primary_key=True, editable=False, default=uuid7)
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='tags',
        null=True,
        blank=True,
        help_text="User who created this tag"
    )
    shared = models.BooleanField(default=False)

    class Meta:
        ordering = ['name']
        verbose_name = "Tag"
        verbose_name_plural = "Tags"

    def __str__(self):
        return self.name


class Script(TimeStampedModel):
    """Represents a script that can be used in experiments."""
    uuid = models.UUIDField(primary_key=True, editable=False, default=uuid7)
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(
        blank=True,
        null=True,
        help_text="Description of the script's purpose and how it should be used"
    )
    code = models.TextField(
        blank=True,
        null=True,
        verbose_name="Code",
        help_text="Inline code for the script"
    )
    script_file = models.FileField(
        upload_to=path_script,
        null=True,
        blank=True,
        validators=[FileExtensionValidator(allowed_extensions=['py', 'sh', 'js', 'rb', 'pl'])]
    )
    script_git_link = models.URLField(
        max_length=500,
        blank=True,
        null=True,
        verbose_name="Link", help_text="Link to the script's repository or other source"
    )
    tags = models.ManyToManyField(Tag, blank=True, related_name='scripts')
    shared = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='scripts',
        null=True,
        blank=True,
        help_text="User who created this script"
    )

    class Meta:
        ordering = ['name']
        verbose_name = "Script"
        verbose_name_plural = "Scripts"

    def __str__(self):
        return self.name

    def clean(self):
        """Validate that at least one of code, script_file, or script_git_link is provided."""
        from django.core.exceptions import ValidationError
        if not any([self.code, self.script_file, self.script_git_link]):
            raise ValidationError(
                "At least one of code, script file, or git link must be provided."
            )


class Tool(TimeStampedModel):
    """Represents a tool that can be used in experiments."""
    uuid = models.UUIDField(primary_key=True, editable=False, default=uuid7)
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(
        blank=True,
        null=True,
        help_text="Description of the tool's purpose and how it should be used"
    )
    tool_file = models.FileField(
        upload_to=path_tool,
        null=True,
        blank=True,
        validators=[FileExtensionValidator(allowed_extensions=['zip', 'tar', 'gz', 'bz2', 'xz', '7z', 'rar'])]
    )
    tool_git_link = models.URLField(
        max_length=500,
        blank=True,
        null=True,
        verbose_name="Link", help_text="Link to the tool's repository or other source"
    )
    tags = models.ManyToManyField(Tag, blank=True, related_name='tools')
    shared = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='tools',
        null=True,
        blank=True,
        help_text="User who created this tool"
    )

    class Meta:
        ordering = ['name']
        verbose_name = "Tool"
        verbose_name_plural = "Tools"

    def __str__(self):
        return self.name

    def clean(self):
        """Validate that at least one of tool_file or tool_git_link is provided."""
        from django.core.exceptions import ValidationError
        if not any([self.tool_file, self.tool_git_link]):
            raise ValidationError(
                "At least one of tool file or git link must be provided."
            )


class Parameter(TimeStampedModel):
    """Represents a parameter for a script."""
    uuid = models.UUIDField(primary_key=True, editable=False, default=uuid7)
    script = models.ForeignKey(
        Script,
        on_delete=models.CASCADE,
        related_name='parameters'
    )
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    parameter_type = models.CharField(
        max_length=20,
        choices=[
            ('string', 'String'),
            ('integer', 'Integer'),
            ('float', 'Float'),
            ('boolean', 'Boolean'),
            ('file', 'File'),
        ],
        default='string'
    )
    default_value = models.TextField(blank=True, null=True)
    required = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='parameters',
        null=True,
        blank=True,
        help_text="User who created this parameter"
    )

    class Meta:
        ordering = ['script__name', 'name']
        verbose_name = "Parameter"
        verbose_name_plural = "Parameters"
        unique_together = ['script', 'name']

    def __str__(self):
        return f"{self.script.name} - {self.name}"


class Hypothesis(TimeStampedModel):
    """Represents a hypothesis to be tested through experiments."""
    uuid = models.UUIDField(primary_key=True, editable=False, default=uuid7)
    version = models.ForeignKey(
        Version,
        on_delete=models.CASCADE,
        related_name='hypotheses'
    )
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    elements = models.ManyToManyField(Element, blank=True, related_name='hypotheses')
    steady_states = models.ManyToManyField(SteadyState, blank=True, related_name='hypotheses')
    justification = models.TextField(
        blank=True,
        null=True,
        verbose_name="Justification (from Agent)",
        help_text="Why this hypothesis is relevant for testing system robustness, provided by the agent"
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='hypotheses',
        null=True,
        blank=True,
        help_text="User who created this hypothesis"
    )

    class Meta:
        ordering = ['version__sut__name', 'version__name', 'name']
        verbose_name = "Hypothesis"
        verbose_name_plural = "Hypotheses"
        unique_together = ['version', 'name']

    def __str__(self):
        if hasattr(self, 'version') and self.version:
            return f"{self.version} - {self.name}"
        return self.name or "New Hypothesis"


class Experiment(TimeStampedModel):
    """Represents an experiment to test a hypothesis."""
    uuid = models.UUIDField(primary_key=True, editable=False, default=uuid7)
    hypothesis = models.ForeignKey(
        Hypothesis,
        on_delete=models.CASCADE,
        related_name='experiments'
    )
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    justification = models.TextField(
        blank=True,
        null=True,
        verbose_name="Justification (from Agent)",
        help_text="Why this experiment is relevant for testing the hypothesis, provided by the agent"
    )
    elements = models.ManyToManyField(Element, blank=True, related_name='experiments')
    steady_states = models.ManyToManyField(SteadyState, blank=True, related_name='experiments')
    scripts = models.ManyToManyField(Script, blank=True, related_name='experiments')
    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='experiments',
        null=True,
        blank=True,
        help_text="User who created this experiment"
    )

    class Meta:
        ordering = ['hypothesis__version__sut__name', 'hypothesis__version__name', 'hypothesis__name', 'name']
        verbose_name = "Experiment"
        verbose_name_plural = "Experiments"
        unique_together = ['hypothesis', 'name']

    def __str__(self):
        if hasattr(self, 'hypothesis') and self.hypothesis:
            return f"{self.hypothesis} - {self.name}"
        return self.name or "New Experiment"


class Execution(TimeStampedModel):
    """Represents the execution of an experiment."""
    STATUS_CHOICES = [
        ('completed', 'Completed'),
        ('not_completed', 'Not Completed'),
    ]

    uuid = models.UUIDField(primary_key=True, editable=False, default=uuid7)
    experiment = models.ForeignKey(
        Experiment,
        on_delete=models.CASCADE,
        related_name='executions'
    )
    execution_date = models.DateTimeField(default=timezone.now)
    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='executions',
        null=True,
        blank=True,
        help_text="User who created this execution"
    )
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='not_completed')
    log = models.FileField(
        upload_to=path_log, 
        null=True, 
        blank=True,
        #validators=[FileExtensionValidator(allowed_extensions=['log', 'txt'])]
    )
    error_message = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['-execution_date']
        verbose_name = "Execution"
        verbose_name_plural = "Executions"

    def __str__(self):
        return f"{self.experiment} - {self.status} ({self.execution_date.strftime('%Y-%m-%d %H:%M')})"

    @property
    def duration(self):
        """Calculate execution duration if both start and end times are available."""
        if self.started_at and self.completed_at:
            return self.completed_at - self.started_at
        return None


class Observation(TimeStampedModel):
    """Represents an observation made during an experiment execution."""
    uuid = models.UUIDField(primary_key=True, editable=False, default=uuid7)
    execution = models.ForeignKey(
        Execution,
        on_delete=models.CASCADE,
        related_name='observations'
    )
    steady_state = models.ForeignKey(
        SteadyState,
        on_delete=models.CASCADE,
        related_name='observations'
    )
    observed_value = models.TextField(
        verbose_name="Observation",
        help_text="Value observed for the steady state metric during the execution"
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='observations',
        null=True,
        blank=True,
        help_text="User who created this observation"
    )
    observation_date = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-observation_date']
        verbose_name = "Observation"
        verbose_name_plural = "Observations"

    def __str__(self):
        return f"{self.steady_state.metric_name}: {self.observed_value}"


class Evaluation(TimeStampedModel):
    """Represents the evaluation of an experiment execution."""
    STATUS_CHOICES = [
        ('pass', 'Pass'),
        ('fail', 'Fail'),
    ]

    uuid = models.UUIDField(primary_key=True, editable=False, default=uuid7)
    execution = models.OneToOneField(
        Execution,
        on_delete=models.CASCADE,
        related_name='evaluation'
    )
    notes = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='evaluations',
        null=True,
        blank=True,
        help_text="User who created this evaluation"
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='fail')
    recommendations = models.TextField(blank=True, null=True)
    evaluation_date = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-evaluation_date']
        verbose_name = "Evaluation"
        verbose_name_plural = "Evaluations"

    def __str__(self):
        return f"{self.execution.experiment} - {self.status}"


class Recovery(TimeStampedModel):
    """Represents the recovery process after an experiment execution."""
    OUTCOME_CHOICES = [
        ('pass', 'Pass'),
        ('fail', 'Fail'),
    ]

    uuid = models.UUIDField(primary_key=True, editable=False, default=uuid7)
    execution = models.OneToOneField(
        Execution,
        on_delete=models.CASCADE,
        related_name='recovery'
    )
    name = models.CharField(max_length=100)
    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='recoveries',
        null=True,
        blank=True,
        help_text="User who created this recovery"
    )
    recovery_process = models.TextField(
        blank=True, 
        null=True,
        help_text="Description of the recovery process performed"
    )
    outcome = models.CharField(max_length=10, choices=OUTCOME_CHOICES, default='fail')
    notes = models.TextField(blank=True, null=True)
    recovery_date = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-recovery_date']
        verbose_name = "Recovery"
        verbose_name_plural = "Recoveries"

    def __str__(self):
        return f"{self.execution.experiment} - {self.name} - {self.outcome}"


class SteadyStateScriptParameter(TimeStampedModel):
    """Represents a parameter value for a script used in a steady state."""
    uuid = models.UUIDField(primary_key=True, editable=False, default=uuid7)
    steady_state = models.ForeignKey(
        SteadyState,
        on_delete=models.CASCADE,
        related_name='steadystatescriptparameters'
    )
    script = models.ForeignKey(
        Script,
        on_delete=models.CASCADE,
        related_name='steadystatescriptparameters',
        help_text="The script being configured for this steady state"
    )
    parameter = models.ForeignKey(
        Parameter,
        on_delete=models.CASCADE,
        related_name='steadystatescriptparameters',
        help_text="The specific parameter of the script to configure"
    )
    parameter_value = models.TextField(
        verbose_name="Parameter Value",
        help_text="The value for this parameter when used with this steady state"
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='steady_state_script_parameters',
        null=True,
        blank=True,
        help_text="User who created this steady state script parameter"
    )

    class Meta:
        ordering = ['steady_state__metric_name', 'script__name', 'parameter__name']
        verbose_name = "Steady State Script Parameter"
        verbose_name_plural = "Steady State Script Parameters"
        unique_together = ['steady_state', 'script', 'parameter']

    def clean(self):
        """Validate that the parameter belongs to the specified script."""
        from django.core.exceptions import ValidationError
        if self.parameter and self.script and self.parameter.script != self.script:
            raise ValidationError(
                f"Parameter '{self.parameter.name}' does not belong to script '{self.script.name}'. "
                f"It belongs to script '{self.parameter.script.name}'."
            )

    def save(self, *args, **kwargs):
        """Override save to run validation."""
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.steady_state.metric_name} - {self.script.name}.{self.parameter.name}: {self.parameter_value}"


class RecoveryScriptParameter(TimeStampedModel):
    """Represents a parameter value for a script used in a recovery process."""
    uuid = models.UUIDField(primary_key=True, editable=False, default=uuid7)
    recovery = models.ForeignKey(
        Recovery,
        on_delete=models.CASCADE,
        related_name='recoveryscriptparameters'
    )
    script = models.ForeignKey(
        Script,
        on_delete=models.CASCADE,
        related_name='recoveryscriptparameters',
        help_text="The script being configured for this recovery process"
    )
    parameter = models.ForeignKey(
        Parameter,
        on_delete=models.CASCADE,
        related_name='recoveryscriptparameters',
        help_text="The specific parameter of the script to configure"
    )
    parameter_value = models.TextField(
        verbose_name="Parameter Value",
        help_text="The value for this parameter when used with this recovery process"
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='recovery_script_parameters',
        null=True,
        blank=True,
        help_text="User who created this recovery script parameter"
    )

    class Meta:
        ordering = ['recovery__name', 'script__name', 'parameter__name']
        verbose_name = "Recovery Script Parameter"
        verbose_name_plural = "Recovery Script Parameters"
        unique_together = ['recovery', 'script', 'parameter']

    def clean(self):
        """Validate that the parameter belongs to the specified script."""
        from django.core.exceptions import ValidationError
        if self.parameter and self.script and self.parameter.script != self.script:
            raise ValidationError(
                f"Parameter '{self.parameter.name}' does not belong to script '{self.script.name}'. "
                f"It belongs to script '{self.parameter.script.name}'."
            )

    def save(self, *args, **kwargs):
        """Override save to run validation."""
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.recovery.name} - {self.script.name}.{self.parameter.name}: {self.parameter_value}"


class ExperimentScriptParameter(TimeStampedModel):
    """Represents a parameter value for a script used in an experiment."""
    uuid = models.UUIDField(primary_key=True, editable=False, default=uuid7)
    experiment = models.ForeignKey(
        Experiment,
        on_delete=models.CASCADE,
        related_name='experimentscriptparameters'
    )
    script = models.ForeignKey(
        Script,
        on_delete=models.CASCADE,
        related_name='experimentscriptparameters',
        help_text="The script being configured for this experiment"
    )
    parameter = models.ForeignKey(
        Parameter,
        on_delete=models.CASCADE,
        related_name='experimentscriptparameters',
        help_text="The specific parameter of the script to configure"
    )
    parameter_value = models.TextField(
        verbose_name="Parameter Value",
        help_text="The value for this parameter when used with this experiment"
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='experiment_script_parameters',
        null=True,
        blank=True,
        help_text="User who created this experiment script parameter"
    )

    class Meta:
        ordering = ['experiment__name', 'script__name', 'parameter__name']
        verbose_name = "Experiment Script Parameter"
        verbose_name_plural = "Experiment Script Parameters"
        unique_together = ['experiment', 'script', 'parameter']

    def clean(self):
        """Validate that the parameter belongs to the specified script."""
        from django.core.exceptions import ValidationError
        if self.parameter and self.script and self.parameter.script != self.script:
            raise ValidationError(
                f"Parameter '{self.parameter.name}' does not belong to script '{self.script.name}'. "
                f"It belongs to script '{self.parameter.script.name}'."
            )

    def save(self, *args, **kwargs):
        """Override save to run validation."""
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.experiment.name} - {self.script.name}.{self.parameter.name}: {self.parameter_value}"