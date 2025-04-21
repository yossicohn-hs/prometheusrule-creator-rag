from json import dumps
from typing import Dict, List, Optional, Any
from pydantic import Field
from langchain import hub
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain_aws import ChatBedrockConverse
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.documents import Document
from langgraph.graph import StateGraph, END
from langgraph.graph import MessagesState
from langgraph.checkpoint.memory import MemorySaver
from extracted_user_info import ExtractedUserInfo
from promts import (
    EXTRACT_INFO_PROMT,
    GENERATE_QUESTION_PROMT,
    GET_CONTEXT_FOR_RETRIEVE_PROMT,
    GENERATE_PROMETHEUS_RULE_PROMT,
    SIMUPLATE_USER_ANSWER_PROMT,
)
from embeddings import init_vectorstore
from dotenv import load_dotenv

MAX_CONVERSATION_ITERATIONS = 50

load_dotenv(verbose=True)

retriever = init_vectorstore(topk=5)

# Define prompt for question-answering
prompt = hub.pull("rlm/rag-prompt")


# State definition
class RuleGenerationState(MessagesState):
    """State for the Prometheus rule generation workflow."""

    service_info: Dict[str, Any] = Field(default_factory=dict)
    context: List[str] = Field(default_factory=list)
    prometheus_rule: Optional[str] = Field(default=None)
    stage: str = Field(default="extract_info")
    attempt_count: int = Field(default=0)
    next_question: Optional[str] = Field(default=None)
    retrieved_docs: List[Document] = Field(default=None)
    session_id: str = Field(default="")


# Initialize LLM
# llm = ChatOpenAI(model="gpt-4o", temperature=0)
llm = ChatBedrockConverse(
    model="us.anthropic.claude-3-7-sonnet-20250219-v1:0",
    # model="anthropic.claude-3-5-haiku-20241022-v1:0",
    # model="amazon.nova-pro-v1:0",
    temperature=0.01,
    max_tokens=1000,
)


def get_context_from_state(state: RuleGenerationState) -> List[Document]:
    service_info = state.get("service_info")
    service_type = service_info.get("service_type")
    framework = service_info.get("framework")
    aws_dependencies = service_info.get("aws_dependencies")
    chain = (
        ChatPromptTemplate.from_template(GET_CONTEXT_FOR_RETRIEVE_PROMT)
        | llm
        | StrOutputParser()
    )
    config = {"configurable": {"thread_id": state.get("session_id")}}
    result_str = chain.invoke(
        {
            "aws_dependencies": aws_dependencies,
            "framework": framework,
            "service_type": service_type,
        },
        config,
    )
    print(f"get_context_from_state : {result_str}")
    
    retrieved_docs = retriever.invoke(result_str)
    print(f"Retrieved documents: {len(retrieved_docs)}")
    for doc in retrieved_docs:  # type: ignore
        metadata = doc.metadata
        name = metadata.get("name")
        print(f"Document name: {name}")
        
    return retrieved_docs


def format_documents(documents: List[Document]):
    return "\n\n".join(
        [f"Document {i+1}:\n{doc.page_content}" for i, doc in enumerate(documents)]
    )


# Define application steps
def retrieve_context(state: RuleGenerationState):
    retrieved_docs = get_context_from_state(state)
    retrieved_docs_as_context = format_documents(retrieved_docs)
    state.update(
        {
            "context": retrieved_docs_as_context,
            "stage": "generate_prometheus_rule",
        }
    )
    return state


