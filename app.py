from __future__ import annotations

import streamlit as st
import os
from datetime import datetime
from google import genai as google_genai
from utils import is_english, build_translate_prompt, format_relevance, generate_di_report
from vector_db import get_vector_db, get_all_source_names, delete_document_from_db, sync_vector_db

# ────────────────────────────────────────────
#  페이지 설정
# ────────────────────────────────────────────
st.set_page_config(page_title="DI 규정 자동 확인 시스템", layout="wide")

KB_DIR = "knowledge_base"
if not os.path.exists(KB_DIR):
    os.makedirs(KB_DIR, exist_ok=True)

# 세션 상태 초기화
defaults = {
    "api_key": "",
    "model_name": "gemini-2.5-flash",
    "translate_on": True,
    "analysis_result": None,
    "proposal_text": "",
    "context_docs": [],
}
for key, val in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = val


# ────────────────────────────────────────────
#  GMP 전문 용어 번역 함수 (캐시)
# ────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def translate_gmp(text: str, api_key: str, model_name: str) -> str:
    if not api_key:
        return "※ 번역을 위해 사이드바에 Gemini API Key를 입력하세요."
    try:
        client = google_genai.Client(api_key=api_key.strip())
        prompt = build_translate_prompt(text)
        response = client.models.generate_content(model=model_name, contents=prompt)
        return response.text.strip()
    except Exception as e:
        return f"번역 오류: {e}"


# ────────────────────────────────────────────
#  검색 결과 카드 렌더링
# ────────────────────────────────────────────
def show_result_card(idx: int, doc, score: float | None, api_key: str, translate_on: bool):
    source = doc.metadata.get("source_name", "알 수 없음")
    page   = doc.metadata.get("page", 0) + 1
    text   = doc.page_content
    pre_translated = doc.metadata.get("ko_translation")

    # 관련도 표시
    if score is not None:
        pct, label = format_relevance(score)
        relevance_str = f" | 관련도: {label} ({pct*100:.0f}%)"
    else:
        relevance_str = ""

    label_str = f"📌 [결과 {idx+1}] {source} — {page}페이지{relevance_str}"

    with st.expander(label_str, expanded=(idx == 0)):
        if score is not None:
            pct, _ = format_relevance(score)
            st.progress(pct, text=f"관련도: {pct*100:.0f}%")

        english = is_english(text)
        if english and translate_on:
            col_orig, col_trans = st.columns(2)
            with col_orig:
                st.markdown("**🇺🇸 원문 (English)**")
                st.markdown(
                    f"<div style='background:#f0f4ff;padding:12px;border-radius:8px;"
                    f"font-size:0.88rem;line-height:1.7;white-space:pre-wrap;'>{text}</div>",
                    unsafe_allow_html=True
                )
            with col_trans:
                st.markdown("**🇰🇷 한국어 번역 (GMP 전문 용어)**")
                if pre_translated:
                    st.markdown(
                        f"<div style='background:#f0fff4;padding:12px;border-radius:8px;"
                        f"font-size:0.88rem;line-height:1.7;white-space:pre-wrap;'>{pre_translated}</div>",
                        unsafe_allow_html=True
                    )
                    st.caption("✨ 사전 번역된 데이터를 사용하여 응답이 빨라졌습니다.")
                else:
                    with st.spinner("실시간 GMP 용어로 번역 중…"):
                        translated = translate_gmp(text, api_key, st.session_state.model_name)
                    st.markdown(
                        f"<div style='background:#f0fff4;padding:12px;border-radius:8px;"
                        f"font-size:0.88rem;line-height:1.7;white-space:pre-wrap;'>{translated}</div>",
                        unsafe_allow_html=True
                    )
        else:
            st.markdown(
                f"<div style='background:#f8f9fa;padding:12px;border-radius:8px;"
                f"font-size:0.88rem;line-height:1.7;white-space:pre-wrap;'>{text}</div>",
                unsafe_allow_html=True
            )

        st.caption(f"📁 출처: {source} | 🔖 페이지: {page}")


