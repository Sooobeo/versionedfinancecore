# P2 설계서: Driver-based 계획·실적차이·재전망 시스템

> **통합 상태 — 2026-09-01**  
> 이 문서는 M1의 **Performance Management & Reforecast 상세 annex**로 보존한다. P1과 P2는 별도 historical·driver·재무제표 모델을 만들지 않고 [P0 통합 마스터 설계서](P0_통합_기업재무_의사결정_시스템_마스터_설계서.md)의 공통 Core를 사용한다. P2 고유의 plan/forecast/actual semantic, variance, reforecast, action, dashboard와 handover 상세는 이 문서를 따른다.

> 운영 driver를 통합 재무전망에 연결하고, plan·forecast·actual의 차이를 원인별로 설명한 뒤 reforecast와 실행조치까지 닫는 개인 FP&A·CEO Staff 포트폴리오 프로젝트

- 버전: 1.0 — reference-grounded design
- 작성일: 2026-08-31
- 상태: 민간 접근가능성·case 선정 전
- 최종 독자: FP&A·Corporate Finance·BizOps·CEO Staff·전략·Treasury·금융사 신사업 채용담당자와 모델 검토자
- 핵심 산출물: versioned planning model, 통합 P&L·BS·CF, variance bridge, reforecast, action register, decision memo, source·assumption·validation log

---

## 0. 설계 원칙

### 0.1 사용자 전제

이 프로젝트는 특정 지원기업을 모사하거나 그 회사에 맞춘 과제를 만드는 것이 아니다. 관련 직무와 금융 도메인에서 재사용 가능한 FP&A 증거를 만드는 것이 목적이다.

FinDone은 본인이 직접 사용하려고 만든 제품이므로 외부 사용자 성장이나 retention을 억지로 검증하는 P0로 바꾸지 않는다.

`[USER]` P2의 핵심 분석데이터는 **분석대상 회사의 임직원·계약자·감독기관만 볼 수 있는 내부자료를 사용하지 않는다.** 민간 개인·법인이 고용관계 없이 합법적으로 확보할 수 있는 공식 공개자료와, 이용조건이 명시된 민간 상용자료만 허용한다. 핵심 모델은 무료 공식·회사 공개자료만으로 완결되게 만들고 상용자료는 선택 cross-check로만 쓴다.

- FinDone이 이미 증명하는 것: 금융 문제정의, 도메인 구조화, AI 활용, 제품 구현, 품질 gate
- P1이 증명하는 것: 공개기업 분석, driver-based 전망, 가치평가와 조건부 판단
- P2가 새로 증명할 것: 민간 공개데이터 기반 운영계획, version control, public actual-to-analyst plan/prior forecast variance, reforecast, 현금·자원배분과 실행조치

### 0.2 제거한 임의 기준

다음 항목은 AFP·CFA·ICAEW가 보편적인 숫자로 정한 기준이 아니므로 P2의 통과조건으로 사용하지 않는다.

| 제거한 임의 기준 | P2에서 사용하는 결정 원리 |
|---|---|
| 특정 지원회사와 닮은 business case | 관련 직무의 공통 업무, 금융 도메인 가치, 데이터 권리·재현성 gate로 case 선택 |
| 특정 산업을 자동 기본값으로 지정 | driver가 관측·검증 가능하고 P&L·BS·CF와 연결되는 사업유형을 선택 |
| driver 개수 고정 | 예측력, 의사결정 관련성, 데이터 신뢰성, 통제가능성으로 material driver만 유지 |
| 월별·분기별 등 고정 cadence | 공시·IR·통계 발표주기, 정보 도착 속도, volatility와 의사결정 오류비용으로 결정 |
| 고정 forecast horizon | 의사결정 lead time, 계절성·cycle, 현금·계약 horizon, 먼 구간의 신뢰성으로 결정 |
| rolling forecast가 내부 budget을 항상 대체 | 공개되지 않은 회사 budget은 사용하지 않고 public guidance·analyst plan·forecast의 목적을 분리 |
| PVM을 모든 사업에 적용 | price·volume·mix가 정의되고 실제 데이터로 분해 가능한 경우만 사용 |
| scenario 수와 sensitivity 폭 고정 | 중요한 경제적 경로, 역사·공식자료, break-even과 risk trigger로 정함 |
| material variance 비율 고정 | 의사결정 영향, 현금·covenant·자원노출, 반복성으로 escalation 기준 결정 |
| forecast accuracy 합격률 고정 | 사전 benchmark, 오차분포, bias, decision impact와 표본 한계를 함께 검토 |
| 프로젝트 주수·단계별 일수 고정 | data feasibility pilot과 산출물 의존관계로 일정 산정 |
| dashboard 수·memo 페이지 수 고정 | 독자가 원인·전망·행동을 검토할 수 있는 충분성으로 결정 |
| 가중점수와 공개 합격점 | 중요한 gate 하나가 실패하면 상쇄하지 않는 비보상적 release gate 사용 |

실무 편의를 위해 숫자가 필요하면 `외부 표준`으로 쓰지 않는다. 민간 공개데이터·의사결정 목적에서 산출한 값, 기준일, 근거, analysis owner, 변경조건을 decision/assumption log에 남긴다.

### 0.3 판단 라벨과 주장 태그

중요한 설계 선택에는 다음 라벨을 붙인다.

| 라벨 | 의미 | 허용 근거 |
|---|---|---|
| `[STD]` | 외부 원칙 | 공식 전문직·회계·모델리스크·spreadsheet 기준 |
| `[EVID]` | case 증거 | 민간이 합법적으로 확보 가능한 공시·회사 IR·정부·거래소·licensed commercial 자료 |
| `[USER]` | 사용자 목적 | 관련 직무·금융 도메인 선호와 공개범위 |
| `[CALC]` | 계산 | 원천에서 재현되는 산식 |
| `[JUDG]` | 전문판단 | 대안·근거·한계·변경조건을 기록한 선택 |

모델과 memo의 개별 주장에는 다음 태그를 사용한다.

| 태그 | 의미 |
|---|---|
| `[F] Fact` | 원천자료에 직접 존재 |
| `[D] Derived` | 허용된 민간 접근자료에서 재현 가능하게 계산 |
| `[A] Assumption` | 계획·전망을 위해 둔 가정 |
| `[I] Inference` | 여러 사실과 계산을 연결한 해석 |
| `[R] Recommendation` | 조건부 행동 제안 |
| `[M] Measured` | 본 프로젝트 test에서 직접 측정 |

문서의 `owner` 표기는 다음으로 제한한다. `analysis owner`는 프로젝트 작성자, `reviewer`는 독립 관점의 검토자, `proposed accountable role`은 공개 조직정보와 일반적인 직무범위에 근거한 제안 역할이다. 분석대상 회사의 실제 내부 책임배정은 공식 공개자료로 확인되지 않는 한 fact로 표시하지 않는다.

---

## 1. 기준 문헌과 적용 범위

### 1.1 핵심 기준

