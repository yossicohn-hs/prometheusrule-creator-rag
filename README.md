

The presentation maintains focus on your specific use case (PrometheusRule generation) while explaining how the different components work together:

The UI for user interaction
The structured information extraction with Pydantic
The follow-up question generation for missing information
The RAG system with ChromaDB for retrieving relevant examples
The final rule generation with validation


# LangGraph + RAG: Building an Agentic PrometheusRule Generator

- Explaining the architecture with a visual flow diagram
- Highlighting the key components of your implementation
- Showing practical code examples of the LangGraph workflow
- Demonstrating a real-world example with user input and system processing
- Emphasizing the benefits for developers to adopt this technology
- Stack Observability and Debug

## Why This Matters
- **Automation of Complex Tasks**: Reduce manual effort in creating Prometheus monitoring rules
- **Knowledge Reuse**: Leverage existing rules as examples through RAG
- **Structured Outputs**: Generate valid YAML that works immediately

## The Architecture

```
┌─────────────┐     ┌───────────────┐     ┌─────────────┐     ┌───────────────┐
│ User (Chat) │────▶│ Extract Info  │────▶│ Generate    │────▶│ RAG Document  │
└─────────────┘     │ (Pydantic)    │     │ Questions   │     │ Retrieval     │
                    └───────────────┘     └─────────────┘     └───────┬───────┘
                            ▲                                          │
                            │                                          ▼
                    ┌───────┴───────┐                        ┌─────────────────┐
                    │ Validate &    │◀───────────────────────│ Generate        │
                    │ Return Rule   │                        │ PrometheusRule  │
                    └───────────────┘                        └─────────────────┘
```

## Key Components

### 1. User Interface
- Simple chat interface
- Context preservation across interactions

### 2. LangGraph Service
- **State Management**: Tracking conversation and extracted parameters
- **Structured Data Flow**: Pydantic models ensuring type safety
- **Decision Making**: Dynamic path routing based on information completeness

### 3. Extract User Info Node
- Identifies metric names, thresholds, and alert severity
- Structured output using Pydantic models
- Decision logic for information completeness

### 4. Question Generation Node
- Creates targeted follow-up questions based on missing information
- Maintains context from previous interactions

### 5. RAG with ChromaDB
- Vector embeddings of existing PrometheusRules
- Semantic similarity search for relevant examples
- Context augmentation for the LLM

### 6. PrometheusRule Generation
- Produces valid YAML configuration
- Follows best practices from retrieved examples
- Built-in validation before returning

## Technical Implementation Details

### LangGraph Flow Definition
```python
from langgraph.graph import StateGraph, END
from pydantic import BaseModel

class ConversationState(BaseModel):
    metrics: Optional[List[str]] = None
    threshold: Optional[float] = None
    severity: Optional[str] = None
    namespace: Optional[str] = None
    rule_yaml: Optional[str] = None
    
# Define the workflow
workflow = StateGraph(ConversationState)

# Add nodes
workflow.add_node("extract_info", extract_user_info)
workflow.add_node("generate_questions", generate_follow_up_questions)
workflow.add_node("retrieve_documents", retrieve_relevant_documents)
workflow.add_node("generate_rule", generate_prometheus_rule)

# Define edges
workflow.add_edge("extract_info", has_complete_info)
workflow.add_conditional_edges(
    "extract_info",
    has_complete_info,
    {
        True: "retrieve_documents",
        False: "generate_questions"
    }
)
workflow.add_edge("generate_questions", "extract_info")
workflow.add_edge("retrieve_documents", "generate_rule")
workflow.add_edge("generate_rule", END)
```

## Example Results

**User Input:**
"Create an alert when CPU usage is too high"

**System Processing:**
1. **Extract Info**: Identifies metric (CPU usage) but no threshold or severity
2. **Generate Questions**: "What threshold would you like to set for high CPU usage? And what severity should this alert have?"
3. **User Response**: "Above 80% for more than 5 minutes, critical severity"
4. **Extract Info**: Updates state with complete information
5. **RAG Retrieval**: Finds similar CPU usage alert examples
6. **Generate Rule**: Creates valid YAML configuration

**Final Output:**
```yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: high-cpu-usage
  namespace: monitoring
spec:
  groups:
  - name: cpu.rules
    rules:
    - alert: HighCPUUsage
      expr: (100 - (avg by(instance) (irate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)) > 80
      for: 5m
      labels:
        severity: critical
      annotations:
        summary: High CPU usage detected
        description: CPU usage on {{ $labels.instance }} has exceeded 80% for more than 5 minutes.
```

## Benefits for Developers

- **Time Savings**: Generate complex rules in seconds instead of minutes/hours
- **Reduced Errors**: Validated output based on proven examples
- **Knowledge Sharing**: Learn from existing patterns in your organization
- **Extensibility**: Add new document types to RAG or expand the workflow

## Getting Started

1. Clone the repo: `git clone https://github.com/your-org/prometheus-rule-agent`
2. Install dependencies: `pip install -r requirements.txt` 
3. Add your own PrometheusRules to the examples directory
4. Run the service: `python service.py`
5. Open the UI: `http://localhost:8000`

## What's Next?

- Support for more Kubernetes resource types
- Integration with GitOps workflow
- Advanced validation with Prometheus rule testing
- Multi-user support with authorization

## Questions?