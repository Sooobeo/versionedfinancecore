# Repository agent instructions

이 파일의 범위는 저장소 전체다. 더 하위 경로에 별도 `AGENTS.md`가 생기면 해당 경로에서는 하위 지침이 추가로 적용된다.

## 작업 전 읽을 것

1. 공통 계약과 구축 순서는 `outline/P0_통합_기업재무_의사결정_시스템_마스터_설계서.md`를 우선한다.
2. 모듈 작업은 관련 annex를 함께 읽는다: M1=P1+P2, M2=P3, M3=P4.
3. 구현 경계는 `docs/architecture.md`, 상세 방식은 `docs/implementation_playbook.md`를 따른다.
4. P0와 annex가 충돌하면 P0의 데이터·version·interface·구축 순서가 우선한다.

`outline/`은 요구사항 원본이다. 사용자가 명시적으로 요청하지 않는 한 수정하지 않는다.

## 현재 상태와 주장 경계

- 합성 D0 구현은 검증됐고, 첫 공개자료 후보인 오리온 진천센터 case는 `FEASIBILITY_ONLY`다. 기준시점은 차터에 기록했으나 실제 R0 근거 gate와 분석 결론은 없다.
- 개인 연구·학습·포트폴리오 프로젝트다. 실제 회사 도입, 예산 승인, 투자·대출 승인, 외부등급 또는 자문으로 표현하지 않는다.
- 합성 fixture는 계산 검증에만 사용하고 실제 회사의 사실·성과·예측력으로 표현하지 않는다.

## 아키텍처 규칙

- `financial_core`만 historical normalization, driver, linked P&L·BS·CF, cash·debt, version·scenario의 canonical 계산을 소유한다.
- M1은 P1과 P2를 합친 모듈이다. 별도 `p1`·`p2` 재무 코어를 만들지 않는다.
- M2와 M3는 공통 Core output을 소비하며 baseline을 복제·재계산하지 않는다.
- `reporting`과 향후 UI는 표현 계층이다. business formula, source parsing 또는 독자적인 숫자 보정을 넣지 않는다.
- `orchestration`은 순서와 I/O만 조정한다. 재무 계산을 넣지 않는다.
- overlay는 opt-in이다. 대상 case의 법인·상품·관할 근거가 없으면 활성화하지 않는다.
- 공통 계약 변경은 `contracts`, case template, 관련 문서와 test를 한 변경 안에서 함께 갱신한다.
- import 방향은 `contracts/evidence -> financial_core -> modules -> reporting/orchestration`을 유지하고 순환 의존성을 만들지 않는다.

## 데이터·시점 규칙

- raw snapshot은 append-only다. 정정본·재수집본이 이전 원문을 덮어쓰면 안 된다.
- material fact마다 `source_id`, `first_public_at`, `retrieved_at`, scope, period, currency, unit와 hash를 추적한다.
- `event_at` 또는 보고기간 말일을 `first_public_at`으로 대신하지 않는다.
- historical 분석에는 cutoff 이후 공개된 사실과 현재의 restated 값을 소급하지 않는다.
- 연결/별도, economic/legal scope, entity, segment, instrument grain을 명시적으로 분리한다.
- `F/D/A/I/R/M` claim tag와 fact·forecast·scenario version을 보존한다.
- 결측을 0으로 바꾸지 않는다. `UNKNOWN`, `NM`, `NOT_APPLICABLE`, `NOT_TESTABLE_FROM_PUBLIC_DATA`, `WITHHELD`를 의미에 맞게 사용한다.
- credential, 개인정보, 고용주·계약상 비공개 자료와 권리가 불명확한 raw feed를 commit하거나 AI context에 넣지 않는다.

## 계산 규칙

