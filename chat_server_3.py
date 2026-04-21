import hashlib
import secrets

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Field, Relationship, Session, SQLModel, create_engine, select

app: FastAPI = FastAPI()

# Jinja2 template engine.
templates = Jinja2Templates(directory="templates")


# ---------------------------------------------------------------------------
# Database models
# ---------------------------------------------------------------------------
#
# User (1) --- (many) ChatMessage
# User (1) --- (many) UserSession
#
# Every message and every session belongs to exactly one user.
# ---------------------------------------------------------------------------


class User(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    # `name` is unique so we can look up a user by name.
    name: str = Field(unique=True, index=True)
    password_hash: str

    messages: list["ChatMessage"] = Relationship(back_populates="user")
    sessions: list["UserSession"] = Relationship(back_populates="user")


class ChatMessage(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    message: str
    user_id: int = Field(foreign_key="user.id")

    user: User | None = Relationship(back_populates="messages")


class UserSession(SQLModel, table=True):
    # `token` is the value stored in the browser cookie.
    token: str = Field(primary_key=True)
    user_id: int = Field(foreign_key="user.id")

    user: User | None = Relationship(back_populates="sessions")


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class Credentials(SQLModel):
    """Body of POST /login and POST /register."""
    name: str
    password: str


class ChatMessageIn(SQLModel):
    """Body of POST /send. The author is taken from the cookie session."""
    message: str


class ChatMessageOut(SQLModel):
    """One message as returned by /poll."""
    name: str
    message: str


class PollResponse(SQLModel):
    messages: list[ChatMessageOut]


class SendResponse(SQLModel):
    ok: bool


# ---------------------------------------------------------------------------
# Database engine and startup
# ---------------------------------------------------------------------------

sqlite_url = "sqlite:///store.db"
engine = create_engine(
    sqlite_url,
    connect_args={"check_same_thread": False},
)


def create_db_and_tables() -> None:
    SQLModel.metadata.create_all(engine)


@app.on_event("startup")
def on_startup() -> None:
    create_db_and_tables()


# ---------------------------------------------------------------------------
# Authentication helpers
# ---------------------------------------------------------------------------

SESSION_COOKIE_NAME = "session_token"


def hash_password(password: str) -> str:
    """Hash a password with SHA-256.

    Note: SHA-256 is too fast and unsalted, which is fine for this
    exercise but not for real production use (prefer bcrypt/argon2).
    """
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def new_session_token() -> str:
    """Return a random, URL-safe session token."""
    return secrets.token_urlsafe(32)


def get_current_user(request: Request, session: Session) -> User | None:
    """Return the logged-in user for this request, or None."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return None
    user_session = session.get(UserSession, token)
    if user_session is None:
        return None
    return session.get(User, user_session.user_id)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Render the login page."""
    return templates.TemplateResponse(
        request=request,
        name="login_0.html",
        context={},
    )


@app.post("/login")
async def login(credentials: Credentials, response: Response):
    """Log an existing user in and set the session cookie."""
    with Session(engine) as session:
        user = session.exec(
            select(User).where(User.name == credentials.name)
        ).first()
        if user is None or user.password_hash != hash_password(credentials.password):
            raise HTTPException(status_code=401, detail="Invalid name or password")

        token = new_session_token()
        session.add(UserSession(token=token, user_id=user.id))
        session.commit()

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
    )
    return {"ok": True}


@app.post("/register")
async def register(credentials: Credentials, response: Response):
    """Create a new user and log them in immediately."""
    with Session(engine) as session:
        existing = session.exec(
            select(User).where(User.name == credentials.name)
        ).first()
        if existing is not None:
            raise HTTPException(status_code=409, detail="User already exists")

        user = User(
            name=credentials.name,
            password_hash=hash_password(credentials.password),
        )
        session.add(user)
        session.commit()
        session.refresh(user)

        token = new_session_token()
        session.add(UserSession(token=token, user_id=user.id))
        session.commit()

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
    )
    return {"ok": True}


@app.get("/chat")
async def chat(request: Request):
    """Authenticated chat page. Unauthenticated users are redirected."""
    with Session(engine) as session:
        user = get_current_user(request, session)
        if user is None:
            return RedirectResponse(url="/login", status_code=303)
        user_name = user.name

    return templates.TemplateResponse(
        request=request,
        name="chat_1.html",
        context={"user_name": user_name},
    )


@app.get("/poll", response_model=PollResponse)
async def poll(request: Request):
    """Return all messages with their author name."""
    with Session(engine) as session:
        user = get_current_user(request, session)
        if user is None:
            raise HTTPException(status_code=401, detail="Not authenticated")

        statement = select(ChatMessage).order_by(ChatMessage.id)
        db_messages = session.exec(statement).all()
        out = [
            ChatMessageOut(
                name=(msg.user.name if msg.user is not None else "?"),
                message=msg.message,
            )
            for msg in db_messages
        ]
    return PollResponse(messages=out)


@app.post("/send", response_model=SendResponse)
async def send(request: Request, body: ChatMessageIn):
    """Store a new message on behalf of the logged-in user."""
    with Session(engine) as session:
        user = get_current_user(request, session)
        if user is None:
            raise HTTPException(status_code=401, detail="Not authenticated")

        session.add(ChatMessage(message=body.message, user_id=user.id))
        session.commit()
    return SendResponse(ok=True)
