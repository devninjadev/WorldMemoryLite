# World Memory Autopilot 0.24.1

Notion에 시장 사건, 기업·산업 맥락과 변화하는 투자 관점을 누적하는 ChatGPT/Codex 스킬입니다.
이번 릴리즈는 ChatGPT에서 다운로드한 `world-memory-autopilot` 0.24.1의 40개 파일을 그대로 반영합니다.

## 설치

GitHub 릴리즈의 `world-memory-autopilot-v0.24.1.zip`을 스킬로 설치하세요.
릴리즈 ZIP은 클라우드에서 다운로드한 원본입니다. 저장소의 해당 파일과 로컬 설치본도
원본 ZIP의 내용과 일치합니다. 커넥터 인증, 실제 Notion 작업 공간과 예약 실행은 별도로 확인해야 합니다.

전체 실행 지침은 [SKILL.md](world-memory-autopilot/SKILL.md)에 있습니다.
기존 설치를 연결하거나 초기 구조를 만들 때는
[deployment.md](world-memory-autopilot/references/deployment.md)와
[notion-layout.md](world-memory-autopilot/references/notion-layout.md)를 따르세요.
로컬 스킬 설치만으로 기존 Hub, 데이터베이스, 예약 설정을 변경하지 않습니다.

## 이번 버전의 동작

- 중요한 사건을 먼저 찾고, 신뢰할 만한 매체의 사실 보도는 출처와 함께 사용합니다.
  제안, 협상, 익명 취재, 전망과 의견은 각각의 불확실성을 보존합니다.
- FinancialJuice, First Squawk, Reuters, Dow Jones와 Bloomberg XML 피드를 보조 검색 자료로 사용합니다.
  실행별로 성공과 실패를 한 번 수집해 재사용하며, 날짜가 없는 항목을 수집 시각으로 대체하지 않습니다.
- 기업, 정책, 안보, 산업과 거시 사건을 폭넓게 검토합니다. 보통 3–8개 사건을 선택하되
  사건의 중요도에 따라 수를 조절하고 동일 주제에 과도하게 집중하지 않습니다.
- 기업·산업·사건 확장이 활성화되고 준비된 경우, 모든 근거 묶음의 검토를 완료해야
  `prepare-report`가 보고서 생성 요청을 반환합니다. 검토 누락을 보고서만 생성하는 경로로 우회하지 않습니다.
- 보고서 저장 후 계획된 기업·산업·사건과 Story 관계를 처리하고,
  `complete-entity-review`로 확인된 결과와 미완료 작업을 구분합니다.
- 검토 결정, 내부 사유와 처리 집계는 실행 중에만 유지하고 보고서 본문에 넣지 않습니다.
- 지원되는 시장 자료는 TradingView를 우선하며 VIX에는 별도 제공자 경로를 사용합니다.
  Alpaca와 Wolfram 등 대안은 현재 접근 가능한 도구와 필드별 결과에 따라 적용합니다.
- 같은 시간창의 보고서가 있으면 재사용하고, 저장 실패·불확실·표시 가능한 URL 부재 시
  생성한 본문과 실제 저장 상태를 반환합니다.

이 스킬은 Python 표준 라이브러리를 사용합니다. 보조 XML 수집기는 curl을 사용합니다.
핵심 지속 저장은 공식 Notion MCP를 통해 수행하며, 스킬 설치가 연결 권한이나 자동매매를 만들지 않습니다.

## 검증과 패키징

클라우드에 포함된 26개 테스트와 릴리즈 도구의 10개 테스트가 통과했습니다.
Python 파일 구문, ZIP 무결성, 40개 파일의 원본·저장소·설치본 일치도 확인했습니다.

```sh
PYTHONPATH=world-memory-autopilot/scripts python3 -B -m unittest discover -s world-memory-autopilot/tests -p test_required_entity_completion.py -v
PYTHONPATH=world-memory-autopilot/scripts python3 -B -m unittest discover -s world-memory-autopilot/tests -p test_financialjuice_feed.py -v
python3 -B -m unittest discover -s tests -p test_release_builder.py -v
python3 scripts/build_world_memory_release.py
```

릴리즈 도구는 클라우드와 동일한 40개 파일을 결정적으로 묶습니다. ZIP 압축 메타데이터는
클라우드 원본과 다를 수 있지만, 각 파일의 바이트 내용은 일치해야 합니다.
그 밖의 개발 테스트, 캐시와 실행 기록은 릴리즈에 포함하지 않습니다.

이전 0.17 계열의 개발 회귀 테스트는 보존되어 있습니다. 일부는 현재의 제공자 계획,
보고서 검토 입력과 CLI 계약과 맞지 않아 실패하며, 전체 과거 회귀 테스트가 통과했다고
주장하지 않습니다. 실제 Workspace Agent, Notion 쓰기, 시장 커넥터와 예약 실행의
성공은 이 로컬 검증 범위에 포함되지 않습니다.
