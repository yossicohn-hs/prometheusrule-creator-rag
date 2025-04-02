from fastapi import (
    FastAPI,
    Request,
    WebSocket,
    WebSocketDisconnect,
    Form,
    Depends,
    HTTPException,
)
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn
import json
import uuid
from typing import Dict, Optional
from pydantic import BaseModel

# Import your RAG application code
from prometheus_rag import (
    RuleGenerationState,
    build_rag_graph,
    handle_user_input,
    AIMessage,
)

app = FastAPI(title="PrometheusRule RAG API")

# Build the graph
graph = build_rag_graph()

# Store conversation states
sessions = {}


# Pydantic models for API requests/responses
class ChatMessage(BaseModel):
    message: str
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    message: str
    session_id: str
    complete: bool
    service_info: Dict = {}
    prometheus_rule: Optional[str] = None


# Create a new session
def create_session():
    session_id = str(uuid.uuid4())
    sessions[session_id] = RuleGenerationState(
        messages=[],
        service_info={},
        context=[],
        prometheus_rule=None,
        stage="extract_info",
        attempt_count=0,
    )
    return session_id


# Get existing session or create new one
def get_session(session_id: Optional[str] = None):
    if session_id and session_id in sessions:
        return session_id, sessions[session_id]
    else:
        new_id = create_session()
        return new_id, sessions[new_id]


# REST API endpoint for chat
@app.post("/api/chat", response_model=ChatResponse)
async def chat(chat_message: ChatMessage):
    session_id, state = get_session(chat_message.session_id)

    # Process message through graph
    updated_state = handle_user_input(state, chat_message.message)

    config = {"configurable": {"thread_id": session_id}}
    result = graph.invoke(updated_state, config)

    # Update session state
    sessions[session_id] = result

    # Get latest AI message
    ai_messages = [
        msg.content for msg in result.get("messages", []) if isinstance(msg, AIMessage)
    ]
    latest_message = ai_messages[-1] if ai_messages else "No response generated."

    # Check if workflow is complete

    is_complete = result.get("stage") == "complete"

    curr_session = sessions.get(session_id)
    all_messages = curr_session.get("messages", [])
    for m in all_messages[-2:]:
        m.pretty_print()
        print("\n\n")

    return ChatResponse(
        message=latest_message,
        session_id=session_id,
        complete=is_complete,
        service_info=result.get("service_info", {}),
        prometheus_rule=result.get("prometheus_rule"),
    )


# WebSocket endpoint for interactive chat
@app.websocket("/ws/chat/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str = None):
    await websocket.accept()

    try:
        # Get or create session
        if not session_id or session_id not in sessions:
            session_id = create_session()
            await websocket.send_json(
                {"type": "session_created", "session_id": session_id}
            )

        state = sessions[session_id]

        while True:
            # Receive message from client
            data = await websocket.receive_json()
            message = data.get("message", "")

            # Process through graph
            updated_state = handle_user_input(state, message)
            result = graph.invoke(updated_state)

            # Update session state
            sessions[session_id] = result
            state = result

            # Get latest AI message
            ai_messages = [
                msg.content
                for msg in result.get("messages", [])
                if isinstance(msg, AIMessage)
            ]
            latest_message = (
                ai_messages[-1] if ai_messages else "No response generated."
            )

            # Send response to client
            await websocket.send_json(
                {
                    "type": "message",
                    "message": latest_message,
                    "complete": result.get("stage") == "complete",
                    "service_info": result.get("service_info", {}),
                    "prometheus_rule": result.get("prometheus_rule"),
                }
            )

    except WebSocketDisconnect:
        print(f"Client disconnected: {session_id}")


# Simple HTML interface
templates = Jinja2Templates(directory="templates")


@app.get("/", response_class=HTMLResponse)
async def get_chat_page(request: Request):
    return templates.TemplateResponse("chat.html", {"request": request})


def clear_session_and_checkpointer(session_id: str):
    # Clear in-memory session
    if session_id in sessions:
        del sessions[session_id]
    
    # Clear checkpointer state (if applicable)
    if hasattr(graph, "checkpointer"):
        graph.checkpointer.clear(session_id)

# REST API endpoint to clear session and checkpointer
@app.delete("/api/session/{session_id}")
async def delete_session(session_id: str):
    if session_id in sessions:
        clear_session_and_checkpointer(session_id)
        return {"message": f"Session {session_id} and its states cleared successfully."}
    else:
        raise HTTPException(status_code=404, detail="Session not found")


# Run the server
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
