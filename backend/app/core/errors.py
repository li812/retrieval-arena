class DuplicateNameError(Exception):
    """A UNIQUE name/label already exists. The message is the database's own (the legacy API returned it as-is)."""
