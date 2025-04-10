__import__('pysqlite3')
import sys
sys.modules['sqlite3'] = sys.modules.pop('pysqlite3')

import streamlit as st

st.set_page_config(page_title="Academic Advisor Chatbot", layout="centered")

from RAG import get_chatbot_response
import sqlite3

st.markdown("## Academic Advising Chatbot")

# Initialize session states
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "uploaded_docs" not in st.session_state:
    st.session_state.uploaded_docs = []

if "user_input" not in st.session_state:
    st.session_state.user_input = ""
if "clear_input" not in st.session_state:
    st.session_state.clear_input = False

if st.session_state.clear_input:
    st.session_state.user_input = ""
    st.session_state.clear_input = False

if st.session_state.chat_history:
    st.markdown("---")
    st.markdown(
        """
        <div style='height: 300px; overflow-y: scroll; padding: 1em; border: 1px solid #ccc; background-color: #f9f9f9'>
        """,
        unsafe_allow_html=True
    )

    for speaker, message in st.session_state.chat_history:
        st.markdown(f"**{speaker}:** {message}")

    st.markdown("</div>", unsafe_allow_html=True)

with st.form("chat_form", clear_on_submit=True):
    user_input = st.text_input("Ask a question:", key="user_input", label_visibility="collapsed")
    submitted = st.form_submit_button("Send")

if submitted and user_input:
    uploaded_context = "\n\n".join(doc["content"] for doc in st.session_state.uploaded_docs) if st.session_state.uploaded_docs else None
    response = get_chatbot_response(user_input, uploaded_docs=uploaded_context)

    st.session_state.chat_history.append(("User", user_input))
    st.session_state.chat_history.append(("Advisor", response))

# Upload documents
uploaded_files = st.file_uploader("Copy and paste your transcript into a file called transcript.txt, and upload it here for questions related to graduation or course recommendations.", type=["txt", "json"], accept_multiple_files=True)
if uploaded_files:
    for file in uploaded_files:
        try:
            content = file.read().decode("utf-8")
            st.session_state.uploaded_docs.append({"name": file.name, "content": content})
        except Exception as e:
            st.error(f"Failed to read {file.name}: {e}")

# Display uploaded files with remove button
if st.session_state.uploaded_docs:
    st.markdown("#### Uploaded Files:")
    for idx, doc in enumerate(st.session_state.uploaded_docs):
        col1, col2 = st.columns([8, 1])
        with col1:
            st.write(f"{doc['name']}")
        with col2:
            if st.button("❌", key=f"remove_{idx}"):
                st.session_state.uploaded_docs.pop(idx)
                st.rerun()
