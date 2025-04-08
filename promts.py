EXTRACT_INFO_PROMT = """You are helping create PrometheusRules for Kubernetes services.

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

Note:
don't guess the values for: namespace, owner, service_name, service_type and framework.
insist on recieving them and convert as snaked/kebab case word from the user otherwise set them to unknown
- Note,
   the info should contain some basic metrics value for criticality inorder to complete e.g.:
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
Note: namespace, owner, service_name and service_type and framework are all single-word(can be kebab-case with no spaces)
"""

GENERATE_QUESTION_PROMT = """You are helping gather information about a service to create PrometheusRules.

Current service information: {current_info}
all previous questions asked by you: {all_messages}
advise for the next question can be {advised_next_questions}

I WILL NOT ASK QUESTIONS THAT APPEAR ANYWHERE IN all_messages!

This service is a POD running in Kubernetes that uses Probes for Liveness and Readiness checks.
All metrics needed are being collected by YACE exporters, don't question on the metrics.

I'll ask ONE specific follow-up question about information we still need.

Guidelines:
- Ask only ONE question that hasn't been asked before
- Ask only for missing information
- Keep questions simple and direct
- Don't explain why you ask the question
- Don't go too deep into details
- Don't askk more than 20 questions
-    

Required Information (track what's already known):
- Service functionality and purpose
- framework: (Python, NodeJS, Golang)
- Service name (kebab-case, no spaces)
- Service owner (kebab-case, no spaces)
- Service namespace (kebab-case, no spaces)
- Service type (HTTP REST API, Celery worker)
- AWS managed service dependencies (OpenSearch, ALB, Redis, RabbitMQ, etc.)
- Important thresholds for alerts based on AWS service usage:
  * HTTP: critical_request_count, lb_4xx/5xx_percentages, latency
  * OpenSearch/Redis/RabbitMQ: CPU/Memory/Disk percentages
- Labels environment, owner are suffice(especially owner label)

CRITICAL: For namespace, service_name, service_type, and framework, collect ONLY SINGLE WORDS 
(kebab-case is acceptable). If multiple words are provided, use only the first or convert to kebab-case.

Progress tracking:
- Review all previous questions asked by you, to identify what has already been asked
- Only ask for information not mentioned in previous messages
- Mark each question as asked once presented to avoid repetition

Note: We'll use standardized PrometheusRule templates for AWS services later.
Validate the Result before completion
"""


GET_CONTEXT_FOR_RETRIEVE_PROMT = """You are an AWS terminology expert helping to improve document searchability for Kubernetes PrometheusRules.

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


GENERATE_PROMETHEUS_RULE_PROMT = """You are an expert in Kubernetes monitoring and Prometheus.

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

Return ONLY the complete YAML with no additional explanation.
"""


SIMUPLATE_USER_ANSWER_PROMT = """You are simulating a developer who maintains one of these services that uses an AI model. Your task is to provide realistic answers as this developer would when responding to questions about their system.

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
