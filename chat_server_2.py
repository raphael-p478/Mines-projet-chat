from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Field, Session, SQLModel, create_engine, select

app: FastAPI = FastAPI()

# Jinja2 template engine (kept from exercise 1).
templates = Jinja2Templates(directory="templates")


# A single chat message. Now it is also a table row in SQLite.
class ChatMessage(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    message: str


# The response returned by the polling endpoint.
class PollResponse(SQLModel):
    messages: list[ChatMessage]


# Small response model used after a message is accepted.
class SendResponse(SQLModel):
    ok: bool


# SQLite database connection.
sqlite_url = "sqlite:///store.db"
engine = create_engine(
    sqlite_url,
    connect_args={"check_same_thread": False},
)


def create_db_and_tables() -> None:
    """Create the SQLite file and all tables if they do not exist yet."""
    SQLModel.metadata.create_all(engine)


@app.on_event("startup")
def on_startup() -> None:
    create_db_and_tables()


@app.get("/chat", response_class=HTMLResponse)
async def chat(request: Request):
    """Serve the chat client page rendered through Jinja2 templates."""
    return templates.TemplateResponse(
        request=request,
        name="chat_0.html",
        context={},
    )


@app.get("/poll", response_model=PollResponse)
async def poll() -> PollResponse:
    """Return the full message history stored in SQLite."""
    with Session(engine) as session:
        statement = select(ChatMessage).order_by(ChatMessage.id)
        db_messages = session.exec(statement).all()
    return PollResponse(messages=list(db_messages))


@app.post("/send", response_model=SendResponse)
async def send(msg: ChatMessage) -> SendResponse:
    """Persist one new chat message in SQLite."""
    # Ensure `id` is None so SQLite generates a fresh primary key,
    # even if the client sent one.
    msg.id = None
    with Session(engine) as session:
        session.add(msg)
        session.commit()
    return SendResponse(ok=True)
