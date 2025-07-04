"""
Helper script to initialize Firestore collections with minimal schema
and (optionally) add seed data for development/testing Doodle Finder game.

USAGE:
  Set GOOGLE_APPLICATION_CREDENTIALS to your service account.
  python setup_initialize_firestore.py

This script is NOT for production but for local/dev/testing/emulator!
"""

import os
import uuid
from google.cloud import firestore

def init_users_collection(db):
    # Add a seed user
    user_doc = {
        "username": "SampleTester",
        "drawings_submitted": 0,
        "total_guesses": 0,
        "correct_guesses": 0,
        "wrong_guesses": 0
    }
    doc_ref = db.collection("users").document("test_uid_123")
    doc_ref.set(user_doc)
    print("Sample user added.")

def init_drawings_collection(db):
    # Add a seed drawing
    drawing_doc = {
        "prompt": "Tiger",
        "author_uid": "test_uid_123",
        "image_url": "https://test-url.generated/for/emulator.png",
        "timestamp": firestore.SERVER_TIMESTAMP,
        "guesses": [],
        "correct_guessers": [],
        "wrong_guessers": []
    }
    drawing_id = str(uuid.uuid4())
    doc_ref = db.collection("drawings").document(drawing_id)
    doc_ref.set(drawing_doc)
    print("Sample drawing added.")

def main():
    db = firestore.Client()
    init_users_collection(db)
    init_drawings_collection(db)
    print("Firestore initialized with seed data. (Run only once for tests.)")

if __name__ == "__main__":
    main()
