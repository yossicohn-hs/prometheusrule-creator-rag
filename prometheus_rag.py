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
from extracted_user_info import ExtractUserInfo
from embeddings import init_vectorstore
from dotenv import load_dotenv


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
    # model="anthropic.claude-3-7-sonnet-20250219-v1:0",
    # model="anthropic.claude-3-5-haiku-20241022-v1:0",
    model="amazon.nova-pro-v1:0",
    temperature=0.01,
    max_tokens=1000,
)

def get_context_from_state(state: RuleGenerationState) -> List[Document]:
    service_info = state.get("service_info")
    service_type = service_info.service_type
    framework = service_info.framework
    aws_dependencies = service_info.aws_dependencies
    chain = (
        ChatPromptTemplate.from_template(
            """You are an AWS terminology expert helping to improve document searchability for Kubernetes PrometheusRules.

For each AWS service, service type, and framework mentioned in the input, generate all common acronyms, abbreviations, and synonyms that might appear in documentation or conversations.

Input:
- AWS Dependencies: {aws_dependencies}
- Service Types: {service_type}
- Frameworks: {framework}

Please format your response as a list of terms separated by columns, with one term per line:

Term | Type | Variations

Example output:
ALB | AWS Service | Application Load Balancer, AWS Load Balancer, ELBv2
Redis | AWS Service | ElastiCache, Amazon ElastiCache for Redis, Redis Cache
RabbitMQ | AWS Service | Amazon MQ, MQ, Message Queue, AMQP
HTTP | Service Type | Web Service, REST API, Web API, HTTP Server
Celery | Service Type | Task Queue, Async Worker, Background Worker
Python | Framework | py, Python3, Django, Flask, FastAPI
Golang | Framework | Go, Go Lang

Include variations in capitalization or phrasing that might be used in documentation to ensure comprehensive vector search indexing.
            """
        )
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
    retrieved_docs = retriever.get_relevant_documents(result_str)
    return retrieved_docs


def format_documents(documents: List[Document]):
    return "\n\n".join(
        [f"Document {i+1}:\n{doc.page_content}" for i, doc in enumerate(documents)]
    )


# Define application steps
def retrieve_context(state: RuleGenerationState):
    retrieved_docs = get_context_from_state(state)
    retrieved_docs_as_context = format_documents(retrieved_docs)
    return {"context": retrieved_docs_as_context, "stage": "generate_rule"}


# Node 1: Extract information from user inputs
def get_extracted_user_info(state: RuleGenerationState) -> ExtractUserInfo:
    """Returns the Extract User Information regarding the service and updates the State."""
    # Get all user messages
    print(f"extract_service_info: {len(state.get("messages"))}")
    # if len(state.get("messages")) > 60:
    #     return {"stage": "generate_rule"}

    # Ask LLM to extract information
    structured_llm = llm.with_structured_output(ExtractUserInfo)

    chain = (
        ChatPromptTemplate.from_template(
            """You are helping create PrometheusRules for Kubernetes services.

all_messages: {all_messages}
Current information: {current_info}

Extract service information from user input and merge with current information.

Context:
- Kubernetes Pod with Liveness/Readiness probes
- Standard PrometheusRule templates available for AWS services

Information to collect:
- Service functionality and purpose
- Service type (HTTP REST API, Celery worker, etc.)
- Implementation language/framework
- AWS dependencies
- Expected load patterns

CRITICAL REQUIREMENT: namespace, owner, service_name, service_type, and framework MUST be SINGLE WORDS (kebab-case allowed, NO SPACES). If multiple words are provided, extract only the first word or convert to kebab-case. Set to "unknown" if unclear.

Metrics thresholds needed for completion:
- HTTP: critical_request_count, lb_4xx_critical_pct, lb_5xx_critical_pct, critical_latency
- OpenSearch/Redis/RabbitMQ: cpu_critical_pct, memory_critical_pct, disk_critical_pct (warning thresholds for each)

Process:
1. Ask ONE follow-up question at a time without explanation
2. Categorize responses in the service_info structure
3. Set is_complete_info to true when sufficient information gathered

Response format:
{{
    "extract_user_info": {{
        "functionality": "...",
        "owner": "single-word",
        "service_name": "single-word",
        "service_type": "single-word",
        "namespace": "single-word",
        "framework": "single-word",
        "aws_dependencies": [...],
        "load_patterns": "...",
        "failure_conditions": "...",
        "is_complete_info": false,
        "next_question": "Your specific follow-up question here (empty if complete)"
    }}
}}
"""
        )
        | structured_llm
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
    extracted: ExtractUserInfo = chain.invoke(
        {
            "current_info": state.get("service_info", {}),
            "all_messages": all_str_messages,
        },
        config,
    )
    
    print(f"extracted: {extracted}")

    
    # Get the updated service info
    updated_info = extracted

    is_complete_info = extracted.is_complete_info

    # Track conversation turns
    attempts = state.get("attempt_count", 0)
    next_attempt = attempts + 1

    # Progress to rule generation after 3 rounds
    if is_complete_info or attempts >= 60:
        return {
            "service_info": updated_info,
            "stage": "retrieve_context",
            "attempt_count": next_attempt,
        }

    # Otherwise, move to question generation
    return {
        "service_info": updated_info,
        "stage": "generate_question",
        "attempt_count": next_attempt,
        "next_question": extracted.next_question
    }
 


# Node 1: Extract information from user inputs
def extract_service_info(state: RuleGenerationState) -> Dict:
    """Extract service information from user messages and update state."""
    # Get all user messages
    print(f"extract_service_info: {len(state.get("messages"))}")
    # if len(state.get("messages")) > 60:
    #     return {"stage": "generate_rule"}

    # Ask LLM to extract information
    chain = (
        ChatPromptTemplate.from_template(
            """You are helping create PrometheusRules for Kubernetes services.
            
all_messages: {all_messages}
Current information: {current_info}
            
Extract relevant service information from user input and merge it with current information.

Context:
- This service runs as a Kubernetes Pod with Liveness and Readiness probes
- Standard PrometheusRule templates will be provided later for AWS services (OpenSearch, ALB, Redis, RabbitMQ, etc.)

Information to collect systematically:
- Service functionality and purpose
- Service type i.e. HTTP REST API, Celery worker
- Implementation language/framework (Python, NodeJS, Golang)
- AWS service dependencies (ALB, Redis, OpenSearch, RDS Postgres, etc.)
- Expected load patterns
- Note, the info should contain some basic metrics value for criticality inorder to complete e.g.:
    - for HTTP:
        - what is the a critical High Request Count
        - LoadBalancer 4xx Critical Percentage(same for warning)
        - LoadBalancer 5xx Critical Percentage(same for warning)
        - critical latency for response time(same for warning)
    - for OpenSearch:
        - what is teh CPU Critical Percentage(same for warning)
        - what is the Memory Critical Percentage(same for warning)
        - what is the Disk Space Critical Percentage(same for warning)
    - for Redis:
        - what is the Memory Critical Percentage(same for warning)
        - what is the CPU Critical Percentage(same for warning)
        - what is the Disk Space Critical Percentage(same for warning)
    - for RabbitMQ(AWS MQ):
        - what is the Memory Critical Percentage(same for warning)
        - what is the CPU Critical Percentage(same for warning)
        - what is the Disk Space Critical Percentage(same for warning)

Process:
1. Ask only one follow-up question at a time(don't explain why you ask the question)
2. Categorize and summarize user responses in the service_info structure
3. When sufficient information is gathered OR user indicates completion, set is_complete_info to true

Response format:
{{
    "service_info": {{
        "functionality": "...",
        "owner": "...",
        "service_name": "...",
        "service_type": "...",
        "namespace": "...",
        "framework": "...",
        "aws_dependencies": [...],
        "load_patterns": "...",
        "failure_conditions": "..."
    }},
    "is_complete_info": false,
    "next_question": "Your specific follow-up question here (empty if complete)"
}}
"""
        )
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
    result_str = chain.invoke(
        {
            "current_info": state.get("service_info", {}),
            "all_messages": all_str_messages,
        },
        config,
    )

    import json

    try:
        # Clean the result if it's in markdown format
        if "```" in result_str:
            import re

            match = re.search(r"```(?:json)?\n(.*?)\n```", result_str, re.DOTALL)
            if match:
                result_str = match.group(1)
            else:
                result_str = (
                    result_str.replace("```json", "").replace("```", "").strip()
                )

        # Parse the JSON
        result = json.loads(result_str)

        # Get the updated service info
        updated_info = result.get("service_info", {})

        is_complete_info = result.get("is_complete_info", False)

        # Track conversation turns
        attempts = state.get("attempt_count", 0)
        next_attempt = attempts + 1

        # Progress to rule generation after 3 rounds
        if is_complete_info or attempts >= 60:
            return {
                "service_info": updated_info,
                "stage": "retrieve_context",
                "attempt_count": next_attempt,
            }

        # Otherwise, move to question generation
        return {
            "service_info": updated_info,
            "stage": "generate_question",
            "attempt_count": next_attempt,
            "next_question": result.get("next_question", ""),
        }
    except json.JSONDecodeError:
        # Simply proceed to question generation on error
        return {
            "stage": "generate_question",
            "attempt_count": state.get("attempt_count", 0) + 1,
        }


# Node 2: Generate follow-up question
def generate_follow_up_question(state: RuleGenerationState) -> Dict:
    """Generate a follow-up question based on current information."""
    # Ask LLM to formulate the next question
    chain = (
        ChatPromptTemplate.from_template(
            """You are helping gather information about a service to create PrometheusRules.
            
Current service information: {current_info}
all_messages: {all_messages}
advise for the next question can be {advised_next_questions}

This service is a POD running in Kubernetes that uses Probes for Liveness and Readiness checks.
All metrics needed are being collected by YACE exporters, don't question on the metrics.
PODS metrics are also being collected.

To better understand this service for PrometheusRule creation, I'll ask ONE specific follow-up question about information we still need.

Guidelines:
- Focusing on a single missing detail with each question
- Don't explain why you ask the question, but be expressive
- Keeping questions simple and direct
- Building on information already provided
- Always ask on Dependencies on AWS Services after you finish the query on the service itself


Priority information to gather (if not yet known):
- Service functionality and purpose
- Service type i.e. HTTP REST API, Celery worker
- Implementation language/framework (Python, NodeJS, Golang)
- AWS managed services it depends on (OpenSearch, ALB, Redis, RabbitMQ, etc.)
- Any specific service metrics already being collected
- Get the follwoing expected alerts by the usage of the AWS Services
    - for HTTP:
        - what is the a critical High Request Count
        - LoadBalancer 4xx Critical Percentage(same for warning)
        - LoadBalancer 5xx Critical Percentage(same for warning)
        - critical latency for response time(same for warning)
    - for OpenSearch:
        - what is teh CPU Critical Percentage(same for warning)
        - what is the Memory Critical Percentage(same for warning)
        - what is the Disk Space Critical Percentage(same for warning)
    - for Redis:
        - what is the Memory Critical Percentage(same for warning)
        - what is the CPU Critical Percentage(same for warning)
        - what is the Disk Space Critical Percentage(same for warning)
    - for RabbitMQ(AWS MQ):
        - what is the Memory Critical Percentage(same for warning)
        - what is the CPU Critical Percentage(same for warning)
        - what is the Disk Space Critical Percentage(same for warning)
- labels: e.g. owner label ,or other needed
- Namespace- the namespace of the service, this is used for the PrometheusRule namespace

Note: We'll use standardized PrometheusRule templates for AWS services later, so we don't need detailed metric specifications at this stage.
The resulted YAML should be verified, no redundant character or new lines
"""
        )
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

    # Return the follow-up question and stay in gather_info stage
    return {
        "messages": state.get("messages", []) + [AIMessage(content=follow_up_question)],
        "stage": "wait_for_user",
    }


# Node 3: Generate PrometheusRule
def generate_rule(state: RuleGenerationState) -> Dict:
    """Generate a PrometheusRule based on service info and examples."""
    # Retrieve examples
    context = state.get("context")

    # Generate rule
    chain = (
        ChatPromptTemplate.from_template(
            """You are an expert in Kubernetes monitoring and Prometheus.

Task: Create a comprehensive PrometheusRule custom resource for the Kubernetes service described below.

SERVICE DETAILS:
{service_info}

REFERENCE EXAMPLES:
{context}

CRITICAL INSTRUCTIONS:
1. For EVERY AWS dependency mentioned in service_info (ALB, OpenSearch, Redis, etc.):
   - Copy ALL alert rules from the corresponding reference examples WITHOUT OMITTING ANY
   - Do not summarize, combine, or simplify the AWS service alert rules
   - Include all expressions, labels, and annotations exactly as they appear in the examples

2. Base service monitoring on type:
   - If HTTP service: Copy ALL rules from http-service.rules example
   - If Celery service: Copy ALL rules from celery-service.rule example
   - Always include ALL standard POD metrics (CPU/Memory/Health) without exception

3. Structure the final YAML to combine:
   - Service-specific rules (based on HTTP/Celery type)
   - Complete AWS dependency rules for EACH dependency
   - Standard POD metrics
   
4. Use labels in the following manner:
   - owner: [team name from service_info]
   - severity: [as defined in original rules]
   - service: [service name]

5. Ensure all alert expressions reference the correct service name and namespace
6. Note,
a Golang/NodeJS(non-Python) services PrometheusRule cannot use the Python example metrics like http_requests_total or http_request_duration_seconds_bucket.
In the non-Python services you can only use the metrics that are being collected by YACE exporters.
The final PrometheusRule must contain EVERY SINGLE ALERT from the reference examples that applies to this service's type and dependencies. Do not omit any alerts from the relevant examples.

Return ONLY the complete YAML with no additional explanation."""
        )
        | llm
        | StrOutputParser()
    )

    config = {"configurable": {"thread_id": state.get("session_id")}}
    rule = chain.invoke(
        {
            "service_info": dumps(state.get("service_info", {}), indent=2),
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

    return {
        "prometheus_rule": rule,
        "context": context,
        "messages": state.get("messages", []) + [AIMessage(content=response)],
        "stage": "complete",
    }


# Process user input
def handle_user_input(state: RuleGenerationState, user_input: str) -> Dict:
    """Add user input to messages and set stage for processing."""
    # Add user message to conversation history
    updated_messages = state.get("messages", []) + [HumanMessage(content=user_input)]

    # If we're at the complete stage, stay there
    if state.get("stage") == "complete":
        return {"messages": updated_messages, "stage": "complete"}

    # Otherwise, always start with information extraction
    return {"messages": updated_messages, "stage": "extract_info"}


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
    elif stage == "generate_rule":
        return "generate_rule"
    elif stage == "complete":
        return "end"
    else:
        return "extract_info"  # Default to information extraction


# Build and return the workflow graph
def build_rag_graph():
    """Create the RAG workflow with separate question generation."""
    workflow = StateGraph(RuleGenerationState)

    # Add nodes with clear separation of concerns
    workflow.add_node("extract_info", get_extracted_user_info)
    workflow.add_node("generate_question", generate_follow_up_question)
    workflow.add_node("retrieve_context", retrieve_context)
    workflow.add_node("generate_rule", generate_rule)

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
            "generate_rule": "generate_rule",
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
        "generate_rule", router, {"generate_rule": END, "complete": END, "end": END}
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
        ChatPromptTemplate.from_template(
            """You are simulating a developer who maintains one of these services that uses an AI model. Your task is to provide realistic answers as this developer would when responding to questions about their system.

Respond only to the specific questions asked without offering additional help or information. Keep responses concise and technical.

Services you maintain (you'll be simulating expertise in one of these):

1. Payment Processing Service (Python/Celery)
   - Event-driven architecture processing payments via RabbitMQ (AWS MQ)
   - owner: "infra-payments"
   - Dependencies: AWS Redis, AWS MQ
   - Current throughput: 40 tasks/second
   - Target capacity: 400 tasks/second

2. Query Processing Service (Golang/HTTP)
   - Processes HTTP requests for payment information
   - owner: "payments"
   - Dependencies: AWS OpenSearch, AWS Application Load Balancer
   - Current throughput: 100 requests/second
   - SLA requirements:
     - Service latency < 100ms
     - OpenSearch query latency < 200ms

3. Query Processing Service (Golang/HTTP)
   - Processes HTTP requests for payment information
   - owner: "payments"
   - Dependencies: AWS OpenSearch, AWS Application Load Balancer
   - Current throughput: 100 requests/second
   - SLA requirements:
     - Service latency < 100ms
     - OpenSearch query latency < 200ms

Respond as the developer of the service relevant to this query:
{agent_question}

Previous conversation context:
{all_answers}

Return only your direct answer as a string without repeating or reformatting the question."""
        )
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
    for i in range(1, 11):
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
