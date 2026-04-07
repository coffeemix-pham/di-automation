import os
import shutil
from langchain_community.vectorstores import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from parser import load_and_split_documents


def _get_embedding_model():
    return HuggingFaceEmbeddings(
        model_name="paraphrase-multilingual-MiniLM-L12-v2",
        model_kwargs={'device': 'cpu'},
        encode_kwargs={'normalize_embeddings': True}
    )


def get_vector_db(
    db_path: str = "vector_db",
    collection_name: str = "di_guidelines",
    api_key: str | None = None,
    model_name: str = "gemini-2.5-flash",
    force_recreate: bool = False,
    progress_callback_for_new=None
):
    """
    로컬 벡터 데이터베이스를 초기화하거나 로드합니다.
    force_recreate=True 이면 기존 DB를 삭제하고 재생성합니다.
    """
    embedding_model = _get_embedding_model()

    if force_recreate and os.path.exists(db_path):
        print(f"Force recreate: deleting {db_path}...")
        shutil.rmtree(db_path)

    if os.path.exists(db_path) and os.listdir(db_path):
        print(f"Loading existing Vector DB from {db_path}...")
        return Chroma(
            persist_directory=db_path,
            embedding_function=embedding_model,
            collection_name=collection_name
        )

    # 신규 생성
    print("Creating new Vector DB...")
    if not os.path.exists("knowledge_base"):
        os.makedirs("knowledge_base", exist_ok=True)

    documents = load_and_split_documents(
        api_key=api_key,
        model_name=model_name,
        progress_callback=progress_callback_for_new
    )

    if not documents:
        print("No documents found in knowledge_base.")
        return None

    return Chroma.from_documents(
        documents=documents,
        embedding=embedding_model,
        persist_directory=db_path,
        collection_name=collection_name
    )


def get_all_source_names(vector_db) -> list:
    """DB에 인덱싱된 모든 파일 이름(source_name) 목록을 반환합니다."""
    if not vector_db:
        return []

    all_data = vector_db.get()
    if not all_data or "metadatas" not in all_data:
        return []

    names = sorted(set(
        m.get("source_name")
        for m in all_data["metadatas"]
        if m.get("source_name")
    ))
    return names


def delete_document_from_db(vector_db, source_name: str) -> bool:
    """
    특정 source_name을 가진 모든 조각을 DB에서 삭제합니다.
    ChromaDB 0.5+ where 필터 문법: {"field": {"$eq": value}}
    """
    if not vector_db or not source_name:
        return False

    try:
        vector_db.delete(where={"source_name": {"$eq": source_name}})
        return True
    except Exception as e:
        print(f"Error deleting '{source_name}': {e}")
        return False


def sync_vector_db(
    vector_db,
    api_key: str | None = None,
    model_name: str = "gemini-2.5-flash",
    kb_dir: str = "knowledge_base",
    progress_callback=None
):
    """
    knowledge_base 폴더와 DB를 대조하여 신규 파일만 추가합니다 (증분 업데이트).
    vector_db가 None이면 디스크에서 로드를 시도한 뒤 증분 동기화를 수행합니다.

    Returns:
        (updated_db, new_count, skipped)
        - updated_db: 업데이트된 Chroma 객체 (실패 시 None)
        - new_count: 새로 추가된 파일 수
        - skipped: 이미 존재하여 건너뛴 파일 수
    """
    if not os.path.exists(kb_dir):
        os.makedirs(kb_dir, exist_ok=True)

    # vector_db가 None이면 디스크에서 로드 시도 (증분 로직은 아래에서 공통 처리)
    if vector_db is None:
        db_path = "vector_db"
        collection_name = "di_guidelines"
        if os.path.exists(db_path) and os.listdir(db_path):
            print("Loading existing DB from disk for sync...")
            embedding_model = _get_embedding_model()
            vector_db = Chroma(
                persist_directory=db_path,
                embedding_function=embedding_model,
                collection_name=collection_name
            )
        else:
            # 디스크에도 없으면 처음부터 생성
            print("No existing DB found. Creating from scratch...")
            new_db = get_vector_db(
                api_key=api_key,
                model_name=model_name,
                progress_callback_for_new=progress_callback
            )
            folder_files = [f for f in os.listdir(kb_dir) if f.endswith('.pdf')]
            count = len(folder_files)
            return new_db, count, 0

    # ── 증분 동기화: 폴더 vs DB 비교 ──
    db_sources = set(get_all_source_names(vector_db))
    folder_files = [f for f in os.listdir(kb_dir) if f.endswith('.pdf')]
    new_files = [f for f in folder_files if f not in db_sources]
    skipped = len(folder_files) - len(new_files)

    if not new_files:
        print("No new documents to sync.")
        return vector_db, 0, skipped

    print(f"Syncing {len(new_files)} new file(s): {new_files}")

    new_documents = load_and_split_documents(
        kb_dir=kb_dir,
        api_key=api_key,
        model_name=model_name,
        target_files=new_files,
        progress_callback=progress_callback
    )

    if not new_documents:
        print("Warning: document processing returned empty list.")
        return None, 0, skipped

    vector_db.add_documents(new_documents)
    print(f"Synced {len(new_files)} document(s) successfully.")
    return vector_db, len(new_files), skipped
