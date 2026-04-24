# AI 트렌드 일일 리포트

공간 콘텐츠 제작팀을 위한 AI 플랫폼 트렌드 자동 수집·분석 시스템.

매일 오전 9시(KST)에 GitHub Actions가 RSS·스크래핑으로 AI 플랫폼 업데이트를 수집하고,
Gemini API로 카드 형태(모델명 / 핵심 인사이트 / 공간 콘텐츠 활용 아이디어)로 구조화해
정적 사이트로 배포합니다.

## 초기 설정

### 1. Gemini API 키 발급
1. https://aistudio.google.com 접속 후 구글 로그인
2. 좌측 **Get API key** → **Create API key** 클릭
3. 키 문자열을 복사 (한 번만 표시됨)

### 2. GitHub Secret 등록
- 저장소 **Settings → Secrets and variables → Actions → New repository secret**
- Name: `GEMINI_API_KEY`
- Secret: 위에서 복사한 키 붙여넣기

### 3. Actions 쓰기 권한 부여
- **Settings → Actions → General → Workflow permissions**
- **"Read and write permissions"** 선택 → Save

### 4. GitHub Pages 활성화
- **Settings → Pages**
- Source: **Deploy from a branch**
- Branch: `main` / Folder: `/docs` → Save

### 5. 첫 실행
- **Actions** 탭 → **Daily AI Trends Update** → **Run workflow** 버튼
- 5-10분 후 `https://{사용자명}.github.io/{저장소명}` 접속

## 디렉토리 구조

```
.
├── .github/workflows/daily-update.yml    # cron + 자동 커밋
├── scripts/
│   ├── sources.yaml                       # 수집 대상 목록 (자유 편집)
│   ├── collect.py                         # 수집 + Gemini 분석
│   └── build.py                           # JSON → HTML 렌더링
├── prompts/
│   └── card_generation.md                 # Gemini 시스템 프롬프트 ★ 품질 튜닝 핵심
├── data/                                  # 자동 생성 (수동 편집 불필요)
│   ├── YYYY/MM/YYYY-MM-DD.json           # 일일 카드
│   └── seen.json                          # 중복 방지 인덱스
├── docs/                                # 자동 생성된 배포 페이지
├── requirements.txt
└── README.md
```

## 운영 팁

### 수집 기간 조정 (중요)
`scripts/collect.py` 상단의 `COLLECTION_WINDOW_HOURS` 값 수정.
- `24` (기본): 최근 24시간 내 발행 글만. 일일 리포트 용도에 적합.
- `48`: 최근 이틀치. 주말 누락 방지 등 예외 상황.
- `72`: 최근 3일치.

날짜 확인이 불가능한 스크래핑 항목은 **기본적으로 제외**됩니다 (신뢰성 우선).
발행일 파싱이 안 되는 소스는 Actions 로그에 "(제외: 날짜불명 N건)"으로 표시되니,
해당 소스의 selector를 조정하거나 `<time datetime="...">` 태그를 포함하는 부모 요소로 변경하세요.

### 수집 소스 추가/제거
`scripts/sources.yaml` 편집. RSS가 있으면 `type: rss`가 우선 (안정적).
스크래핑은 사이트 구조가 바뀌면 selector 조정 필요.

### 카드 품질 개선 — 가장 중요
`prompts/card_generation.md` 편집. 이 파일이 카드 품질의 80%를 결정합니다.

초기 1-2주는 매일 카드를 읽어보며:
- 어색한 번역 → 해당 패턴을 막는 규칙 추가
- 활용 아이디어가 일반론 → few-shot 예시에 좋은 예 추가
- 노이즈 과다 → `FILTER_KEYWORDS` 조정 (scripts/collect.py 상단)

변경 후 commit → 다음 cron 실행부터 반영.

### 실행 주기 변경
`.github/workflows/daily-update.yml` 의 cron 표현식 수정.
- 매일 09:00 KST: `'0 0 * * *'` (UTC 기준)
- 매일 09:00 + 18:00 KST: `'0 0,9 * * *'`
- 주 1회 (월요일 09:00 KST): `'0 0 * * 1'`

### 수동 실행
Actions 탭 → Daily AI Trends Update → **Run workflow** 버튼.
즉시 수집 트리거. 긴급한 업데이트 대응 시 유용.

### 에러 대응
Actions 탭에서 실패한 실행 클릭 → 로그 확인. 흔한 경우:
- **GEMINI_API_KEY not found**: Secret 재등록
- **Permission denied to push**: Workflow permissions 재확인
- **Scrape error (특정 소스)**: 해당 소스만 건너뛰고 나머지는 정상 동작. sources.yaml에서 해당 소스 제거하거나 selector 수정.
- **Gemini HTTP 429**: 무료 티어 분당 제한 초과. `GEMINI_RATE_LIMIT_SLEEP` (collect.py) 값을 늘리기.

## 비용

- GitHub Actions: Public 저장소 무료 (무제한)
- GitHub Pages: Public 저장소 무료
- Gemini 2.5 Flash: 무료 티어 하루 1,500회 / 분당 15회. 본 프로젝트 사용량은 일 20-50회 수준.

## 향후 확장

- **주간/월간/분기 합성**: `scripts/reports.py` 추가, 별도 cron 트리거
- **분기 리포트(외부용)**: 문서형 레이아웃으로 별도 페이지 (`docs/quarterly.html`)
- **태그/중요도 필터 UI**: 현재는 정적. 클라이언트 JS로 필터 기능 추가 가능
- **모바일 최적화**: 현재 반응형 기본 수준. 필요 시 별도 레이아웃
