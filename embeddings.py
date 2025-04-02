import os
import yaml
from typing import List, Dict, Any

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.documents import Document
from langchain_community.vectorstores import Chroma

# from langchain_openai import OpenAIEmbeddings
from langchain_community.embeddings import HuggingFaceBgeEmbeddings
from langchain_core.vectorstores import VectorStore
from dotenv import load_dotenv

load_dotenv(verbose=True)


def load_yaml_files(directory_path: str) -> List[Document]:
    """
    Load all YAML files from a directory and convert them to LangChain Document objects.

    Args:
        directory_path: Path to the directory containing YAML files

    Returns:
        List of Document objects with YAML content and metadata
    """
    documents = []

    # Ensure directory exists
    if not os.path.exists(directory_path):
        print(f"Creating directory {directory_path}")
        os.makedirs(directory_path)
        return documents

    # Iterate through all files in the directory
    for filename in os.listdir(directory_path):
        if filename.endswith(".yaml") or filename.endswith(".yml"):
            file_path = os.path.join(directory_path, filename)

            try:
                with open(file_path, "r") as file:
                    # Load and parse YAML content
                    yaml_content = yaml.safe_load(file)

                    # Convert YAML to string representation for indexing
                    yaml_str = yaml.dump(yaml_content)

                    # Extract some basic metadata from the YAML if possible
                    metadata = {
                        "source": filename,
                        "file_path": file_path,
                    }

                    # Add YAML-specific metadata if available
                    if isinstance(yaml_content, dict):
                        if "kind" in yaml_content:
                            metadata["kind"] = yaml_content["kind"]
                        if (
                            "metadata" in yaml_content
                            and "name" in yaml_content["metadata"]
                        ):
                            metadata["name"] = yaml_content["metadata"]["name"]
                        if "apiVersion" in yaml_content:
                            metadata["api_version"] = yaml_content["apiVersion"]

                    # Create a Document object
                    doc = Document(page_content=yaml_str, metadata=metadata)
                    documents.append(doc)
                    print(f"Loaded {filename}")
            except yaml.YAMLError as e:
                print(f"Error parsing {filename}: {e}")
            except Exception as e:
                print(f"Error processing {filename}: {e}")

    return documents


def setup_vectorstore(
    documents: List[Document], persist_directory: str = None
) -> VectorStore:
    """
    Set up a ChromaDB vector store with the provided documents.

    Args:
        documents: List of Document objects to index
        persist_directory: Optional directory to persist the vector store

    Returns:
        An initialized vector store
    """

    # Initialize embedding model
    # embeddings = OpenAIEmbeddings()
    embeddings = HuggingFaceBgeEmbeddings(model_name="BAAI/bge-large-en-v1.5")

    if (
        os.path.exists(persist_directory)
        and os.path.isdir(persist_directory)
        and len(os.listdir(persist_directory)) > 0
    ):
        print(f"Loading existing vector store from {persist_directory}")

        # Load existing vector store
        vectorstore = Chroma(
            persist_directory=persist_directory, embedding_function=embeddings
        )

        print(f"Loaded vector store with {vectorstore._collection.count()} documents")
        return vectorstore

    # Create the vector store
    if persist_directory:
        # Create persistent vector store
        vectorstore = Chroma.from_documents(
            documents=documents,
            embedding=embeddings,
            persist_directory=persist_directory,
        )
        # Persist the vector store to disk
        vectorstore.persist()
        print(f"Vector store persisted to {persist_directory}")
    else:
        # Create in-memory vector store
        vectorstore = Chroma.from_documents(documents=documents, embedding=embeddings)

    print(f"Indexed {len(documents)} documents in the vector store")
    return vectorstore


def create_retriever(
    vectorstore: VectorStore, search_kwargs: Dict[str, Any] = None
) -> Any:
    """
    Create a retriever from the vector store with specified search parameters.

    Args:
        vectorstore: The vector store to create a retriever from
        search_kwargs: Optional search parameters like k (number of results to return)

    Returns:
        A retriever that can be used to get relevant documents
    """
    if search_kwargs is None:
        search_kwargs = {"k": 3}  # Default to returning top 3 results

    return vectorstore.as_retriever(search_kwargs=search_kwargs)


def init_vectorstore(topk: int) -> Any:
    yaml_dir = "./sample_prometheus_rules"
    persist_dir = "./chroma_db"

    # Load documents
    documents = load_yaml_files(yaml_dir)

    # Setup vector store
    vectorstore = setup_vectorstore(documents, persist_directory=persist_dir)

    # Create retriever
    retriever = create_retriever(vectorstore, search_kwargs={"k": topk})
    return retriever


# # Example usage
# if __name__ == "__main__":
#     # Directory containing YAML files
#     yaml_dir = "./sample_prometheus_rules"
#     persist_dir = "./chroma_db"

#     # Load documents
#     documents = load_yaml_files(yaml_dir)

#     # Setup vector store
#     vectorstore = setup_vectorstore(documents, persist_directory=persist_dir)

#     # Create retriever
#     retriever = create_retriever(vectorstore, search_kwargs={"k": 2})

#     # Test retrieval
#     all_info = query = (
#         "I have a service using AWS ALB(aws_applicationelb) and AWS Opensearch, can you help me create a PrometheusRule ?"
#     )
#     print(f"\nQuery: {query}")

#     retrieved_docs = retriever.get_relevant_documents(query)

#     print(f"Retrieved {len(retrieved_docs)} documents:")
#     for i, doc in enumerate(retrieved_docs):
#         print(f"\nDocument {i+1} (Source: {doc.metadata.get('source')}):")
#         print(f"Relevance: This document is from {doc.metadata.get('source')}")

#         # Print a snippet of the content (first 150 chars)
#         content_preview = (
#             doc.page_content[:250] + "..."
#             if len(doc.page_content) > 150
#             else doc.page_content
#         )
#         print(f"Content Preview: {content_preview}")

#     # Initialize LLM with LangChain Core
# from langchain_openai import ChatOpenAI

# llm = ChatOpenAI(model="gpt-4o", temperature=0)
# # Use LangChain Core Runnables
# chain = (
#     ChatPromptTemplate.from_template(
#         """
#     You are analyzing a request for creating PrometheusRules for Kubernetes services.

#     User request: {question}

#     Analyze what information we already have about the service and what we still need to know.
#     Determine whether we need to ask follow-up questions.

#     Use the retrived docs here to define the resulted PromeheuRule:
#     {{retrieved_docs}}
#     Return a JSON with the following structure:
#     {{
#         "existing_info": {{key details already provided by the user}},
#         "missing_info": [list of information we still need],
#         "needs_more_info": boolean indicating if we need to ask follow-up questions,
#         "prometheus_rule": {{the PrometheusRule to be created at this phase}},
#     }}
#     """
#     )
#     | llm
#     | StrOutputParser()
# )

# result_str = chain.invoke(
#     {
#         "question": query,
#         "retrieved_docs": "\n\n---\n\n".join(
#             [doc.page_content for doc in retrieved_docs]
#         ),
#     }
# )
# print(f"\nResult: {result_str}")