# ────────────────────────────────────────────
#  사이드바 설정
# ────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ 시스템 설정")
    input_key = st.text_input(
        "Gemini API Key",
        type="password",
        value=st.session_state.api_key,
        placeholder="AIza…"
    )
    if input_key:
        st.session_state.api_key = input_key.strip()

    st.markdown("---")
    st.subheader("🤖 AI 모델 설정")
    available_models = [
        "gemini-2.5-flash",
        "gemini-2.5-pro",
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
    ]
    selected_model = st.selectbox(
        "사용할 AI 모델 선택",
        options=available_models,
        index=0
    )
    st.session_state.model_name = selected_model

    st.markdown("---")
    st.session_state.translate_on = st.toggle(
        "🌐 영문 자동 번역 (GMP 전문 용어)", value=st.session_state.translate_on
    )

    st.markdown("---")
    score_threshold = st.slider(
        "🎯 최소 관련도 임계값",
        min_value=0.0, max_value=2.0, value=1.5, step=0.1,
        help="L2 거리 기준. 낮을수록 엄격한 필터링 (0=완전 일치, 2=무관)"
    )

    st.markdown("---")
    st.info("💡 '문서 관리' 탭에서 신규 문서를 등록하거나 삭제할 수 있습니다.")


# ────────────────────────────────────────────
#  벡터 DB 로드
# ────────────────────────────────────────────
@st.cache_resource
def load_db():
    try:
        return get_vector_db()
    except Exception:
        return None

if "db" not in st.session_state:
    st.session_state.db = load_db()

db = st.session_state.db


# ────────────────────────────────────────────
#  메인 타이틀
# ────────────────────────────────────────────
st.title("🛡️ 데이터 완전성(DI) 규정 자동 확인 시스템")
st.markdown("규제기관의 가이드라인을 기반으로 **정확한 원문 출처와 번역본**을 제공합니다.")
st.markdown("---")

tab1, tab2, tab3, tab4 = st.tabs(["🔍 규정 검색", "📝 제안서 검토", "📂 전문 열람", "⚙️ 문서 관리"])


# ──── 탭 1: 규정 검색 ────
with tab1:
    st.subheader("가이드라인 검색")
    query = st.text_input(
        "키워드 또는 확인하고 싶은 내용을 입력하세요",
        placeholder="예: ALCOA 원칙, 감사추적, data integrity",
        key="search_q"
    )
    result_count = st.slider("검색 결과 수", min_value=1, max_value=10, value=5)

    if query:
        if not db:
            st.error("데이터베이스가 비어 있습니다. '문서 관리' 탭에서 동기화를 진행해 주세요.")
        else:
            with st.spinner("검색 중…"):
                results_with_scores = db.similarity_search_with_score(query, k=result_count)

            # 유사도 임계값 필터링
            filtered = [(doc, score) for doc, score in results_with_scores if score <= score_threshold]

            if not filtered:
                st.warning(f"관련 조항을 찾을 수 없습니다. (임계값: {score_threshold}, 미달 결과 {len(results_with_scores)}개 제외)")
                if results_with_scores:
                    st.info("임계값을 높이거나 다른 키워드로 검색해 보세요.")
            else:
                st.caption(f"총 {len(filtered)}개 결과 표시 (임계값 {score_threshold} 이하)")
                for idx, (doc, score) in enumerate(filtered):
                    show_result_card(idx, doc, score, st.session_state.api_key, st.session_state.translate_on)


