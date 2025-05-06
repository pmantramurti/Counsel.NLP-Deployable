import os
import re
import traceback
import zipfile
import streamlit as st
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from typing_extensions import List, TypedDict
from langchain.schema import Document
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma
from langgraph.graph import START, StateGraph
from huggingface_hub import login
from huggingface_hub.utils import HfHubHTTPError
from langchain_nvidia_ai_endpoints import ChatNVIDIA

if not os.environ.get("NVIDIA_API_KEY"):
  os.environ["NVIDIA_API_KEY"] = "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"

NUM_DOCS = 5
MEMORY_LENGTH = 2
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
        return ChatNVIDIA(
            model="meta/llama-3.2-3b-instruct",
            api_key="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",
            temperature=0.4,
            max_tokens=256,
            repetition_penalty=1.02
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
            if not filters:
                return None
            if isinstance(filter, list):
                return filter[0]
            return filter
            #return filter[0] if len(filters) != 0 else None

        elif "prerequisite" in normalized_question:
            i = 1
            for c in match_courses(normalized_question):
                filters.append({f"prereq_{i}": {"$eq": c}})
                i += 1
            filter = {"$and": filters} if "and" in normalized_question else {"$or": filters}
            if len(filters) < 2:
                filter = filters
            if not filters:
                return None
            if isinstance(filter, list):
                return filter[0]
            return filter
            #return filter[0] if len(filters) != 0 else None

        else:
            i = 1
            for c in match_courses(normalized_question):
                filters.append({f"coreq_{i}": {"$eq": c}})
                i += 1
            filter = {"$and": filters} if "and" in normalized_question else {"$or": filters}
            if len(filters) < 2:
                filter = filters
            if not filters:
                return None
            if isinstance(filter, list):
                return filter[0]
            return filter
            #return filter[0] if len(filters) != 0 else None

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
    if "f1" in state["question"] or "F1" in state["question"]:
        state["question"].replace("F1", "F-1")
        state["question"] = state["question"].replace("f1", "f-1")
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

Keep your responses short.

If you do not know the answer, say so. Do not provide any information that is not required to answer the question.

Break up your response into numbered sections only if needed. 

If you don't know something, like the course name associated with a course code, just give the code.

{uploaded_docs}

{chat_history}

Context:
{context}

{prior_context}

### User: {question}
### Advisor:
"""
def generate(state: State) -> State:
    docs_content = "\n\n".join(doc.page_content for doc in state["context"])
    st.session_state.curr_docs_retrieved = docs_content
    prior_docs_count = int(np.sum(st.session_state.docs_saved[-MEMORY_LENGTH:]))
    prior_content = (
        "Past conversation context:\n\n" + "\n\n".join(
            doc for doc in st.session_state.all_documents[-prior_docs_count:]
        )
        if prior_docs_count > 0
        else ""
    )
    #keywords = ["graduate", "graduation", "course", "coursework", "gpa", "credit", "transcript", "requirement", "degree"]
    #personal_pronouns = [" my ", " i ", " me ", " myself "]

    #norm_question = normalize(state["question"])

    # Require BOTH a keyword AND a personal reference
    #has_keyword = any(kw in norm_question for kw in keywords)
    #has_pronoun = any(pr in f" {norm_question} " for pr in personal_pronouns)
    if state.get("chat_history", []):
        chat_history = "Dialogue so far:" + "\n".join(
            f"{speaker},{content}" for speaker, content in state["chat_history"][-(MEMORY_LENGTH * 2):] if "transcript.txt" not in content
        )
    else:
        chat_history = ""
    filter_prompt = ("""
You are an academic advisor chatbot.

You need to decide whether a user's question REQUIRES access to their PERSONAL INFORMATION or PERSONAL TRANSCRIPT (such as a record of completed courses, grades, or academic standing) to provide a complete and personalized answer.

Answer [YES] if the question depends on personalized data like:
- What courses the student has already completed
- The student’s GPA or academic progress
- Specific degree progress that depends on individual transcripts
+ This includes ANY question where the user is asking for personalized course recommendations, even if they don’t explicitly mention their transcript.

Answer [NO] if the question can be fully answered using ONLY general academic information (such as course catalogs, policies, or standard requirements) WITHOUT needing to know anything about the student’s own transcript.

---

### Examples:

Q: I need a general education course that covers physical activities. Any recommendations?
A: [NO]

Q: What are the restricted courses that I cannot take for MSSE major as an elective course?
A: [NO]

Q: What courses should I take next semester?
A: [YES]

Q: How do I apply for Optional Practical Training (OPT)?
A: [NO]

Q: What is the GPA requirement for graduation?
A: [NO]

Q: What electives do I have left?
A: [YES]

---

### User's question:
{question}

### Your answer:
""")
    filter_query = filter_prompt.format(question=state["question"])
    filter_ans = normalize(llm.invoke(filter_query).content)
    is_personal = "yes" in filter_ans
    print(filter_ans)
    if is_personal:
        uploaded_content = st.session_state.uploaded_docs["content"]
        chat_history = ""
        prior_content = ""
        docs_content = ""
    else:
        uploaded_content = ""
    print(uploaded_content)

    #print(docs_content)
    messages = prompt_template.format(
        context=docs_content,
        prior_context=prior_content,
        uploaded_docs=uploaded_content,
        question=state["question"],
        chat_history=chat_history
    )
    response = llm.invoke(messages).content
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

def compare_docs_to_answer(response, docs, embeds, threshold=0.50):
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
        return response['answer'].strip()

    except HfHubHTTPError as e:
        if "Model too busy" in str(e):
            return "The model is currently overloaded. Please try again in a minute."
        else:
            print("HuggingFace error:", e)
            return f"A server-side issue occurred. Error : {e}"

    except Exception as e:
        traceback.print_exc()
        return "An unexpected error occurred. Please try again."