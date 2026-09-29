# Implementation Playbook

이 문서는 `AGENTS.md`의 필수 규칙을 실제 설계·코드·최적화 작업으로 옮기는 방법을 정리한다. 외부 표준을 가장하는 고정 성능 목표나 재무 임계값은 두지 않는다. 첫 case의 규모와 관측된 병목을 기준으로 갱신한다.

## 1. 구현 단위

기능을 폴더 단위가 아니라 아래 수직 흐름 단위로 완성한다.

```text
source locator
-> immutable snapshot + hash
-> raw fact
-> normalized fact
-> calculation output
-> validation result
-> memo field
-> release manifest
```

한 단계의 output contract와 실패 상태가 정의되지 않았으면 다음 계층을 먼저 확장하지 않는다.

## 2. 의존성과 소유권

| 영역 | 소유하는 것 | 소유하지 않는 것 |
|---|---|---|
| `contracts` | enum, ID, record/schema | I/O, 계산 |
| `evidence` | source, rights, timestamp, hash, cutoff | 재무 판단 |
| `financial_core` | normalization, driver, statements, cash/debt, versions | M1/M2/M3 결론 |
| `modules/m1` | variance, reforecast, valuation, action | 별도 historical model |
| `modules/m2` | alternatives, incremental CF, sources/uses, break-even | status quo 재구축 |
| `modules/m3` | obligor, liquidity, covenant, refi, claim/recovery | group 재무 재구축 |
| `reporting` | chart/table/memo rendering | 숨은 계산·수기 override |
| `orchestration` | dependency 실행, build, release | domain formula |

공통 데이터가 부족하면 모듈에서 임시 계산을 만들지 말고 Core 계약을 확장한다.

## 3. 저장과 처리 전략

### 새 metric 체크리스트

새 metric을 추가하기 전에 아래를 모두 정의한다.

- grain, economic/legal scope, entity/segment/instrument
- period type, currency, unit, sign convention
- null/unknown/NM 상태와 source precedence
- formula, rounding boundary와 cash inclusion flags
- source 또는 assumption ID와 known-answer fixture

같은 의미의 metric이 이미 있으면 새 이름을 만들지 말고 기존 계약을 확장한다.

### 새 source adapter 체크리스트

- access·retention·transformation·redistribution 권리
- stable document/accession/reception ID
- event, first-public, retrieval timestamp의 분리
- raw snapshot과 content hash 보존 가능성
- pagination·amendment·partial-response 처리
- sample 또는 material-total 원문 대사
- 재실행 시 중복 fact를 만들지 않는 idempotency

### Raw와 evidence

- source별 원문을 content hash로 식별하고 같은 내용의 중복 다운로드를 감지한다.
- source metadata와 본문을 분리한다. metadata는 query 가능하게, 원문은 immutable object로 보존한다.
- API pagination은 page별 receipt와 전체 수집 completeness를 기록한다.
- ETag, Last-Modified 또는 accession/reception ID가 제공되고 이용조건이 허용할 때만 조건부 재수집을 사용한다.
- 원문 저장권리가 없으면 locator와 허용된 최소 파생값만 남긴다.

### Analytical storage

- 초기 canonical 교환형식은 case template의 CSV/JSON이다.
- 데이터가 커지면 DuckDB를 query engine, Parquet을 typed snapshot으로 사용한다.
- long-format fact table을 기본으로 하고 UI용 wide table은 build artifact로 생성한다.
- partition은 실제 pruning에 쓰이는 `case_id`, source 또는 period 축만 사용한다. 작은 파일을 과도하게 분할하지 않는다.
- schema와 enum은 코드·template·release manifest에 같은 version으로 기록한다.

### Incremental build

각 node의 cache key는 최소한 아래를 포함한다.

```text
source_hash + mapping_version + assumption_version
+ scenario_version + code_version + relevant_config_hash
```

상위 key가 바뀌면 영향을 받는 downstream node만 다시 계산한다. dependency를 증명할 수 없는 cache는 폐기한다.

## 4. 계층별 최적화

### Evidence ingestion

- 네트워크 요청은 rate limit와 이용조건을 준수해 batch하고 retry에는 지수 backoff와 최대 횟수를 둔다.
- 다운로드와 parsing을 분리해 parser 수정 때 원문을 다시 받지 않게 한다.
- 실패 응답·부분 응답을 정상 빈 결과로 저장하지 않는다.

### Normalization과 financial core

- account mapping은 코드 분기보다 versioned mapping table로 관리한다.
- 기간·단위·통화·sign을 normalization 입구에서 확정하고 downstream 반복 변환을 줄인다.
- 재무 schedule은 명시적 input/output table을 가진 pure transform으로 만든다.
- DuckDB/Arrow 사용 시 필요한 열과 기간을 먼저 projection/filter하고 조인 전 key uniqueness를 검사한다.
- P&L·BS·CF, cash·debt roll-forward residual은 매 build마다 계산한다.

### M1

