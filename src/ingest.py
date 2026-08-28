"""
Phase 4 ingestion for BankAssist Advisor: chunk the policy corpus and embed
it into a persisted Chroma vector store, using LangChain's own integrations
(langchain_openai.OpenAIEmbeddings, langchain_chroma.Chroma,
langchain_text_splitters.RecursiveCharacterTextSplitter) rather than calling
the OpenAI/Chroma SDKs directly -- this is what makes "Framework usage" a
real, checkable fact rather than a name on a slide.

Re-running this script rebuilds the collection from scratch (idempotent).
"""
import re
from pathlib import Path

import yaml
from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

ROOT = Path(__file__).resolve().parents[1]  # .../Capstone_Project_Arindam Sarkar
CORPUS_DIR = ROOT / "data" / "policy_corpus"
VECTORSTORE_DIR = ROOT / "vectorstore"
COLLECTION_NAME = "policy_corpus"
EMBED_MODEL = "text-embedding-3-small"
CHUNK_TOKENS = 500
CHUNK_OVERLAP = 80

load_dotenv(ROOT / ".env")

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)


def parse_doc(path: Path):
    text = path.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(text)
    if not match:
        raise ValueError(f"{path.name}: missing YAML frontmatter")
    frontmatter = yaml.safe_load(match.group(1))
    body = match.group(2).strip()
    return frontmatter, body


def build_documents():
    splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        encoding_name="cl100k_base",
        chunk_size=CHUNK_TOKENS,
        chunk_overlap=CHUNK_OVERLAP,
    )
    documents = []
    for path in sorted(CORPUS_DIR.glob("*.md")):
        frontmatter, body = parse_doc(path)
        chunks = splitter.split_text(body)
        for i, chunk in enumerate(chunks):
            metadata = {
                "doc_id": frontmatter["doc_id"],
                "product": frontmatter.get("product") or "",
                "version": str(frontmatter["version"]),
                "effective_date": str(frontmatter["effective_date"]),
                "supersedes": str(frontmatter.get("supersedes") or ""),
                "superseded_by": str(frontmatter.get("superseded_by") or ""),
                "status": frontmatter.get("status") or "",
                "source_file": path.name,
                "chunk_index": i,
                "chunk_id": f"{frontmatter['doc_id']}::{frontmatter['version']}::chunk{i}",
            }
            documents.append(Document(page_content=chunk, metadata=metadata))
    return documents


def main():
    documents = build_documents()
    ids = [d.metadata["chunk_id"] for d in documents]

    embeddings = OpenAIEmbeddings(model=EMBED_MODEL)

    # Idempotent rebuild: drop any existing collection of this name first.
    try:
        Chroma(
            collection_name=COLLECTION_NAME,
            embedding_function=embeddings,
            persist_directory=str(VECTORSTORE_DIR),
        ).delete_collection()
    except Exception:
        pass

    Chroma.from_documents(
        documents=documents,
        embedding=embeddings,
        ids=ids,
        collection_name=COLLECTION_NAME,
        persist_directory=str(VECTORSTORE_DIR),
        collection_metadata={"hnsw:space": "cosine"},
    )

    n_docs = len(list(CORPUS_DIR.glob("*.md")))
    print(f"Ingested {len(documents)} chunk(s) from {n_docs} source document(s) into {VECTORSTORE_DIR}")
    for d in documents:
        print(f"  {d.metadata['chunk_id']}  ({len(d.page_content.split())} words)")


if __name__ == "__main__":
    main()
