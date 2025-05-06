#import os
#os.environ["TORCH_DISABLE_SOURCE_WATCHER"] = "none"
print("Starting")
#__import__('pysqlite3')
#import sys
#sys.modules['sqlite3'] = sys.modules.pop('pysqlite3')
print("Importing streamlit")
import torch
import os
torch.classes.__path__ = [os.path.join(torch.__path__[0], torch.classes.__file__)]
import streamlit as st
print("Streamlit imported")
st.set_page_config(page_title="Academic Advisor Chatbot", layout="centered")
print("Importing RAG.py")
import RAGNVIDIA
#import RAG
#import RAGOffline
print("RAG.py imported")
import sqlite3
print("Setup Complete")
import courseRec
st.markdown("## Academic Advising Chatbot")
import markdown
import re

# Initialize session states
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "uploaded_docs" not in st.session_state:
    user_info = "IMPORTANT: If the question is about the user's coursework or about their graduation, then ask them to upload 'transcript.txt' as your response. For anything else, skip this line and use the rest of the information provided to answer their question"
    st.session_state.uploaded_docs = {"name": "user_info", "content": user_info}
if "all_documents" not in st.session_state:
    st.session_state.all_documents = []
if "docs_saved" not in st.session_state:
    st.session_state.docs_saved = []
if "user_input" not in st.session_state:
    st.session_state.user_input = ""
if "user_input_given" not in st.session_state:
    st.session_state.user_input_given = False

if "curr_docs_retrieved" not in st.session_state:
    st.session_state.curr_docs_retrieved = ""

chat_html = """
<div id='chat-box' style='height: 400px; overflow-y: auto; padding: 1em; border: 1px solid #ccc; background-color: var(--background-color);'>
"""
chat_html += "\n"
for speaker, message in st.session_state.chat_history:
    newline_msg = re.sub(r'\s(\d+\.\s)', r'\n\1', message)
    newline_msg = re.sub(r' - ', r'\n - ', newline_msg)
    print(newline_msg)
    print(st.session_state.curr_docs_retrieved)
    chat_html += f"**{speaker}:**\n\n {newline_msg}\n\n"

chat_html += st.session_state.curr_docs_retrieved
chat_html += "</div>"
st.markdown(chat_html, unsafe_allow_html=True)

user_input = st.chat_input("Ask a question:")
if user_input and user_input.strip():
    st.session_state.chat_history.append(("User", user_input.strip()))
    st.session_state.awaiting_response = True
    st.rerun()

# Upload documents
uploaded_files = st.file_uploader("Copy and paste your transcript into 'transcript.txt'. Upload it here for questions related to graduation or course recommendations. To include your current courses, navigate to"
                                  " Course History in one.sjsu, and select download to receive a file called ps.xls. Once you upload this file, the advisor will be able to check your current courses. ", type=["txt", "xls"], accept_multiple_files=True)
correct_file = False
for file in uploaded_files:
    if file.name == "transcript.txt":
        with open("courses.txt", "r") as f:
            course_list = f.read().splitlines()
        correct_file = True
        contents = file.read().decode("utf-8")
        major, courses_taken, gpa_per_sem, curr_gpa = courseRec.parse_transcript(contents, course_list)
if correct_file:
    for file in uploaded_files:
        if file.name == "ps.xls":
            current_courses = courseRec.parse_course_list(file)
            for course, semester, name in current_courses:
                courses_taken[course] = ["In Progress", semester, name]

    course_rec, cred_req = courseRec.course_recommendation(courses_taken, major)
    user_info = courseRec.display_recommendation(courses_taken, course_rec, cred_req, curr_gpa, major)
    st.session_state.uploaded_docs = {"name": "user_info", "content": user_info}
if st.session_state.get("awaiting_response", False):
    with st.spinner("Advisor is typing..."):
        user_message = st.session_state.chat_history[-1][1]
        history_without_last = st.session_state.chat_history[:-1]

        response = RAGNVIDIA.get_chatbot_response(user_message, st.session_state.uploaded_docs, history_without_last)
        st.session_state.chat_history.append(("Advisor", response))#.replace('\n', '<br>')))
        st.session_state.awaiting_response = False
        st.rerun()