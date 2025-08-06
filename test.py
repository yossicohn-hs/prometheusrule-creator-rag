from json import dumps
from typing import Dict, List, Optional, Any
from pydantic import Field
from langchain import hub
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.documents import Document
from langgraph.graph import StateGraph, END
from langgraph.graph import MessagesState
from langgraph.checkpoint.memory import MemorySaver

from embeddings import init_vectorstore
from dotenv import load_dotenv
from extracted_user_info import ExtractUserInfo
from langchain_aws import ChatBedrockConverse

# model="amazon.nova-pro-v1:0",

llm = ChatBedrockConverse(
    # model="anthropic.claude-3-7-sonnet-20250219-v1:0",
    # model="anthropic.claude-3-5-haiku-20241022-v1:0",
    model="amazon.nova-pro-v1:0",
    temperature=0.01,
    max_tokens=1000,
)
structured_llm = llm.with_structured_output(ExtractUserInfo)
# llm_with_tools = llm.bind_tools([ExtractUserInfo])


chain = (
    ChatPromptTemplate.from_template(
        """I have a Golang service used as an HTTP serviceand dependeing AWS Opensearch as well as AWS ALB
            the service name is imageme because it is creating images and  the namespace is imageme-ns
            """
    )
    | structured_llm
)


# config = {"configurable": {"thread_id":"2"}}
result = chain.invoke({})


messages = [
    ("system", "You are a helpful translator. Translate the user sentence to French."),
    ("human", "I love programming."),
]
llm.invoke(messages)


from typing import List, Optional
from pydantic import BaseModel, Field
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_aws import ChatBedrockConverse
from extracted_user_info import extractUserInfo


# 1. Define your Pydantic model
class PrometheusRule(BaseModel):
    name: str = Field(description="Name of the alert rule")
    description: str = Field(description="Description of what the alert monitors")
    expr: str = Field(description="PromQL expression for the alert condition")
    for_duration: str = Field(
        description="Duration the condition must be true before alerting"
    )
    severity: str = Field(description="Alert severity (warning, critical, etc.)")
    service: str = Field(description="Service this alert is monitoring")

    class Config:
        schema_extra = {
            "example": {
                "name": "HighCPUUsage",
                "description": "CPU usage above 80% for 5 minutes",
                "expr": 'sum(rate(container_cpu_usage_seconds_total{namespace="myapp"}[5m])) / sum(kube_pod_container_resource_limits_cpu_cores{namespace="myapp"}) > 0.8',
                "for_duration": "5m",
                "severity": "warning",
                "service": "myapp",
            }
        }


# 2. Create a parser for your model
parser = PydanticOutputParser(pydantic_object=extractUserInfo)

# 3. Initialize your Bedrock model
llm = ChatBedrockConverse(
    model="anthropic.claude-3-7-sonnet-20250219-v1:0",
    temperature=0.01,
    max_tokens=None,
)

# 4. Create your prompt with format instructions
prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You are an expert in creating Prometheus alert rules for Kubernetes services.
    
    {format_instructions}
    
    Based on the information provided, create a properly formatted Prometheus alert rule.""",
        ),
        ("human", "{query}"),
    ]
)

# 5. Build your chain with the parser
# chain = (
#     prompt.partial(format_instructions=parser.get_format_instructions())
#     | llm
#     | parser
# )

# 6. Invoke the chain
# result = chain.invoke({
#     "query": "Create an alert for high memory usage in the HTTP service namespace that triggers when memory usage is above 85% for 10 minutes."
# })


prompt = ChatPromptTemplate.from_template(
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
  """
)

chain = (
    prompt.partial(format_instructions=parser.get_format_instructions()) | llm | parser
)

result = chain.invoke({"all_messages": [], "current_info": {}})
# # Now result is a PrometheusRule object you can work with
# print(result.name)
# print(result.expr)


from typing import List, Optional
from pydantic import BaseModel, Field
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_aws import ChatBedrockConverse


# 1. Define your Pydantic model
class PrometheusRule(BaseModel):
    name: str = Field(description="Name of the alert rule")
    description: str = Field(description="Description of what the alert monitors")
    expr: str = Field(description="PromQL expression for the alert condition")
    for_duration: str = Field(
        description="Duration the condition must be true before alerting"
    )
    severity: str = Field(description="Alert severity (warning, critical, etc.)")
    service: str = Field(description="Service this alert is monitoring")

    class Config:
        schema_extra = {
            "example": {
                "name": "HighCPUUsage",
                "description": "CPU usage above 80% for 5 minutes",
                "expr": 'sum(rate(container_cpu_usage_seconds_total{namespace="myapp"}[5m])) / sum(kube_pod_container_resource_limits_cpu_cores{namespace="myapp"}) > 0.8',
                "for_duration": "5m",
                "severity": "warning",
                "service": "myapp",
            }
        }


# 2. Create a parser for your model
parser = PydanticOutputParser(pydantic_object=PrometheusRule)

# 3. Initialize your Bedrock model
llm = ChatBedrockConverse(
    model="anthropic.claude-3-7-sonnet-20250219-v1:0",  # Or whichever model is working
    temperature=0.01,
    max_tokens=None,
)

# 4. Create your prompt with format instructions
prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You are an expert in creating Prometheus alert rules for Kubernetes services.
    
    {format_instructions}
    
    Based on the information provided, create a properly formatted Prometheus alert rule.""",
        ),
        ("human", "{query}"),
    ]
)

# 5. Build your chain with the parser
chain = (
    prompt.partial(format_instructions=parser.get_format_instructions()) | llm | parser
)

# 6. Invoke the chain
result = chain.invoke(
    {
        "query": "Create an alert for high memory usage in the HTTP service namespace that triggers when memory usage is above 85% for 10 minutes."
    }
)

# Now result is a PrometheusRule object you can work with
print(result.name)
print(result.expr)

# next_question': 'Information collection complete.'}
# /Users/yossi.cohn/hiredscore/git/prometheusrule-creator-rag/prometheus_rag.py:79: LangChainDeprecationWarning: The method `BaseRetriever.get_relevant_documents` was deprecated in langchain-core 0.1.46 and will be removed in 1.0. Use :meth:`~invoke` instead.
#   retrieved_docs = retriever.get_relevant_documents(result_str)
