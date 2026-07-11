# 네이버 외국인 순매수·순매도 대시보드

컴퓨터에 Python을 설치하지 않아도 됩니다.

GitHub Actions가 네이버 증권 페이지를 읽어 `data.json`을 만들고,
GitHub Pages가 `index.html`을 웹페이지로 보여줍니다.

## 들어 있는 파일

- `index.html`: 차트 화면
- `update.py`: 네이버 데이터를 읽는 자동화 코드
- `data.json`: 자동으로 갱신되는 데이터
- `requirements.txt`: GitHub가 설치할 도구 목록
- `.github/workflows/update.yml`: 평일 자동 실행 설정

## 설치 순서

1. GitHub에서 새 Public 저장소를 만듭니다.
2. 이 ZIP을 압축 해제합니다.
3. 폴더 안의 모든 파일과 `.github` 폴더를 저장소에 업로드합니다.
4. 저장소의 Actions 메뉴에서 워크플로를 수동 실행합니다.
5. Settings → Pages에서 main 브랜치와 `/ (root)`를 선택합니다.
6. 생성된 GitHub Pages 주소를 Notion에 `/embed`로 넣습니다.

## 주의

네이버가 웹페이지 구조를 바꾸면 자동 수집 코드도 수정해야 할 수 있습니다.
