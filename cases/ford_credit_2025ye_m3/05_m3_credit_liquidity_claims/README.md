# M3 — Credit, Liquidity and Claims

issuer capacity, instrument loss severity와 market signal을 분리한다. 연결재무를 특정 obligor의 자유로운 지급재원으로 간주하지 않는다.

Covenant는 원문 정의와 material input이 공개될 때만 재계산한다. Recovery는 증거가 부족하면 `STRUCTURE_ONLY`, market signal이 없으면 `NO_PUBLIC_MARKET_SIGNAL`이 정상 상태다.

이 case의 `debt_facilities.csv`는 2025년 말 그룹 기준 공시 aggregate와 FCE/Ford Bank의 개별 시설을 구분한다. 무담보 aggregate는 특정 채권이나 단일 법적 obligor가 아니다. ABS aggregate는 여러 유동화 법인의 채무다. 공시된 미사용 약정액은 자산 적격성·헤지·성과·차입 법인 조건을 확인하지 않은 즉시 인출 가능액으로 취급하지 않는다.

`maturities.csv`의 숫자는 2025-12-31 현재 연도별 **bucket**이고 실제 지급일이 아니다. 그래서 `event_date`를 비워 두었다. 장기채무의 이자는 원금과 별도 행에 보관하며 채무자별로 배분하지 않는다. `covenants.csv`는 공개된 조건만 기록하며 headroom을 계산하지 않는다. `claims_recovery.csv`와 `stress_cases.csv`는 법적 가치 풀과 날짜별 현금 경로가 부족해 비어 있다.

[신용 메모](credit_memo.md)와 [공식 근거](../01_evidence_core/evidence_notes.md)를 참조한다. M3 판단은 `WITHHELD`다.

# 공통 실행 adapter 보강 (2026-10-03)

`build-case`는 기존 Core normalized fact를 사용한 4개 독립 공시 산술 대사와 법인·시설·만기 bucket·공개조건을 M3 JSON으로 내보낸다. source와 숫자 대사만으로 법적 현금접근 또는 담보 회수가능성을 승인하지 않는다. 자세한 근거·한계는 [추가 확인 기록](../07_validation_governance/evidence_followup_20261003.md)을 따른다.

`debt_facilities.csv`의 `unit`은 실제 금액행에 필수이며 통화와 일치해야 한다. `USD`, `USD_MILLION`, `USD_BILLION`처럼 단위를 명시한다. 과거 header-only case는 그대로 호환된다. `nominal_undrawn` 대사는 잔여약정 산술만 검사하며 drawable cash는 항상 별도 증거를 요구한다.

선택적 `public_terms.csv` 계약:

- key·scope: `term_id`, `instrument_id`, `legal_entity_id`, `term_type`
- value: `value`, `currency`, `unit`, `as_of_date`
- provenance: `source_id`, `snapshot_id`, `content_sha256`, `first_public_at`, `retrieved_at`, `verified_at`, `source_location`, `claim_tag`, `limitation`
- 지원 유형: `CAPACITY_EXPIRY_WITHIN_TWELVE_MONTHS`, `CAPACITY_EXCEEDS_ELIGIBLE_RECEIVABLES`, `ISSUER_REPORTED_AVAILABLE`, `FACILITY_MATURITY_YEAR`, `DRAW_CONDITION`, `SUPPORT_AGREEMENT`, `GUARANTEE`, `RECOURSE`

ID·열 중복/폭·scope foreign key·receipt hash와 시각·cutoff를 검사한다. 금액은 유한한 비음수 Decimal, 연도는 `YEAR` bucket, 서술형은 `TEXT`이며 `claim_tag=F`만 받는다. `verified_at`는 과거 최초공개시각을 바꾸지 않는다. 보충 원문의 historical byte identity가 미검증이면 그 한계도 출력과 release blocker에 보존한다.

