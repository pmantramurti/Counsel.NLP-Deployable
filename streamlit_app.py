import os
os.environ["STREAMLIT_WATCHDOG_ENABLED"] = "false"
print("Starting")
__import__('pysqlite3')
import sys
sys.modules['sqlite3'] = sys.modules.pop('pysqlite3')
print("Importing streamlit")
import torch
import os
torch.classes.__path__ = [os.path.join(torch.__path__[0], torch.classes.__file__)]
import streamlit as st
print("Streamlit imported")
st.set_page_config(page_title="Counsel.NLP Chatbot", layout="wide")
print("Importing RAG.py")
import RAGNVIDIA
#import RAG
#import RAGOffline
print("RAG.py imported")
import sqlite3
print("Setup Complete")
import courseRec
import re

# Global CSS for nicer styling
st.markdown("""
    <style>
        body {font-family: 'Segoe UI', sans-serif;}
        .block-container {padding-top: 2rem;}
    </style>
""", unsafe_allow_html=True)

st.title("🎓 Counsel.NLP - Academic Advising Chatbot")

# Expander with rich instructions
with st.expander("💬 What can I ask this chatbot?"):
    st.markdown("""
### ✅ **What You Can Ask Counsel.NLP**

Counsel.NLP can help answer academic advising questions based on over **1000 courses** and **general advising topics** at San José State University (SJSU), specifically for the **MSAI, MSCS, and MSSE programs due to time constraint**.

---

#### 🧾 **Course-Level Questions**
- **Descriptions of courses**  
  ➤ “What is the description for CMPE 257?”  
- **Units for a course**  
  ➤ “How many units is CS 156?”  
- **Prerequisites or corequisites**  
  ➤ “What are the prerequisites for CMPE 260?”  
- **Categories or special notes**  
  ➤ “Which movement area does KIN 2B fulfill?”  
- **Class structure**  
  ➤ “What’s the class format for AE 110?”
- **Grading**  
  ➤ “What is the grading system for CHIN 132?”

---

#### 🧑‍🎓 **Program-Level Questions (MSAI, MSCS, MSSE)**
- **Core courses**  
  ➤ “What are the core courses for the MSAI major?” 
- **Prerequisites**  
  ➤ “What are the prerequisites for the MSCMPE major?”   
- **Electives and specialization tracks**  
  ➤ “What electives can I take for MSSE?”  
  ➤ “What are specialization tracks for MSAI major?”  
- **Culminating experience options**  
  ➤ “What are the culminating experience options for the MSSE major?”  
- **Graduate writing requirements**  
  ➤ “Do I need to complete GWAR for MSCS?”

---

#### 🧩 **General Advising and Administrative Topics**
- **Provisional admission status**  
  ➤ “How can I clear my provisional admission status as a graduate student?”

- **Residency classification for tuition**  
  ➤ “How do I confirm my California residency status for tuition purposes?”

- **Leave of absence policy**  
  ➤ “Can I take a semester off from my graduate program?”

- **Switching graduate programs**  
  ➤ “How do I switch to a different graduate program?”

- **Double enrollment restrictions**  
  ➤ “Can I enroll in two master's programs at the same time?”

- **Undergraduate coursework in GPA**  
  ➤ “Are undergraduate courses included in my graduate GPA?”

- **Graduation timeline and forms**  
  ➤ “What forms are needed to apply for graduation?”  
  ➤ “How do I change my expected graduation date?”  
  ➤ “What is the deadline for submitting my candidacy form?”

- **Transfer credit policies**  
  ➤ “Can I transfer courses from another institution to my graduate degree?”

- **Academic standing and GPA**  
  ➤ “What GPA do I need to maintain for good academic standing?”  
  ➤ “What grades are considered satisfactory or unsatisfactory?”

- **Maintaining F-1 status**  
  ➤ “What are the requirements to maintain my F-1 visa status?”

- **J-1 visitor program**  
  ➤ “What are the eligibility requirements for the J-1 exchange visitor program?”

- **Financial aid support**  
  ➤ “Who can I contact for financial aid or scholarships?”

- **Mental health and counseling services**  
  ➤ “Does SJSU offer counseling or wellness support for students?”

- **Alumni connections and career services**  
  ➤ “Are there organizations where I can connect with SJSU alumni?”  
  ➤ “What support does the Writing Center or Career Center offer graduate students?”

---

#### 📎 **How to Upload Your Transcript**
To ask questions about graduation eligibility or course recommendations, please paste your unofficial transcript into a file named `transcript.txt`, then upload it below.

To include your currently enrolled courses:
1. Visit the **Course History** section in your [MySJSU portal](https://one.sjsu.edu).
2. Click **Download** to export your course list as `ps.xls`.
3. Upload the `ps.xls` file here so the advisor can check your academic progress and provide more accurate guidance.
""")

# Initialize session states
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "uploaded_docs" not in st.session_state:
    user_info = "Ask the user to upload 'transcript.txt' for more information."
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

# Render chat history using st.chat_message
for speaker, message in st.session_state.chat_history:
    with st.chat_message("user" if speaker == "User" else "Advisor"):
        formatted_msg = re.sub(r'\s(\d+\.\s)', r'\n\1', message)
        formatted_msg = re.sub(r' - ', r'\n - ', formatted_msg)
        st.markdown(formatted_msg)

# Chat input
user_input = st.chat_input("Ask a question about your courses, program, or advising...")
if user_input and user_input.strip():
    st.session_state.chat_history.append(("User", user_input.strip()))
    st.session_state.awaiting_response = True
    st.rerun()
# Upload documents
uploaded_files = st.file_uploader("📎 Upload transcript.txt and optionally ps.xls", type=["txt", "xls"], accept_multiple_files=True)
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
# Process user question
if st.session_state.get("awaiting_response", False):
    with st.spinner("Advisor is typing..."):
        user_message = st.session_state.chat_history[-1][1]
        history_without_last = st.session_state.chat_history[:-1]

        response = RAGNVIDIA.get_chatbot_response(user_message, st.session_state.uploaded_docs, history_without_last)
        st.session_state.chat_history.append(("Advisor", response))
        st.session_state.awaiting_response = False
        st.rerun()
