# Doodle Finder Firestore Database Model & Security Rules

This folder contains the data model and security settings for the Doodle Finder drawing and guessing game, designed for compatibility with both FastAPI backend and real-time gameplay.

---

## Firestore Collections & Docs

### 1. users (Collection)

- **Document ID:** `uid` (Firebase Auth UID)
- **Fields:**
  - `username`         : string (unique handle)
  - `drawings_submitted`: number (count)
  - `total_guesses`     : number
  - `correct_guesses`   : number
  - `wrong_guesses`     : number

#### Example:
```json
{
  "username": "CoolTiger99",
  "drawings_submitted": 2,
  "total_guesses": 16,
  "correct_guesses": 8,
  "wrong_guesses": 8
}
```

### 2. drawings (Collection)

- **Document ID**: `drawing_id` (generated UUID)
- **Fields:**
  - `prompt`: string (e.g., "Flamingo")
  - `author_uid`: string (author's UID)
  - `image_url`: string (signed Storage URL)
  - `timestamp`: timestamp (creation)
  - `guesses`: array\<string\> (legacy; may be unused)
  - `correct_guessers`: array\<string\> (uids)
  - `wrong_guessers`: array\<string\> (uids)

#### Example:
```json
{
  "prompt": "Flamingo",
  "author_uid": "uYV3F08Ee9n...d8O",
  "image_url": "https://firebasestorage.googleapis.com/...",
  "timestamp": 1675219000,
  "guesses": [],
  "correct_guessers": ["BfYZQK...", "KbSt8..."],
  "wrong_guessers": ["J4mAz...", "Nbp2z..."]
}
```

### Leaderboard and Real-Time

- **Leaderboard**: Always computed dynamically, no separate collection.
- **WebSocket push** from backend on `/drawings` or guess update for leaderboard and real-time stats.

---

## Real-Time Features

- All users read drawings/user stats in real time.
- Leaderboard updates sent via backend websocket (not by Firestore listeners).
- Data structure optimized for quick leaderboard calculation and atomic stat updates.

---

## Security Rules

See [`firestore.rules`](./firestore.rules) and [`storage.rules`](./storage.rules):
- Users can only access their profile/stats.
- Drawings can be read by anyone authenticated, created by any user, but only the author can update/delete their own.
- Only authenticated users can upload/read drawing images (`drawings/{drawing_id}.png`) from storage.

---

## Storage Layout

- Images stored at path: `/drawings/{drawing_id}.png`
- Signed URLs generated and stored in each drawing's doc.

---

## Compatibility Notes

- Designed for backend API contract in `src/api/main.py` (see backend for Pydantic models, endpoints).
- No subcollections or nested docs are used at present.
- Ensure frontend and backend always use valid Firestore document IDs and field types as described.

---

Task completed: Firestore data model schema and security rules generated for all gameplay entities, ready for backend and frontend integration.
