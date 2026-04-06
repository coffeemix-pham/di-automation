import time
import functools
from datetime import datetime

def is_english(text: str) -> bool:
    """텍스트의 80% 이상이 ASCII 문자이면 영어로 판단"""
    if not text:
        return False
    ascii_count = sum(1 for c in text if ord(c) < 128)
    return (ascii_count / len(text)) >= 0.8

GMP_TRANSLATE_PROMPT_TEMPLATE = """당신은 국내 제약회사에서 20년 이상 GMP(우수 의약품 제조 및 품질관리 기준) 업무를 담당한 전문가입니다.

아래 영어 원문을 한국어로 번역하되, 다음 규칙을 반드시 따르세요:

[번역 규칙]
1. 제약/GMP 분야에서 공식적으로 사용하는 한국어 전문 용어를 사용할 것
   (예: Audit Trail → 감사추적, Data Integrity → 데이터 완전성, ALCOA → ALCOA 원칙,
        Validation → 밸리데이션, Qualification → 적격성 평가, Raw Data → 원본 데이터,
        SOP → 표준작업지침서(SOP), Quality Unit → 품질부서, Complete → 완전한,
        Contemporaneous → 동시기록, Accurate → 정확한, Legible → 판독 가능한,
        Original → 원본, Traceable → 추적 가능한, Good Documentation Practice → 우수 기록 관리 기준,
        CAPA → 시정 및 예방조치(CAPA), Change Control → 변경 관리, OOS → 규격 외(OOS),
        Computer System Validation → 컴퓨터 시스템 밸리데이션)
2. 의미가 명확히 전달되도록 자연스럽게 번역할 것
3. 영어 약어는 처음 등장 시 "한국어(영어)" 형식으로 병기할 것
4. 번역문만 출력하고, 설명이나 부연은 추가하지 말 것

[영어 원문]
{text}

[한국어 번역]"""

def build_translate_prompt(text: str) -> str:
    """GMP 번역 프롬프트 생성 (단일 진실 공급원)"""
    return GMP_TRANSLATE_PROMPT_TEMPLATE.format(text=text)

def format_relevance(score: float) -> tuple[float, str]:
    """
    ChromaDB L2 거리 점수를 관련도 백분율로 변환.
    normalize_embeddings=True 설정 시 L2 거리 범위는 0~2.
    낮을수록 유사 → 높은 관련도
    """
    pct = max(0.0, min(1.0, 1.0 - score / 2.0))
    if pct >= 0.75:
        label = "🟢 높음"
    elif pct >= 0.50:
        label = "🟡 보통"
    else:
        label = "🔴 낮음"
    return pct, label

def generate_di_report(
    proposal_text: str,
    analysis_result: str,
    context_docs: list,
    model_name: str
) -> str:
    """
    Tab2 분석 결과를 DI 위반 검토 보고서 형식(UTF-8 텍스트)으로 변환.
    context_docs: LangChain Document 객체 리스트
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    separator = "=" * 60

    lines = [
        separator,
        "데이터 완전성(DI) 위반 검토 보고서",
        f"생성 일시: {now}",
        f"사용 AI 모델: {model_name}",
        separator,
        "",
        "[검토 대상 문장]",
        proposal_text.strip(),
        "",
        "[참조 가이드라인 원문]",
    ]

    for i, doc in enumerate(context_docs, start=1):
        src = doc.metadata.get("source_name", "알 수 없음")
        page = doc.metadata.get("page", 0) + 1
        lines.append(f"\n{i}. {src} — {page}페이지")
        lines.append(doc.page_content.strip())

    lines += [
        "",
        "[AI 분석 결과]",
        analysis_result.strip(),
        "",
        separator,
        "※ 본 보고서는 AI 분석 결과이며, 최종 판단은 전문가 검토가 필요합니다.",
        separator,
    ]

    return "\n".join(lines)
