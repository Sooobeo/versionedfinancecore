# Data Contract

현재 case template과 기본 config의 `schema_version`은 `2`다. 모든 material record는 아래 식별 축을 직접 보존하거나 검증 가능한 ID로 참조한다.

- program, case, release, as-of, first-public, retrieval, source와 immutable snapshot/hash
- accounting scope(연결/별도), economic scope, legal entity, segment, instrument와 필요한 scope bridge
- period start/end/type, currency, unit, sign convention
- version type, publication status, supersession
- scenario purpose, decision lens

## D0/R0 증거와 정규화 계약

- `source_ledger.csv`의 `source_id`는 원천 식별자이고 `snapshot_id`는 특정 수집본·정정본의 불변 식별자다. 채워진 행은 두 ID, `first_public_at`, `retrieved_at`, `content_sha256`, 권리 정보를 보존한다. 같은 원천을 다시 수집하거나 정정본이 나오면 기존 snapshot을 수정하지 않고 새 `snapshot_id`를 추가한다.
- `retention_right`, `transformation_right`, `redistribution_right`, `cutoff_eligible`은 `YES`/`NO`만 허용한다. 원문 보관은 보관·재배포 권리 확인 후, raw fact 추가는 변환 권리 확인 후 수행한다.
- `raw_facts.csv`는 `source_id`와 `snapshot_id`로 원문 행을 참조하며 `content_sha256`, `first_public_at`, `retrieved_at`을 직접 가진다. `raw_account_id`는 원문 계정 또는 태그이고, `version_id`는 `02_financial_core/versions.csv`의 실제값 version을 참조한다. raw fact의 hash·공개시점·수집시점은 참조한 snapshot과 모순되면 안 된다.
- `normalized_actuals.csv`는 `source_fact_id`로 raw fact를 참조하고 `source_id`, `snapshot_id`, `content_sha256`, `first_public_at`, `retrieved_at`을 직접 보존한다. 정규화가 원천 lineage나 값의 공개시점을 바꾸지 않는다. `version_id`는 raw fact와 일치해야 한다.
- `accounting_scope`는 연결/별도 등 회계범위를 명시한다. `economic_scope_id`와 `legal_entity_id`는 다른 축이다. 둘의 관계가 판단에 쓰이면 `scope_bridges.csv`의 `bridge_id`를 `economic_legal_scope_bridge_id`로 참조하고, bridge 자체의 공개시점·원천·검토상태를 확인한다. 빈 bridge ID를 동일 범위라는 근거로 해석하지 않는다.
- scope bridge도 원천 `snapshot_id`·`content_sha256`·`first_public_at`·`retrieved_at`을 보존해 법적 범위 연결의 시점과 증거를 검증한다.
- `mappings.csv`의 `sign_multiplier`는 승인된 실제 mapping에서 명시적인 `+1` 또는 `-1`이다. 정규화값은 원시값에 이 부호 규칙을 적용하며 mapping ID·version과 규칙을 남긴다. 단위 또는 통화 변환이 필요하면 별도 근거·유효기간·검토상태가 있는 governed rule을 먼저 정의한다. 첫 D0 normalizer는 단위·통화 불일치를 자동 변환하지 않고 거부한다.
- `cash_identity_checks.csv`는 현금 기초잔액, 영업·투자·재무 현금흐름, 환율·기타, 기말잔액의 raw `fact_id` 여섯 개와 `version_id`를 고정한다. Core가 각 raw ID를 정규화 actual로 해석한 뒤 기간·회계/경제/법적 범위·단위·통화·version의 호환성을 확인하고 나서 cash roll-forward residual을 계산한다. 식별 실패나 불일치를 0으로 보정하지 않는다.
- `scenarios.csv`의 `baseline_version_id`는 해당 scenario가 참조하는 불변 Core version이다. 같은 scenario 경로의 행들은 동일한 baseline/version/purpose를 가져야 하며, `input_value`는 `mechanism=ABSOLUTE_OVERRIDE`일 때 해당 driver·기간의 절대값이다. 출처 또는 가정 ID 없이 임의 충격을 적용하지 않는다.

