"""
build_db.py — DI 규정 데이터베이스 사전 구축 스크립트
------------------------------------------------------
사용법:
  python build_db.py              (번역 포함, API Key 프롬프트)
  python build_db.py --no-translate (번역 생략, 빠른 구축)
  python build_db.py --key AIza... (키 직접 입력)

출력: di_automation_v2_extracted/vector_db/  ← 앱 실행 시 자동 인식
"""
from __future__ import annotations

import os
import re
import sys
import time
import shutil
import argparse
from datetime import datetime, timedelta

# ────────── 경로 설정 ──────────
SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
KB_DIR       = os.path.join(SCRIPT_DIR, "..", "knowledge_base")   # 원본 PDF 경로
DB_DIR       = os.path.join(SCRIPT_DIR, "vector_db")             # 출력 DB 경로
BATCH_SIZE   = 10   # 한 번의 API 호출로 번역할 청크 수
CHUNK_SIZE   = 1000
CHUNK_OVERLAP = 200

# ────────── GMP 번역 프롬프트 ──────────
_PROMPT_HEADER = """당신은 국내 제약회사에서 20년 이상 GMP(우수 의약품 제조 및 품질관리 기준) 업무를 담당한 전문가입니다.
아래 번호로 구분된 영어 텍스트들을 각각 한국어로 번역하세요.

[번역 규칙]
1. 제약/GMP 분야 공식 한국어 전문 용어 사용
   (Audit Trail→감사추적, Data Integrity→데이터 완전성, ALCOA→ALCOA 원칙,
    Validation→밸리데이션, Qualification→적격성 평가, Raw Data→원본 데이터,
    SOP→표준작업지침서(SOP), CAPA→시정 및 예방조치(CAPA),
    Change Control→변경 관리, OOS→규격 외(OOS), CSV→컴퓨터 시스템 밸리데이션(CSV),
    Audit→감사, Contemporaneous→동시기록, Legible→판독 가능한,
    Good Documentation Practice→우수 기록 관리 기준)
2. 영어 약어는 처음 등장 시 "한국어(영어)" 형식으로 병기
3. 번역문만 출력 (설명, 부연 없음)
4. 반드시 "[번호]" 태그를 유지하여 각 번역을 구분

[원문]
{numbered_texts}

[번역 결과]"""


def is_english(text: str) -> bool:
    if not text:
        return False
    ascii_count = sum(1 for c in text if ord(c) < 128)
    return (ascii_count / len(text)) >= 0.8


def batch_translate(texts: list[str], client, model_name: str) -> list[str | None]:
    """영어 텍스트 리스트를 한 번의 API 호출로 번역합니다."""
    numbered = "\n\n".join(f"[{i+1}]\n{t}" for i, t in enumerate(texts))
    prompt = _PROMPT_HEADER.format(numbered_texts=numbered)

    try:
        response = client.models.generate_content(model=model_name, contents=prompt)
        result = response.text.strip()
    except Exception as e:
        print(f"\n    ⚠ 배치 번역 API 오류: {e}")
        return [None] * len(texts)

    # "[번호] 번역내용" 패턴으로 파싱
    translations: list[str | None] = [None] * len(texts)
    pattern = re.compile(r'\[(\d+)\]\s*(.*?)(?=\[\d+\]|$)', re.DOTALL)
    for m in pattern.finditer(result):
        idx = int(m.group(1)) - 1
        if 0 <= idx < len(texts):
            translations[idx] = m.group(2).strip()
    return translations


def fmt_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{int(seconds)}초"
    m, s = divmod(int(seconds), 60)
    return f"{m}분 {s}초" if m < 60 else f"{m//60}시간 {m%60}분"


