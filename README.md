# Counsel.NLP Deployable version

Once our project reached the user interactive stage of development, we needed a separate github to keep the various versions of the program that would be accessed by our various deployment methods, with the latest version being the public streamlit cloud application that can be found [here](https://counsel-nlp.streamlit.app).

# Local deployment instructions:

In order to run the program locally, take the following steps:
## 1. Downloads
### A. Download program files: The [model backend](RAGNVIDIA.py), the [streamlit frontend](streamlit_app.py), and the [transcript handler](courseRec.py)
### B. Download dataset files: The [course list](courses.txt), the [vector store zip file](vector__store.zip), the [MSAI file](msai_dataset.json), the [MSCMPE file](mscmpe_dataset.json) and the [MSSE file](msse_dataset.json).
## 2. Execution
### A. Store all the files in the same folder, then run the following command - `streamlit run streamlit_app.py`
