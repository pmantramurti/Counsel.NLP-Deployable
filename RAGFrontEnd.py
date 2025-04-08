from flask import Flask, render_template, request, jsonify
from RAG import get_chatbot_response, uploaded_docs
app = Flask(__name__)

@app.route("/")
def home():
    return render_template("webpage.html")

@app.route("/chat", methods=["POST"])
def chat():
    user_input = request.json.get("message")
    chatbot_response = get_chatbot_response(user_input)

    return jsonify({"message": chatbot_response})

@app.route("/upload", methods=["POST"])
def upload_file():
    if "file" not in request.files:
        return jsonify({"error": "No file part"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No selected file"}), 400

    content = file.read().decode("utf-8")  # Read as raw text

    # Store content in dictionary
    uploaded_docs[file.filename] = content

    return jsonify({"status": "stored", "filename": file.filename})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
