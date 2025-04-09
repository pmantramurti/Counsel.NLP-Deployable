import os
import zipfile
import streamlit as st
import requests
import time
from typing_extensions import List, TypedDict
from langchain.schema import Document
from langchain_huggingface import HuggingFaceEndpoint, HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
from langchain import hub
from langgraph.graph import START, StateGraph
from huggingface_hub import login

@st.cache_resource
def unzip_vector_store(zip_path="vector__store.zip", extract_to="vector__store"):
    if not os.path.exists(extract_to):
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_to)
    return extract_to

@st.cache_resource
def load_embeddings():
    try:
        return HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2",
            model_kwargs={"device": "cpu"},
            huggingfacehub_api_token=st.secrets.get("HF_TOKEN")
        )
    except Exception as e:
        st.error(f"🚨 Error loading embedding model: {e}")
        st.stop()

@st.cache_resource
def load_vector_store():
    embeddings = load_embeddings()
    directory = unzip_vector_store()
    return Chroma(persist_directory=directory, embedding_function=embeddings)

@st.cache_resource
def load_llm():
    try:
        login(st.secrets.get("HF_TOKEN", ""))
        return HuggingFaceEndpoint(
            repo_id="meta-llama/Llama-3.2-3B",
            task="text-generation",
            max_new_tokens=512,
            temperature=0.7,
            do_sample=True,
            repetition_penalty=1.03
        )
    except Exception as e:
        st.error("🚨 Could not load the LLM. Check your token or connectivity.")
        st.stop()

@st.cache_data
def load_courses(filepath="courses.txt"):
    with open(filepath, "r") as f:
        return f.read().splitlines()


vector_store = load_vector_store()
llm = load_llm()
courses = load_courses()


def classify_question(question: str):
    if "between" in question:
        filters = [{"class_name": {"$eq": c}} for c in courses if c in question]
        return {"$or": filters} if filters else None
    elif "require" in question or "have" in question:
        if "corequisite" in question and "prerequisite" in question:
            coreq_pos = question.find("corequisite")
            prereq_pos = question.find("prerequisite")
            filters = []
            i = j = 1
            if coreq_pos < prereq_pos:
                sec_1 = question[:coreq_pos]
                sec_2 = question[coreq_pos:]
                for c in courses:
                    if c in sec_1:
                        filters.append({f"coreq_{i}": {"$eq": c}})
                        i += 1
                    if c in sec_2:
                        filters.append({f"prereq_{j}": {"$eq": c}})
                        j += 1
            else:
                sec_1 = question[:prereq_pos]
                sec_2 = question[prereq_pos:]
                for c in courses:
                    if c in sec_1:
                        filters.append({f"prereq_{i}": {"$eq": c}})
                        i += 1
                    if c in sec_2:
                        filters.append({f"coreq_{j}": {"$eq": c}})
                        j += 1
            return {"$and": filters} if "and" in question else {"$or": filters} if filters else None

        elif "prerequisite" in question:
            filters = [{f"prereq_{i}": {"$eq": c}} for i, c in enumerate(courses, 1) if c in question]
            return filters[0] if len(filters) == 1 else {"$and": filters} if "and" in question else {"$or": filters} if filters else None
        else:
            filters = [{f"coreq_{i}": {"$eq": c}} for i, c in enumerate(courses, 1) if c in question]
            return filters[0] if len(filters) == 1 else {"$and": filters} if "and" in question else {"$or": filters} if filters else None
    elif "need" in question:
        last_course = ""
        for c in courses:
            if c in question and question.find(last_course) < question.find(c):
                last_course = c
        return {"class_name": last_course} if last_course else None
    else:
        for c in courses:
            if c in question:
                return {"class_name": c}
    return None


class State(TypedDict):
    question: str
    context: List[Document]
    answer: str
    uploaded_docs: str | None

def retrieve(state: State):
    filter = classify_question(state["question"])
    retrieved_docs = vector_store.similarity_search(
        state["question"],
        k=5,
        filter=filter
    )
    return {"context": retrieved_docs}

def generate(state: State):
    docs_content = "\n\n".join(doc.page_content for doc in state["context"])
    user_docs = f"\n\n### User Info:\n{state['uploaded_docs']}" if state['uploaded_docs'] else ""
    
    messages = f"""### System:
        You are an academic advising assistant. Answer the student's question directly and completely, but do not include extra information beyond what was asked.
        
        ### User:
        Question: {state['question']}
        
        ### Context:
        {docs_content}{user_docs}
        
        ### Answer:
        """
    response = llm.invoke(messages)
    return {"answer": response}

graph_builder = StateGraph(State).add_sequence([retrieve, generate])
graph_builder.add_edge(START, "retrieve")
graph = graph_builder.compile()

# === ENTRYPOINT ===

def get_chatbot_response(user_question, uploaded_docs=None):
    retries = 3
    for attempt in range(retries):
        try:
            response = graph.invoke({"question": user_question, "uploaded_docs": uploaded_docs})
            return response["answer"].strip()
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 503:
                print(f"Server unavailable. Retrying ({attempt + 1}/{retries})...")
                time.sleep(2)
            else:
                raise e
    return "Error: The chatbot service is temporarily unavailable. Please try again later."
