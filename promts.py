EXTRACT_INFO_PROMT = """// use this to clearly define the task and job needed by the model
Task:
Extract and organize Kubernetes service information for PrometheusRules creation.

// use this to provide contextual information related to the task
Context information:
- The model needs to collect specific information about a Kubernetes service
- Information will be collected incrementally through a Q&A process
- all_messages: {all_messages}
- Current information: {current_info}

// use this to provide any model instructions that you want model to adhere to
Model Instructions:
- Extract relevant service information from user input and merge it with current information
- Ask only one follow-up question at a time
- Update the response structure with each user response
- For required fields, enforce single-word kebab-case format
- For environment, only accept "production", "preprod", or "dev"
- Set "is_complete_info" to true when:
  1. All 5 required fields have non-empty values AND number of questions asked was > 10
  2. User provided information that addresses framework, service_type, 5 other required fields, environment AND number of questions asked was > 10
  3. User explicitly states they are done or don't have more information
  4. There are no more logical questions to ask given the context
- When setting "is_complete_info" to true, set next_question to "Information collection complete."
- Required fields: namespace, owner, service_name, service_type, framework, environment

// use this to provide response style and formatting guidance
Response style and format requirements:
- Return a JSON object with the following structure:
{{
  "Service_info":
    {{
      "functionality": "",                   // the service functionality
      "owner": "",                           // the service owner label - single-word kebab-case
      "environment": "",                     // deployment environment (must be one of: production, preprod, dev)
      "service_name": "",                    // the service name - single-word kebab-case
      "service_type": "",                    // the service type HTTP/Celery - single-word kebab-case
      "namespace": "",                       // the kubernetes namespace - single-word kebab-case
      "framework": "",                       // the programming framework/language - single-word kebab-case
      "aws_dependencies": [],                // a list of AWS dependencies
      "load_patterns": [],                   // a list of different load patterns
      "failure_conditions": [],              // a list of failure conditions
      "is_complete_info": false,             // is the questioning is complete
      "next_question": ""                    // the service info recommended question
    }}
}}
"""

GENERATE_QUESTION_PROMT = """You are helping gather information about a service to create PrometheusRules.

Current service information: {current_info}
previous questions, answers: {all_messages}
advise for the next question can be {advised_next_questions}

I WILL NOT ASK QUESTIONS THAT APPEAR ANYWHERE IN all_messages!

Don't invent data instead of the user, just ask for the missing information.

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

Required Information (by the order, track what's already known):
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
- Review all previous questions asked by you(previous questions, answers), as well as Current service information to identify what has already been asked
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

Please format your response as a list of terms separated by columns, with one term per line in the following values only:

Term | Type | Variations

Please stick to the following Possible values:
ALB | AWS Service | Application Load Balancer, AWS Load Balancer, ALB
Redis | AWS Service | Redis, Redis Cache
RabbitMQ | AWS Service | Amazon MQ, MQ, Message Queue, AMQP
HTTP | Service Type | Web Service, REST API, HTTP Server
Celery | Service Type | RabbitMQ, Redis
Python | Framework | Python3, Flask, FastAPI
Golang | Framework | Go, GoLang
NodeJS | Framework | Nodejs, Typescipt, Javascript

this would be used in query the vector search indexing.
"""


GENERATE_PROMETHEUS_RULE_PROMT = """You are an expert in Kubernetes monitoring and Prometheus.

Task: Create a comprehensive PrometheusRule custom resource for the Kubernetes service described below.


CRITICAL INSTRUCTIONS:
1. DEPENDENCY ALERTS - HIGHEST PRIORITY:
   - Extract ALL dependencies from service_info["aws_dependencies"] array
   - For EACH identified dependency in the array, you MUST include ALL corresponding alert rules
   - Specifically check for "AWS Redis", "Redis", "ElastiCache", "AWS MQ", "RabbitMQ" and include ALL related alerts
   - Exact copy is required - do not modify, summarize, or omit ANY dependency alert rules
   - IMPORTANT: If "AWS Redis" or "Redis" appears ANYWHERE in service_info, you MUST include ALL Redis alert rules

2. Additional dependencies check:
   - Also scan service_info["failure_conditions"] for any mentioned dependencies
   - If any dependency (like "Redis connection issues") is mentioned here, ensure its alerts are included

3. Service-type monitoring:
   - Use service_info["service_type"] to determine monitoring type
   - For service_type = "celery": Include ALL rules from celery-service.rule example
   - For service_type = "http": Include ALL rules from alb.rules, if its a Python you may use http-service.rules as well
   - if you have redis use redis.rules as well other dependencies
   - if you have Opensearch use opensearch.rules as well other dependencies
   - if you have HTTP use alb.rules
   - All PrometehusRules MUST have the DesiredVsActualPods and HighMemoryConsumption rules included

4. Standard monitoring:
   - ALWAYS include ALL standard POD metrics (CPU/Memory/Health)
   - These are required for every service regardless of type

5. Kubernetes YAML structure:
   - Group alerts by type (service-specific, each dependency, standard metrics)
   - Ensure proper indentation and YAML formatting

6. Labels configuration:
   - owner: service_info["owner"]
   - severity: [as defined in original rules]
   - service: service_info["service_name"]

7. Technical requirements:
   - All alert expressions MUST reference the correct service_name and namespace from service_info
   - For non-Python services, use only metrics collected by YACE exporters
   - Do not use Python-specific metrics for non-Python services
   - You MUST be sure to generate a full Valid PrometheusRule YAML

VERIFICATION CHECKLIST (MANDATORY):
- Did you include ALL Redis alerts? (CRITICAL CHECK)
- Did you include ALL RabbitMQ alerts? (CRITICAL CHECK)
- Did you check for ALL dependencies in both aws_dependencies AND failure_conditions?
- Did you include ALL service-type specific alerts based on service_type value?
- Did you include ALL standard POD metrics?
- Did you correctly set all labels using values from service_info?

The final PrometheusRule MUST contain EVERY SINGLE ALERT from the REFERENCE EXAMPLES that applies to this service's type and ALL its dependencies without exception.

SERVICE DETAILS:
{service_info}

REFERENCE EXAMPLES:
{context}

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