- forecast cube는 `version × scenario × period × metric × scope` key로 한 번 만든다.
- actual-to-plan과 actual-to-prior-forecast는 같은 variance engine을 사용한다.
- price·volume·mix interaction convention은 case 중간에 바꾸지 않는다.
- valuation은 운영 forecast를 입력으로 받되 별도 claim bridge와 eligibility 결과를 낸다.

### M2

- status quo path를 immutable baseline으로 공유하고 option별 delta만 관리한다.
- option 전체 모델 복제보다 공통 baseline + option driver override를 우선한다.
- project cash flow와 financing cash flow를 event/component ID로 연결해 중복을 검출한다.
- NPV만 출력하지 말고 max price, break-even 또는 switching variable 중 의사결정에 필요한 경계를 함께 계산한다.

### M3

- cash와 debt는 period-end table만으로 끝내지 않고 지급·만기 event를 별도 관리한다.
- facility draw는 cash, debt face, interest, maturity, covenant와 undrawn availability를 같은 event로 갱신한다.
- 최소 timestep은 coupon·maturity·seasonality가 만드는 intra-period trough를 포착하도록 정한다.
- reverse stress solver는 먼저 단조성을 확인하고 bracket을 기록한다. 비단조이면 복수 해와 탐색범위를 반환하고 단일 임계값으로 축약하지 않는다.
- recovery waterfall은 legal entity/value pool/claim class별 가치보존 check를 항상 함께 낸다.

### Reporting과 UI

- 화면과 memo는 release-ready output table만 읽는다.
- template 안에서 재무 formula, 임계값 판단 또는 누락값 보정을 수행하지 않는다.
- 표와 chart는 `output_id`를 유지해 memo 숫자에서 원 계산으로 역추적할 수 있게 한다.
- 큰 데이터는 UI에 직접 전달하지 않고 독자 질문에 맞춘 precomputed view를 생성한다.

## 5. 수치 정확성과 실패 처리

- money와 contractual rate는 decimal precision을 명시한다. 계산 중 표시용 rounding을 하지 않는다.
- tolerance는 통화·source 단위·반올림 방식과 materiality에서 도출하고 test에 이유를 남긴다.
- division by zero, negative EBITDA, missing covenant input은 예외 상태이며 유리한 ratio로 치환하지 않는다.
- scenario shock에는 source 또는 assumption ID, 적용기간, mechanism과 dependency group이 필요하다.
- override는 원값, 변경값, 이유, 작성자, 검토자와 timestamp를 보존한다.

## 6. 테스트 전략

| 변경 유형 | 최소 검증 |
|---|---|
| 계약·enum | parsing, invalid input, template compatibility |
| source parser | frozen fixture, missing/custom field, amendment |
| normalization | period/scope/unit/sign, restatement, duplicate key |
| 재무 계산 | identity, known answer, zero/negative/missing boundary |
| M1 | variance additivity, immutable version, no-look-ahead |
| M2 | option-status quo identity, sources=uses, financing double count |
| M3 | cash/debt roll-forward, RCF event, covenant direction, waterfall conservation |
| report | output ID와 snapshot 숫자 일치 |
| release | hash 재현, gate fail-closed, secret/restricted exclusion |

실제 회사 원문을 테스트 fixture로 commit하기 전에 저장·재배포 권리를 확인한다. 권리가 불명확하면 같은 구조의 `SYNTHETIC_TEST` fixture를 만들고 그 한계를 표시한다.

## 7. 성능 측정

최적화 PR 또는 변경에는 가능하면 아래를 남긴다.

```text
benchmark name:
input rows/files/bytes:
case and period scope:
command:
baseline wall time / peak memory:
new wall time / peak memory:
output hash or reconciliation comparison:
environment:
```

우선순위는 대체로 중복 I/O 제거, source-hash incremental build, query projection/filter, vectorized calculation, serialization 개선 순이다. 병렬화는 source rate limit, deterministic output과 memory 사용을 확인한 뒤 적용한다.

## 8. Release와 rollback

- build 결과는 staging에서 생성하고 gate 통과 전 publication state를 `WITHHELD`로 유지한다.
- release content ID는 input/config/code/output hash로 결정하며 `generated_at`과 분리한다.
- manifest에는 schema/contract version, code revision, runtime environment, cutoff, gate/review 결과와 limitation을 포함한다.
- clean environment에서 reproduction command를 실행해 output hash를 확인한다.
- 이전 release를 수정하지 않는다. 정정은 supersession 관계를 가진 새 release로 만든다.
- rollback은 이전 release를 다시 가리키는 작업이지 과거 파일을 재작성하는 작업이 아니다.

## 9. 변경 완료 체크리스트

- authoritative 설계서와 구현 경계가 일치한다.
- case-specific 판단값이 공통 코드에 hard-code되지 않았다.
- source부터 output까지 lineage와 실패 상태가 보존된다.
- 관련 template·schema·문서·test가 함께 갱신됐다.
- 테스트와 compile check를 통과했다.
- 생성 파일, credential, restricted data가 변경사항에 섞이지 않았다.
- 아직 구현하지 않은 기능과 검증하지 못한 가정을 공개적으로 표시했다.
