# Evidence core

모든 사실의 원문, 공개시점, retrieval, 권리, scope와 변환 lineage를 관리한다. snapshot과 raw fact는 append-only이며 정정본이 원본을 덮지 않는다.

- `source_ledger.csv`: 원천 `source_id`와 불변 수집본 `snapshot_id`, 공개·수집시점, 권리, SHA-256을 기록한다.
- `raw_facts.csv`: 각 fact의 원문 snapshot/hash, `raw_account_id`, 공개·수집시점, 회계·경제·법적 범위와 실제값 `version_id`를 보존한다.
- `mappings.csv`: 원문 계정에서 metric으로 가는 versioned mapping과 명시적 `sign_multiplier`(`+1`/`-1`)를 기록한다.
- `scope_bridges.csv`: 경제적 범위와 법인 범위의 근거 있는 관계를 기록한다. 관계가 필요한 fact는 `economic_legal_scope_bridge_id`로 이를 참조한다.

시간대가 있는 `first_public_at`을 cutoff와 비교한다. `event_at`, 보고기간 말일, `retrieved_at`을 공개시각으로 대체하지 않는다. 단위·통화 변환에는 별도 승인된 규칙이 필요하며, 첫 D0 normalizer는 불일치를 거부한다.

Walmart P1 자료 pilot은 [수집·공개시점·권리·단위 기록](evidence_pilot.md)에 정리했다. 세 공식 SEC 제출 문서의 최초 locator/hash로 161개 연결 사실을 고정했고, Q1 공시의 새 수집 vintage에서 재무상태표 44개 사실을 추가해 205개다. Core 입력 receipt는 네 개이며, FY26 10-K HTML의 lease·cash-tax 위치를 검증하기 위한 다섯 번째 별도 locator-only receipt를 추가했다. 이 별도 receipt는 raw fact를 추가하거나 기존 Core fact를 바꾸지 않는다. 기존 receipt·fact는 그대로 둔다. 추가 추출은 `ingest_sec_q1_balance_supplement.py`로 재현하며, 원래 `ingest_sec_financials.py`의 고정 digest를 변경하지 않는다. 8-K의 USD millions→USD 변환은 case extractor와 mapping reason에 명시돼 있다.

`assumption_evidence.csv`는 가이던스와 평가 가정에 대한 32개 출처 위치·관측값을 보관한다. 여기에는 FY26 10-K의 lease·D&A·cash-tax 위치와 FY27 Q1이 2026-04-30까지만 포괄한다는 locator가 포함된다. `observation_sha256`은 선택한 관측값의 해시이며 원천 문서 전체의 해시가 아니다. Nasdaq·NYU 관측값은 공개 시각과 이용 권리가 독립적으로 확인되지 않아 재무 사실 ledger나 release 입력에 넣지 않고 screening 근거로만 쓴다. 독립 검토와 P1 valuation release gate는 별도로 판정한다.

