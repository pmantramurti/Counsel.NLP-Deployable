import os
import re
import zipfile
import streamlit as st
from typing_extensions import List, TypedDic
from langchain.schema import Document
from langchain_huggingface import HuggingFaceEndpoint, HuggingFaceEmbeddings
from langchain_chroma import Chroma
from langgraph.graph import START, StateGraph
from huggingface_hub import login
from huggingface_hub.utils import HfHubHTTPError

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
            model_kwargs={"device": "cpu"}
        )
    except Exception as e:
        st.error(f"🚨 Error loading embedding model: {e}")
        st.stop()

@st.cache_resource
def load_vector_store():
    print("Loading Embeddings")
    embeddings = load_embeddings()
    print("Unzipping vector store")
    directory = unzip_vector_store()
    return Chroma(persist_directory=directory, embedding_function=embeddings)

@st.cache_resource
def load_llm():
    try:
        print("Logging in")
        login(st.secrets.get("HF_TOKEN", ""))
        print("Loading model pipeline")
        return HuggingFaceEndpoint(
            repo_id="meta-llama/Llama-3.2-3B-Instruct",
            task="text-generation",
            max_new_tokens=256,
            do_sample=False,
            temperature=0,
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
print("vector store loaded")
llm = load_llm()
print("model loaded")
courses = load_courses()


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().replace("-", " ")).strip()

def classify_question(question: str):
    normalized_question = normalize(question)
    filters = []

    def match_courses(section: str):
        matched = []
        section = normalize(section)
        for c in courses:
            if normalize(c) in section:
                matched.append(c)
        return matched

    if "between" in normalized_question:
        for c in match_courses(normalized_question):
            filters.append({"class_name": {"$eq": c}})
        return {"$or": filters} if len(filters) != 0 else None

    elif "require" in normalized_question or "have" in normalized_question:
        if "corequisite" in normalized_question and "prerequisite" in normalized_question:
            coreq_pos = normalized_question.find("corequisite")
            prereq_pos = normalized_question.find("prerequisite")
            filters = []
            i, j = 1, 1
            if coreq_pos < prereq_pos:
                sec_1 = normalized_question[:coreq_pos]
                sec_2 = normalized_question[coreq_pos:]
                for c in match_courses(sec_1):
                    filters.append({f"coreq_{i}": {"$eq": c}})
                    i += 1
                for c in match_courses(sec_2):
                    filters.append({f"prereq_{j}": {"$eq": c}})
                    j += 1
            else:
                sec_1 = normalized_question[:prereq_pos]
                sec_2 = normalized_question[prereq_pos:]
                for c in match_courses(sec_1):
                    filters.append({f"prereq_{i}": {"$eq": c}})
                    i += 1
                for c in match_courses(sec_2):
                    filters.append({f"coreq_{j}": {"$eq": c}})
                    j += 1
            filter = {"$and": filters} if "and" in normalized_question else {"$or": filters}
            if len(filters) < 2:
                filter = filters
            return filter[0] if len(filters) != 0 else None

        elif "prerequisite" in normalized_question:
            i = 1
            for c in match_courses(normalized_question):
                filters.append({f"prereq_{i}": {"$eq": c}})
                i += 1
            filter = {"$and": filters} if "and" in normalized_question else {"$or": filters}
            if len(filters) < 2:
                filter = filters
            return filter[0] if len(filters) != 0 else None

        else:
            i = 1
            for c in match_courses(normalized_question):
                filters.append({f"coreq_{i}": {"$eq": c}})
                i += 1
            filter = {"$and": filters} if "and" in normalized_question else {"$or": filters}
            if len(filters) < 2:
                filter = filters
            return filter[0] if len(filters) != 0 else None

    elif "need" in normalized_question:
        last_course = ""
        last_pos = -1
        for c in courses:
            pos = normalized_question.find(normalize(c))
            if pos > last_pos:
                last_pos = pos
                last_course = c
        return {"class_name": last_course} if last_course else None

    else:
        for c in courses:
            if normalize(c) in normalized_question:
                return {"class_name": c}

    return None


class State(TypedDict):
    question: str
    context: List[Document]
    answer: str
    uploaded_docs: str | None
    source_documents: List[str]
    chat_history: List[str]

def retrieve(state: State) -> State:
    filter = classify_question(state["question"])
    retrieved_docs = vector_store.similarity_search(
        state["question"],
        k=10,
        filter=filter
    )
    return {
        "context": retrieved_docs,
        "source_documents": [doc.page_content for doc in retrieved_docs]
    }
prompt_template = """
    Answer the question based on the context below.
    Do not make up information. Be concise and to the point.
    
    Context: {context}
    
    User Info:
    {uploaded_docs}

    Dialogue thus far:
    {chat_history}
    
    Question: {question}

    Answer:
    """
def generate(state: State) -> State:
    docs_content = "\n\n".join(doc.page_content for doc in state["context"])
    uploaded_content = "\n\n".join(doc["content"] for doc in state.get("uploaded_docs", []))
    chat_history = "\n".join(f"{speaker},{content}" for speaker, content in state.get("chat_history", []))
    messages = prompt_template.format(
        context=docs_content,
        uploaded_docs=uploaded_content,
        question=state["question"],
        chat_history = chat_history
    )
    response = llm.invoke(messages)

    # Post-processing
    response = response.replace("\n", " ").replace("  ", " ")
    response = re.sub(r"\bI don't know\b|\bAdditionally\b|\bIn conclusion\b|\bbased on the context\b", "", response).strip()
    response = re.sub(r"\t\+|\t", "", response)

    return {"answer": response, "source_documents": state["source_documents"]}


graph_builder = StateGraph(State).add_sequence([retrieve, generate])
graph_builder.add_edge(START, "retrieve")
graph = graph_builder.compile()

# === ENTRYPOINT ===

def get_chatbot_response(user_question, uploaded_docs=None, chat_history=None):
    try:
        response = graph.invoke({
            "question": user_question,
            "uploaded_docs": uploaded_docs or [],
            "chat_history": chat_history or []
        })
        return response["answer"].strip()
    
    except HfHubHTTPError as e:
        if "Model too busy" in str(e):
            return "The model is currently overloaded. Please try again in a minute."
        else:
            print("HuggingFace error:", e)
            return f"A server-side issue occurred. Error : {e}"
    
    except Exception as e:
        traceback.print_exc()
        return "An unexpected error occurred. Please try again."
