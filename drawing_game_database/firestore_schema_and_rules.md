# Drawing Game Firestore Database Structure & Security Rules

This document describes the Firestore collections, field structure, real-time requirements, and Firebase Security Rules to support all backend and real-time features of the Doodle Finder drawing game.

---
## 1. Collections & Entities

### a. **users**

- **Purpose:** Store user profiles and statistics.
- **Document ID:** `uid` (unique per user)
- **Fields:**
  - `username`: `string` — Unique, user-chosen handle.
  - `drawings_submitted`: `number` — Total drawings added by user.
  - `total_guesses`: `number` — Total guesses made by user.
  - `correct_guesses`: `number` — Number of correct guesses by user.
  - `wrong_guesses`: `number` — Number of wrong guesses by user.

**Structure Example:**
```json
{
  "username": "CoolTiger99",
  "drawings_submitted": 2,
  "total_guesses": 11,
  "correct_guesses": 5,
  "wrong_guesses": 6
}
```

---

### b. **drawings**

- **Purpose:** Store all submitted drawings and metadata.
- **Document ID:** `drawing_id` (UUID)
- **Fields:**
  - `prompt`: `string` — The animal/bird/reptile prompt.
  - `author_uid`: `string` — UID of drawing author.
  - `image_url`: `string` — Signed URL from Firebase Storage.
  - `timestamp`: `timestamp` — Server timestamp at creation.
  - `guesses`: `array<string>` — Used/legacy; usually ignored.
  - `correct_guessers`: `array<string>` — UIDs who guessed correctly.
  - `wrong_guessers`: `array<string>` — UIDs who guessed wrong.

**Structure Example:**
```json
{
  "prompt": "Flamingo",
  "author_uid": "n5KvW5...",
  "image_url": "https://firebasestorage.googleapis.com/...",
  "timestamp": 1675012800,
  "guesses": [],
  "correct_guessers": ["BfYZQKx3...", "KbSt8..."],
  "wrong_guessers": ["H2pjV5l...", "Jd5hq..."]
}
```

---

### c. **Leaderboard & Statistics**

- **Leaderboard is computed, not a Firestore collection.**
- Always derived at runtime by sorting all `drawings` by `correct_guessers.length`.
- No explicit `leaderboard` collection needed.
- User statistics are in the `users` collection.

---

## 2. Real-Time Features

- **Realtime leaderboard:**
  - Handled over WebSocket; on `drawings` update or guess, backend pushes leaderboard to connected clients.
  - No special Firestore requirements aside from quick update propagation.
- **Realtime stats:**
  - User stats can be read directly from `users/{uid}`; backend keeps in sync via atomic increments.

---

## 3. Security Rules

Supports REST API pattern; assumes users are authenticated with Firebase Auth.

```firebase
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {

    // Users collection - user can read/write their own profile only
    match /users/{userId} {
      allow read, write: if request.auth != null && request.auth.uid == userId;
    }

    // Drawings - anyone logged in can read; only author can create
    match /drawings/{drawingId} {
      // All users can read all drawings
      allow get, list: if request.auth != null;

      // Anyone logged in can add a drawing
      allow create: if request.auth != null;

      // Only author can update their drawing (rare; as drawn)
      allow update, delete: if request.auth != null && request.resource.data.author_uid == request.auth.uid;
    }

    // No other collections should be accessible
    match /{document=**} {
      allow read, write: if false;
    }
  }
}
```

**Notes:**
- **Guesses:** No separate collection; live in the `drawings/{drawingId}` fields.
- **Leaderboard:** Always backend-generated, not stored.
- **Stats:** All in `users/{uid}`.

---

## 4. Storage Buckets (Images)

- Images are stored in Cloud Storage under `drawings/{drawing_id}.png`
- Use signed URLs for secure, temporary access.

**Sample Storage Security Rule** (Only allow upload/read by authenticated users):
```firebase
rules_version = '2';
service firebase.storage {
  match /b/{bucket}/o {
    match /drawings/{allPaths=**} {
      allow read, write: if request.auth != null;
    }
  }
}
```

---

## 5. Real-Time Data Notes

- All client real-time features are powered by backend WebSocket broadcast (not Firestore Subscriptions).
- Firestore structure is optimized for quick lookups and leaderboard sorting.

---

## 6. Summary Table

| Entity     | Firestore Collection | Document ID      | Fields (Summary)              | Real-Time?            |
|------------|---------------------|------------------|-------------------------------|-----------------------|
| Users      | `users`             | `uid`            | username, stats fields        | Yes (stats updates)   |
| Drawings   | `drawings`          | `drawing_id`     | prompt, author_uid, image_url, correct/wrong_guessers | Yes (new drawings, guess updates) |
| Leaderboard| (computed)          | N/A              | (ordered top N drawings)      | Yes (broadcast)       |

---

## 7. Compatibility Notes

- **Compatible with backend code at `src/api/main.py`**. All endpoints interact with documented fields and collections only.
- **NO nested subcollections used at this time.**
- **Realtime is enabled via backend WebSocket ingestion only.**

---

# End of database definition