def build_database(api_key: str | None, model_name: str = "gemini-2.5-flash",
                   force: bool = False) -> None:
    from langchain_community.document_loaders import PyPDFLoader
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    from langchain_community.vectorstores import Chroma
    from langchain_huggingface import HuggingFaceEmbeddings

    # ── 기존 DB 처리 ──
    if os.path.exists(DB_DIR) and os.listdir(DB_DIR):
        if force:
            print(f"기존 DB 삭제 중: {DB_DIR}")
            shutil.rmtree(DB_DIR)
        else:
            ans = input(f"\n기존 벡터 DB가 존재합니다 ({DB_DIR}). 덮어쓰겠습니까? [y/N] ").strip().lower()
            if ans != 'y':
                print("취소되었습니다.")
                return
            shutil.rmtree(DB_DIR)

    # ── Gemini 클라이언트 초기화 (google.genai 신 SDK) ──
    gemini_client = None
    if api_key:
        from google import genai as google_genai
        gemini_client = google_genai.Client(api_key=api_key)
        print(f"✅ Gemini 모델: {model_name}")
    else:
        print("⚠ API Key 없음 — 번역 생략, 원문만 색인합니다.")

    # ── PDF 목록 ──
    kb_dir = os.path.abspath(KB_DIR)
    if not os.path.exists(kb_dir):
        print(f"오류: knowledge_base 폴더를 찾을 수 없습니다: {kb_dir}")
        sys.exit(1)

    pdf_files = sorted(f for f in os.listdir(kb_dir) if f.endswith('.pdf'))
    if not pdf_files:
        print("오류: knowledge_base 폴더에 PDF 파일이 없습니다.")
        sys.exit(1)

    print(f"\n📂 경로: {kb_dir}")
    print(f"📄 처리 파일: {len(pdf_files)}개\n")

    # ── 텍스트 분할기 ──
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        length_function=len,
        separators=["\n\n", "\n", " ", ""]
    )

    # ── 임베딩 모델 로드 ──
    print("🔄 임베딩 모델 로드 중 (최초 실행 시 다운로드, 약 1-2분)...")
    embedding_model = HuggingFaceEmbeddings(
        model_name="paraphrase-multilingual-MiniLM-L12-v2",
        model_kwargs={'device': 'cpu'},
        encode_kwargs={'normalize_embeddings': True}
    )
    print("✅ 임베딩 모델 준비 완료\n")

    vector_db = None  # 첫 파일 처리 시 생성, 이후 add_documents로 증분 추가
    total_start = time.time()
    global_chunk_count = 0
    translated_count = 0
    failed_batches = 0

    for file_idx, pdf_file in enumerate(pdf_files, start=1):
        file_path = os.path.join(kb_dir, pdf_file)
        file_start = time.time()

        # 이름 줄이기 (50자)
        short_name = pdf_file if len(pdf_file) <= 50 else pdf_file[:47] + "..."
        print(f"[{file_idx:02d}/{len(pdf_files):02d}] 📄 {short_name}")

        try:
            loader = PyPDFLoader(file_path)
            pages = loader.load()
        except Exception as e:
            print(f"       ❌ PDF 로드 오류: {e}\n")
            continue

        for page in pages:
            page.metadata["source_name"] = pdf_file

        chunks = splitter.split_documents(pages)
        for idx, chunk in enumerate(chunks):
            chunk.metadata["index"] = idx

        # 영어 청크 추출
        eng_indices = [i for i, c in enumerate(chunks) if is_english(c.page_content)]
        print(f"       📊 총 {len(chunks)}청크 | 영어(번역 대상): {len(eng_indices)}청크")

        # ── 배치 번역 ──
        if gemini_client and eng_indices:
            batches = [eng_indices[i:i+BATCH_SIZE] for i in range(0, len(eng_indices), BATCH_SIZE)]
            batch_start = time.time()

            for b_idx, batch_indices in enumerate(batches, start=1):
                texts = [chunks[i].page_content for i in batch_indices]

                # ETA 계산 (현재 파일 내 배치 처리 속도 기반)
                batches_done_this_file = b_idx - 1
                if batches_done_this_file > 0:
                    rate = (time.time() - batch_start) / batches_done_this_file
                    remaining = (len(batches) - b_idx + 1) * rate
                    eta_str = f" | 잔여: ~{fmt_duration(remaining)}"
                else:
                    eta_str = ""

                print(f"       🌐 배치 번역 [{b_idx:3d}/{len(batches)}]{eta_str}", end='\r')

                translations = batch_translate(texts, gemini_client, model_name)

                for local_idx, (chunk_idx, trans) in enumerate(zip(batch_indices, translations)):
                    if trans:
                        chunks[chunk_idx].metadata["ko_translation"] = trans
                        translated_count += 1
                    else:
                        failed_batches += 1

                # Rate Limit 방지
                time.sleep(0.5)

            file_elapsed = time.time() - file_start
            print(f"       ✅ 번역 완료 ({len(batches)}배치 | {fmt_duration(file_elapsed)})          ")
        elif not gemini_client and eng_indices:
            print(f"       ℹ  번역 생략 (API Key 없음)")
        else:
            print(f"       ℹ  한국어 문서 — 번역 불필요")

        # ── 파일별 즉시 DB 반영 (메모리 최소화) ──
        print(f"       💾 DB 색인 중... ({len(chunks)}청크)", flush=True)
        embed_s = time.time()
        if vector_db is None:
            vector_db = Chroma.from_documents(
                documents=chunks,
                embedding=embedding_model,
                persist_directory=DB_DIR,
                collection_name="di_guidelines"
            )
        else:
            vector_db.add_documents(chunks)
        global_chunk_count += len(chunks)
        print(f"       ✅ 색인 완료 ({fmt_duration(time.time()-embed_s)})", flush=True)
        print(flush=True)

    total_elapsed = time.time() - total_start

    if vector_db is None:
        print("처리된 문서가 없습니다. knowledge_base를 확인하세요.", flush=True)
        return

    print(f"{'─'*60}", flush=True)
    print(f"📊 최종 결과:", flush=True)
    print(f"   • 처리 파일: {len(pdf_files)}개", flush=True)
    print(f"   • 총 청크:   {global_chunk_count}개", flush=True)
    print(f"   • 번역 완료: {translated_count}개 청크", flush=True)
    print(f"   • 총 소요시간: {fmt_duration(total_elapsed)}", flush=True)
    print(f"   • DB 저장 위치: {os.path.abspath(DB_DIR)}", flush=True)
    print(f"\n💡 회사 PC 배포 방법:", flush=True)
    print(f"   1. 'vector_db' 폴더 전체를 회사 PC의 앱 폴더에 복사", flush=True)
    print(f"   2. 앱 실행 후 API Key만 입력하면 즉시 검색 가능", flush=True)
    print(f"{'─'*60}", flush=True)


def main():
    parser = argparse.ArgumentParser(description="DI 규정 벡터 DB 사전 구축 스크립트")
    parser.add_argument("--key", default="", help="Gemini API Key")
    parser.add_argument("--model", default="gemini-2.5-flash", help="Gemini 모델명")
    parser.add_argument("--no-translate", action="store_true", help="번역 생략 (빠른 구축)")
    parser.add_argument("--force", action="store_true", help="기존 DB 확인 없이 덮어쓰기")
    args = parser.parse_args()

    print("=" * 60)
    print("🛡️  DI 규정 벡터 DB 사전 구축 스크립트")
    print(f"    시작 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    api_key = None
    if not args.no_translate:
        api_key = args.key.strip()
        if not api_key:
            api_key = input("\nGemini API Key를 입력하세요 (번역 생략 시 Enter): ").strip()
        if not api_key:
            print("API Key 없음 — 번역 없이 진행합니다.\n")
            api_key = None

    build_database(api_key=api_key, model_name=args.model, force=args.force)


if __name__ == "__main__":
    main()