| 설계 영역 | 공식 자료 | P2 적용 |
|---|---|---|
| FP&A 역할 | [AFP — What is FP&A?](https://fpacert.financialprofessionals.org/certification/what-is-fp-a) | integrated planning·forecasting, performance management, financial analysis를 의사결정 지원으로 연결한다. |
| Driver-based model | [AFP — Guide to Driver-based Models and Plans](https://www.financialprofessionals.org/training-resources/resources/guides/fp-a-guides/Detail/driver-based-modelling) | 운영·외부 driver와 financial outcome의 관계를 명시하고, 목표·범위·implication·communication·change process를 설계한다. |
| FP&A 실무역량 | [AFP — FPAC Test Specifications](https://fpacert.financialprofessionals.org/exam/specifications) | actual 대 prior/plan/forecast variance, PVM, P&L·BS·CF projection, headcount·expense, scenario·sensitivity, model validation을 포함한다. |
| Rolling forecast | [AFP — 8 Steps for Creating a Rolling Forecast](https://www.financialprofessionals.org/training-resources/resources/articles/Details/8-steps-for-creating-a-rolling-forecast) | 사용자·의사결정을 먼저 정의하고, horizon·increment·detail은 상황과 오판 위험에 맞추며 actual-to-forecast를 what·why·action으로 연결한다. |
| Business partnering | [AFP — Finance Business Partnering](https://www.financialprofessionals.org/glossary/finance-business-partnering) | integrated planning, management reporting, decision support를 연결하고 business owner·FP&A의 역할과 effective challenge를 구분한다. |
| 통합 재무모델 | [CFA — Introduction to Financial Statement Modeling](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/introduction-to-financial-statement-modeling) | revenue에서 시작해 forecast income statement·balance sheet·cash flow를 연결한다. |
| Forecast object·horizon | [CFA — Company Analysis: Forecasting](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/company-analysis-forecasting) | 정보가용성·정확성·설명력·검증가능성, 산업 cycle·회사 특성·목적에 맞는 object와 horizon을 선택한다. |
| 운전자본·유동성 | [CFA — Working Capital and Liquidity](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/working-capital-and-liquidity) | 고객·공급자 조건, AR·inventory·AP, cash conversion과 liquidity를 운영계획에 연결한다. |
| 분석 해석 | [CFA — Financial Analysis Techniques](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/financial-analysis-techniques) | 단순 계산보다 무엇이 왜 일어났고 가치·위험에 어떤 의미인지 설명한다. |
| Spreadsheet 품질 | [ICAEW — Twenty Principles for Good Spreadsheet Practice](https://www.icaew.com/technical/technology/excel-community/20-principles-for-good-spreadsheet-practice-2024-edition) | 목적·독자에 맞는 input–process–output, 일관된 formula, checks, review, version·access control을 적용한다. |
| 모델 검증 | [Federal Reserve — SR 26-2 Model Risk Management](https://www.federalreserve.gov/frrs/guidance/supervisory-guidance-on-model-risk-management.htm) | 목적·방법·데이터·중요도에 비례한 validation, outcomes analysis, monitoring, documentation과 effective challenge 원칙만 참고한다. |
| Management accounting | [AICPA & CIMA — Global Management Accounting Principles](https://www.aicpa-cima.com/resources/download/gmap-global-accounting-principles) | 정보·분석을 조직의 의사결정과 가치창출에 연결하는 상위 원칙을 참고한다. |
| 재무제표·현금흐름 | [IFRS — IAS 1](https://www.ifrs.org/issued-standards/list-of-standards/ias-1-presentation-of-financial-statements.html/), [IAS 7](https://www.ifrs.org/issued-standards/list-of-standards/ias-7-statement-of-cash-flows/) | 공개기업 actual을 사용할 때 재무제표 범위와 현금흐름 분류를 존중한다. |

### 1.2 적용상 주의

- AFP의 직무·practice 자료는 P2의 역량 범위 근거다. 특정 회사의 정답, driver 수, 전망기간, 갱신주기, variance threshold를 정하지 않는다.
- AFP rolling forecast 자료는 horizon·increment에 보편적인 rule of thumb이 없다고 명시한다. 따라서 `12개월`, `매월` 같은 값을 외부 표준으로 쓰지 않는다.
- CFA 자료는 기업전망·재무모델 원칙이다. 내부 예산 승인이나 KPI owner의 조직규정을 대신하지 않는다.
- IFRS는 actual 재무보고의 인식·표시 기준이지 내부 management view·forecast의 고정 양식을 정하는 기준이 아니다. actual과 management view 사이의 mapping을 공개한다.
- SR 26-2는 은행 모델리스크 감독지침이고 일반 개인 포트폴리오에 직접 적용되는 규제가 아니다. P2는 위험기반 validation과 독립적인 challenge 원칙만 비례 적용하며 `규제 준수`를 주장하지 않는다.
- AICPA/CIMA 자료는 상위 management accounting 원칙이다. 아래의 구체적인 파일구조·PVM 산식·gate는 해당 기관이 의무화한 형식이 아니라 이 프로젝트의 `[JUDG]` 구현안이다.

---

## 2. 프로젝트 목적과 핵심 질문

### 2.1 목적

P2는 다음 폐쇄루프를 재현 가능하게 증명한다.

```text
의사결정 질문
→ operating·external driver와 metric 정의
→ public target/guidance·analyst plan·forecast version
→ public actual·reconciliation
→ variance attribution
→ updated assumptions·reforecast·scenario
→ proposed accountable role·recommended action·trigger
→ 이후 actual과 outcome monitoring
```

핵심은 dashboard를 만드는 것이 아니라, 숫자의 차이를 실제 조정 가능한 driver와 현금·자원배분 결정으로 연결하는 것이다.

### 2.2 핵심 질문

case와 as-of date를 확정한 뒤 다음 문장을 구체화한다.

> `[as-of date]` 기준으로 계획에서 무엇이 왜 벗어났고, 현재 이용 가능한 정보로 어디에 도달할 것으로 보이며, 어떤 driver를 누가 조정해야 결과와 현금경로가 바뀌는가?

독자에 따라 마지막 결정은 달라질 수 있다.

- FP&A·Corporate Finance: forecast revision, public guidance/analyst-plan gap, cash·resource risk
- BizOps·CEO Staff: KPI 책임구조 제안, 실행 우선순위, operating cadence
- Treasury: cash runway, liquidity buffer, funding timing
- 금융사 전략·Fintech: volume·yield/take rate·loss·funding·control cost를 함께 본 성장판단

### 2.3 하지 않을 것

- 특정 지원기업의 비공개 매출·고객·원가·runway를 추정해 실제값처럼 제시하지 않는다.
- public target/guidance·analyst plan·forecast를 같은 숫자로 두고 `계획 달성 가능`을 증명했다고 하지 않는다.
- 새 actual이 들어올 때 과거 forecast를 덮어쓰지 않는다.
- price·volume·mix 정의가 없는데 PVM 차트를 만들지 않는다.
- 상관관계만으로 driver의 인과관계나 관리가능성을 확정하지 않는다.
- 합성데이터 test를 실제 회사의 forecast 정확도·비용절감·의사결정 성과로 표현하지 않는다.
- 분석대상 회사의 내부 budget, ERP, payroll, CRM, customer·merchant transaction, 계약자료가 있어야만 성립하는 설계를 하지 않는다.
- 웹에서 기술적으로 보인다는 이유만으로 robots·약관·저작권·database right를 무시해 수집하지 않는다.
- spreadsheet 결과를 회계·투자·법률 자문 또는 실제 내부통제 효력으로 표현하지 않는다.

---

## 3. 민간 접근가능 데이터와 Case 선정

### 3.1 민간 접근가능성의 정의

`민간 접근가능`은 분석대상 회사에 취업·파견·자문계약을 맺거나 감독·수사 권한을 가져야만 볼 수 있는 자료가 아니라, 일반 개인·법인이 동일하거나 공개된 조건으로 합법적으로 취득할 수 있다는 뜻이다.

| Access class | Core 사용 | 조건 |
|---|---|---|
| `PUBLIC_OFFICIAL` | 허용 | DART·KIND·KRX·중앙은행·통계기관·법령 등 공식 공개자료 |
| `PUBLIC_COMPANY` | 허용 | 회사 공시·IR·earnings release·공개 KPI·공개 가격표·공개 product document |
| `COMMERCIAL_LICENSED` | 선택 | 민간 구매·구독이 가능하고 license가 분석·재배포 범위를 허용할 때만 사용 |
| `PUBLIC_WEB` | 보조 | 약관·robots·저작권·database right를 확인하고 재현 가능한 lawful collection만 사용 |
| `SYNTHETIC_TEST_ONLY` | test만 허용 | 허용 source의 구조·범위를 토대로 생성하되 factual evidence·actual·truth set으로 사용 금지 |

P2 core는 `PUBLIC_OFFICIAL`과 `PUBLIC_COMPANY`만으로 완결한다. `COMMERCIAL_LICENSED`는 결과를 재현하는 데 필수로 만들지 않고, 사용 시 provider·상품명·접근일·가격조건·license·재배포 제한을 기록한다.

다음은 제외한다.

- 분석대상 회사의 내부 ERP·CRM·payroll·budget·sales pipeline·customer/merchant transaction
- 임직원·계약자 전용 dashboard, data room, NDA 자료
- 감독기관·수사기관·신용정보집중기관만 접근 가능한 비공개 자료
- leak·무단공유·약관위반 scraping·license 범위를 넘는 재배포
- 출처와 이용권한을 설명할 수 없는 vendor export

### 3.2 합성데이터의 제한된 역할

합성데이터는 민간 접근 actual을 대체하지 않는다. PVM·versioning·cash roll-forward·exception handling 같은 계산 engine의 unit/integration test에만 사용한다.

- public source에서 확인할 수 없는 실제 기업의 product/customer 세부값을 채우는 용도로 쓰지 않는다.
- synthetic row는 actual·forecast performance truth set과 물리·논리적으로 분리한다.
- generator·seed·parameter·source basis·생성목적·제약을 공개한다.
- 화면·export·memo에도 `SYNTHETIC_TEST_ONLY` label을 유지한다.
- synthetic test 결과로 실제 회사의 variance 원인·예측력·경영성과를 주장하지 않는다.

### 3.3 금융 도메인 우선 archetype

아래는 지원회사 목록이 아니라 민간이 확보 가능한 공개 KPI로 driver 구조를 만들기 위한 후보군이다.

| Archetype | 민간 확보 가능한 후보 source | Driver 후보 | 한계 |
|---|---|---|---|
| 상장 결제·거래형 | 공시·earnings release·IR KPI·공개 가격정책·거시 결제통계 | TPV·transaction·active account, take rate, processing·risk cost | 회사가 공개하지 않은 merchant/customer grain은 사용하지 않음 |
| 상장 은행·소비자금융 | 사업보고서·분기보고서·regulatory disclosure·중앙은행/감독 공개통계 | average loan/deposit, yield/NIM, funding rate, fee, credit cost, capital·liquidity | 내부 risk grade·PD·LGD·collection curve를 발명하지 않음 |
| 상장 증권·자산운용 | 공시·IR·AUM·net flow·시장거래 통계 | AUM·flow·fee rate, brokerage volume, funding·market sensitivity | proprietary position·client asset detail은 제외 |
| 공개 KPI가 충분한 비금융 benchmark | 공시·IR의 volume·price·store/capacity·inventory KPI | price·volume·mix, unit cost, working capital | 금융 도메인 신호가 약해질 수 있어 비교대안으로만 사용 |

금융 도메인 우선순위는 `결제·거래형 → 은행·소비자금융 → 증권·자산운용`이 아니라, 아래 gate를 통과하는 민간 공개자료의 깊이로 결정한다. 특히 price·volume·mix가 공개되지 않으면 PVM을 억지로 만들지 않고 `actual vs prior public-data forecast`와 공개 driver bridge로 범위를 줄인다.

### 3.4 비보상적 선정 gate

#### Gate A — 민간 접근가능성·license

- 원천 URL/provider, 접근일, access class와 이용조건을 기록할 수 있다.
- 취업·NDA·감독권한 없이 동일 조건으로 다시 확보할 수 있다.
- 핵심 모델이 무료 공식·회사 공개자료만으로 재현된다.
- commercial source가 없어도 핵심 결론이 무너지지 않는다.

#### Gate B — 역사적 vintage

- 각 공시·IR·통계의 발표일과 대상기간을 보존할 수 있다.
- 과거 forecast origin 당시 이용 가능했던 정보집합을 재구성할 수 있다.
- 최신 정정값과 as-reported/public-at-the-time 값을 구분할 수 있다.

#### Gate C — 역할·결정 관련성

- 관련 직무의 계획·성과관리·현금·의사결정 질문으로 바꿀 수 있다.
- 특정 지원회사 없이도 독립적인 FP&A·CEO Staff·금융 분석 증거가 된다.
- output이 조건부 action 또는 monitoring trigger로 연결된다.

#### Gate D — Driver 관측가능성

- public source에 실제로 존재하는 material driver의 정의·단위·기간을 기록할 수 있다.
- driver가 없으면 공개 재무 line·aggregate KPI로 범위를 줄일 수 있다.
- 미공개 driver를 actual처럼 역산하지 않는다.

#### Gate E — 통합 재무 연결

- 공개 driver에서 revenue·cost·working capital·funding을 거쳐 P&L·BS·CF로 연결할 수 있다.
- actual과 analyst plan/forecast의 accounting scope·기간·통화·단위를 맞출 수 있다.
- 공개정보로 연결할 수 없는 부분을 assumption·limitation으로 분리한다.

#### Gate F — Variance·outcome 검증

- 공개 actual과 비교할 immutable analyst forecast vintage가 존재하거나 직접 사전 생성할 수 있다.
- PVM 또는 business-specific bridge의 입력이 모두 민간 접근가능 source에 있다.
- 설명하지 못한 residual과 공개자료 한계를 숨기지 않는다.

#### Gate G — 실행가능성

- 작은 source pilot로 grain, 발표지연, 결측, 정정, 공개 KPI continuity와 병목을 확인했다.
- core와 optional scope를 분리할 수 있다.
- 일정은 pilot 처리량과 review 의존관계에서 산출할 수 있다.

하나의 필수 gate가 실패하면 다른 강점으로 상쇄하지 않는다. 더 단순한 archetype·aggregate model로 바꾸고 decision log에 이유를 남긴다.

### 3.5 선정 기록 템플릿

| 필드 | 기록 |
|---|---|
| Archetype | 사업유형과 제외한 대안 |
| Access classes | PUBLIC_OFFICIAL / PUBLIC_COMPANY / 선택 commercial |
| Source access | URL/provider·접근일·비용·license·재배포 제한 |
| Intended user | 의사결정자·reviewer |
| Decision question | 결과가 바꿀 선택 |
| Grain | 공개된 entity·segment·product·period 범위 |
| Actual source | 공시·IR·통계 원천·발표일·정정상태 |
| Planning versions | public target/guidance·analyst plan·forecast·scenario |
| Material drivers | 공개 정의·단위·source·업데이트 시점 |
| Statement scope | 공개 P&L·BS·CF와 management mapping 한계 |
| Variance candidate | 적용할 공개-data bridge와 제외할 bridge |
| Cash question | liquidity·funding·working-capital 결정 |
| Synthetic test | test 범위·실제 evidence와 분리 방식 |
| Limitations | 미공개 grain·인과·license·재현성 한계 |
| Gate result | A–G pass/fail과 근거 |

---

## 4. Public target·Analyst plan·Forecast·Actual의 의미

### 4.1 Version semantic

P2에서는 다음 값을 섞지 않는다.

| Version | P2 정의 | 사용 목적 |
|---|---|---|
| `Public target/guidance` | 회사가 공식 공개한 목표·전망범위·운영 KPI | 회사가 공개한 기대와 outcome 비교 |
| `Analyst plan` | 민간 공개자료와 명시적 가정으로 작성자가 만든 통합 운영·재무 기준선 | driver·resource·cash의 일관된 계획 simulation |
| `Analyst forecast` | 해당 as-of date에 민간이 확보할 수 있었던 정보만으로 본 현실적인 best estimate | 미래 outcome·위험·기회 |
| `External estimate/consensus` | 공개 웹 또는 일반 민간 고객이 구매 가능한 라이선스로 취득한 제3자 전망 | optional benchmark만 허용; provider·estimate timestamp·point-in-time vintage·coverage·license 기록 |
| `Scenario` | 특정 가정·사건이 성립할 때의 일관된 대안 경로 | what-if·contingency |
| `Public actual` | 공시·IR·공식통계에 공개되고 발표일·정정상태가 보존된 관측결과 | outcome analysis·모델 갱신 |
| `Internal budget` | 회사 내부의 승인된 자원배분 기준선 | 개념은 설명하되 공개되지 않으면 P2 데이터·비교축으로 사용하지 않음 |

회사가 `guidance`라고 공개한 값을 `budget`으로 바꾸어 부르지 않는다. 공개 actual·target/guidance와 작성자의 analyst plan/forecast를 화면·파일·memo에서 계속 구분한다.

이 문서의 `analyst plan`과 `analyst forecast`는 프로젝트 작성자가 민간 공개자료로 생성한 값이며 sell-side analyst estimate나 vendor consensus를 뜻하지 않는다. 외부 전망을 사용하면 `external_estimate_consensus`로 별도 저장하고 현재 조회되는 backfilled·revised 값이 과거 point-in-time 전망인 것처럼 쓰이지 않게 한다.

### 4.2 Forecast는 target의 복사본이 아니다

- public target/guidance와 gap을 없애려고 analyst forecast 가정을 근거 없이 조정하지 않는다.
- analyst forecast는 현실적 예상, public target/guidance는 회사가 공개한 기대·지향점으로 분리한다.
- gap은 실패를 숨길 항목이 아니라 action·risk·opportunity를 찾는 입력이다.
- 개인 포트폴리오에서 assumption owner는 작성자이며 reviewer가 calculation·consistency·합리적 근거를 challenge한다. 실제 회사의 business owner 승인을 받았다고 표현하지 않는다.

근거: [AFP Finance Business Partnering](https://www.financialprofessionals.org/glossary/finance-business-partnering), [AFP Rolling Forecast Guide](https://www.afponline.org/docs/default-source/default-document-library/pub/2015-fp-a-guide-to-implementing-rolling-forecasts-1.pdf?sfvrsn=7c7e466b_2).

### 4.3 Version key

각 숫자는 최소한 다음 차원을 가진다.

```text
case_id
entity
business_unit / product / channel  # 공개 source가 제공할 때만; 아니면 aggregate/null
metric_or_account
period
version_type        # public_target / analyst_plan / analyst_forecast / scenario / public_actual
version_id
as_of_date
forecast_origin
data_vintage
publication_status  # preliminary / filed / revised / restated
currency
unit
source_id
assumption_id
access_class
source_release_date
```

과거 forecast는 immutable snapshot으로 보존한다. 수정이 필요하면 새 `version_id`를 만들고 supersedes 관계를 기록한다.

### 4.4 필수 비교 view

- Public actual vs 당시 민간이 이용 가능했던 prior analyst forecast
- Public actual vs frozen analyst plan — 회사 budget variance가 아닌 model comparison으로 표시
- Public actual vs comparable public target/guidance — 정의·기간이 맞을 때만
- Public actual vs prior-period public actual — 비교 목적이 있을 때
- Latest analyst forecast vs prior analyst forecast vintage
- Latest analyst forecast vs public target/guidance
- Scenario vs latest analyst forecast

비교 기준을 섞지 않는다. 특히 `actual vs latest forecast`는 최신 forecast가 이미 actual을 포함할 수 있으므로 과거 예측정확도로 쓰지 않는다. 회사 내부 budget이 공개되지 않았다면 `actual vs company budget` 표를 만들지 않는다.

---

## 5. 민간 데이터·provenance·합성 test

### 5.1 Source hierarchy

1. DART·KIND·KRX·금융기관 경영공시 등 법정·거래소 공식 공개자료
2. 회사 IR·earnings release·공개 KPI·공개 가격표·product document
3. 정부·중앙은행·통계기관의 공개 원문·API
4. 민간이 구매 가능한 licensed commercial data — optional cross-check
5. 위 원천에서 재현되는 calculation
6. 근거·범위·기준일이 명시된 analyst assumption
7. synthetic test fixture — factual evidence와 분리

검색요약·기사·LLM 출력은 핵심 actual이나 driver의 유일한 원천이 될 수 없다. 핵심 결론은 1–3의 원천만으로 재현 가능해야 한다.

### 5.2 Actual fact table

```text
actual_fact
  case_id
  data_origin
  entity_id
  public_segment_or_product_id
  account_or_metric_id
  period_start
  period_end
  amount
  quantity
  currency
  unit
  publication_status
  source_provider
  source_document_id
  source_release_date
  retrieval_url
  retrieval_timestamp
  source_hash
  access_class
  license_or_terms
  restatement_link
```

공개 원천이 제공하지 않는 customer·merchant·employee grain을 만들지 않는다. 실제 공개된 entity·segment·product·geography·period 범위만 사용하고 집계 전후의 reconciliation key를 보존한다.

`actual_fact.data_origin`에는 `PUBLIC_OFFICIAL` 또는 `PUBLIC_COMPANY`만 허용한다. Commercial cross-check와 synthetic test fixture는 별도 namespace에 두고 public actual truth set에 union하지 않는다.

### 5.3 Planning fact table

```text
planning_fact
  case_id
  version_type
  version_id
  as_of_date
  forecast_origin
  scenario_id
  entity_id
  public_segment_or_product_id
  account_or_metric_id
  period
  value
  currency
  unit
  assumption_id
  author_or_assumption_owner
  review_status
  created_at
  supersedes_version_id
  source_cutoff_timestamp
  model_version
```

### 5.4 Metric dictionary

| 필드 | 의미 |
|---|---|
| Metric ID·name | 변하지 않는 식별자와 표시명 |
| Business definition | 무엇을 포함·제외하는지 |
| Formula | 분자·분모·집계규칙 |
| Unit·currency | 수량·비율·통화·환율 quote |
| Grain | 공개된 entity·segment·product·geography·period |
| Source | 공식 URL·문서·table·공개 정의 |
| Definition provider | 회사·공시기관·통계기관 |
| Analysis owner | mapping·assumption·검토 책임 |
| Availability | release cadence·발표지연 |
| Restatement policy | 변경 시 vintage 처리 |
| Leading/lagging | 결과보다 먼저 움직이는지 |
| Controllability | 직접·간접·비통제 |
| Limitation | bias·누락·proxy 위험 |

KPI 이름만 같고 정의가 다른 상태를 허용하지 않는다. 정의 변경은 새 effective date와 mapping을 남긴다.

### 5.5 합성 test fixture 규칙

합성자료는 공개 actual의 빈칸을 메우는 ledger가 아니라 계산·통제 test fixture다. 다음을 모두 공개한다.

- 생성 목적과 실제 회사와 무관하다는 표시
- random seed와 generator version
- 기간·grain·통화·단위
- business identities와 회계 roll-forward
- base assumption과 distribution 선택 이유
- 의도적으로 삽입한 price·volume·mix·cost·working-capital shock
- missing·late·restated data test case
- action이 test driver를 바꾸는 simulation rule
- synthetic input과 expected test output
- 현실성과 일반화의 한계

synthetic row는 `actual_fact`가 아니라 별도 `test_fixture` namespace에 저장한다. 단순히 analyst plan에 작은 noise를 더하지 않고 알려진 원인별 shock와 회계 identity를 설계해 variance engine이 예상 원인을 복원하고 residual을 노출하는지 시험한다. 이 test는 실제 기업 forecast 정확도나 실제 variance의 근거가 아니다.

### 5.6 발표일·cut-off·정정

- preliminary release, filed report, revised disclosure, restated actual을 구분한다.
- 공시의 분기값·누적값·부분기간을 같은 full-period actual처럼 비교하지 않는다.
- IR preliminary와 법정공시 확정값 차이는 별도 revision으로 기록한다.
- restatement가 발생하면 최신 비교가능 series와 과거 public-at-the-time vintage를 모두 보존한다.
- analyst plan·forecast 생성 당시 공개되지 않았던 정정값을 과거 outcome test에 넣지 않는다.

각 outcome test는 비교 전에 `first public release`, `filed actual`, `latest restated actual` 중 평가대상을 선언한다. 운영상 예측오차는 forecast origin 이후 최초로 이용 가능해진 유효 공개값을 기준으로 보고하고, latest-restated 결과는 별도 view로 둔다. 사후 정정값으로 과거 오차를 조용히 덮어쓰지 않는다.

### 5.7 접근·license·재현성

- source URL, provider, release date, retrieval date, access class를 기록한다.
- commercial data는 product·subscription tier·접근일·historical point-in-time 제공 여부·license·redistribution 및 derived-output 권리와 대체 공개 source를 적는다.
- 공개 web 자료는 이용약관·robots·저작권·database right와 호출 제한을 지킨다.
- commercial source의 파생결과 공개가 계약에서 명시적으로 허용될 때만 숫자·화면을 표시한다. 금지되거나 불명확하면 숫자·화면·원시행을 공개하지 않고 `비공개 cross-check 사용` 사실만 기록한다. 핵심 결론은 무료 공식·회사 공개자료만으로 재현한다.
- 원문이 변경·삭제될 수 있으면 허용 범위에서 hash·문서 ID·읽기전용 citation snapshot을 보존한다.
- 민간 접근성이 사라지거나 license가 바뀌면 source를 교체하거나 해당 output을 release 범위에서 제거한다.

---

## 6. 모델 아키텍처와 통제

### 6.1 논리적 layer

```text
00_about_scope
01_calendar_dimensions
02_public_actual_raw_snapshot
03_mapping_normalization
04_metric_dictionary_driver_tree
05_public_target_analyst_plan_versions
06_forecast_assumptions_versions
07_operating_schedules
08_integrated_pl_bs_cf
09_variance_bridges
10_reforecast_scenarios
11_risk_opportunity_actions
12_management_dashboard_memo
13_checks_validation
14_change_review_release
```

파일·sheet 이름은 프로젝트 구현안이며 외부 표준이 아니다. 중요한 것은 input–process–output과 version·check가 분리되는 것이다. 근거: [ICAEW Twenty Principles](https://www.icaew.com/technical/technology/excel-community/20-principles-for-good-spreadsheet-practice-2024-edition).

### 6.2 계산 흐름

```text
Public actual raw ──→ mapping ──→ normalized public actual ─┐
                                                            ├─→ variance → cause/action
Analyst plan snapshot ──────────────────────────────────────┤
Analyst forecast vintage ───────────────────────────────────┘

Driver assumptions ─→ operating schedules ─→ P&L
                                      ├─────→ working capital / BS
                                      ├─────→ capex / financing
                                      └─────→ cash flow / liquidity

New public actual + reviewed assumption changes
  ─→ new immutable forecast vintage
  ─→ scenarios
  ─→ decision memo / action register
```

### 6.3 Spreadsheet·model 구조 원칙

- input은 한 번 입력하고 계산식 안에 숨은 hardcode를 두지 않는다.
- public actual, analyst plan, forecast assumption, calculation, output, check를 시각·논리적으로 분리한다.
- 전체 기간에 같은 formula logic을 유지하고 예외는 exception table에서 관리한다.
- version·as-of date·currency·unit·sign convention을 상단에 표시한다.
- row·column subtotal과 statement 간 cross-foot을 자동화한다.
- 새 period·product·channel 추가 시 formula를 수동 복사하지 않아도 되는 구조를 우선한다.
- 외부 link·query·macro·script는 analysis maintainer, purpose, refresh, failure behavior를 문서화한다.
- manual override는 원값, 변경값, 공개근거, 작성자, reviewer sign-off, 유효기간과 reversal 조건을 남긴다.

### 6.4 Chart of accounts·management mapping

아래 management view는 공개 KPI·공시 line 또는 같은 scope의 공개 numerator·denominator로 재현할 수 있을 때만 활성화하는 후보 taxonomy다. 미공개 product·customer·employee·supplier·contract·unit-cost allocation을 actual처럼 만들지 않는다.

| Actual accounting view | Management view 예시 | Mapping rule |
|---|---|---|
| Revenue account | product/channel revenue | recognition scope와 gross/net basis 일치 |
| Cost of sales | variable transaction/product cost | revenue driver와 동일 grain 또는 documented allocation |
| Personnel expense | function/headcount cost | average FTE·loaded cost·timing schedule |
| Marketing expense | channel/campaign spend | acquisition·revenue와 인과를 자동 단정하지 않음 |
| Receivables | collection schedule·DSO | billings와 revenue 차이 반영 |
| Inventory | units·unit cost·days | purchase·COGS·write-down 연결 |
| Payables | supplier terms·DPO | relevant purchase base 사용 |
| Capex·PPE | maintenance/growth schedule | depreciation·cash flow 연결 |
| Debt·interest | funding schedule | opening, draw, repayment, rate, covenant |

공개재무 actual을 사용할 경우 management breakdown이 없으면 임의 배분하지 않는다. aggregate model로 범위를 줄이고 limitation을 표시한다.

### 6.5 자동 checks

#### Source·grain

- row count·control total이 raw와 normalized 사이에서 reconcile
- duplicate key와 누락 dimension 탐지
- period·currency·unit 혼입 탐지
- access class·source release date·license metadata 누락 탐지
- actual_fact의 data_origin이 PUBLIC_OFFICIAL 또는 PUBLIC_COMPANY인지 확인

#### Version

- forecast origin 이후 공개된 actual이 과거 forecast vintage에 들어가지 않음
- version_id·as_of date·origin의 unique·ordering check
- public actual이 선택된 period에 forecast formula가 결과를 덮지 않음
- public target/guidance·analyst plan·forecast가 잘못 merge되지 않음

#### Accounting·cash

- assets = liabilities + equity
- beginning cash + CFO + CFI + CFF + FX/other explained = ending cash
- opening balance + additions − reductions = closing balance
- P&L·BS change·CF 간 material line reconciliation
- publicly disclosed supporting schedule 또는 analyst-modeled schedule 합계 = statement line

#### Variance

- total variance = 표시된 driver effects + residual
- PVM·cost bridge가 chosen convention 아래 exact-additive
- aggregation level을 바꿔도 subtotal과 total이 일치
- FX translation·constant-currency basis가 명시됨

#### Reasonableness

- impossible negative count·rate·days와 divide-by-zero 탐지
- extreme input에서 formula failure·sign reversal·circularity 점검
- growth·margin·cash·working-capital 관계의 경제적 일관성 검토

---

## 7. Driver tree와 metric 선정

### 7.1 Driver 선정 기준

driver는 다음 질문을 통과해야 한다.

- `Decision relevance`: 이 값이 바뀌면 실제 action이나 자원결정이 바뀌는가?
- `Economic link`: financial outcome과 설명 가능한 구조적 관계가 있는가?
- `Predictive evidence`: 실제 데이터에서 측정·도출되고 설명력·안정성을 시험할 수 있는가?
- `Availability`: 필요한 시점에 신뢰 가능한 값이 도착하는가?
- `Definition stability`: 기간·부서·제품 간 같은 정의를 유지하는가?
- `Controllability`: 일반적인 proposed role이 직접·간접으로 영향을 줄 수 있는가? 실제 회사의 책임배정으로 오인되지 않는가?
- `Lead time`: 결과보다 먼저 움직여 대응시간을 주는가?
- `Parsimony`: 추가 복잡성이 의사결정·정확성·설명력의 개선으로 정당화되는가?

AFP는 driver-based model이 operational·external driver와 financial outcome을 연결하고, key driver가 데이터에서 측정·도출되며 강한 predictive ability를 가져야 한다고 설명한다. 다만 driver 개수는 이 설계에서 고정하지 않는다. 근거: [AFP Driver-based Models and Plans](https://www.financialprofessionals.org/training-resources/resources/guides/fp-a-guides/Detail/driver-based-modelling).

### 7.2 Driver category

```text
External
  market demand, macro, FX, rate, regulation, seasonality

Demand
  customers/accounts, leads, conversion, orders, usage, retention

Price/yield
  list price, discount, realized price, take rate, yield

Mix
  product, channel, geography, customer segment, risk grade

Capacity/productivity
  headcount, throughput, utilization, service level, automation

Cost
  unit input cost, processing fee, compensation, cloud, logistics

Working capital
  billing/collection, DSO, inventory days, supplier terms, DPO

Investment/funding
  capex, project milestone, debt draw/repayment, funding rate

Risk/control
  loss, fraud, refund, chargeback, operational incident, compliance cost
```

이 category는 탐색 taxonomy일 뿐 입력목록이 아니다. 각 driver를 `OBSERVED_PUBLIC`, `DERIVED_PUBLIC`, `ANALYST_ASSUMPTION` 중 하나로 표시하고, 공개 source가 없는 driver는 actual bridge에서 제외한다.

### 7.3 Driver card

| 필드 | 내용 |
|---|---|
| Driver | 이름·ID |
| Outcome | 영향을 받는 KPI·account·cash |
| Relationship | formula·lag·non-linearity |
| Evidence | actual test·공식 source |
| Direction | expected sign과 예외 |
| Owner | 정의·입력·action 책임 |
| Controllability | direct/indirect/external |
| Availability | 공개 frequency·latency·publication status |
| Range | 역사·계약·capacity·공식자료 근거 |
| Scenario use | 어떤 위험·기회를 표현하는지 |
| Limitation | proxy·endogeneity·definition change |
| Revalidation trigger | 관계를 다시 시험할 사건 |

### 7.4 Driver selection test

- correlation만 보고 driver로 승인하지 않는다.
- trend·seasonality·common cause를 제거한 뒤 관계를 재검토한다.
- 필요한 경우 lag와 saturation·capacity ceiling을 시험한다.
- outlier가 data error인지 실제 사건인지 분리한다.
- 더 단순한 baseline과 설명력·안정성·유지비용을 비교한다.
- driver가 바뀌었을 때 P&L·BS·CF와 decision output이 예상 방향으로 움직이는지 perturbation test를 한다.
- weak·unstable driver는 보조 indicator로 낮추거나 제외하고 이유를 남긴다.

---

## 8. Business model module

P2 core는 하나의 archetype만 깊게 구현한다. 아래 driver와 식은 공개 KPI·공시 line·공개 계약조건에서 입력을 직접 확보하거나 동일 scope의 공개 numerator·denominator로 재현할 수 있을 때만 활성화하는 후보 taxonomy다. 미공개 customer·employee·supplier·contract·unit-cost 값은 actual로 추정하거나 synthetic으로 채우지 않는다. 공개 입력이 없으면 해당 module을 비활성화하고 aggregate public-financial model로 범위를 축소한다.

### 8.1 결제·거래형

```text
Transactions
  = active accounts × transactions per active account

TPV
  = transactions × average ticket

Gross transaction revenue
  = TPV × effective take rate

Variable processing cost
  = TPV × effective processing rate
    + transaction-count-based fees

Risk/control cost
  = observed chargeback/refund/fraud amounts
    + publicly disclosed support/operations cost
```

- TPV·transaction·active account의 공식 정의를 metric dictionary에 둔다.
- take rate는 gross/net revenue scope와 accounting presentation을 맞춘다.
- fraud·chargeback·loss rate는 관측자료가 없으면 probability를 발명하지 않고 명시적 stress assumption으로만 쓴다.
- 미공개 support/operations allocation은 actual이 아니라 명시적 analyst scenario assumption으로만 사용한다.
- settlement timing과 payable/receivable 구조를 cash schedule에 연결한다.

### 8.2 구독·software

```text
Ending customers
  = beginning customers + new customers − churned customers

Average customers
  = period-weighted customer exposure

Revenue
  = average customers × recognized ARPU
    + usage/project/other revenue where applicable

Gross profit
  = revenue − hosting/service/delivery cost
```

- ARR·billings·revenue·cash collection을 구분한다.
- cohort·contract timing이 material하면 단순 beginning/ending average 대신 recognition schedule을 사용한다.
- acquisition spend와 new customers 사이의 인과를 자동 확정하지 않는다.

### 8.3 소비재·product

```text
Revenue
  = Σ(product/channel units × realized price)

COGS
  = units sold × unit cost

Ending inventory units
  = beginning units + purchases/production − units sold − write-offs

Inventory value
  = accounting policy와 cost flow를 반영한 schedule
```

- sell-in·sell-through·returns·discount를 구분한다.
- product/channel mix가 정의될 때 PVM을 적용한다.
- inventory write-down·obsolescence와 cash purchase timing을 별도 schedule로 둔다.

### 8.4 Marketplace

```text
Orders
  = active buyers × orders per buyer

GMV
  = orders × average order value

Revenue
  = GMV × effective take rate
    + recognized service revenue
```

GMV는 recognized revenue가 아니다. principal/agent와 gross/net presentation은 공개 actual을 사용할 때 회사 공시·회계정책에 맞춘다.

### 8.5 대출·금융서비스 확장

```text
Average earning asset
  = period-weighted receivable or asset balance

Interest/yield revenue
  = average earning asset × effective yield

Funding cost
  = average funded balance × effective funding rate

Observed credit/fraud cost
  = 실제 charge-off·provision·loss 데이터의 정의에 맞춘 amount
```

- origination, repayment, delinquency, loss, funding, capital·liquidity를 하나의 flow로 연결한다.
- PD·LGD·EAD 또는 expected credit loss를 사용할 경우 관측·검증 가능한 데이터와 적용 회계·risk scope가 있어야 한다.
- 데이터가 없으면 cash collection·coverage·stress model로 범위를 제한하고 실제 risk estimate로 표현하지 않는다.

### 8.6 Cost·headcount·capex

```text
Average FTE
  = opening FTE + timing-weighted hires − timing-weighted exits

Personnel cost
  = average FTE × loaded cost per FTE
    + separately modeled variable compensation

Capex cash
  = publicly disclosed capex guidance·commitment·project milestone
    또는 명시적 analyst-assumed schedule

Depreciation
  = opening asset schedule + new capex schedule under stated policy
```

- 공개 headcount·인력비·채용공고 등으로 관측 가능한 범위에서만 headcount·compensation driver를 쓴다.
- 미공개 hire/exit timing이나 vacancy를 actual variance 원인으로 단정하지 않는다. Analyst scenario에서만 가정·근거·범위를 표시한다.
- 공개자료가 hiring delay를 직접 뒷받침하지 않으면 personnel underspend를 지속 가능한 효율로 해석하지 않는다.
- capex와 expense classification은 actual accounting mapping과 일관되게 유지한다.

---

## 9. 통합 Plan·Forecast·Actual 모델

### 9.1 Planning flow

```text
Strategic objective
→ operating driver target
→ resource/capacity requirement
→ revenue·cost·working capital·capex
→ P&L·BS·CF·liquidity
→ frozen analyst plan snapshot
```

계획은 chart of accounts line을 전년도 비율로 일괄 증가시키는 표로 끝내지 않는다. material line은 business driver 또는 명시적 계약·schedule과 연결하고, 연결할 정보가 없으면 aggregate assumption과 한계를 기록한다.

### 9.2 Integrated statements

- Revenue·COGS·opex·tax에서 net income까지 연결한다.
- AR·inventory·AP와 기타 material working-capital account를 운영 driver에 연결한다.
- capex·depreciation·asset roll-forward를 연결한다.
- debt·interest·repayment·funding need를 cash와 연결한다.
- operating·investing·financing cash flow와 ending cash를 balance sheet에 대사한다.
- accounting view와 management view 사이 allocation·non-GAAP adjustment를 따로 표시한다.

근거: [AFP FPAC Test Specifications](https://fpacert.financialprofessionals.org/exam/specifications), [CFA Introduction to Financial Statement Modeling](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/introduction-to-financial-statement-modeling).

### 9.3 Working capital·liquidity

관계가 실제 사업에 적합할 때 다음 후보를 사용한다.

```text
Accounts receivable
  ≈ relevant billing/revenue base × collection-days convention

Inventory
  ≈ relevant COGS/purchase base × inventory-days convention

Accounts payable
  ≈ relevant purchase/cost base × payment-days convention

Cash_t
  = Cash_(t-1) + CFO_t + CFI_t + CFF_t + explained FX/other_t
```

- day-count basis와 average/ending balance의 의미를 명시한다.
- billings와 revenue, purchases와 COGS가 다르면 직접 schedule을 우선한다.
- negative working capital이 사업구조인지 stress인지 구분한다.
- cash floor·funding trigger는 공개된 covenant, debt maturity, liquidity requirement 또는 공식 guidance가 있을 때만 fact로 사용한다. 공개 근거가 없으면 analyst scenario threshold로 라벨링하고 회사의 실제 내부 risk tolerance라고 표현하지 않는다.

근거: [CFA Working Capital and Liquidity](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/working-capital-and-liquidity).

### 9.4 Reforecast mechanics

```text
Latest outlook(period, as_of)
  = declared outcome policy가 선택한 public actual,
    if that period was reported before as_of
  = current analyst forecast vintage, otherwise
```

- public actual이 발표된 period는 lock하고 이후 기간만 새 정보로 갱신한다.
- prior forecast vintage를 보존한다.
- 새 가정은 공개 evidence·작성자·review status·effective period를 가진다.
- horizon 끝이 이동하는 rolling 방식이면 새 far period를 추가하되 그 상세도가 decision value를 제공하는지 검토한다.
- reforecast와 scenario를 분리한다. reforecast는 current best estimate, scenario는 조건부 대안이다.

### 9.5 Horizon·increment·cadence

고정 기간과 주기를 사용하지 않는다. 다음을 decision log에 기록한다.

- forecast가 지원할 결정과 lead time
- 공시·IR KPI·공식통계의 실제 발표빈도와 latency
- 계절성·cycle·contract·capacity·funding horizon
- 먼 기간 세부예측의 신뢰성과 유지비용
- 잘못된 결정의 재무·운영 영향
- volatility와 최근 구조변화
- 공개정보 갱신주기와 reviewer·가상 의사결정자가 판단할 수 있는 cadence

cadence는 공개 공시·IR·통계의 발표주기와 release latency, 외부 분석 의사결정의 lead time, 사업 변동성 및 오류비용으로 정한다. 회사 내부 close·management decision calendar를 알고 있다고 가정하지 않는다.

scheduled refresh는 public result·KPI·macro release와 분석 의사결정 cycle에 맞추고, 다음 사건은 event-driven update 후보로 둔다.

- material price·volume·mix·cost change
- 공개된 중요 계약·규제·제품·capacity milestone
- liquidity·funding·covenant headroom 악화
- data source·metric definition·accounting scope 변경
- 지속적인 forecast bias 또는 model override

---

## 10. Variance 분석

### 10.1 비교 순서

1. 비교 version·vintage·as-of date를 명확히 표시한다.
2. total variance를 P&L·BS·CF와 reconcile한다.
3. 정의 가능한 economic driver로 분해한다.
4. controllable·uncontrollable, timing·permanent, recurring·one-off를 구분한다.
5. residual을 숨기지 않는다.
6. what happened → why → implication → recommended action → proposed accountable role → trigger로 연결한다.

### 10.2 단일 price × volume

`[JUDG]` 아래는 exact-additive 구현 convention 중 하나다.

```text
R0 = P0 × V0
R1 = P1 × V1

Pure price effect   = (P1 − P0) × V0
Pure volume effect  = (V1 − V0) × P0
Interaction effect  = (P1 − P0) × (V1 − V0)

Total variance
  = Pure price + Pure volume + Interaction
  = R1 − R0
```

interaction을 price 또는 volume에 배분할 수도 있지만 순서 의존성이 생긴다. 선택 convention과 이유를 문서화하고 period·dashboard 사이에서 바꾸지 않는다.

### 10.3 Multi-product PVM

planned quantity `q0_i`, actual quantity `q1_i`, planned price `p0_i`, actual price `p1_i`, planned mix `m0_i`, actual mix `m1_i`로 정의한다.

```text
Q0 = Σq0_i
Q1 = Σq1_i
m0_i = q0_i / Q0
m1_i = q1_i / Q1

Price variance
  = Σ q1_i × (p1_i − p0_i)

Volume variance
  = (Q1 − Q0) × Σ(m0_i × p0_i)

Mix variance
  = Q1 × Σ((m1_i − m0_i) × p0_i)

Price + Volume + Mix
  = Actual revenue − Planned revenue
```

이 산식은 P2의 구현 convention이지 AFP가 유일하게 의무화한 공식이 아니다. quantity가 음수·0이거나 product definition이 바뀌면 적용가능성을 다시 판단한다.

여기서 `planned`는 작성자의 frozen analyst plan/forecast, `actual`은 동일 scope의 public actual을 뜻한다. 제품·segment별 수량과 realized price가 base와 actual 양쪽 공개 vintage에 직접 존재하거나, 동일 scope의 공개 revenue와 quantity로 realized price를 재현할 수 있을 때만 PVM을 실행한다. 공개 list price를 realized price로 간주하지 않는다. 할인·수량·mix 입력이 미공개이면 PVM을 비활성화하고 aggregate revenue/driver bridge와 residual로 보고한다. Synthetic PVM fixture는 계산검증 전용이며 actual variance chart에 포함하지 않는다.

### 10.4 금융서비스형 bridge

business definition이 맞을 때 다음 원인 후보를 사용한다.

- transaction/asset volume
- take rate·yield·pricing
- product·channel·risk-grade mix
- funding rate·funding mix
- loss·fraud·refund·chargeback
- servicing·processing unit cost
- collection·settlement timing
- external rate·FX·regulation

`volume × rate`만으로 risk·funding·control cost를 누락하지 않는다. 금융서비스 P2는 revenue growth와 risk-adjusted cash를 함께 보여야 한다.

### 10.5 Cost variance

사업에 맞는 identity를 먼저 확정한다.

```text
Variable cost = activity volume × unit cost
Personnel cost = average FTE × loaded rate + variable components
Cloud/usage cost = usage units × unit rate
Logistics cost = shipments × cost per shipment
```

원인 후보:

- activity/volume
- rate·price
- mix
- efficiency/yield
- headcount
- compensation rate
- hire/exit timing
- vendor·contract
- FX·inflation
- one-off·reclassification

underrun이 hiring delay나 activity shortfall 때문이면 `비용효율`로 분류하지 않는다.

### 10.6 Working-capital·cash variance

- revenue/COGS variance와 collection·inventory·payment timing effect를 분리한다.
- AR은 revenue 또는 billings 기준이 무엇인지 명시한다.
- inventory는 unit volume, unit cost, purchase timing, write-off를 구분한다.
- AP는 purchase base와 supplier terms를 연결한다.
- cash bridge는 EBITDA만 보여주지 않고 working capital, capex, tax, interest, financing을 포함한다.
- liquidity decision을 바꾸는 variance는 P&L variance보다 우선 escalation할 수 있다.

### 10.7 FX·scope·accounting

- transaction FX와 translation FX를 구분할 수 있을 때 분리한다.
- constant-currency view의 quote, rate source, average/closing rate를 명시한다.
- acquisition·disposal·new product·org transfer 등 scope change를 like-for-like performance와 분리한다.
- account reclassification은 경제적 variance로 포장하지 않는다.

### 10.8 Materiality와 escalation

보편적인 `±10%` 같은 threshold를 사용하지 않는다. 다음을 결합해 결정한다.

- cash·liquidity·funding·covenant 영향
- public target/guidance·strategy·market·regulatory condition 영향
- proposed role이 검토할 수 있는 크기와 lead time
- 반복성·지속성·bias
- uncertainty와 data quality
- aggregate에서는 작아도 product·channel에서 큰 risk
- 결론·resource allocation을 바꿀 가능성

threshold와 변경조건은 승인 전에 기록한다. threshold 미만이어도 fraud·control·data-integrity 신호는 별도 escalation할 수 있다.

---

## 11. Reforecast·scenario·action loop

### 11.1 Reforecast 절차

1. public actual의 publication status·completeness·source total을 확인한다.
2. prior plan·forecast와 동일 scope·currency·grain으로 normalize한다.
3. total variance와 driver bridge를 reconcile한다.
4. fact, timing, one-off, structural change, data issue를 구분한다.
5. 기존 assumption 중 evidence가 깨진 항목을 식별한다.
6. 작성자가 revised assumption·range·effective date와 공개근거를 등록하고, reviewer가 계산·일관성·합리적 근거를 challenge한다. 분석대상 회사의 실제 business owner와 합의하거나 승인을 받았다고 표현하지 않는다.
7. 새 immutable forecast vintage를 생성한다.
8. P&L·BS·CF·cash·liquidity를 재계산한다.
9. material risk·opportunity scenario와 action을 평가한다.
10. decision memo와 monitoring trigger를 갱신한다.

이 순서는 P2의 dependency logic이며 고정 조직 프로세스가 아니다.

### 11.2 Scenario와 sensitivity

- scenario는 driver·재무제표·cash·action이 내부 일관된 경제적 경로다.
- sensitivity는 한 가정 또는 제한된 가정 변화가 output에 미치는 영향을 본다.
- scenario 수를 미리 정하지 않는다.
- 범위는 공개 역사적 분포, 공개된 계약·capacity disclosure, 회사·산업 공식자료, macro source, break-even·stress에서 도출한다.
- 확률을 부여하면 base rate·market evidence·전문판단과 기준일을 기록한다.
- 확률 근거가 없으면 정성적 conditional path로 유지한다.
- upside만큼 liquidity·funding·execution downside를 포함한다.

### 11.3 Risk·opportunity register

| 필드 | 기록 |
|---|---|
| ID | 변경되지 않는 식별자 |
| Driver/event | 무엇이 변하는가 |
| Evidence | source·as-of date |
| Direction/range | 재무영향 방향·근거 범위 |
| Statement/cash impact | P&L·BS·CF·liquidity |
| Scenario | 연결된 경로 |
| Leading indicator | 먼저 확인할 metric |
| Trigger | 재검토·action 조건 |
| Proposed accountable role | 공개 조직정보와 일반적 직무범위에 근거한 제안 역할; 실제 회사의 책임배정 fact가 아님 |
| Action options | 가능한 조치와 trade-off |
| Status | recommended / monitoring / publicly_announced / publicly_observed / closed |
| Review result | 이후 공개적으로 관측된 결과와 한계 |

### 11.4 Action register

```text
action_id
decision_id
linked_driver
linked_variance
proposed_owner_role
action_description
expected_mechanism
expected_financial_effect
cash_effect
dependencies
decision_date
effective_period
leading_indicator
review_trigger
status
publicly_observed_outcome
lesson
```

action 효과는 `[A]` 또는 `[R]`로 유지한다. 회사 공시·IR·공식자료로 실행과 결과가 공개적으로 확인된 경우에만 `[M]`으로 변경하며, 공개되지 않은 내부 실행·절감·성과를 추정하지 않는다. 외부 요인과 counterfactual 한계도 함께 설명한다.

### 11.5 Decision rule

결론은 한 점 전망이 아니라 조건으로 표현한다.

> `driver X`가 `evidence-based range`를 벗어나고 `cash/decision output`이 `documented material condition`을 충족하면, `proposed accountable role`이 `action A/B`를 검토하는 방안을 제안한다. 이는 실제 회사의 책임배정 fact가 아니다. 반대 지표가 확인되면 action을 보류하고 forecast assumption을 재검토한다.

threshold 숫자는 case evidence에서 산출한다. 없으면 `TBD after pilot`로 남기며 가짜 정밀도를 만들지 않는다.

---

## 12. Management dashboard·memo·handover

### 12.1 Dashboard가 답할 질문

- 현재 public actual·latest analyst forecast·public target/guidance는 각각 어디인가?
- 계획에서 벗어난 material variance는 무엇이며 bridge가 합산되는가?
- 일시적 timing과 구조적 변화는 무엇인가?
- 어떤 driver가 미래 P&L·cash·liquidity를 바꾸는가?
- prior forecast 대비 무엇이 바뀌었는가?
- 어떤 risk·opportunity가 열려 있고 proposed role·trigger·action은 무엇인가?
- 데이터가 preliminary·synthetic·limited인 곳은 어디인가?

### 12.2 Core view

| View | 핵심 내용 |
|---|---|
| Executive outlook | actual, plan, latest forecast, target와 조건부 conclusion |
| Driver tree | leading/lagging KPI와 financial linkage |
| Variance bridge | total → driver → residual, timing/permanent, controllability |
| Forecast change | prior vintage → latest vintage assumption 변화 |
| Integrated finance | P&L·BS·CF와 cash·liquidity |
| Risk/opportunity | scenario, trigger, proposed accountable role, recommended action |
| Forecast performance | vintage별 error·bias·decision impact |
| Data quality | publication status, missing, revision/restatement, mapping·check exception |

view 수나 차트 형식은 고정하지 않는다. 독자와 decision에 필요하지 않은 장식은 제거한다.

### 12.3 Decision memo

분량이 아니라 다음 내용의 충분성으로 판단한다.

- decision·as-of date·intended use
- current outlook과 target/plan gap
- material variance와 원인
- prior forecast에서 바뀐 가정
- P&L·cash·liquidity impact
- risk·opportunity scenario
- action option, proposed accountable role, trade-off
- recommendation과 trigger
- 반대 근거·data/model limitation
- 다음 actual에서 확인할 outcome

### 12.4 Handover guide

- data refresh source provider·analysis maintainer·cut-off
- public result release와 revision/restatement 처리
- 새 version 생성·freeze·rollback
- mapping·metric definition 변경절차
- assumption input·reviewer sign-off
- checks·exception 해결
- variance convention
- dashboard·memo refresh
- review·release·archive
- access·privacy·secret 관리

---

## 13. 검증·outcome analysis·monitoring

### 13.1 적용 원칙

검증은 숫자형 정확도만 보는 절차가 아니다.

- conceptual soundness: driver·statement·variance·decision logic이 타당한가?
- process verification: input·mapping·formula·version·control이 의도대로 작동하는가?
- outcomes analysis: 과거 forecast와 실제 결과가 어떻게 달랐는가?
- benchmark: 더 단순한 방법보다 가치가 있는가?
- effective challenge: 작성자와 다른 관점에서 가정·결론을 반박했는가?
- ongoing monitoring: 데이터·관계·사용범위가 변했는가?

근거: [Federal Reserve SR 26-2](https://www.federalreserve.gov/frrs/guidance/supervisory-guidance-on-model-risk-management.htm). P2는 규제 준수가 아닌 비례적 품질 원칙으로만 참고한다.

### 13.2 Look-ahead 없는 outcome analysis

1. 각 forecast origin의 당시 data vintage와 assumption을 복원한다.
2. 이후 restatement·현재 정보가 과거 forecast에 들어가지 않게 한다.
3. 목적에 맞는 horizon별 actual과 비교한다.
4. rolling-origin이 가능하면 독립 origin을 활용한다.
5. 구조변화·공시 revision·outlier·data issue를 표시한다.
6. error가 analyst resource·cash recommendation을 바꿀 정도였는지 본다.

합성자료만 쓴 경우에는 실제 예측 성능을 주장하지 않는다. 생성과정의 알려진 shock를 bridge가 복원하는지, identities·versioning·checks가 통과하는지만 검증한다.

### 13.3 Benchmark

사용 전에 목적에 맞는 baseline을 선언한다.

- prior-period 유지
- 전년동기 또는 seasonal-naive
- frozen analyst plan 또는 comparable public guidance
- prior forecast vintage
- 단순 trend·driver-free model
- 적법하게 이용 가능한 external estimate/consensus — 당시 point-in-time vintage, contributor coverage, 사용·파생결과 표시 권리가 확인될 때만

현재 조회되는 backfilled·revised consensus를 과거 forecast처럼 사용하지 않는다. 외부 consensus는 작성자의 analyst forecast와 별도 객체·benchmark로 유지한다.

전부를 기계적으로 쓰지 않는다. 선택·제외 이유와 비교 horizon을 남긴다.

### 13.4 Error·bias metric

| 지표 | 사용 |
|---|---|
| MAE | 같은 단위·규모에서 원 단위 평균오류 |
| Bias/mean error | 지속적 과대·과소 forecast |
| MASE | 정의한 naive baseline 대비 scale-adjusted error가 필요할 때 |
| Absolute/percentage variance | actual이 0·근접0·부호변경하지 않는 적합한 line에서 보조 사용 |
| Decision impact | error가 cash·hiring·investment·action 결론을 바꿨는지 |

MAPE는 actual이 0·근접0이거나 순이익·FCF처럼 부호가 바뀌는 line에서 왜곡될 수 있다. MASE는 denominator와 seasonal period를 명시하고 `<1`을 보편적 합격선으로 쓰지 않는다. 근거: [Hyndman & Koehler (2006)](https://doi.org/10.1016/j.ijforecast.2006.03.001).

### 13.5 검증 결론

고정 오차율 대신 다음을 함께 본다.

- 사전 benchmark 대비 horizon별 성능
- bias·오차분포·표본 수와 불확실성
- driver relationship의 안정성
- variance residual과 mapping exception
- sensitivity·stress의 경제적 일관성
- cash·decision impact
- 알려진 limitation과 보완통제
- reviewer finding과 unresolved issue

결론 상태는 행동과 연결한다.

- `사용 가능`
- `특정 version·grain·decision에 한해 사용 가능`
- `보완통제 조건부 사용`
- `재보정·재설계 필요`
- `사용 불가`

### 13.6 Monitoring·revalidation trigger

고정 연간 횟수로 정하지 않는다.

- 새 filed actual·revision·restatement 공개
- 지속적 bias·error deterioration
- material residual·manual override 증가
- metric·account·product·org definition 변경
- data source·schema·system 변경
- pricing·business model·capacity·regime 변경
- forecast 목적·사용자·horizon·decision exposure 변경
- model formula·automation·vendor update

### 13.7 Independent review

- 개발자와 가능한 한 다른 reviewer가 source, mapping, formula, variance convention, assumption, decision logic을 검토한다.
- 작은 개인 프로젝트라면 동료·멘토가 reviewer가 될 수 있으나, 검토범위·finding·response를 기록한다.
- review 강도는 데이터 민감성, model complexity, cash·decision impact와 공개 주장 위험에 비례한다.
- reviewer가 수정을 요구할 수 있고 unresolved issue가 release restriction으로 이어져야 effective challenge다.

---

## 14. 실행계획: 달력이 아닌 dependency gate

### Phase A — 목적·case·데이터 feasibility

- intended user, decision, as-of date, prohibited use를 정한다.
- 민간 access class와 business archetype에 Gate A–G를 적용한다.
- 공식 공시·IR·통계 한 개 grain·period를 raw → normalized → statement까지 pilot한다.
- source release date, license, public KPI continuity, synthetic-test 분리와 가장 큰 병목을 확인한다.

`완료 gate:` case가 특정 지원회사·내부자료 없이 관련 직무·금융 결정에 연결되고, 민간이 재확보 가능한 source와 일정 산정 근거가 있다.

### Phase B — Semantic·version·source foundation

- public target/guidance·analyst plan·forecast·scenario·public actual 정의를 고정한다.
- calendar·version key·metric dictionary·source ledger를 만든다.
- COA·management mapping과 restatement policy를 정한다.
- public actual·planning fact의 control total을 만든다.

`완료 gate:` 숫자가 version·as-of·period·unit·source까지 추적되고 정의 충돌과 덮어쓰기가 방지된다.

### Phase C — Driver tree·통합 planning model

- driver candidate를 business identity와 data로 시험한다.
- core archetype schedule을 만든다.
- revenue·cost·working capital·capex·funding을 P&L·BS·CF에 연결한다.
- analyst plan과 initial analyst forecast snapshot을 freeze한다.

`완료 gate:` material driver가 financial outcome과 연결되고 accounting·cash·roll-forward check가 통과한다.

### Phase D — Public actual·variance engine

- public actual ingestion·release cut-off·revision·restatement를 구현한다.
- public actual vs analyst plan, public actual vs prior analyst forecast를 분리한다.
- business-appropriate PVM·cost·cash bridge를 만들고 exact-additivity를 검증한다.
- residual·timing·scope·data issue를 노출한다.

`완료 gate:` 공개 source total variance가 statement와 reconcile되고, 민간 데이터로 설명한 원인·residual·미공개 한계가 구분된다.

### Phase E — Reforecast·scenario·action

- new public actual과 reviewed assumption change로 새 analyst forecast vintage를 만든다.
- coherent scenario·sensitivity와 risk/opportunity register를 연결한다.
- proposed accountable role, expected mechanism, cash impact, trigger를 기록한다.
- public target/guidance·analyst forecast gap을 숨기지 않고 decision memo로 전달한다.

`완료 gate:` reforecast가 과거 version을 훼손하지 않고, 변경 driver·재무영향·action·trigger가 연결된다.

### Phase F — Validation·communication·release

- look-ahead 없는 outcome analysis와 사전 benchmark를 수행한다.
- formula·source·driver·variance·claim을 독립 관점에서 review한다.
- dashboard, memo, handover, read-only snapshot을 만든다.
- limitation·synthetic label·prohibited use를 공개한다.

`완료 gate:` 아래 release gate가 모두 통과한다.

### 일정 산정

Phase A pilot 후 다음 작업량으로 일정을 계산한다.

- 공개된 period·segment·product·account grain
- mapping·definition·restatement 복잡성
- 합성 generator와 known-shock test 범위
- core business schedule과 statement 수
- variance convention·scenario 복잡성
- forecast origin과 reviewer 가용성
- 공개 deadline과 optional deliverable

마감이 촉박하면 선택 dashboard·automation·영상 범위를 줄인다. source lineage, version integrity, accounting·cash reconciliation, variance identity, limitation은 생략하지 않는다.

---

## 15. 비보상적 release gate

단일 점수와 합격점을 사용하지 않는다. material gate가 실패하면 공개하지 않거나 사용범위를 명시적으로 제한한다.

### Gate R1 — 민간 접근가능성·provenance

- 모든 core actual·driver에 source URL/provider, release date, access class, period·unit이 있다.
- 취업·NDA·감독권한 없이 민간이 합법적으로 다시 확보할 수 있다.
- 핵심 결론은 무료 공식·회사 공개자료만으로 재현된다.
- commercial source의 license·비용·재배포 제한과 공개 대체 source가 기록된다.
- synthetic test fixture가 public actual·truth set과 분리된다.
- AI·검색요약이 핵심 actual의 유일한 근거가 아니다.

### Gate R2 — Semantic·version integrity

- public target/guidance·analyst plan·forecast·scenario·public actual 정의가 분리된다.
- 과거 analyst forecast vintage와 public actual publication status가 보존된다.
- data restatement와 model revision이 구분된다.
- comparison view가 동일 scope·period·currency·unit을 사용한다.

### Gate R3 — Statement·cash integrity

- operating schedules가 P&L·BS·CF에 연결된다.
- balance·cash·roll-forward·subledger checks가 통과한다.
- public source가 제공하지 않는 management allocation을 actual처럼 만들지 않았고, 공개 accounting actual과 analyst view 차이가 설명된다.
- unexplained material difference가 숨겨지지 않는다.

### Gate R4 — Variance integrity

- total variance가 driver effect와 residual 합계로 reconcile된다.
- PVM·cost·FX convention과 순서 의존성이 문서화된다.
- timing·scope·reclassification·data issue가 economic performance와 구분된다.
- materiality가 decision impact에 연결된다.

### Gate R5 — Forecast reasonable basis

- key driver가 공개데이터·경제논리·analysis owner·range에 연결된다.
- horizon·cadence·scenario 범위의 근거가 있다.
- public target/guidance를 analyst best estimate로 위장하지 않는다.
- benchmark·outcome analysis·bias·표본 한계가 기록된다.

### Gate R6 — Action·decision linkage

- what·why·implication·action이 연결된다.
- proposed accountable role, expected mechanism, cash effect, trigger와 반대 근거가 있다.
- action 전 예상효과와 action 후 측정결과가 구분된다.
- 실제 경영지원·도입·절감을 과장하지 않는다.

### Gate R7 — Effective challenge·reproducibility

- 다른 사람이 source → mapping → driver → statement → variance → reforecast → decision 경로를 추적할 수 있다.
- reviewer finding·response·remaining restriction이 있다.
- 실행환경·refresh·version·rollback·handover가 문서화된다.
- read-only snapshot의 숫자가 model·memo와 일치한다.

---

## 16. 산출물 구조

### 16.1 필수 산출물

- `README`: 목적, 독자, decision, 민간 access policy, as-of, intended/prohibited use
- source/evidence ledger와 URL·release date·license note
- public actual raw snapshot·document ID·hash
- synthetic test fixture specification·seed·known shock — 계산 test가 있을 때만
- metric dictionary·COA/management mapping
- public target/guidance·analyst plan·forecast·scenario version register
- driver tree·assumption register
- integrated operating schedule와 P&L·BS·CF·cash model
- public-actual-to-analyst-plan / public-actual-to-prior-forecast variance bridge
- reforecast와 scenario·risk/opportunity register
- action/decision log
- validation·benchmark·review finding·limitation report
- management dashboard·decision memo
- handover·change log·read-only release snapshot

### 16.2 선택 산출물

- interactive dashboard
- automated refresh pipeline
- English executive summary
- role-specific memo
- 공개 가능한 sample dataset
- interaction이 중요한 경우의 demo

선택 산출물은 관련 직무 증거를 새로 추가할 때만 만든다. 형식·개수·분량은 품질기준이 아니다.

### 16.3 Logical folder mapping

```text
p2_fpa_system/
├─ README.md
├─ scope_decisions/
├─ sources_public_actual/
├─ access_license_register/
├─ synthetic_test_fixtures/
├─ mappings_metric_dictionary/
├─ planning_versions/
├─ model_integrated_financials/
├─ variance/
├─ reforecast_scenarios/
├─ decisions_actions/
├─ dashboard_memo/
├─ validation_review/
├─ controls_change_handover/
└─ release_snapshot/
```

폴더명은 구현 예시다. 기존 작업환경에 맞게 바꿀 수 있으나 lineage와 immutable vintage는 유지한다.

---

## 17. 관련 직무별 변형

특정 회사용 새 프로젝트를 만들지 않는다. 같은 P2 core에서 역할별로 증거 순서와 decision view만 바꾼다.

| 관련 직무 | 먼저 보여줄 내용 | 심화 내용 |
|---|---|---|
| FP&A·Corporate Finance | integrated plan, variance, reforecast, P&L·BS·CF | assumption governance, business partnering, scenario |
| BizOps·CEO Staff | driver tree, proposed role, recommended action, management memo | cross-functional dependency, decision trigger, operating cadence |
| Treasury·Liquidity | working capital, cash bridge, funding need | liquidity stress, collection/payment action |
| Credit·Risk | downside driver, cash coverage, reforecast bias | covenant·funding·loss stress — 데이터가 허용할 때 |
| 금융사 전략·Fintech | volume·take rate/yield·loss·funding economics | risk/control cost, scenario, scale/stop condition |
| Equity/Credit RA | actual-to-forecast bridge와 earnings driver | forecast revision, quality of earnings, cash conversion |

P2는 FP&A core를 유지한다. M&A valuation이나 credit underwriting 전체를 억지로 포함하지 않고, 필요한 경우 P3·P4로 분리한다.

---

## 18. 이력서·면접 표현

### 18.1 이력서 한 줄 구조

`개인 프로젝트 + 민간 access class·범위 + driver/statement/variance/reforecast 작업 + 검증 방식 + 공개 가능한 결과·한계`

공식 공개자료 core 예시:

> 민간이 재확보 가능한 공시·IR·거래소·거시자료만으로 금융서비스 operating driver를 P&L·BS·CF에 연결하고, public actual 대비 prior analyst forecast의 variance·reforecast·cash/action pack을 제작; 발표일 vintage, source·version·cash reconciliation과 독립 review를 수행.

합성 test fixture를 함께 쓴 경우:

> 공식 공개자료 기반 분석모델과 별도의 synthetic test fixture를 분리하고, 알려진 PVM·working-capital shock에서 exact reconciliation·version integrity를 검증; synthetic 결과는 실제 기업의 세부실적·예측력 근거로 사용하지 않음.

### 18.2 면접 구조

1. 왜 이 decision과 민간 access policy·source를 선택했는가
2. public target/guidance·analyst plan·forecast·public actual을 어떻게 분리했는가
3. 어떤 driver를 왜 선택·제외했는가
4. variance convention이 어떻게 total과 reconcile되는가
5. reforecast가 무엇을 바꿨고 cash·action에 어떤 의미인가
6. 어떤 test·benchmark·review가 실패했고 어떻게 수정했는가
7. 민간 공개데이터의 grain·release lag와 합성 test 때문에 무엇을 주장할 수 없는가

### 18.3 피해야 할 표현

- 합성데이터인데 `실적개선`
- 실제 사용자가 없는데 `경영진 도입`
- simulation인데 `비용 절감`
- target을 forecast로 둔 뒤 `달성 가능성 검증`
- dashboard만 만들고 `FP&A 시스템 구축`
- 공개자료로 만든 가상 case인데 `회사 예산 수립`
- 혼자 만든 프로젝트인데 `cross-functional team 리드`
- 모델 추정치를 `확정 전망`으로 표현

대신 다음처럼 말한다.

- `민간이 확보 가능한 공식 공개자료 기준으로 설계했다`
- `versioned forecast와 variance identity를 구현했다`
- `조건부 scenario와 action trigger를 제안했다`
- `known-shock·reconciliation·outcome test를 수행했다`
- `회사 내부 budget·세부 ledger·행동결과가 없어 적용범위를 제한했다`

---

## 19. 첫 실행 체크리스트

- [ ] intended user·decision·as-of date·prohibited use를 한 문장으로 적는다.
- [ ] 모든 source의 access class·URL·release date·license를 기록한다.
- [ ] business archetype 후보에 Gate A–G를 적용한다.
- [ ] 공식 공개자료 한 grain·period의 raw → mapping → statement pilot을 수행한다.
- [ ] public target/guidance·analyst plan·forecast·scenario·public actual semantic을 고정한다.
- [ ] version_id·as_of·origin·publication status·currency·unit key를 만든다.
- [ ] metric dictionary와 COA/management mapping 초안을 만든다.
- [ ] key driver 후보의 public availability·relationship·analysis owner·range를 시험한다.
- [ ] operating schedule을 P&L·BS·CF·cash에 연결한다.
- [ ] analyst plan과 initial analyst forecast snapshot을 freeze한다.
- [ ] public actual을 ingest하고 synthetic test fixture는 별도 namespace에 둔다.
- [ ] public actual vs analyst plan과 public actual vs prior analyst forecast를 분리한다.
- [ ] variance convention과 exact-additivity check를 만든다.
- [ ] residual·timing·scope·data issue를 표시한다.
- [ ] 새 assumption으로 reforecast version을 생성한다.
- [ ] risk/opportunity, proposed role, recommended action, trigger를 연결한다.
- [ ] benchmark·metric·review 범위를 사용 전에 선언한다.
- [ ] release gate reviewer와 공개 snapshot 범위를 정한다.

첫날 목표는 dashboard를 그리는 것이 아니다. `민간이 다시 확보할 수 있는 공개 source로 version·data grain·driver·재무연결을 끝까지 검증할 수 있는 case를 확정하는 것`이다.

---

## 20. 참고문헌

### FP&A·planning·business partnering

- [AFP — What is FP&A?](https://fpacert.financialprofessionals.org/certification/what-is-fp-a)
- [AFP — FPAC Test Specifications 2025B–2031A](https://fpacert.financialprofessionals.org/exam/specifications)
- [AFP — Guide to Driver-based Models and Plans](https://www.financialprofessionals.org/training-resources/resources/guides/fp-a-guides/Detail/driver-based-modelling)
- [AFP — 8 Steps for Creating a Rolling Forecast](https://www.financialprofessionals.org/training-resources/resources/articles/Details/8-steps-for-creating-a-rolling-forecast)
- [AFP — Guide to Implementing Rolling Forecasts](https://www.afponline.org/docs/default-source/default-document-library/pub/2015-fp-a-guide-to-implementing-rolling-forecasts-1.pdf?sfvrsn=7c7e466b_2)
- [AFP — Finance Business Partnering](https://www.financialprofessionals.org/glossary/finance-business-partnering)
- [AFP — Our Favorite Financial Analyses](https://www.financialprofessionals.org/training-resources/resources/articles/Details/our-favorite-financial-analyses)
- [AICPA & CIMA — Global Management Accounting Principles](https://www.aicpa-cima.com/resources/download/gmap-global-accounting-principles)
- [AICPA & CIMA — Strategic Resource Management with Integrated Performance Management](https://www.aicpa-cima.com/professional-insights/article/strategic-resource-management-with-ipm)

### 기업전망·재무·운전자본

- [CFA — Introduction to Financial Statement Modeling](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/introduction-to-financial-statement-modeling)
- [CFA — Company Analysis: Forecasting](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/company-analysis-forecasting)
- [CFA — Working Capital and Liquidity](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/working-capital-and-liquidity)
- [CFA — Financial Analysis Techniques](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/financial-analysis-techniques)
- [IFRS — IAS 1 Presentation of Financial Statements](https://www.ifrs.org/issued-standards/list-of-standards/ias-1-presentation-of-financial-statements.html/)
- [IFRS — IAS 7 Statement of Cash Flows](https://www.ifrs.org/issued-standards/list-of-standards/ias-7-statement-of-cash-flows/)

### Spreadsheet·모델 검증

- [ICAEW — Twenty Principles for Good Spreadsheet Practice](https://www.icaew.com/technical/technology/excel-community/20-principles-for-good-spreadsheet-practice-2024-edition)
- [Federal Reserve — SR 26-2 Model Risk Management](https://www.federalreserve.gov/frrs/guidance/supervisory-guidance-on-model-risk-management.htm)
- [Federal Reserve — SR 26-2 발행문·적용범위](https://www.federalreserve.gov/supervisionreg/srletters/SR2602.htm)
- [Hyndman & Koehler (2006), Another look at measures of forecast accuracy](https://doi.org/10.1016/j.ijforecast.2006.03.001)
- [Tashman (2000), Out-of-sample tests of forecasting accuracy](https://doi.org/10.1016/S0169-2070(00)00065-0)

### 공개데이터 후보

- [OpenDART](https://opendart.fss.or.kr/intro/main.do)
- [KIND 회사별 공시검색](https://kind.krx.co.kr/disclosure/searchdisclosurebycorp.do?method=searchDisclosureByCorpMain)
- [KRX Data Marketplace](https://data.krx.co.kr/contents/MDC/MAIN/main/index.cmd)
- [금융위원회 — 금융공공데이터 개방](https://www.fsc.go.kr/in060000)
- [공공데이터포털 — 금융위원회 기업기본정보 API](https://www.data.go.kr/dataset/15043184/openapi.do)
- [한국은행 ECOS](https://ecos.bok.or.kr/api/)
- [KOSIS OpenAPI](https://sso.kosis.kr/serviceInfo/openAPIGuide.do)
- [SEC EDGAR Search & APIs](https://www.sec.gov/search-filings)
- 분석대상 회사의 공식 IR·earnings release·공개 KPI·가격표·product document

금융위원회는 금융공공데이터가 기업정보, 공시정보, 금융회사정보, 자본시장정보, 금융회사통계정보, 시세정보와 금융상품기본정보 등을 Open API로 제공한다고 설명한다. 개별 API의 이용허락범위는 서로 다를 수 있으므로 source register에서 유형과 상업적 이용·변경·출처표시 조건을 개별 확인한다.

---

## Disclaimer

이 문서는 관련 직무와 금융 도메인 역량을 위한 개인 프로젝트 설계서다. 특정 지원회사와 무관하며 실제 조직의 내부 budget·forecast·성과를 나타내지 않는다. Core 분석은 분석대상 회사와의 고용·계약·감독관계 없이 민간이 합법적으로 확보할 수 있는 공식 공개자료로만 완결한다. 상용자료는 license 범위의 선택 cross-check이며, 합성자료는 계산·통제 test fixture로만 사용한다. 결과는 투자·회계·세무·법률 자문이 아니며 모든 판단은 기준일 당시 공개정보, 명시된 analyst assumption, 알려진 데이터·모델 한계에 한정된다.
