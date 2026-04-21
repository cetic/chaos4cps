import ast

def smart_convert(value):
    value = value.strip()

    # Check for boolean
    if value.lower() == "true":
        return True
    elif value.lower() == "false":
        return False

    # Try integer
    try:
        return int(value)
    except ValueError:
        pass

    # Try float
    try:
        return float(value)
    except ValueError:
        pass

    # Try list, dict, tuple, etc. using ast.literal_eval
    try:
        parsed = ast.literal_eval(value)
        return parsed
    except (ValueError, SyntaxError):
        pass

    # Default: return as string
    return value
