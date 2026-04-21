from django import template

register = template.Library()

@register.filter
def length_is(value, arg):
    """Returns True if the length of value is equal to arg."""
    try:
        return len(value) == int(arg)
    except (ValueError, TypeError):
        return False

@register.filter
def count_completed(execution):
    if not execution:
        return 0
    if execution.status == "completed":
        return 1
    return 0

@register.filter
def count_by_status(data, status):
    return data.filter(status=status).count()

@register.filter
def count_by_outcome(data, outcome):
    return data.filter(outcome=outcome).count()