## D1 Core 운영 baseline 참조

- `financial_core.project_model_path`는 driver별 source 또는 assumption ID와 이용 가능 시각을 cutoff에 대조하고, 연속 기간의 P&L·BS·CF 및 현금·부채 잔액을 대사한 `ModelPathResult`를 만든다. `ModelPathSpec`에는 연결/별도 `accounting_scope`와 금액 `unit`이 필수이며, `content_sha256`에는 입력 계보와 계산 결과가 들어간다.
- `financial_core.operating_baseline_ref`는 그 결과에서 `OperatingBaselineRef`를 발행한다. 참조에는 case·version·accounting/economic/legal scope·currency·unit·information cutoff, 원본 `model_path_sha256`, 순서가 보존된 기간 ID와 시작·종료일, 이를 모두 해시한 `output_id`가 포함된다. 같은 경로를 다시 계산하면 같은 참조 ID가 나오며 driver 값·근거·범위·기간이 바뀌면 ID도 바뀐다.
- `financial_core.project_free_cash_flow_path`는 Core의 연결 재무경로를 독립 대사하고 기간별 FCFE를 `CFO - capex + debt draw - principal repayment`로 계산한다. 배당 전 주주가용현금흐름이며, 이 좁은 Core 모델의 `interest_expense`는 영업현금흐름에 포함된 현금이자로 처리된다. 실제 이자 발생·지급의 시점 차이가 material하면 이 모델을 확장해야 한다.
- FCFF는 `EBIT + depreciation - Δ(매출채권 + 재고 - 매입채무) - capex - unlevered cash taxes`다. `unlevered_cash_taxes`는 기간·계산방식 ID·source/assumption ID·이용가능시각을 가진 별도 입력이다. 차입구조가 반영된 세금비용이나 현금납부세액에서 세후 이자를 암묵적으로 더하지 않는다. 이 별도 세금 입력이 없으면 FCFF는 `UNKNOWN`이며 FCFF 숫자 `output_id`도 발행하지 않는다.
- FCFE·FCFF에는 서로 다른 기간별 Core `output_id`를 부여한다. 이 ID는 Core baseline ID, 기간, 통화·단위, 공식·구성항목 및 FCFF의 별도 세금 근거를 고정한다. M1은 이 값과 ID를 소비하며 현금흐름을 다시 계산하지 않는다.
- 현재 연결 재무경로의 계정 범위는 매출 수량×가격, 현금 영업비용, 매출채권·재고·매입채무, 미지급세금, 유형자산, 부채 원금, 배당으로 한정된다. 리스, 기타 자산·부채, 비현금/OCI, 외환, 인수·처분 등 material 계정이 있는 회사는 해당 범위를 명시적으로 확장하고 실제 재무제표와 대사하기 전까지 이 경로를 완전한 회사 전망으로 사용하지 않는다.
- Walmart 후보에 이 좁은 모델을 직접 대입하지 않는다. [FY26 10-K 연결재무제표](https://www.sec.gov/Archives/edgar/data/104169/000010416926000055/wmt-20260131.htm)는 영업·금융리스 사용권자산과 의무, goodwill/기타 자산, 이연세금/기타 부채, 비지배지분, OCI, 자사주매입, 외환 및 제한성 현금을 별도로 표시한다. 재무상태표 현금과 현금흐름표 현금+제한성 현금도 같은 정의가 아니다. 실제 P1 baseline에는 매출·마진의 공개시점 고정 driver, 각 material 계정의 forecast 가정과 비현금·FX·인수/처분 roll-forward, 제한성 현금 bridge, 부채·리스 현금/비현금 bridge, 비지배지분·자사주 환원 및 무차입 현금세금 schedule이 필요하다. 현재 case에 이 입력과 승인된 가정 ID가 없으므로 summary의 `other` 값을 대사 잔차로 역산해 채우거나 완전한 3표/FCFF 전망이라고 표시하지 않는다.
- M1의 P1 가치평가는 Core 참조와 기간별 FCF 출력을 고정해 소비한다. 계산 성공만으로 할인율, terminal state, 원천 권리, 공시 cutoff, 방법 적격성, 독립 검토 또는 실제 회사의 release 적격성을 주장하지 않는다.

## 핵심 규칙

1. 원문 snapshot과 raw fact는 append-only다.
2. `first_public_at`과 `retrieved_at`을 시간대가 있는 시각으로 보존하고 보고기간 말일 또는 `event_at`으로 대체하지 않는다. 역사적 cutoff 적격성은 해당 version의 `first_public_at <= analysis_cutoff`로 판정한다.
3. 최초 공개 actual과 정정·재작성 actual은 별도의 append-only `version_id`를 가진다. `PUBLIC_ACTUAL`이라는 version type과 `PRELIMINARY`·`FILED`·`REVISED`·`RESTATED` publication status는 다른 축이다. `latest_restated`를 과거 ex-ante 판단에 소급하지 않는다.
4. 연결·별도, economic scope·legal claim scope를 섞지 않는다. metric 비교 전 scope·period·currency·unit·sign·grain의 호환성을 확인한다.
5. 사실·파생값·가정·추론·권고·측정 결과를 각각 `F/D/A/I/R/M`으로 표시한다.
6. 하나의 cash component를 한 번 계산하고 FCFF·FCFE·CFADS·liquidity별 포함 flag로 소비한다.
7. 누락값을 0으로 바꾸지 않는다. `UNKNOWN`, `NM`, `NOT_APPLICABLE`, `NOT_TESTABLE_FROM_PUBLIC_DATA`, `WITHHELD`를 의미에 맞게 구분한다.
8. D0 합성 fixture는 계약·계산 검증에만 사용한다. 공개자료 기반 R0 gate와 실제 회사 결론은 별도로 판정한다.

CSV 파일의 첫 행은 최소 계약이다. 실제 case에서 필드를 추가할 수 있지만 의미가 같은 필드를 새 이름으로 복제하지 않는다.

## Offline case build 계약

기존 재무·증거 schema v2와 별도로 선택적 `00_charter/build_recipe.json`은 adapter 실행 계약 v1을 사용한다. 필드는 `schema_version=1`, 순서 있는 `steps`, 중복 없는 문자열 목록 `scope_limitations`다. 템플릿의 `steps=[]`는 미설정 상태로, `validate-case`는 허용하지만 `build-case`는 계산 없이 완료로 처리하지 않는다. 기존 recipe 없는 case는 이전 명령과 호환되며 새 `build-case` 사용 전 recipe를 추가해야 한다.

허용 step은 `core_cash`, `conditional_valuation`, `guidance_comparison`, `dfs_reproduction`, `capital_evidence`, `credit_evidence`다. 중복·미등록 step과 임의 script/command 필드는 거부한다. 조건부 가치평가와 credit evidence는 먼저 같은 case의 `core_cash`를 실행해야 한다. 모듈 adapter는 차터의 활성 모듈과 일치해야 한다. `capital_evidence`는 M2 공개근거의 충족·부분·누락 상태를 재현하며 cash/NPV를 생성하지 않는다. 숫자 가정은 기존 case config/assumption register에 두며 recipe에 계산식을 넣지 않는다.

`outputs/review_report.json`은 [release 절차](release_process.md)의 검토 보고서 v1을 따른다. `executed_steps`의 `REPRODUCED`는 실행 성공을 의미하며 모듈 release 적격성을 의미하지 않는다. `artifact_hashes`는 이번 실행에서 생성한 계산물 전체를 가리킨다. 보고서의 `output_id`는 생성시각을 제외한 내용의 hash로 계산하고 검토 memo가 이를 참조한다.

`credit_evidence`는 같은 Core의 closing cash fact ID, 범위·기준일·단위를 보존해 그룹 현금 참고값으로 표시한다. 법인별 현금과 접근제약이 없으면 `UNKNOWN`, 정의가 불완전한 covenant는 M3 함수를 통해 `NOT_TESTABLE_FROM_PUBLIC_DATA`로 남긴다. 연간 만기를 날짜별 지급 경로로 변환하거나 공개 기준액 문자열을 임의 숫자로 해석하지 않는다. 수치 covenant 재계산에는 별도 계약별 component adapter가 필요하다.

## Conditional consolidated-model adapter metadata (v2)

`conditional_model_config.json` is an optional, case-local adapter contract for a
review-only M1 conditional forecast. It is not a generic financial-assumption
template and the case template deliberately does not ship one. A new case may
opt in only after it supplies its own pinned fact selectors, source versions,
and reviewed assumptions; copying Walmart's numerical assumptions would not
create support for another company.

The supported `adapter_metadata` shape (`metadata_required`) has
`schema_version=2`, `review_status=WITHHELD`, `assumption_evidence_path`,
`source_ledger_path`, `version_type`, `scenario_purpose`, `fact_contract`,
`source_versions`, `opening_balance`, `historical_fact_selectors`,
`claim_aggregates`, `lease_policy`, `wacc`, `terminal`,
`unlevered_cash_tax`, `dcf`, `artifacts`, `review_csv`, and `valuation_controls`. Its paths are
relative to the case root; all company/date/source choices therefore remain in
the case config rather than in orchestration code.

The adapter accepts only a full Core `normalized_actuals.csv` contract. Before
using a fact it validates the CSV shape plus every row's case ID, economic and
legal scope, accounting scope, currency/unit, timezone-bearing public and
retrieval times, and cutoff. Each configured source version must also be in the
case source ledger, have the configured economic scope, be cutoff eligible, and
have been public by the case cutoff. It builds review artifacts only; it does
not fetch data, overwrite raw facts, calculate a release decision, or promote a
withheld screen.

The current adapter requires an exact integer metadata version 2. The preserved
v1 config is a provenance snapshot, not a runnable current-engine config; it is
rejected early rather than silently given new controls. The top-level config
schema remains version 1, separate from this adapter-metadata version.

The October 3 metadata v2 adds `valuation_controls` with
`historical_lease_cash_tax` and `dated_stub`. Historical controls declare their
period and unit, an `evidence_by_field` mapping for each numeric observation,
a `source_receipt` object (`source_id`, `locator_entity_scope`, `snapshot_id`,
`content_sha256`, `first_public_at`, `retrieved_at`) and explicit model-policy
booleans. Values, units, period and source identity
must agree with the referenced assumption-evidence rows and their eligible
receipts. These observations are diagnostic inputs, not replacement Core
forecast facts. The diagnostic preserves `historical_evidence_state=KNOWN`
separately from `forward_application_state=UNKNOWN`; neither the residual D&A
nor a historical cash-tax ratio silently becomes a forecast assumption.

The dated-stub control consumes the Core period dates, dated DCF output ID and
dated evidence for the last disclosed period. An unavailable realized cash
flow before the valuation date keeps the boundary `WITHHELD` and
`release_consumable_enterprise_value=null`. It does not allocate cash pro rata
or infer missing cash from annual guidance. Both controls have independent
output IDs nested in the valuation artifact, while the old conditional
arithmetic remains identifiable as a diagnostic screen.

Config revisions carry `revision_id`, `revises_version_id`,
`prior_config_sha256` and a reason. The Walmart v2 scenario preserves its exact
v1 config separately; existing numerical v1 artifacts are not rewritten. A
declared `MIXED_OPERATING_AND_FINANCE` lease policy describes the conditional
model's choices, not verified lease-treatment eligibility. A stale bond issue
yield is labeled as such and cannot become an as-of marginal borrowing rate
merely by changing its name.

## Automated reproduction handover (v1)

`contracts/reproduction.py`는 두 번의 fresh build가 비교해야 하는 manifest 필드를 고정한다. `reproduce-case`는 새 출력 폴더의 `first/<case_id>/<stage_id>`와 `second/<case_id>/<stage_id>`에 독립적으로 계산하고, 생성시각을 제외한 source/input/config/code/output/memo/content identity, 파일 목록·hash, gate 및 limitation을 대조한다.

생성 전용 `reproduction_report.json`의 `schema_version=1`, `kind=AUTOMATED_REPRODUCTION_HANDOVER`다. `case_id`, `analysis_cutoff`, 두 상대 stage 경로, `compared_fields`, `verified_identity`, 원 검토 보고서의 `review_output_id`, 미해결 `remaining_release_blockers`, limitation과 내용 기반 `output_id`를 보존한다. 템플릿 case에 사전 작성할 입력이 아니며 모든 값은 실제 두 build 검증에서 생성한다. 자동재현 `PASS`와 `human_review_state=NOT_PERFORMED`, `publication_state=WITHHELD`, `release_ready=false`는 서로 다른 축이다.

`verify-reproduction`은 현재 code/config로 양쪽 stage, 보고서 재계산, memo 일치와 전체 파일 inventory를 다시 확인한다. 경로 탈출·symlink·중복 JSON key·비유한 수치를 허용하지 않는다. 이 artifact는 사람 검토나 underlying source/model 적격성 gate를 대체하거나 변경하지 않는다.

## M2 public evidence coverage (v1)

선택적 `04_m2_capital_allocation/public_m2_evidence.csv`와 case template의 같은 헤더는 `evidence_id`, `criterion`, `coverage`, `source_id`, `snapshot_id`, `first_public_at`, `claim_tag`, `disclosed_value`, `unit`, `currency`, `economic_scope_id`, `timing_basis`, `statement`, `limitation`을 보존한다. criterion은 status quo/option 현금 경로, 공통 기준시점, 세후 기준, 법적·경제적 범위, 자금 접근성, 실행권리의 일곱 종류다.

완전·부분 근거는 적격 source receipt를 참조해야 하고 output에 receipt의 hash와 수집시각까지 포함한다. 값이 있으면 단위·범위·시점 근거가 필요하다. 출처 없는 MISSING은 조사 범위의 누락에 대한 추론으로만 기록하며 실제 사실·숫자로 취급하지 않는다. 한 criterion의 PARTIAL/MISSING은 별도 supersession 없이 COMPLETE 한 행으로 상쇄할 수 없다. 이 계약은 cash component나 실제 option value의 입력 계약이 아니므로 충족 상태만으로 NPV·funding 합계를 만들지 않는다.

## M3 public credit terms (v1)

선택적 `05_m3_credit_liquidity_claims/public_terms.csv`는 template과 같은 필드로 공시된 조건을 기록한다. `term_id`, `instrument_id`, `legal_entity_id`, `term_type`, `value`, `currency`, `unit`, `as_of_date`, `source_id`, `snapshot_id`, `content_sha256`, `first_public_at`, `retrieved_at`, `verified_at`, `source_location`, `claim_tag`, `limitation`이 필수다.

지원 유형은 `CAPACITY_EXPIRY_WITHIN_TWELVE_MONTHS`, `CAPACITY_EXCEEDS_ELIGIBLE_RECEIVABLES`, `ISSUER_REPORTED_AVAILABLE`, `FACILITY_MATURITY_YEAR`, `DRAW_CONDITION`, `SUPPORT_AGREEMENT`, `GUARANTEE`, `RECOURSE`다. 금액은 유한한 비음수 Decimal이며 통화·단위를 명시한다. 연도는 `YEAR` bucket일 뿐 지급일로 바꾸지 않는다. 서술형은 `TEXT`/`NOT_APPLICABLE`, 직접 공시 조건의 태그는 `F`다. instrument/entity 관계, **참조한 exact receipt**의 hash·권리·cutoff와 시각을 검증한다. 같은 source ID의 다른 적격 receipt로 늦거나 부적격인 snapshot을 대신 승인하지 않는다.

`debt_facilities.csv`에 `unit` 열을 추가했다. 기존 header-only case는 호환되지만 금액행에는 통화와 일치하는 단위가 필요하다. 공시 nominal commitment−drawn 대사와 실제 drawable cash는 다른 상태다. M3의 공시 산술 점검은 Core normalized fact ID를 참조하는 독립 검산이며 새 baseline이나 가용자금 계산을 소유하지 않는다.

