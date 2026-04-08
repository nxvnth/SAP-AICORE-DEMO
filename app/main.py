import os, argparse
from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn
from dotenv import load_dotenv
from langchain_openai import AzureChatOpenAI
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
from langchain.chains import ConversationalRetrievalChain
from langchain.memory import ConversationBufferWindowMemory
import chromadb
from auth import get_token

load_dotenv()

def make_llm():
    token = get_token()
    base_url = (
        f"{os.environ['AICORE_API_URL']}"
        f"/v2/inference/deployments/{os.environ['AICORE_DEPLOYMENT_ID']}"
    )
    return AzureChatOpenAI(
        api_key=token,
        azure_endpoint=base_url,
        api_version="2024-02-01",
        deployment_name="gpt-4o",
        model_name="gpt-4o",
        temperature=0.3,
        default_headers={"AI-Resource-Group": os.environ.get("AICORE_RESOURCE_GROUP", "default")},
    )

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

# Initialise once at startup — not on every request
llm = make_llm()
retriever = make_retriever()
memory = ConversationBufferWindowMemory(
    memory_key="chat_history",
    return_messages=True,
    k=5,  # remember last 5 exchanges
)
chain = ConversationalRetrievalChain.from_llm(
    llm=llm,
    retriever=retriever,
    memory=memory,
    verbose=False,
)

app = FastAPI()

class ChatRequest(BaseModel):
    message: str

@app.get("/v1/health")
def health():
    return {"status": "OK"}

@app.post("/v1/chat")
async def chat(req: ChatRequest):
    result = chain.invoke({"question": req.message})
    return {"response": result["answer"]}

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["serve", "ingest"], default="serve")
    args = parser.parse_args()
    if args.mode == "ingest":
        import ingest
        ingest.main()
    else:
        uvicorn.run(app, host="0.0.0.0", port=8080)
