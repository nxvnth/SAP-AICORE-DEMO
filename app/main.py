import os, argparse
from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn
from dotenv import load_dotenv
from langchain_openai import AzureChatOpenAI
from langchain_groq import ChatGroq
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
from langchain.chains import ConversationalRetrievalChain
from langchain.memory import ConversationBufferWindowMemory
import chromadb
from auth import get_token
import gradio as gr
import gradio_client.utils as client_utils

# Monkey-patch Gradio Client's schema parser to prevent Pydantic V2 boolean crash
orig_json_schema_to_python_type = client_utils._json_schema_to_python_type
def patched_json_schema_to_python_type(schema, defs=None):
    if isinstance(schema, bool):
        return "Any"
    return orig_json_schema_to_python_type(schema, defs)
client_utils._json_schema_to_python_type = patched_json_schema_to_python_type

import boto3
import ingest

load_dotenv()

# Lazy globals — initialized on first request, not at startup
_llm = None
_retriever = None
_chain = None

def make_llm():
    if "GROQ_API_KEY" in os.environ:
        return ChatGroq(
            api_key=os.environ["GROQ_API_KEY"],
            model="llama-3.3-70b-versatile",
            temperature=0.3
        )

    # token = get_token()
    # base_url = (
    #     f"{os.environ['AICORE_API_URL']}"
    #     f"/v2/inference/deployments/{os.environ['AICORE_DEPLOYMENT_ID']}"
    # )
    # return AzureChatOpenAI(
    #     api_key=token,
    #     azure_endpoint=base_url,
    #     api_version="2024-02-01",
    #     deployment_name="gpt-4o",
    #     model_name="gpt-4o",
    #     temperature=0.3,
    #     default_headers={"AI-Resource-Group": os.environ.get("AICORE_RESOURCE_GROUP", "default")},
    # )

def make_retriever():
    embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
    client = chromadb.HttpClient(
        host=os.environ["CHROMA_HOST"],
        port=int(os.environ["CHROMA_PORT"]),
    )
    vectorstore = Chroma(
        client=client,
        collection_name="rag_docs",
        embedding_function=embeddings,
    )
    return vectorstore.as_retriever(search_kwargs={"k": 4})

def get_chain():
    global _llm, _retriever, _chain
    if _chain is None:
        _llm = make_llm()
        _retriever = make_retriever()
        _memory = ConversationBufferWindowMemory(
            memory_key="chat_history",
            return_messages=True,
            k=5,
        )
        _chain = ConversationalRetrievalChain.from_llm(
            llm=_llm,
            retriever=_retriever,
            memory=_memory,
            verbose=False,
        )
    return _chain

app = FastAPI()

def handle_upload(filepath, progress=gr.Progress()):
    if not filepath:
        return "No file selected."
    try:
        progress(0.1, desc="Connecting to MinIO Storage...")
        s3 = ingest.get_minio_client()
        bucket = os.environ["MINIO_BUCKET"]
        filename = os.path.basename(filepath)
        
        progress(0.3, desc=f"Pushing '{filename}' into Azure...")
        s3.upload_file(filepath, bucket, f"docs/{filename}")
        
        progress(0.6, desc="Vectorizing document chunks on ChromaDB...")
        # Programmatically run ingestion locally
        ingest.main()
        
        progress(1.0, desc="Indexing complete!")
        return f"✅ Successfully uploaded '{filename}' and updated the vector database!"
    except Exception as e:
        return f"❌ Error: {str(e)}"

def handle_chat(message, history):
    res = get_chain().invoke({"question": message})
    return res["answer"]

with gr.Blocks(title="SAP AI Core RAG") as ui:
    gr.Markdown("# 🤖 Enterprise RAG Chatbot")
    with gr.Tab("Chat"):
        gr.ChatInterface(fn=handle_chat)
    with gr.Tab("Document Management"):
        gr.Markdown("Directly upload new files into your Azure VM's MinIO storage and update ChromaDB instantly.")
        file_input = gr.File(label="Select Document (PDF/TXT)")
        status_text = gr.Textbox(label="Status", interactive=False)
        upload_btn = gr.Button("Upload and Ingest", variant="primary")
        upload_btn.click(fn=handle_upload, inputs=[file_input], outputs=[status_text])

class ChatRequest(BaseModel):
    message: str
    model_config = {"extra": "allow"}

@app.get("/v1/health")
def health():
    return {"status": "OK"}

@app.post("/v1/chat")
async def api_chat(req: ChatRequest):
    result = get_chain().invoke({"question": req.message})
    return {"response": result["answer"]}

# Mount Gradio AFTER defining standard FastAPI routes!
app = gr.mount_gradio_app(app, ui, path="/")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["serve", "ingest"], default="serve")
    args = parser.parse_args()
    if args.mode == "ingest":
        import ingest
        ingest.main()
    else:
        uvicorn.run(app, host="0.0.0.0", port=8080)