from pydantic import BaseModel, Field  


class ExtractUserInfo(BaseModel):
    """Always use this schema to structure your response to the user."""
    functionality: str = Field(description="the service functionality")
    owner: str = Field(description="the service owner label", pattern=r"^\S+$")
    service_name: str = Field(description="the service name", pattern=r"^\S+$")
    service_type: str = Field(description="the service type HTTP/Celery")
    namespace: str = Field(description="the answer to the user's question", pattern=r"^\S+$")
    framework: str = Field(description="the service namespace", pattern=r"^\S+$")
    aws_dependencies: list[str] = Field(description="a list of AWS dependencies")
    load_patterns: list[str] = Field(description="a list of different load patterns")
    failure_conditions: list[str] = Field(description="a list of failure conditions")
    is_complete_info: bool = Field(description="is the questioning is complete")
    next_question: str = Field(description="the service info recommended question")
