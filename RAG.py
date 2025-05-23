import os
import re
import traceback
import zipfile
import streamlit as st
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from typing_extensions import List, TypedDict
from langchain.schema import Document
from langchain_huggingface import HuggingFaceEndpoint, HuggingFaceEmbeddings
from langchain_chroma import Chroma
from langgraph.graph import START, StateGraph
from huggingface_hub import login
from huggingface_hub.utils import HfHubHTTPError

NUM_DOCS = 10
MEMORY_LENGTH = 5
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
    return Chroma(persist_directory=directory, embedding_function=embeddings), embeddings


@st.cache_resource
def load_llm():
    try:
        print("Logging in")
        login(st.secrets.get("HF_TOKEN", ""))
        print("Loading model pipeline")
        return HuggingFaceEndpoint(
            #repo_id="meta-llama/Llama-3.2-3B-Instruct",
            repo_id="meta-llama/Llama-3.3-70B-Instruct",
            task="text-generation",
            max_new_tokens=256,
            do_sample=False,
            temperature=0.3,
            repetition_penalty=1.2
        )
    except Exception as e:
        st.error("🚨 Could not load the LLM. Check your token or connectivity.")
        st.stop()


@st.cache_data
def load_courses(filepath="courses.txt"):
    with open(filepath, "r") as f:
        return f.read().splitlines()


vector_store, embeddings = load_vector_store()
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
    source_documents: List[str]
    chat_history: List[str]

def retrieve(state: State) -> State:
    docs_filter = classify_question(state["question"])
    retrieved_docs = vector_store.similarity_search(
        state["question"],
        k=NUM_DOCS,
        filter=docs_filter
    )
    return {
        "context": retrieved_docs,
        "source_documents": [doc.page_content for doc in retrieved_docs]
    }

#results = vector_store.similarity_search_with_relevance_scores("your query", k=4)
prompt_template = """
You are an academic advising assistant. Respond factually and clearly using only the provided information.

If you do not know the answer, say so. Use newline characters to format your response.

Do not provide any information that is not required to answer the question.

{uploaded_docs}

{chat_history}

Context:
{context}

{prior_context}

Important: If the user's question does not require context, ignore all context given

### User: {question}
### Advisor:
"""
def generate(state: State) -> State:
    docs_content = "\n\n".join(doc.page_content for doc in state["context"])
    prior_docs_count = int(np.sum(st.session_state.docs_saved[-MEMORY_LENGTH:]))
    prior_content = (
        "Past conversation context:\n\n" + "\n\n".join(
            doc for doc in st.session_state.all_documents[-prior_docs_count:]
        )
        if prior_docs_count > 0
        else ""
    )
    keywords = ["graduate", "graduation", "course", "coursework", "gpa", "credit", "transcript", "requirement",
                "degree", "complete", "recommend"]
    norm_question = normalize(state["question"])
    if any(kw in norm_question for kw in keywords) or st.session_state.user_input_given:
        uploaded_content = st.session_state.uploaded_docs["content"]
        if not st.session_state.user_input_given and uploaded_content != "IMPORTANT: If the question is about the user's coursework or about their graduation, then ask them to upload transcript.txt as your response. For anything else, skip this line and use the rest of the information provided to answer their question":
            st.session_state.user_input_given = True
    else:
        uploaded_content = ""
    #print(uploaded_content)
    if state.get("chat_history", []):
        chat_history = "Dialogue so far:" + "\n".join(
            f"{speaker},{content}" for speaker, content in state["chat_history"][-(MEMORY_LENGTH * 2):]
        )
    else:
        chat_history = ""
    #print(docs_content)
    if "f1" in state["question"] or "f-1" in state["question"]:
        state["question"] += " work"
    messages = prompt_template.format(
        context=docs_content,
        prior_context=prior_content,
        uploaded_docs=uploaded_content,
        question=state["question"],
        chat_history=chat_history
    )
    response = llm.invoke(messages)
    num_docs = 0

    filtered_docs = compare_docs_to_answer(response, state["context"], embeddings)
    print(len(filtered_docs))
    for doc in filtered_docs:
        if doc.page_content not in st.session_state.all_documents:
            num_docs += 1
            st.session_state.all_documents.append(doc.page_content)
    st.session_state.docs_saved.append(num_docs)
    # Post-processing
    response = response.replace("\n", " ").replace("  ", " ")
    response = response.split("### User:")[0]
    #response = re.sub(r"\bI don't know\b|\bAdditionally\b|\bIn conclusion\b|\bbased on the context\b", "",
    #                  response).strip()
    response = re.sub(r"\bbased on the context\b", "",response).strip()
    response = re.sub(r"\t\+|\t", "", response)
    response = re.sub("•", "\n\t•", response)
    #print(response)
    return {"answer": response, "source_documents": state["source_documents"]}

def compare_docs_to_answer(response, docs, embeds, threshold=0.5):
    response_embedding = embeds.embed_query(response)
    doc_texts = [doc.page_content for doc in docs]
    if not doc_texts:
        return []
    doc_embeddings = embeds.embed_documents(doc_texts)
    if not doc_embeddings:
        return []
    sims = cosine_similarity([response_embedding], doc_embeddings)[0]
    filtered_docs = [doc for doc, sim in zip(docs, sims) if sim >= threshold]

    return filtered_docs

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