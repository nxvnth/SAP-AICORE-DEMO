import os, boto3, tempfile
from pathlib import Path
from dotenv import load_dotenv
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
import chromadb

load_dotenv()

def get_minio_client():
    return boto3.client(
        "s3",
        endpoint_url=os.environ["MINIO_ENDPOINT"],
        aws_access_key_id=os.environ["MINIO_ACCESS_KEY"],
        aws_secret_access_key=os.environ["MINIO_SECRET_KEY"],
    )

def download_docs_from_minio(local_dir: str) -> list:
    """Download all files from MinIO bucket docs/ prefix to a local temp dir."""
    s3 = get_minio_client()
    bucket = os.environ["MINIO_BUCKET"]
    response = s3.list_objects_v2(Bucket=bucket, Prefix="docs/")
    paths = []
    for obj in response.get("Contents", []):
        key = obj["Key"]
        local_path = os.path.join(local_dir, Path(key).name)
        s3.download_file(bucket, key, local_path)
        paths.append(local_path)
        print(f"Downloaded: {key}")
    return paths

def load_documents(file_paths: list):
    docs = []
    for path in file_paths:
        if path.endswith(".pdf"):
            docs.extend(PyPDFLoader(path).load())
        elif path.endswith(".txt"):
            docs.extend(TextLoader(path).load())
    return docs

def main():
    print("Starting ingestion...")
    with tempfile.TemporaryDirectory() as tmp:
        file_paths = download_docs_from_minio(tmp)
        if not file_paths:
            print("No documents found in MinIO docs/ prefix. Upload some files first.")
            return

        docs = load_documents(file_paths)
        splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
        chunks = splitter.split_documents(docs)
        print(f"Split into {len(chunks)} chunks")

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
        vectorstore.add_documents(chunks)
        print(f"Ingestion complete. {len(chunks)} chunks stored in ChromaDB.")

if __name__ == "__main__":
    main()