# ──── 탭 2: 제안서 위반 검토 ────
with tab2:
    st.subheader("SOP/제안서 규정 준수 분석")
    proposal_text = st.text_area(
        "검토할 문장을 입력하세요",
        height=250,
        placeholder="예: '전자 기록은 수정 시 기존 내용을 덮어씌워 보관한다.'"
    )

    if st.button("🔎 분석 실행"):
        if not st.session_state.api_key:
            st.error("API Key가 필요합니다.")
        elif not proposal_text.strip():
            st.warning("분석할 내용을 입력하세요.")
        elif not db:
            st.error("데이터베이스가 없습니다.")
        else:
            with st.spinner("가이드라인 대조 중…"):
                context_docs = db.similarity_search(proposal_text, k=5)
                context = "\n\n---\n\n".join(
                    [f"[{d.metadata.get('source_name')}] {d.page_content}" for d in context_docs]
                )
                prompt = (
                    "당신은 제약 GMP 분야의 데이터 완전성(DI) 전문가입니다.\n"
                    "아래 가이드라인 원문을 근거로 제안서의 규정 준수 여부를 분석하세요.\n"
                    "위반 사항이 있으면 구체적인 조항과 함께 명확히 지적하고, 개선 방안을 제시하세요.\n\n"
                    f"[참조 가이드라인]\n{context}\n\n"
                    f"[검토 대상 문장]\n{proposal_text}"
                )
                try:
                    client = google_genai.Client(api_key=st.session_state.api_key)
                    response = client.models.generate_content(
                        model=st.session_state.model_name, contents=prompt
                    )
                    analysis = response.text

                    # 세션 상태에 저장 (보고서 다운로드용)
                    st.session_state.analysis_result = analysis
                    st.session_state.proposal_text = proposal_text
                    st.session_state.context_docs = context_docs

                    st.markdown(analysis)
                except Exception as e:
                    st.error(f"오류: {e}")

    # 분석 결과가 있으면 보고서 다운로드 버튼 표시
    if st.session_state.analysis_result:
        st.markdown("---")
        report_text = generate_di_report(
            proposal_text=st.session_state.proposal_text,
            analysis_result=st.session_state.analysis_result,
            context_docs=st.session_state.context_docs,
            model_name=st.session_state.model_name
        )
        filename = f"DI_검토보고서_{datetime.now().strftime('%Y%m%d_%H%M')}.txt"
        st.download_button(
            label="📥 DI 위반 검토 보고서 다운로드 (.txt)",
            data=report_text.encode("utf-8-sig"),  # BOM 포함 → Windows 메모장 한글 정상 출력
            file_name=filename,
            mime="text/plain; charset=utf-8"
        )


# ──── 탭 3: 전체 문서 열람 ────
with tab3:
    st.subheader("📂 등록 가이드라인 전체 보기")
    source_names = get_all_source_names(db)

    if not source_names:
        st.info("등록된 문서가 없습니다. '문서 관리' 탭에서 문서를 추가해 주세요.")
    else:
        selected_doc = st.selectbox("문서 선택", options=source_names)
        if selected_doc:
            # ChromaDB 0.5+ where 필터 문법 수정
            doc_data = db.get(where={"source_name": {"$eq": selected_doc}})
            chunks = []
            for i in range(len(doc_data["documents"])):
                chunks.append({
                    "text": doc_data["documents"][i],
                    "meta": doc_data["metadatas"][i]
                })
            chunks.sort(key=lambda x: (x["meta"].get("page", 0), x["meta"].get("index", 0)))

            for chunk in chunks:
                orig = chunk["text"]
                trans = chunk["meta"].get("ko_translation")
                pg = chunk["meta"].get("page", 0) + 1

                if is_english(orig):
                    c1, c2 = st.columns(2)
                    with c1:
                        st.markdown(f"<small>Pg {pg}</small>", unsafe_allow_html=True)
                        st.markdown(orig)
                    with c2:
                        if trans:
                            st.markdown(
                                f"<div style='background:#f1f8e9;padding:10px;border-radius:6px;'>{trans}</div>",
                                unsafe_allow_html=True
                            )
                        else:
                            st.warning("사전 번역본 없음")
                else:
                    st.markdown(f"<small>Pg {pg}</small>", unsafe_allow_html=True)
                    st.markdown(orig)
                st.markdown("<hr>", unsafe_allow_html=True)


