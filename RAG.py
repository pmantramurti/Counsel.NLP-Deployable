from langchain_huggingface import HuggingFaceEndpoint, HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
from langchain import hub
from langgraph.graph import START, StateGraph
from typing_extensions import List, TypedDict
from langchain.schema import Document
from huggingface_hub import login
import requests
import time

login("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")

# LOAD VECTOR STORE
embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2", model_kwargs={'device': 'cpu'})
directory = "./vector__store"
vector_store = Chroma(persist_directory=directory, embedding_function=embeddings)
vector_store.get()

uploaded_docs = {}

Llama_model = "meta-llama/Llama-3.2-1B-Instruct"

llm = HuggingFaceEndpoint(
    repo_id=Llama_model,
    task="text-generation",
    max_new_tokens=512,
    temperature=0.7,
    do_sample=True,
    repetition_penalty=1.03
)


# GET LIST OF COURSES
with open("courses.txt", "r") as f:
  courses = f.read().splitlines()

def classify_question(question: str):
  if "between" in question:
    filters = []
    for c in courses:
      if c in question:
        filters.append({"class_name":{"$eq": c}})
    filter = {"$or": filters}
    return filter if len(filters) != 0 else None
  elif "require" in question or "have" in question:
    if "corequisite" in question and "prerequisite" in question:
      coreq_pos = question.find("corequisite")
      prereq_pos = question.find("prerequisite")
      filters = []
      if coreq_pos < prereq_pos:
        sec_1 = question[:coreq_pos]
        sec_2 = question[coreq_pos:]
        i = 1
        j = 1
        for c in courses:
          if c in sec_1:
            filters.append({f"coreq_{i}": {"$eq": c}})
            i += 1
          if c in sec_2:
            filters.append({f"prereq_{j}": {"$eq": c}})
            j += 1
        filter = {"$and": filters} if "and" in question else {"$or": filters}
        if len(filters) < 2:
          filter = filters
        return filter[0] if len(filters) != 0 else None
      else:
        sec_1 = question[:prereq_pos]
        sec_2 = question[prereq_pos:]
        for c in courses:
          i = 1
          j = 1
          if c in sec_1:
            filters.append({f"prereq_{i}": {"$eq": c}})
            i += 1
          if c in sec_2:
            filters.append({f"coreq_{j}": {"$eq": c}})
            j += 1
        filter = {"$and": filters} if "and" in question else {"$or": filters}
        if len(filters) < 2:
          filter = filters
        return filter[0] if len(filters) != 0 else None

    # PREREQ
    elif "prerequisite" in question:
      # Require multiple prerequisites
        filters = []
        i = 1
        for c in courses:
          if c in question:
            filters.append({f"prereq_{i}": {"$eq": c}})
            i += 1
        filter = {"$and": filters} if "and" in question else {"$or": filters}
        if len(filters) < 2:
          filter = filters
        return filter[0] if len(filters) != 0 else None
    else:
      filters = []
      i = 1
      for c in courses:
        if c in question:
          filters.append({f"coreq_{i}": {"$eq": c}})
          i += 1
      filter = {"$and": filters} if "and" in question else {"$or": filters}
      if len(filters) < 2:
        filter = filters
      return filter[0] if len(filters) !=0 else None
  elif "need" in question:
    last_course = ""
    for c in courses:
      if c in question:
        if question.find(last_course) < question.find(c):
          last_course = c
    return {"class_name": last_course}
  else:
    #FIND THE CLASS
    for c in courses:
      if c in question:
        return {"class_name": c}
  return None


class State(TypedDict):
    question: str
    context: List[Document]
    answer: str


def retrieve(state: State):
    filter = classify_question(state["question"])
    retrieved_docs = vector_store.similarity_search(state["question"],
        k=5,
        filter=filter)
    return {"context": retrieved_docs}


def generate(state: State):
    docs_content = "\n\n".join(doc.page_content for doc in state["context"])
    messages = f"""### System:
        You are an academic advising assistant. Answer the student's question directly and completely, but do not include extra information beyond what was asked.

        ### User:
        Question: {state['question']}

        ### Context:
        {docs_content}

        ### Answer:
        """
    response = llm.invoke(messages)
    return {"answer": response}


graph_builder = StateGraph(State).add_sequence([retrieve, generate])
graph_builder.add_edge(START, "retrieve")
graph = graph_builder.compile()
__all__ = ["get_chatbot_response", "uploaded_docs"]

def get_chatbot_response(user_question):
  retries = 3  # Number of retry attempts
  for attempt in range(retries):
    try:
      response = graph.invoke({"question": user_question})
      return response["answer"].strip()
    except requests.exceptions.HTTPError as e:
      if e.response.status_code == 503:  # Handle server unavailability
        print(f"Server unavailable. Retrying ({attempt + 1}/{retries})...")
        time.sleep(2)  # Wait before retrying
      else:
        raise e  # Re-raise the error if it's not a 503
  return "Error: The chatbot service is temporarily unavailable. Please try again later."