# Node 1: Extract information from user inputs
def extract_service_info(state: RuleGenerationState) -> Dict:
    """Extract service information from user messages and update state."""
    # Get all user messages
    print(f"extract_service_info: {len(state.get("messages"))}")

    structured_output_llm = llm.with_structured_output(ExtractedUserInfo)
    # Ask LLM to extract information
    chain = ChatPromptTemplate.from_template(EXTRACT_INFO_PROMT) | structured_output_llm

    all_messages = state.get("messages", [])
    all_str_messages = ""
    for msg in all_messages:
        content = msg.content
        name = "Question" if type(msg) is AIMessage else "Answer"
        all_str_messages = (
            all_str_messages + "\n" + f"------ {name} ------\n" + content + "\n"
        )
    config = {"configurable": {"thread_id": state.get("session_id")}}
    extraced_info: ExtractedUserInfo = chain.invoke(
        {
            "current_info": state.get("service_info", {}),
            "all_messages": all_str_messages,
        },
        config,
    )
    next_question = extraced_info.next_question
    service_info_dict = extraced_info.__dict__
    # print(f"last User Message: {all_messages[:-1]}")
    print(f"service_info_dict: {service_info_dict}")
    del service_info_dict["next_question"]

    try:
        # Clean the result if it's in markdown format
        state.update(
            {
                "stage": "generate_question",
                "service_info": service_info_dict,
                "next_attempt": state.get("attempt_count", 0) + 1,
                "next_question": next_question,
            }
        )

        # Progress to rule generation after 3 rounds
        if (
            extraced_info.is_complete_info
            or state.get("attempt_count", 0) >= MAX_CONVERSATION_ITERATIONS
        ):
            state.update({"stage": "retrieve_context"})
            return state

        # Otherwise, move to question generation
        return state
    except Exception as error:
        print(f"Error in extracting service info: {error}")
        # Simply proceed to question generation on error
        state.update(
            {
                "stage": "complete",
                "service_info": service_info_dict,
            }
        )
        return state


# Node 2: Generate follow-up question
def generate_follow_up_question(state: RuleGenerationState) -> Dict:
    """Generate a follow-up question based on current information."""
    # Ask LLM to formulate the next question
    chain = (
        ChatPromptTemplate.from_template(GENERATE_QUESTION_PROMT)
        | llm
        | StrOutputParser()
    )

    all_messages = state.get("messages", [])
    all_str_messages = ""
    for msg in all_messages:
        content = msg.content
        name = "AI" if type(msg) is AIMessage else "User"
        all_str_messages = (
            all_str_messages + "\n" + f"------ {name} ------\n" + content + "\n"
        )
    config = {"configurable": {"thread_id": state.get("session_id")}}
    follow_up_question = chain.invoke(
        {
            "current_info": state.get("service_info", {}),
            "all_messages": all_str_messages,
            "advised_next_questions": state.get("next_question", ""),
        },
        config,
    )
    state.update(
        {
            "messages": state.get("messages", [])
            + [AIMessage(content=follow_up_question)],
            "stage": "wait_for_user",
        }
    )
    # Return the follow-up question and stay in gather_info stage
    return state


# Node 3: Generate PrometheusRule
def generate_prometheus_rule(state: RuleGenerationState) -> Dict:
    """Generate a PrometheusRule based on service info and examples."""
    # Retrieve examples
    context = state.get("context")

    # Generate rule
    chain = (
        ChatPromptTemplate.from_template(GENERATE_PROMETHEUS_RULE_PROMT)
        | llm
        | StrOutputParser()
    )

    config = {"configurable": {"thread_id": state.get("session_id")}}
    rule = chain.invoke(
        {
            "service_info": state.get("service_info", {}),
            "context": "\n".join(context),
        },
        config,
    )

    # Present the result to the user
    response = f"""
Based on the information you've provided, I've created a PrometheusRule for your service:

```yaml
{rule}
```

This rule includes alerts based on the metrics and thresholds you mentioned. Let me know if you'd like to make any adjustments.
"""
    state.update(
        {
            "messages": state.get("messages", []) + [AIMessage(content=response)],
            "stage": "complete",
            "prometheus_rule": rule,
            "context": context,
        }
    )
    return state


# Process user input
def handle_user_input(state: RuleGenerationState, user_input: str) -> Dict:
    """Add user input to messages and set stage for processing."""
    # Add user message to conversation history
    updated_messages = state.get("messages", []) + [HumanMessage(content=user_input)]

    # If we're at the complete stage, stay there
    state.update(
        {
            "messages": updated_messages,
            "stage": "extract_info",
        }
    )
    if state.get("stage") == "complete":
        state.update(
            {
                "messages": updated_messages,
                "stage": "complete",
            }
        )
    # Otherwise, always start with information extraction
    return state


# Define routing based on state
def router(state: RuleGenerationState) -> str:
    """Route to the next node based on the current state."""
    stage = state.get("stage", "extract_info")

    if stage == "extract_info":
        return "extract_info"
    elif stage == "generate_question":
        return "generate_question"
    elif stage == "wait_for_user":
        return "end"
    elif stage == "retrieve_context":
        return "retrieve_context"
    elif stage == "generate_prometheus_rule":
        return "generate_prometheus_rule"
    elif stage == "complete":
        return "end"
    else:
        return "extract_info"  # Default to information extraction


