from pydantic import BaseModel, Field


class ExtractedUserInfo(BaseModel):
    """Always use this schema to structure your response to the user."""

    functionality: str = Field(description="the service functionality")
    owner: str = Field(description="the service owner label - single-word kebab-case")
    environment: str = Field(
        description="the environment name - single-word kebab-case"
    )
    service_name: str = Field(description="the service name - single-word kebab-case")
    service_type: str = Field(
        description="the service type HTTP/Celery - single-word kebab-case"
    )
    namespace: str = Field(
        description="the answer to the user's question- single-word kebab-case"
    )
    framework: str = Field(description="the service namespace- single-word kebab-case")
    aws_dependencies: list[str] = Field(description="a list of AWS dependencies")
    load_patterns: list[str] = Field(description="a list of different load patterns")
    failure_conditions: list[str] = Field(description="a list of failure conditions")
    is_complete_info: bool = Field(description="is the questioning is complete")
    next_question: str = Field(description="the service info recommended question")