# ──── 탭 4: 문서 관리 ────
with tab4:
    st.subheader("📂 문서 동기화 및 관리")

    # ── 1. 신규 PDF 업로드 ──
    st.markdown("### 📤 신규 PDF 업로드")
    uploaded_files = st.file_uploader(
        "파일을 선택하거나 끌어다 놓으세요",
        type="pdf",
        accept_multiple_files=True
    )
    if uploaded_files:
        for f in uploaded_files:
            with open(os.path.join(KB_DIR, f.name), "wb") as out:
                out.write(f.read())
        st.success(f"{len(uploaded_files)}개 파일이 'knowledge_base'에 저장되었습니다.")

    st.markdown("---")

    # ── 2. 동기화 (증분 업데이트) ──
    st.markdown("### 🔄 데이터베이스 동기화")
    st.caption("폴더에 새로 추가된 파일을 인식하여 번역 및 색인을 진행합니다.")

    if st.button("🚀 신규 문서 반영 시작", type="primary"):
        if not st.session_state.api_key:
            st.error("사전 번역을 위해 Gemini API Key가 필요합니다.")
        else:
            progress_bar = st.progress(0.0, text="준비 중...")
            status_text = st.empty()

            def ui_progress(current_file: str, current_idx: int, total: int):
                if total == 0:
                    return
                progress_val = current_idx / total
                progress_bar.progress(progress_val, text=f"처리 중: {current_file}")
                status_text.text(f"[{current_idx}/{total}] {current_file}")

            sync_success = False
            with st.status("신규 문서를 분석 중입니다...", expanded=True) as sync_status:
                try:
                    result = sync_vector_db(
                        st.session_state.db,
                        api_key=st.session_state.api_key,
                        model_name=st.session_state.model_name,
                        progress_callback=ui_progress
                    )
                    updated_db, new_count, skipped = result

                    if updated_db is None:
                        sync_status.update(label="⚠️ 문서 처리 실패: PDF 파싱 오류 또는 빈 파일", state="error")
                    elif new_count == 0:
                        st.session_state.db = updated_db
                        sync_status.update(label=f"ℹ️ 신규 문서 없음 (이미 등록된 파일 {skipped}개)", state="complete")
                    else:
                        st.session_state.db = updated_db
                        progress_bar.progress(1.0, text="완료!")
                        sync_status.update(
                            label=f"✅ 동기화 완료! 신규 {new_count}개 반영 (기존 {skipped}개 유지)",
                            state="complete"
                        )
                        sync_success = True
                except Exception as e:
                    sync_status.update(label=f"❌ 오류 발생: {e}", state="error")

            # st.rerun()은 with st.status() 블록 밖에서 호출해야 화면 업데이트가 보장됨
            if sync_success:
                st.rerun()

    st.markdown("---")

    # ── 3. 문서 삭제 관리 ──
    st.markdown("### 🗑️ 등록 문서 관리 (삭제)")
    sources = get_all_source_names(db)
    if not sources:
        st.info("현재 등록된 문서가 없습니다.")
    else:
        for src in sources:
            col_name, col_del = st.columns([4, 1])
            with col_name:
                st.text(f"📄 {src}")
            with col_del:
                if st.button("삭제", key=f"del_{src}"):
                    file_path = os.path.join(KB_DIR, src)
                    if os.path.exists(file_path):
                        os.remove(file_path)
                    if delete_document_from_db(db, src):
                        st.success(f"'{src}' 삭제 완료")
                        st.rerun()
                    else:
                        st.error("삭제 중 오류가 발생했습니다.")


# ────────────────────────────────────────────
#  푸터
# ────────────────────────────────────────────
st.markdown("---")
st.caption("🛡️ DI Automation System v2 | 유사도 점수 표시 · 보고서 다운로드 · 진행률 표시 기능 포함")
