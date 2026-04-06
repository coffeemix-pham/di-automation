# 🛡️ 데이터 완전성(DI) 자동 확인 시스템: 회사 PC 배포 가이드

본 시스템은 국내외 제약 규제기관의 최신 가이드라인을 기반으로 **정확한 규정 검색 및 제안서 위반 여부 분석**을 지원합니다. 아래 절차를 따라 회사 PC에 성공적으로 설치하고 구동해 보세요.

---

## 📋 1. 준비 사항 (Pre-requisites)
1. **파이썬 설치**: 회사 PC에 [Python 3.9 이상](https://www.python.org/downloads/windows/) 버전이 설치되어 있어야 합니다. (설치 시 `Add Python to PATH` 옵션을 반드시 체크하세요.)
2. **인터넷 연결**: 분석 및 번역을 위해 **Gemini API** 호출(인터넷 검색 가능 환경)이 필요합니다.
3. **API Key**: [Google AI Studio](https://aistudio.google.com/app/apikey)에서 발급받은 본인의 API Key를 준비하세요.

---

## 🚀 2. 설치 및 실행 단계 (Deployment)

### **1단계: 폴더 복사 및 압축 해제**
- 집(개인 PC)에서 작업한 `di_automation` 폴더 전체를 압축하여 회사 PC의 작업 가능한 위치(예: `C:\Users\YourName\Desktop\di_automation`)에 압축을 풉니다.

### **2단계: 최초 1회 환경 구축**
- 회사 PC의 해당 폴더 안에서 다음 명령어를 한 번만 실행하면 필요한 라이브러리(`langchain`, `streamlit` 등)가 자동으로 설치됩니다.
- **방법**: 명령 프롬프트(CMD) 또는 터미널을 열고 다음 입력:
  ```bash
  pip install -r requirements.txt
  ```

### **3단계: 프로그램 실행 (가장 쉬운 방법)**
- 폴더 내의 **`run_app.bat`** 파일을 더블 클릭하세요!
- 잠시 대기하면 자동으로 웹 브라우저가 열리며 시스템 화면이 나타납니다.

---

## 💡 3. 주요 기능 활용 팁

- **🔍 규정 검색**: "Audit Trail", "ALCOA" 등을 검색하여 원문과 GMP 전문 번역을 동시에 확인하세요.
- **🌐 영문 번역**: 영어 원문은 사이드바의 `영문 자동 번역` 토글이 켜져 있으면 자동으로 한국어 GMP 용어로 번역됩니다.
- **📂 문서 추가**: 새로운 가이드라인 PDF가 생기면 `knowledge_base` 폴더에 넣고 앱을 재시작하면 자동으로 색인됩니다. (또는 앱 실행 중 사이드바의 Upload 버튼 활용)

---

## 🛠️ 4. 문제 해결 (Troubleshooting)

- **404 모델 오류**: 사이드바의 `사용할 AI 모델 선택` 메뉴에서 `gemini-flash-latest` 또는 `gemini-1.5-pro` 등을 하나씩 시도해 보세요.
- **보안 차단**: 회사 보안 프로그램이 특정 파일을 차단한다면, 해당 폴더를 제외(Exception) 설정하거나 보안 담당자에게 요청하세요.
- **번역 중단**: API Key에 공백이 포함되지 않았는지 다시 확인하고, 인터넷 연결 상태를 점검하세요.

---
© 2024 Corporate Data Integrity Assistant | Designed for Pharmaceutical Professionals