# Build and return the workflow graph
def build_rag_graph():
    """Create the RAG workflow with separate question generation."""
    workflow = StateGraph(RuleGenerationState)

    # Add nodes with clear separation of concerns
    workflow.add_node("extract_info", extract_service_info)
    workflow.add_node("generate_question", generate_follow_up_question)
    workflow.add_node("retrieve_context", retrieve_context)
    workflow.add_node("generate_prometheus_rule", generate_prometheus_rule)

    # Connect nodes with conditional routing
    workflow.add_conditional_edges(
        "extract_info",
        router,
        {
            "extract_info": "extract_info",
            "generate_question": "generate_question",
            "retrieve_context": "retrieve_context",
            "end": END,
        },
    )

    workflow.add_conditional_edges(
        "retrieve_context",
        router,
        {
            "retrieve_context": "retrieve_context",
            "generate_prometheus_rule": "generate_prometheus_rule",
            "end": END,
        },
    )

    workflow.add_conditional_edges(
        "generate_question",
        router,
        {
            "extract_info": "extract_info",
            "generate_question": "generate_question",
            "wait_for_user": END,
            "end": END,
        },
    )

    workflow.add_conditional_edges(
        "generate_prometheus_rule",
        router,
        {"generate_prometheus_rule": END, "complete": END, "end": END},
    )

    # Set entry point
    workflow.set_entry_point("extract_info")
    memory = MemorySaver()
    graph = workflow.compile(checkpointer=memory)

    return graph


# Graph for LangGraph Studio
graph = build_rag_graph()


# =========================================== Simulate user answer ===========================================
def simulate_user_answer(state: MessagesState) -> str:
    """Generate an answer to the LLM questions."""
    # Retrieve examples
    # Generate rule
    chain = (
        ChatPromptTemplate.from_template(SIMUPLATE_USER_ANSWER_PROMT)
        | llm
        | StrOutputParser()
    )
    messages = state.get("messages", [])
    last_message = messages[-1] if messages else None
    if last_message and isinstance(last_message, AIMessage):
        content = last_message.content.replace("AI: ", "")

    all_answers = "\n".join(
        [msg.content for msg in messages if isinstance(msg, HumanMessage)]
    )

    response_answer = chain.invoke(
        {"agent_question": content, "all_answers": all_answers}
    )
    return response_answer


# Process message function for LangGraph Studio
def process_message(state, message: str):
    """Process a user message in the RAG workflow."""
    # Initialize state if this is a new conversation
    if not state:
        state = RuleGenerationState(
            messages=[],
            service_info={},
            context=[],
            prometheus_rule=None,
            stage="extract_info",
            attempt_count=0,
        )
    config = {"configurable": {"thread_id": 1}}
    # Add the user message to state
    updated_state = handle_user_input(state, message)

    # Run the graph
    result = graph.invoke(updated_state, config)

    return result


# For local testing
if __name__ == "__main__":
    state = RuleGenerationState(
        messages=[],
        service_info={},
        context=[],
        prometheus_rule=None,
        stage="extract_info",
        attempt_count=0,
        session_id="1",
    )

    # Test with initial message
    print("\n--- INITIAL MESSAGE ---")
    simu_state = MessagesState()
    simu_state.update(
        {"messages": [AIMessage(content="Hi, Develoepr how can I help you")]}
    )
    answer = simulate_user_answer(simu_state)
    simu_state.update(
        {"messages": simu_state.get("messages", []) + [HumanMessage(content=answer)]}
    )
    state = process_message(state, answer)

    # Print assistant response
    for i in range(1, MAX_CONVERSATION_ITERATIONS):
        print(f"\n--- INITIAL MESSAGE {i}---")
        assistant_messages = [
            msg.content
            for msg in state.get("messages", [])
            if isinstance(msg, AIMessage)
        ]
        agent_questions = None
        if assistant_messages:
            agent_questions = assistant_messages[-1]
            print(f"\n\nAI: {agent_questions}")
        simu_state.update(
            {
                "messages": simu_state.get("messages", [])
                + [AIMessage(content=agent_questions)]
            }
        )
        answer = simulate_user_answer(simu_state)
        simu_state.update(
            {
                "messages": simu_state.get("messages", [])
                + [HumanMessage(content=answer)]
            }
        )
        print(f"\nUser: {answer}")
        state = process_message(state, answer)
        if state.get("stage") == "complete":
            print("\n--- COMPLETED ---\n\n")
            print(f"\nPrometheusRule: {state.get('prometheus_rule')}")
            break
