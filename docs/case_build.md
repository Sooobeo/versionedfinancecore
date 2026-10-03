# 공개자료 case의 계산·검토 실행

다섯 공개자료 사례를 동일 명령으로 재현하고, 계산물과 남은 release blocker를 묶는다. 로컬에 기록된 사실과 가정을 사용하므로 실행 시 네트워크·API key가 필요 없다. 개인 연구용 계산 재현이며 독립적인 사람의 검토나 실제 투자·신용 결론을 대신하지 않는다.

## 실행

저장소 루트에서 Python 3.11 이상을 사용한다.

```powershell
$env:PYTHONPATH = 'src'
python -m versioned_finance_core build-case cases/walmart_20260521_p1_valuation --build-root build/case_review
python -m versioned_finance_core verify-build <출력된-stage-경로>
```

같은 입력·코드로 같은 root에 재실행하면 기존 결과를 덮어쓰지 않고 실패한다. 재현 비교에는 새로운 `--build-root`를 지정한다. 출력된 stage의 `outputs/review_memo.md`가 시작점이다. `release_manifest.json`은 source/input/config/code/output/memo hash, gate, 환경과 제한사항을 보존한다. `verify-build`는 무결성과 현재 코드/config 일치를 확인한다. 실제 재계산 비교에는 두 번의 `build-case`가 필요하다.

두 번의 새 계산과 비교를 한 명령으로 수행하려면 자동 인수인계 명령을 사용한다.

```powershell
python -m versioned_finance_core reproduce-case cases/walmart_20260521_p1_valuation --output-dir build/walmart_handover
python -m versioned_finance_core verify-reproduction build/walmart_handover
```

대상 폴더는 존재하지 않아야 한다. `first/`와 `second/` 아래에서 각각 원천부터 계산하고, 파일별 hash·source/input/config/code/output/memo/content identity와 gate 상태를 대조한다. `reproduction_memo.md`는 두 검토 메모로 연결되고 `reproduction_report.json`은 비교 근거와 남은 blocker를 보존한다. 자동 재현 `PASS`는 **사람 검토·재무 가정 검증·원천 권리·전체 release PASS를 뜻하지 않는다.** 원본 case gate를 수정하지 않으며 사람 검토는 `NOT_PERFORMED`, publication은 `WITHHELD`다. 같은 설치 환경 안의 반복 실행이므로 교차 운영체제 검증도 주장하지 않는다.

## 사례별 실행 범위

| Case | recipe | 실제 생성하는 것 | 추가 자료가 필요한 것 |
|---|---|---|---|
| 오리온 진천센터 | Core cash → Capital evidence | 정규화 fact, 모회사 별도 현금 대사, 프로젝트 현금·권리·자금 근거의 충족 범위 | 운영 driver, 잔여 프로젝트 지출·이연권, 법인별 가용 현금 |
| Walmart 실적 비교 | Guidance comparison | 동일 정의 guidance range와 실제치 비교 | 차이의 원인, 연결 재무·재전망, 독립 검토 |
| Walmart 가치평가 | Core cash → Conditional valuation | 조건부 연결 3표, FCFF/FCFE, 할인율·DCF screen, 부분 claim bridge, 가정 표 | 시장 입력의 시점·권리, 리스·현금세금, 평가일 현금/claim, terminal·downside, 독립 검토 |
| SWA DFS | DFS reproduction | 공개 연차 현금흐름 산술과 표시 반올림 범위 | status quo/defer, 잔여 지출·날짜, JV 현금 귀속·확약 funding |
| Ford Credit | Core cash → Credit evidence | 현금 대사, 그룹과 채무자 현금 구분, covenant 계산가능성 | 채무자별 현금·지급일·CFADS, draw 조건, 담보·청구권, 독립 검토 |

Walmart 가치평가의 선언된 조건부 가정은 검증된 예측으로 승격되지 않는다. SWA DFS의 저자 전망 재현은 M2의 증분 투자안 평가가 아니며, Ford Credit의 annual maturity bucket은 지급일별 유동성 경로가 아니다. 현행 recipe는 각 case의 공개자료로 가능한 범위를 실행한다.

## 무엇이 끝나야 실제 release인가

1. 각 stage의 `outputs/review_report.json`과 `review_findings.csv`에서 미해결 항목을 확인한다. 필요한 자료의 법인·기간·단위·최초 공개시각을 먼저 고정한다.
2. 새로 확보한 원천은 receipt와 fact vintage를 추가하고, 기존 raw fact를 덮어쓰지 않는다. 현재 역사적 cutoff 이후 처음 공개된 내용은 당시 입력에 넣을 수 없다.
3. 근거가 뒷받침하는 별도 scenario/config/version을 만든다. 가정의 합리성, 주요 하방과 결론 전환조건을 검토한다.
4. 실제 계약·경제성 문제를 이해하는 사람이 핵심 가정과 반대논리를 검토하고 challenge·response·retest를 남긴다. AI 에이전트의 코드 검사는 이 사람 검토를 충족하지 않는다.
5. 해소된 입력으로 재계산하고 활성 모듈 gate, memo 연결, 재현성을 다시 확인한다. 공개자료가 끝내 부족한 모듈은 보류 또는 비활성화한다. 필수 조건을 모두 충족한 새 stage만 발행 후보가 된다.

UI·데이터베이스·대용량 최적화는 이 실행 경로와 판단 근거의 후속 확장이다. 현재 규모에서 측정한 병목 없이 DuckDB나 cache를 필수 의존성으로 추가하지 않는다.

## 2026-10-03 첫 통합 검증 기록 (후속 보강 이전)

- `python -m pytest`: 321개 통과. `python -m compileall -q src`, `python -m ruff check src tests`도 통과했다.
- 위 다섯 case를 `build/review_20261003`과 `build/review_replay_20261003`에 각각 새로 계산했다. 모두 `verify-build`에 해당하는 무결성 검증을 통과했고, 두 실행의 input/output/memo/content hash와 파일별 hash가 일치했다.
- 모든 결과는 `WITHHELD`, `release_ready=false`다. 각 case 아래의 stage 디렉터리에서 `outputs/review_memo.md`를 먼저 읽는다. `build/`는 로컬 재생성 산출물이며 저장소에 commit하거나 공개 release로 발행하지 않았다.
- 중복 JSON key, 비표준 NaN/Infinity, 중복 gate/finding CSV 열, 잘못된 행 너비, 입력 scope/cutoff 불일치, 계산 중 원문 snapshot 변경·삭제, 기존 stage 덮어쓰기를 거부하는 회귀 검사를 포함한다.
- GitHub Actions에 Python 3.11/3.12 테스트·compile·lint 작업을 추가했다. 이 기록은 로컬 검증 결과이며 원격 CI 실행 성공을 뜻하지 않는다.

## 2026-10-03 후속 최종 검증

M1/M2/M3 공개근거·통제와 자동 인수인계까지 보강한 후 전체 **389개 테스트**, compileall, Ruff가 통과했다. 다섯 사례에 `reproduce-case`로 총 10회 fresh build를 만들고 `verify-reproduction`으로 각 bundle을 검증했다. 모두 동일한 stable identity와 파일 hash를 재현했다. 새 결과는 `build/nonhuman_20261003/<case_id>/reproduction_memo.md`에서 시작하며, stage ID·검증 범위·남은 자료와 구현 한계는 [후속 작업 기록](nonhuman_followup_20261003.md)에 있다. 모든 publication은 여전히 `WITHHELD`다.
