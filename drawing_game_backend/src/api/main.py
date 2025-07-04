import os
import uuid
from typing import List, Dict, Any

from fastapi import FastAPI, HTTPException, Depends, Header, UploadFile, File, status, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse
from starlette.websockets import WebSocketState

import firebase_admin
from firebase_admin import credentials, auth, firestore, storage

# Initialize Firebase Admin SDK if not already initialized
FIREBASE_CRED_JSON = os.getenv("FIREBASE_CRED_JSON", "/secrets/firebase/credentials.json")
FIREBASE_STORAGE_BUCKET = os.getenv("FIREBASE_STORAGE_BUCKET", "<your-bucket>.appspot.com")
if not firebase_admin._apps:
    cred = credentials.Certificate(FIREBASE_CRED_JSON)
    firebase_admin.initialize_app(cred, {
        "storageBucket": FIREBASE_STORAGE_BUCKET,
    })

db = firestore.client()
bucket = storage.bucket()

app = FastAPI(
    title="Doodle Finder Backend API",
    description="API for the Doodle Finder drawing and guessing game. Integrates with Firebase Auth/Firestore/Storage.",
    version="1.0.0",
    openapi_tags=[
        {"name": "Auth", "description": "Authentication for users."},
        {"name": "Drawing", "description": "Endpoints for drawing CRUD and upload."},
        {"name": "Guess", "description": "Endpoints to submit/validate guesses on drawings."},
        {"name": "User", "description": "Endpoints for user profile/statistics."},
        {"name": "Leaderboard", "description": "Real-time leaderboard."},
        {"name": "WebSocket", "description": "WebSocket endpoints for real-time updates."}
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

bearer_scheme = HTTPBearer()

# --- Utility & Security ----
def verify_firebase_token(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)):
    """Verify Firebase Auth JWT, used for endpoint security."""
    if not credentials or not credentials.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")
    try:
        decoded = auth.verify_id_token(credentials.credentials)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    return decoded

def get_user_doc(uid: str):
    return db.collection("users").document(uid)

def get_drawing_doc(drawing_id: str):
    return db.collection("drawings").document(drawing_id)

def broadcast_leaderboard():  # Called after DB update, sends to all active sockets
    for ws in websocket_manager.list_clients("leaderboard"):
        if ws.application_state == WebSocketState.CONNECTED:
            leaderboard = get_leaderboard_internal()
            try:
                import asyncio
                asyncio.create_task(ws.send_json({"event": "leaderboard", "payload": leaderboard}))
            except Exception:
                pass

# --- Pydantic Models ----
class LoginRequest(BaseModel):
    username: str = Field(..., description="Username for anonymous login")

class LoginResponse(BaseModel):
    token: str
    uid: str

class DrawingBase(BaseModel):
    drawing_id: str = Field(..., description="Drawing unique ID")
    prompt: str = Field(..., description="Prompt (e.g., 'Tiger')")
    author_uid: str
    image_url: str
    timestamp: int
    guesses: List[str] = []
    correct_guessers: List[str] = []
    wrong_guessers: List[str] = []

class DrawingCreateRequest(BaseModel):
    prompt: str = Field(..., description="Prompt assigned (e.g., 'Flamingo')")
    image_data_url: str = Field(..., description="Base64 DataURL of image (or optionally upload with /upload_drawing)")
    # If uploading via multipart, this field is ignored

class GuessRequest(BaseModel):
    drawing_id: str
    guess: str

class GuessResultResponse(BaseModel):
    correct: bool
    message: str
    drawing_id: str

class UserStatsResponse(BaseModel):
    uid: str
    username: str
    drawings_submitted: int
    total_guesses: int
    correct_guesses: int
    wrong_guesses: int

class LeaderboardEntry(BaseModel):
    drawing_id: str
    prompt: str
    author_uid: str
    correct_guess_count: int

# ---- WebSocket Real-Time ----
class WebSocketManager:
    def __init__(self):
        self.rooms: Dict[str, List[WebSocket]] = {}

    def add(self, ws: WebSocket, room: str):
        if room not in self.rooms:
            self.rooms[room] = []
        self.rooms[room].append(ws)

    def remove(self, ws: WebSocket, room: str):
        if room in self.rooms and ws in self.rooms[room]:
            self.rooms[room].remove(ws)

    def list_clients(self, room: str):
        return self.rooms.get(room, [])

websocket_manager = WebSocketManager()

# ---- API Endpoints ----

# PUBLIC_INTERFACE
@app.post("/login", response_model=LoginResponse, tags=["Auth"], summary="Anonymous login")
async def login(req: LoginRequest):
    """Anonymous login using username. Issues Firebase custom token."""
    # Generate a UID (or find existing for username)
    existing_users = db.collection("users").where("username", "==", req.username).get()
    if existing_users:
        user_doc = existing_users[0]
        uid = user_doc.id
    else:
        uid = str(uuid.uuid4())
        db.collection("users").document(uid).set({
            "username": req.username,
            "drawings_submitted": 0,
            "total_guesses": 0,
            "correct_guesses": 0,
            "wrong_guesses": 0,
        })
    try:
        firebase_token = auth.create_custom_token(uid)
    except Exception as e:
        raise HTTPException(500, f"Auth error: {e}")
    return LoginResponse(token=firebase_token.decode(), uid=uid)

# PUBLIC_INTERFACE
@app.get("/drawings", response_model=List[DrawingBase], tags=["Drawing"], summary="List all drawings")
async def list_drawings(token=Depends(verify_firebase_token)):
    """Get all current drawings."""
    docs = db.collection("drawings").stream()
    out = []
    for doc in docs:
        item = doc.to_dict()
        item['drawing_id'] = doc.id
        out.append(DrawingBase(**item))
    return out

# PUBLIC_INTERFACE
@app.get("/drawings/{drawing_id}", response_model=DrawingBase, tags=["Drawing"], summary="Get single drawing")
async def get_drawing(drawing_id: str, token=Depends(verify_firebase_token)):
    """Fetch metadata and guess lists for a drawing."""
    doc = get_drawing_doc(drawing_id).get()
    if not doc.exists:
        raise HTTPException(404, "Not found")
    obj = doc.to_dict()
    obj["drawing_id"] = drawing_id
    return DrawingBase(**obj)

# PUBLIC_INTERFACE
@app.post("/add_drawing", tags=["Drawing"], summary="Add a new drawing")
async def add_drawing(req: DrawingCreateRequest, token=Depends(verify_firebase_token)):
    """Add a new drawing (store image in Firebase Storage, metadata in Firestore)."""
    uid = token["uid"]
    prompt = req.prompt
    # Save image to Storage
    img_bytes = req.image_data_url.split(",")[1]
    import base64
    img_data = base64.b64decode(img_bytes)
    drawing_id = str(uuid.uuid4())
    image_path = f"drawings/{drawing_id}.png"
    blob = bucket.blob(image_path)
    blob.upload_from_string(img_data, content_type="image/png")
    img_url = blob.generate_signed_url(version="v4", expiration=3600 * 24 * 30, method="GET")

    drawing_doc = {
        "prompt": prompt,
        "author_uid": uid,
        "image_url": img_url,
        "timestamp": firestore.SERVER_TIMESTAMP,
        "guesses": [],
        "correct_guessers": [],
        "wrong_guessers": [],
    }
    get_drawing_doc(drawing_id).set(drawing_doc)
    # Update user stats
    user_ref = get_user_doc(uid)
    user_ref.update({"drawings_submitted": firestore.Increment(1)})
    broadcast_leaderboard()
    return JSONResponse({"drawing_id": drawing_id, "image_url": img_url})

# PUBLIC_INTERFACE
@app.post("/guess", response_model=GuessResultResponse, tags=["Guess"], summary="Guess on a drawing")
async def guess(req: GuessRequest, token=Depends(verify_firebase_token)):
    """Submit a guess for a drawing. Updates guesses per user."""
    user_uid = token["uid"]
    doc = get_drawing_doc(req.drawing_id).get()
    if not doc.exists:
        raise HTTPException(404, "Drawing not found")
    obj = doc.to_dict()
    prompt = obj["prompt"].strip().lower()
    guess_term = req.guess.strip().lower()
    already_guessed = user_uid in (obj.get("correct_guessers", []) + obj.get("wrong_guessers", []))
    if already_guessed:
        return GuessResultResponse(correct=False, message="Already guessed this drawing", drawing_id=req.drawing_id)
    correct = (guess_term == prompt)
    if correct:
        get_drawing_doc(req.drawing_id).update({
            "correct_guessers": firestore.ArrayUnion([user_uid])
        })
        # Update user stats
        user_ref = get_user_doc(user_uid)
        user_ref.update({"correct_guesses": firestore.Increment(1), "total_guesses": firestore.Increment(1)})
    else:
        get_drawing_doc(req.drawing_id).update({
            "wrong_guessers": firestore.ArrayUnion([user_uid])
        })
        user_ref = get_user_doc(user_uid)
        user_ref.update({"wrong_guesses": firestore.Increment(1), "total_guesses": firestore.Increment(1)})

    # Update leaderboard via broadcast
    broadcast_leaderboard()
    msg = "Correct! 🎉" if correct else "Wrong. Try again or guess other drawings!"
    return GuessResultResponse(correct=correct, message=msg, drawing_id=req.drawing_id)

# PUBLIC_INTERFACE
@app.get("/user", response_model=UserStatsResponse, tags=["User"], summary="Get current user stats")
async def get_user_stats(token=Depends(verify_firebase_token)):
    """Returns statistics for the logged-in user."""
    uid = token["uid"]
    doc = get_user_doc(uid).get()
    if not doc.exists:
        raise HTTPException(404, "User not found")
    d = doc.to_dict()
    return UserStatsResponse(
        uid=uid,
        username=d["username"],
        drawings_submitted=d.get("drawings_submitted", 0),
        total_guesses=d.get("total_guesses", 0),
        correct_guesses=d.get("correct_guesses", 0),
        wrong_guesses=d.get("wrong_guesses", 0),
    )

# --------- Leaderboard ---------
def get_leaderboard_internal(top_n=5) -> List[Dict[str, Any]]:
    drawings = db.collection("drawings").stream()
    sortable = []
    for doc in drawings:
        obj = doc.to_dict()
        sortable.append({
            "drawing_id": doc.id,
            "prompt": obj.get("prompt"),
            "author_uid": obj.get("author_uid"),
            "correct_guess_count": len(obj.get("correct_guessers", [])),
        })
    ordered = sorted(sortable, key=lambda d: d["correct_guess_count"], reverse=True)
    return ordered[:top_n]

# PUBLIC_INTERFACE
@app.get("/leaderboard", response_model=List[LeaderboardEntry], tags=["Leaderboard"], summary="Top drawings (real-time)")
async def leaderboard(token=Depends(verify_firebase_token)):
    """Get the current leaderboard: drawings with the most correct guesses."""
    entries = get_leaderboard_internal()
    return [LeaderboardEntry(**entry) for entry in entries]

@app.websocket("/ws/leaderboard")
async def ws_leaderboard(websocket: WebSocket):
    """
    WebSocket providing real-time leaderboard updates.

    Usage:
    Connect and receive leaderboard dicts on any update. For demo/testing.
    """
    await websocket.accept()
    websocket_manager.add(websocket, "leaderboard")
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        websocket_manager.remove(websocket, "leaderboard")

# --------- (Optional) File Upload variant ---------
@app.post("/upload_drawing", tags=["Drawing"], summary="Upload drawing image (multipart)")
async def upload_drawing(prompt: str = Header(...), file: UploadFile = File(...), token=Depends(verify_firebase_token)):
    """
    Upload drawing as file upload (PNG recommended).
    """
    uid = token["uid"]
    data = await file.read()
    drawing_id = str(uuid.uuid4())
    image_path = f"drawings/{drawing_id}.png"
    blob = bucket.blob(image_path)
    blob.upload_from_string(data, content_type=file.content_type)
    img_url = blob.generate_signed_url(version="v4", expiration=3600 * 24 * 30, method="GET")

    drawing_doc = {
        "prompt": prompt,
        "author_uid": uid,
        "image_url": img_url,
        "timestamp": firestore.SERVER_TIMESTAMP,
        "guesses": [],
        "correct_guessers": [],
        "wrong_guessers": [],
    }
    get_drawing_doc(drawing_id).set(drawing_doc)
    get_user_doc(uid).update({"drawings_submitted": firestore.Increment(1)})
    broadcast_leaderboard()
    return JSONResponse({"drawing_id": drawing_id, "image_url": img_url})

# PUBLIC_INTERFACE
@app.get("/health", tags=["User"], summary="Health check")
def health_check():
    """API health check."""
    return {"message": "Healthy"}

# ---- OpenAPI WebSocket Docs Endpoint ---
# PUBLIC_INTERFACE
@app.get("/ws_docs", tags=["WebSocket"])
def ws_docs():
    """
    WebSocket Usage Documentation.
    """
    return {
        "websockets": [
            {
                "endpoint": "/ws/leaderboard",
                "summary": "Real-time leaderboard updates. Connect and receive updates.",
                "how": "On connection, you'll receive leaderboard updates pushed automatically when the leaderboard changes."
            }
        ]
    }

# - End of File -
