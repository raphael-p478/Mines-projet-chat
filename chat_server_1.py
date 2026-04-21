from collections import deque

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

app: FastAPI = FastAPI()

# Jinja2 template engine. FastAPI will look for HTML files in the
# `templates/` folder. We put `chat_0.html` there without changing it.
templates = Jinja2Templates(directory="templates")


# A single chat message sent by one user.
class ChatMessage(BaseModel):
    name: str
    message: str


# The response returned by the polling endpoint.
class PollResponse(BaseModel):
    messages: list[ChatMessage]


# Small response model used after a message is accepted.
class SendResponse(BaseModel):
    ok: bool


# In-memory message history for this demo application.
messages: deque[ChatMessage] = deque(maxlen=128)


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
    """Return the current message history. Returns HTTP 200 on success."""
    return PollResponse(messages=list(messages))


@app.post("/send", response_model=SendResponse)
async def send(msg: ChatMessage) -> SendResponse:
    """Store one new chat message. Returns HTTP 200 on success."""
    messages.append(msg)
    return SendResponse(ok=True)
