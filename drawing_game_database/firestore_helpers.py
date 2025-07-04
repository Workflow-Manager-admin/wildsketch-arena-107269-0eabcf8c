"""
Helper utilities for Firestore drawing game:
- Schema validation for testing/admin scripts.
- Useful field checks during data import.
"""

REQUIRED_DRAWING_FIELDS = [
    "prompt", "author_uid", "image_url", "timestamp",
    "guesses", "correct_guessers", "wrong_guessers"
]

REQUIRED_USER_FIELDS = [
    "username", "drawings_submitted", "total_guesses",
    "correct_guesses", "wrong_guesses"
]

# PUBLIC_INTERFACE
def validate_drawing_doc(doc: dict) -> bool:
    """Validate that a Firestore drawing document conforms to schema."""
    for field in REQUIRED_DRAWING_FIELDS:
        if field not in doc:
            raise ValueError(f"Field '{field}' missing in drawing doc")
    # Optional: type checks
    if not isinstance(doc["prompt"], str):
        raise ValueError("Field 'prompt' must be string")
    if not isinstance(doc["author_uid"], str):
        raise ValueError("Field 'author_uid' must be string")
    if not isinstance(doc["image_url"], str):
        raise ValueError("Field 'image_url' must be string")
    # guesses, correct_guessers, wrong_guessers: list
    for key in ["guesses", "correct_guessers", "wrong_guessers"]:
        if not isinstance(doc.get(key, []), list):
            raise ValueError(f"Field '{key}' must be list")
    return True

# PUBLIC_INTERFACE
def validate_user_doc(doc: dict) -> bool:
    """Validate that a Firestore user document conforms to schema."""
    for field in REQUIRED_USER_FIELDS:
        if field not in doc:
            raise ValueError(f"Field '{field}' missing in user doc")
    if not isinstance(doc["username"], str):
        raise ValueError("Field 'username' must be string")
    for k in ["drawings_submitted", "total_guesses", "correct_guesses", "wrong_guesses"]:
        if not isinstance(doc[k], int):
            raise ValueError(f"Field '{k}' must be int")
    return True
