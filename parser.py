from __future__ import annotations

import os
import time
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from utils import is_english, build_translate_prompt


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=3, max=15),
    retry=retry_if_exception_type(Exception),
    reraise=False
)
def _call_translate_api(client, model_name: str, prompt: str) -> str | None:
    """Gemini API 호출 — google.genai 신 SDK (최대 3회 재시도, 지수 백오프 3~15초)"""
    response = client.models.generate_content(model=model_name, contents=prompt)
    return response.text.strip()


def translate_chunk(text: str, client, model_name: str) -> str | None:
    """단일 청크를 GMP 전문 용어로 번역합니다."""
    try:
        prompt = build_translate_prompt(text)
        return _call_translate_api(client, model_name, prompt)
    except Exception as e:
        print(f"Translation failed after retries: {e}")
        return None


def load_and_split_documents(
    kb_dir: str = "knowledge_base",
    api_key: str | None = None,
    model_name: str = "gemini-2.5-flash",
    target_files: list | None = None,
    progress_callback=None
) -> list:
    """
    knowledge_base 디렉토리의 PDF를 읽어 청크로 분할하고 사전 번역합니다.

    Args:
        kb_dir: PDF 파일이 있는 디렉토리
        api_key: Gemini API 키 (없으면 번역 생략)
        model_name: 사용할 Gemini 모델명
        target_files: 지정 시 해당 파일만 처리
        progress_callback: (file_name, current_idx, total) → None 형태의 진행 콜백
    """
    documents = []

    if not os.path.exists(kb_dir):
        os.makedirs(kb_dir, exist_ok=True)
        return []

    if target_files:
        pdf_files = [f for f in target_files if f.endswith('.pdf')]
    else:
        pdf_files = [f for f in os.listdir(kb_dir) if f.endswith('.pdf')]

    if not pdf_files:
        return []

    # google.genai 신 SDK로 클라이언트 1회 초기화
    gemini_client = None
    if api_key:
        from google import genai as google_genai
        gemini_client = google_genai.Client(api_key=api_key)

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        length_function=len,
        separators=["\n\n", "\n", " ", ""]
    )

    for file_idx, pdf_file in enumerate(pdf_files):
        if progress_callback:
            progress_callback(pdf_file, file_idx, len(pdf_files))

        file_path = os.path.join(kb_dir, pdf_file)
        if not os.path.exists(file_path):
            print(f"Skipping missing file: {pdf_file}")
            continue

        try:
            print(f"Processing: {pdf_file} ...")
            loader = PyPDFLoader(file_path)
            pages = loader.load()

            for page in pages:
                page.metadata["source_name"] = pdf_file

            chunks = text_splitter.split_documents(pages)

            for idx, chunk in enumerate(chunks):
                chunk.metadata["index"] = idx

            # 사전 번역 (API 키 있을 때만)
            if gemini_client:
                print(f"  Pre-translating {len(chunks)} chunks for {pdf_file}...")
                for i, chunk in enumerate(chunks):
                    if is_english(chunk.page_content):
                        translated = translate_chunk(chunk.page_content, gemini_client, model_name)
                        if translated:
                            chunk.metadata["ko_translation"] = translated

                    # API Rate Limit 방지: 10청크마다 1초 대기
                    if (i + 1) % 10 == 0:
                        time.sleep(1)
                print(f"  Pre-translation done for {pdf_file}.")

            documents.extend(chunks)
            print(f"  Finished {pdf_file}: {len(chunks)} chunks.")

        except Exception as e:
            print(f"Error processing {pdf_file}: {e}")

    # 완료 콜백
    if progress_callback:
        progress_callback("완료", len(pdf_files), len(pdf_files))

    return documents