- 금액·비율의 핵심 계산에는 binary float 오차를 숨기지 않는다. Python에서는 `Decimal`, 저장 계층에서는 명시적 decimal precision을 우선한다.
- 내부 계산은 반올림하지 않고 표시·계약상 필요한 경계에서만 반올림한다.
- formula 안에 threshold·shock·환율·세율을 숨기지 않는다. case별 근거와 함께 config 또는 assumption register에 둔다.
- scenario와 판단 threshold는 historical distribution, official guidance, market evidence, contract boundary 또는 break-even/switching value에서 도출하고 근거 ID를 남긴다.
- 같은 경제적 정의는 한 번 계산하고 ID로 참조한다. 독립 check 목적의 재계산만 허용하고 이유를 기록한다.
- FCFF·FCFE·CFADS·debt service·liquidity·sources/uses 포함 여부를 cash component flag로 관리해 이중계상을 막는다.
- 오류·음수·0 denominator를 자동으로 0 또는 유리한 값으로 치환하지 않는다.
- 계산 함수는 가능한 한 pure, deterministic, typed하게 작성하고 I/O와 분리한다.

## 모듈별 필수 경계

- M1: actual·plan·prior forecast·scenario를 구분하고 variance는 driver effect와 residual의 합으로 대사한다.
- M1 valuation: FCFF/FCFE와 discount rate claim을 맞추고 terminal·peer eligibility를 기록한다.
- M2: 항상 `option world - status quo world`의 증분 세후현금흐름을 사용한다. sunk cost, opportunity cost, cannibalization과 financing double count를 점검한다.
- M3: group cash와 obligor accessible cash를 구분한다. debt face/carrying, committed/uncommitted funding, covenant/recovery evidence state를 혼합하지 않는다.
- covenant·recovery·rating/spread는 공개근거가 충분할 때만 수치화한다. 부족하면 명시적 제한 상태를 출력한다.

## 성능 최적화 규칙

- 정확한 기준 결과와 대표 fixture를 먼저 고정하고 측정된 병목만 최적화한다.
- benchmark에는 입력 규모, command, wall time, peak memory, 결과 hash를 기록한다.
- 동일 source의 반복 parsing과 동일 baseline/scenario의 중복 계산을 피한다. source hash와 dependency key로 incremental rebuild한다.
- 표 형식 계산은 row loop보다 DuckDB/Arrow의 projection·filter·join·grouping 또는 검증된 vectorized 연산을 우선한다.
- 전체 dataset을 무조건 메모리에 올리지 않는다. 필요한 case·기간·열을 먼저 제한한다.
- cache는 source/version/scenario/code hash를 key로 사용하며 key가 불완전하면 사용하지 않는다.
- 최적화 전후에 reconciliation, known-answer와 output hash가 동일한지 검증한다.

## Release 규칙

- `build/`는 재생성 가능한 staging이고 `releases/`는 immutable publication이다. 기존 release를 덮어쓰지 않고 새 `release_id`를 만든다.
- manifest에는 contract/schema version, cutoff, source/input/config/code hash, 실행환경, gate 결과, review 상태와 limitation을 기록한다.
- 생성시각 같은 비결정적 metadata는 content identity와 분리한다. 동일 input·code·config는 동일한 계산 결과 hash를 내야 한다.
- memo와 chart는 release output ID를 참조하며 수기 복사한 숫자를 canonical 값으로 삼지 않는다.

## 테스트와 완료 조건

- 계산 변경: unit + known-answer + boundary/missing-data + regression test를 추가한다.
- schema 변경: template CSV/JSON, parser/contract, 문서와 integration test를 함께 갱신한다.
- ingestion 변경: live network를 기본 test dependency로 만들지 말고 권리가 확인된 작은 fixture로 parsing을 검증한다.
- release 변경: gate 실패 시 기본 상태가 `WITHHELD`인지 검증한다.
- 기존 경로와 case를 자동으로 덮어쓰는 CLI를 만들지 않는다.
- 완료 전 `python -m pytest`와 `python -m compileall -q src`를 실행한다. `ruff`가 설치돼 있으면 `ruff check src tests`도 실행한다.
- 사용자에게 구현 범위, 검증 결과, 아직 미구현인 부분과 제한사항을 명확히 보고한다.
