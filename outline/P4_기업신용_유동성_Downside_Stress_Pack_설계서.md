# P4 설계서: 기업신용·유동성·Downside Stress Pack

> **통합 상태 — 2026-09-01**  
> 이 문서는 M3 **Credit, Liquidity & Claims 상세 annex**로 보존한다. source·rights·vintage, historical operating/financial spine, common cash·funding·scenario와 governance는 [P0 통합 마스터 설계서](P0_통합_기업재무_의사결정_시스템_마스터_설계서.md)를 우선한다. P4 고유의 obligor·instrument·covenant·refinancing·claim·recovery·rating/spread lens와 credit release gate는 독립적으로 유지한다.

> **핵심 질문:** 어떤 조건에서 차입자의 원리금 지급능력이 훼손되며, 조달·차환·담보·청구권 구조를 반영한 하방과 monitoring trigger는 무엇인가?

| 항목 | 정의 |
|---|---|
| 문서 버전 | P4 v1.0 |
| 작성일 | 2026-09-01 |
| Analysis cutoff | 대상 case 선정 전; 실제 분석마다 별도 timestamp 고정 |
| 설계 상태 | 공식 reference 기반 구현 설계 · 대상 case 선정 전 |
| 기본 범위 | 기업 obligor의 공개자료 기반 desktop credit analysis; 비금융 일반기업은 core example, 금융·REIT·PF는 sector-appropriate overlay |
| 기본 독자 | CEO Staff·Strategy RA, Credit RA, 대출심사·기업금융, Credit Risk, 채권 리서치, Treasury, FP&A |
| 핵심 산출물 | credit memo, debt·facility register, 통합 현금·debt-service model, joint/reverse stress, covenant monitor, illustrative recovery range |
| 사용 경계 | 개인 포트폴리오와 학습용 분석이며 실제 대출승인·등급부여·법률의견·투자권유가 아님 |

---

## 0. 설계 원칙

### 0.1 사용자 전제

1. 이 프로젝트는 특정 지원기업의 채용 과제에 종속되지 않는다. 관련 직무와 금융 도메인에서 재사용 가능한 개인 프로젝트다.
2. 정규직 전환을 전제로 하지 않는다. 프로젝트의 가치는 근무기간이 아니라 재현 가능한 판단 과정, 증거 규율, 계산 무결성으로 증명한다.
3. FinDone은 사용자가 자신을 위해 만든 제품이다. 외부 고객 수, 전환율, 매출, 검증된 product-market fit을 만들거나 암시하지 않는다.
4. core 분석은 민간 개인이 합법적으로 확보 가능한 무료 공개자료만으로 완결한다.
5. 상용 데이터는 개인 구독·라이선스·파생물 이용이 허용될 때만 선택적 cross-check로 쓴다. 접근하지 못한 상용 수치를 추정해 채우지 않는다.
6. 합성데이터는 계산·통제의 known-answer test에만 쓴다. 실제 기업의 사실, 검증 결과, 신용 증거로 쓰지 않는다.
7. 고정 DSCR, 레버리지, 최소현금, shock, 회수율, 등급 문턱을 보편 기준으로 발명하지 않는다. 실제 계약, 적용 가능한 공식 방법론, 공개 역사, 공식 시나리오 또는 reverse-stress switching value로 결정한다.
8. 공개자료가 부족하면 결론을 약하게 만드는 것이 아니라 결론의 범위를 줄인다. 필요한 정보가 없을 때의 정답은 <code>NOT_TESTABLE_FROM_PUBLIC_DATA</code>, <code>INSUFFICIENT_PUBLIC_EVIDENCE</code> 또는 <code>WITHHELD</code>일 수 있다.
9. 외부 등급과 스프레드는 관측치다. 독립 분석의 결론을 대신하지 않는다.
10. P4는 실제 차입자 접촉, 비공개 은행시설, data room, 담보권 perfection 확인, 법률 due diligence 없이 수행하는 public-desktop pack이다.

### 0.2 제거한 임의 기준

| 임의 기준 | 왜 제거하는가 | 대체 기준 |
|---|---|---|
| “Debt/EBITDA가 특정 배수 이하면 안전” | 업종, 회계정의, 변동성, 만기, 담보, 금리, cash conversion을 무시 | 회사별 cash generation, 실제 만기·약정, 공개 역사, reverse stress |
| “DSCR이 특정 숫자 이상이면 승인” | CFADS와 debt service 정의가 계약·목적마다 다름 | 목적별 metric dictionary와 기간별 cash trough |
| “현금은 매출의 일정 비율” | 운영현금 수요는 결제주기·급여·계절성·규제에 따라 다름 | 공개 운전자본 경로, 관측된 trough, 계약상·운영상 제약 |
| “base/downside는 매출 일정 비율 하락” | 사업 driver 간 상호작용과 실제 역사에 무관 | 회사·산업 역사, 공식 거시자료, 공개 principal risk, switching value |
| “만기는 자동 차환” | 시장폐쇄, 가격, 담보, 약정, 실행시점을 무시 | committed source와 uncommitted refinancing을 분리 |
| “공시상 covenant compliant면 headroom도 충분” | 계약 정의와 실제 계산값을 알 수 없음 | 원문과 구성요소가 있을 때만 계산; 아니면 미산출 |
| “담보부는 회수율이 높다” | 담보 범위·가치·선순위·비용·관할법을 무시 | 법인·자산·lien·claim별 공개증거 기반 waterfall |
| “외부 등급을 PD로 변환” | scale·기간·방법론·agency·issuer/issue가 다름 | 원 관측치 보존, 같은 기관의 공개 방법론이 있을 때만 제한적 해석 |
| “스프레드는 순수 부도확률” | 유동성, 옵션, risk premium, 기술적 수급 포함 | 동일 통화·만기·선순위·옵션 비교와 신호 분해 |
| “회수율 haircut 또는 multiple 고정” | 자산·관할·사이클·구조와 무관 | 공개 거래·운영·자산 근거의 범위와 switching analysis |
| “은행도 일반기업 EBITDA framework” | 예금·이자·차입·규제자본의 경제적 성격이 다름 | 금융회사 전용 overlay 또는 scope 제외 |

### 0.3 판단 라벨과 주장 태그

모든 중요한 문장·숫자·결정은 최소 하나의 근거 라벨을 가진다.

| 라벨 | 의미 | 예시 |
|---|---|---|
| [STD] | 법령·회계기준·공식 방법론 | IFRS 7 만기분석의 성격 |
| [PROPRIETARY_METHODOLOGY_REFERENCE] | 공개 locator가 있는 상업기관 방법론 참고 | edition·scope·rights를 기록한 rating criteria |
| [EVID] | 원문 공시·계약·시장 관측 | 공시된 만기, 실제 TRACE 거래 |
| [USER] | 사용자가 정한 목적·제약 | 민간 접근가능 데이터만 사용 |
| [CALC] | 공개 input으로 재현한 계산 | debt roll-forward, cash trough |
| [JUDG] | analyst 판단 | stress driver, 조건부 결론 |

주장의 성격도 분리한다.

| 태그 | 의미 |
|---|---|
| [F] | Fact: 기준시점에 공개된 사실 |
| [D] | Derived: 사실에서 기계적으로 산출 |
| [A] | Assumption: 미래·미관측 input |
| [I] | Interpretation: 의미 해석 |
| [R] | Recommendation: 조건부 판단 |
| [M] | Measured: formula test·재현시간·오류율처럼 본 프로젝트에서 직접 측정한 값 |

<code>[MODEL]</code>은 근거 라벨이나 주장 태그가 아니라 자체 정의 metric의 namespace다. 외부기관의 동명 metric과 혼동을 막기 위해 쓰며, 실제 input과 판단에는 위 라벨·태그를 별도로 붙인다.

Owner 표기는 다음으로 제한한다.

- <code>analysis_owner</code>: 개인 프로젝트 작성자
- <code>reviewer</code>: 모델·가정을 독립적으로 challenge하는 검토자
- <code>proposed_accountable_role</code> 또는 <code>proposed_monitoring_role</code>: 공개 조직정보와 일반 직무범위에 근거한 제안

분석대상 회사의 실제 내부 책임배정·승인권자는 공식 공개자료로 확인되지 않는 한 [F]가 아니다.

금지 예:

- “[F] 이 회사의 covenant headroom은 충분하다” — 계약 정의와 input이 없으면 쓸 수 없다.
- “[D] 외부등급을 이용한 내부 PD는 X%다” — 같은 scale·기간의 권위 있는 mapping과 이용권한이 없으면 쓸 수 없다.
- “[R] 실제 대출을 승인한다” — P4의 권한·정보범위를 넘는다.

허용 예:

- “[EVID][F] 회사는 원문 공시에서 보고일 현재 covenant 준수라고 밝혔다.”
- “[CALC][D] 공개된 계약 정의와 공시 구성요소로 계산한 headroom은 기준시점에 양수다.”
- “[JUDG][R] 공개자료 기반 개인 분석에서는 조건 A와 B가 충족될 때만 acceptable로 분류한다.”

---

## 1. 기준 문헌과 적용 범위

### 1.1 핵심 기준

| 영역 | 기준·공식 자료 | P4에서 쓰는 범위 |
|---|---|---|
| 기업 신용분석 | [CFA Institute, Credit Analysis for Corporate Issuers](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/credit-analysis-for-corporate-issuers) | business·industry·governance, profitability·liquidity·leverage·coverage, issuer와 issue risk 분리 |
| 신용위험 | [CFA Institute, Credit Risk](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/credit-risk) | PD·LGD·EAD 개념과 expected loss 사용 경계 |
| 신용모형 | [CFA Institute, Credit Analysis Models](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/credit-analysis-models) | structural·reduced-form·transition·spread model의 한계 이해 |
| 현금흐름표 | [IFRS Foundation, IAS 7](https://www.ifrs.org/issued-standards/list-of-standards/ias-7-statement-of-cash-flows/) | CFO·CFI·CFF와 현금 대사 |
| 금융상품 측정 | [IFRS Foundation, IFRS 9](https://www.ifrs.org/issued-standards/list-of-standards/ifrs-9-financial-instruments/) | effective interest, carrying amount, modification·derecognition의 회계 bridge |
| 유동성 공시 | [IFRS Foundation, IFRS 7](https://www.ifrs.org/issued-standards/list-of-standards/ifrs-7-financial-instruments-disclosures/) | liquidity risk, undiscounted contractual maturity, risk disclosure |
| 분류·covenant | [IFRS Foundation, IAS 1](https://www.ifrs.org/issued-standards/list-of-standards/ias-1-presentation-of-financial-statements/) | current/non-current와 covenant disclosure 해석 |
| 리스 | [IFRS Foundation, IFRS 16](https://www.ifrs.org/issued-standards/list-of-standards/ifrs-16-leases/) | lease liability와 cash/coverage의 대칭 조정 |
| 충당·우발 | [IFRS Foundation, IAS 37](https://www.ifrs.org/issued-standards/list-of-standards/ias-37-provisions-contingent-liabilities-and-contingent-assets/) | provision·contingent liability의 공개 한계 |
| supplier finance | [IFRS Foundation, Supplier Finance Arrangements amendments](https://www.ifrs.org/news-and-events/news/2023/05/iasb-increases-transparency-of-companies-supplier-finance/) | reverse factoring의 조건·금액·due-date·유동성 위험 |
| 미국 유동성 설명 | [SEC Regulation S-K Item 303](https://www.ecfr.gov/current/title-17/chapter-II/part-229/subpart-229.300/section-229.303) | 단기·장기 liquidity, material cash requirements, known trends |
| 미국 계약문서 | [SEC Regulation S-K Item 601](https://www.ecfr.gov/current/title-17/chapter-II/part-229/subpart-229.600/section-229.601) | indenture·material contract exhibit 탐색과 누락 가능성 |
| 미국 filing API | [SEC EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) | submissions·XBRL facts의 무료 수집과 원문 대사 |
| 한국 공시 | [금융감독원 OpenDART](https://opendart.fss.or.kr/guide/main.do) | 정기·수시공시와 API, 접수번호·정정 이력 |
| 한국 시장공시 | [KRX KIND](https://kind.krx.co.kr/main.do?method=loadInitPage&scrnmode=1) | 상장법인·채권 관련 공시의 원문 확인 |
| 한국 채권시장 | [KRX 정보데이터시스템](https://data.krx.co.kr/contents/MDC/MAIN/main/index.cmd) | 이용조건 확인 후 종목·가격·수익률 관측 |
| 미국 채권거래 | [FINRA, What Is TRACE?](https://www.finra.org/investors/insights/what-is-TRACE) | 체결 가격·수익률·거래량의 성격과 quote와의 차이 |
| 시장 data rights | [FINRA, About Corporate and Agency Bond Data](https://www.finra.org/finra-data/fixed-income/about-cna-data) | 비상업적 이용·과거자료·약관 확인 |
| stress 기법 | [UK FRC, Guidance on the Going Concern Basis of Accounting](https://www.frc.org.uk/library/standards-codes-policy/accounting-and-reporting/annual-corporate-reporting/guidance-on-going-concern-basis/) | severe-but-plausible·sensitivity·reverse stress의 기법 참고 |
| switching value | [HM Treasury, The Green Book 2026](https://www.gov.uk/government/publications/the-green-book-appraisal-and-evaluation-in-central-government/the-green-book-2026) | 과도한 정밀도 경계와 switching-value 기법 참고 |
| 미국 담보·우선권 | [11 U.S.C. §506](https://uscode.house.gov/view.xhtml?edition=prelim&num=0&req=granuleid%3AUSC-prelim-title11-section506), [§507](https://uscode.house.gov/view.xhtml?req=%28title%3A11+section%3A507%28a%29+edition%3Aprelim%29) | secured claim과 법정 우선권의 case-specific 확인 |
| 한국 도산법 | [국가법령정보센터, 채무자 회생 및 파산에 관한 법률](https://www.law.go.kr/법령/채무자회생및파산에관한법률) | 회생담보권·재단채권·별제권 등 현행 조문 확인 |
| spreadsheet 통제 | [ICAEW, 20 Principles for Good Spreadsheet Practice](https://www.icaew.com/technical/technology/excel-community/20-principles-for-good-spreadsheet-practice-2024-edition) | input·calculation·output 분리와 review 가능성 |
| model risk | [Federal Reserve, SR 26-2 Model Risk Management](https://www.federalreserve.gov/frrs/guidance/supervisory-guidance-on-model-risk-management.htm) | 목적·한계·독립적 검토·ongoing monitoring의 참고 |

### 1.2 적용상 주의

- CFA 자료는 전문 학습체계다. 특정 회사의 승인 기준이나 rating methodology로 가장하지 않는다.
- IFRS는 적용 회계기준과 공시를 해석하는 기준이다. 회사가 US GAAP 또는 다른 기준을 쓰면 해당 기준과 원문을 우선한다.
- FRC와 Green Book은 stress·uncertainty 기법의 참고다. 한국·미국 기업에 대한 법적 의무로 표현하지 않는다.
- SEC·EDGAR API의 standardized XBRL fact는 custom tag, footnote, exhibit의 계약조건을 모두 담지 못한다. 항상 원문 filing과 대사한다.
- OpenDART API 추출치는 원문 전체가 아니며 정정·첨부문서를 놓칠 수 있다. 접수번호와 원문을 보존한다.
- FINRA TRACE는 actual trade이지 현재 bid/ask quote가 아니다. 거래가 드문 채권의 오래된 체결을 현재 조달비용으로 쓰지 않는다.
- KRX·FINRA·rating agency·지수 제공자의 저장·가공·재배포 약관은 사용 시점에 별도 확인한다.
- 법령 인용은 구조를 이해하기 위한 출발점이다. 담보권 유효성, perfection, 상계, 보증 집행, 절차별 배분은 법률의견이 필요할 수 있다.
- Fed model-risk guidance는 규제대상 기관에 대한 감독지침이다. P4는 그 원칙을 개인 프로젝트의 통제 참고로만 사용한다.

---

## 2. 프로젝트 목적과 핵심 질문

### 2.1 목적

P4의 목적은 “부채비율이 높다/낮다”는 요약이 아니다. 아래 chain을 공개자료만으로 재현한다.

<code>사업과 거버넌스 → 현금창출 → debt·facility·maturity → liquidity·debt service → covenant·refinancing → joint/reverse stress → claim·recovery → rating·spread 비교 → 조건부 credit memo·monitoring</code>

분석자는 세 가지 축을 섞지 않는다.

1. **Issuer capacity:** 차입자 또는 그룹이 약정대로 지급할 능력.
2. **Instrument loss severity:** 특정 채무상품이 default 시 받을 수 있는 가치와 시점.
3. **Market pricing:** 시장가격이 반영하는 default 외 유동성·옵션·risk premium.

### 2.2 핵심 의사결정 질문

> 정의된 기준시점과 법적 채무자·채무상품에 대해 base, evidence-backed downside, reverse stress에서 회사가 최소 운영현금, 현금이자, 원금, 실제 약정, 만기 요구를 충족하는가? 실패한다면 최초 실패시점·필요 유동성·반전변수는 무엇이며, 해당 상품의 공개정보 기반 downside/recovery 범위와 monitoring trigger는 무엇인가?

분석 시작 전에 아래를 고정한다.

| 필드 | 질문 |
|---|---|
| decision perspective | 은행 대출심사, 채권 투자, corporate treasury, counterparty risk 중 무엇인가 |
| obligor | 실제 원리금 지급의무를 지는 법인은 누구인가 |
| instrument | 어느 대출·사채·리스·보증·facility를 분석하는가 |
| loss object | missed payment, covenant breach, liquidity shortfall, mark-to-market loss 중 무엇인가 |
| as-of | 어떤 공개시점까지의 정보만 쓰는가 |
| horizon | 어떤 만기·put·covenant·운영주기를 포함해야 하는가 |
| currency | 기능통화, 표시통화, 원리금 통화는 무엇인가 |
| jurisdiction | 발행자·담보·계약·도산 절차의 관할은 어디인가 |
| decision authority | 개인 모의 분석인지 실제 권한 있는 심사인지 |

### 2.3 의사결정 상태

P4는 “승인/거절”을 실제 금융기관의 권한처럼 표현하지 않는다. 실제 mandate, decision policy, risk tolerance가 명시된 모의 case에서만 조건부 support/no-support로 mapping한다. 그 정보가 없으면 아래처럼 모델 조건 충족 상태만 보고한다.

| 상태 | 의미 |
|---|---|
| MODEL_CONDITIONS_MET | 공개증거와 정의된 stress에서 선언한 지급·유동성 조건을 충족 |
| MODEL_CONDITIONS_MET_IF | 명시한 선행조건·보호조항·가격·규모가 충족될 때만 모델 조건 충족 |
| MONITOR_BOUNDARY | 현재 모델 조건은 충족하나 가까운 trigger가 상태를 바꿀 수 있음 |
| MODEL_CONDITIONS_NOT_MET | 정의한 stress에서 하나 이상의 선언된 조건을 충족하지 못함 |
| INSUFFICIENT_PUBLIC_EVIDENCE | 판단에 필수인 공개증거가 없음 |

상태는 관점·상품·declared policy에 종속된다. 같은 회사라도 senior secured lender, unsecured bondholder, equity investor의 결론이 다를 수 있다. risk appetite가 없으면 “감수 가능한 범위”를 임의로 만들지 않는다.

### 2.4 하지 않을 것

- 실제 은행 내부등급, regulatory PD/LGD, 승인결재를 모방하지 않는다.
- 외부 rating을 자체 rating처럼 복사하거나 agency-equivalent/implied rating을 주장하지 않는다.
- 공개되지 않은 covenant formula, collateral perfection, borrowing-base availability를 채우지 않는다.
- expected loss를 계산하기 위해 PD·LGD·EAD를 임의로 만들지 않는다.
- 만기 차환, 자산매각, 증자, sponsor support를 자동으로 성공한다고 가정하지 않는다.
- negative EBITDA를 음수 leverage라는 유리한 숫자로 보여주지 않는다.
- 연결재무제표의 자산을 모든 채권자가 동일하게 청구할 수 있다고 보지 않는다.
- book value를 담보 회수액으로 자동 사용하지 않는다.
- 유동성 부족, covenant breach, event of default, insolvency, bankruptcy를 동의어로 쓰지 않는다.
- hindsight로 과거 신용결정을 재작성하지 않는다.

---

## 3. 민간 접근가능 데이터와 case 선정

### 3.1 민간 접근가능성의 정의

| Access class | 정의 | 기본 처리 |
|---|---|---|
| A — free official public | 정부·규제기관·법령·공식통계의 무료 공개자료 | core 후보; 저장·가공·재배포 권리는 별도 판정 |
| B — free issuer public | 회사 홈페이지, 감사보고서, IR, prospectus, 공개 계약·공시 | core 후보; 원문 전체 재배포 권리는 별도 판정 |
| C — free-view/restricted public | 거래소·시장 인프라 등 무료 조회가 가능하지만 저장·가공·재배포 조건이 별도인 자료 | restricted supplement; 허용된 locator·최소 파생값만 |
| D — paid private subscription | 개인이 합법적으로 구독 가능 | 선택 cross-check만 |
| E — permissioned/non-public | 고용주 시스템, lender portal, data room, NDA, 규제 보고 원본 | 금지 |
| F — synthetic | 인공 case·수치 | 계산 테스트에만 허용 |

접근가능성, 비용, 저장·가공·재배포 권리는 서로 다른 축이다. “웹에서 보인다” 또는 “무료 조회된다”는 것만으로 core 저장·재배포 권한이 생기지 않는다. 각 source에 access, retention, transformation, redistribution 권리를 기록하고, 필요한 권리가 확인된 자료만 core input으로 release한다.

### 3.2 core에서 제외하는 자료

- 은행 내부 facility statement와 covenant certificate
- confidential information memorandum, lender presentation, data room
- non-public borrowing base, collateral appraisal, lien search, account control agreement
- sponsor support letter 또는 guarantee의 비공개 원본
- 임직원 전용 KPI, treasury forecast, cash pooling 제한
- regulator-only capital·liquidity return
- 비공개 rating committee material
- 불법 복제한 paywalled report·historical feed
- 개인식별정보, 계정 비밀키, 접근토큰

제외자료가 없어서 생기는 한계는 evidence ledger에 적는다. 가정으로 숨기지 않는다.

### 3.3 합성데이터의 제한된 역할

합성 case는 다음만 검증한다.

- opening debt + draw + PIK/FX/other − repayment = closing debt
- opening cash + operating/financing/investing/FX = closing cash
- max-type·min-type covenant headroom의 방향
- floating-rate reset과 hedge의 계산
- facility draw와 debt·interest·maturity의 동시 반영
- waterfall의 가치 보존과 pari passu pro rata
- management action의 선행조건·timing
- negative/zero denominator의 <code>NM</code> 처리

합성 test 결과를 “실제 기업 분석이 검증됐다”, “모델 정확도”, “회수율 적중”으로 표현하지 않는다.

### 3.4 공개데이터로 가능한 실행 모드

| Mode | 조건 | 허용 결론 |
|---|---|---|
| A — full public pack | 원문 재무·채무·만기·주요 계약이 충분하고, 시장자료는 있으면 rights-cleared supplement로 사용 | cash/debt stress, 일부 covenant, 제한적 recovery range; 시장자료가 없으면 NO_PUBLIC_MARKET_SIGNAL |
| B — cash and refinancing pack | 계약·담보 정보는 부족하나 재무·만기·조달은 충분 | 지급능력·유동성·차환 gap, covenant는 proxy 또는 미산출 |
| C — evidence-gap memo | 법인·채무·현금·계약 핵심이 불충분 | 필요한 정보, 관측 가능한 risk, withheld 결론 |

Mode C도 실패가 아니다. 공개정보 한계를 정확히 식별하는 것이 credit judgment의 일부다.

다만 Mode C는 유효한 feasibility/evidence-gap 산출물이지 §2의 full P4 credit pack 완성은 아니다. <code>coverage_state=FEASIBILITY_ONLY</code>로 표시하고 cash·covenant·recovery 결론을 완성본처럼 공개하지 않는다.

### 3.5 case archetype

아래는 순위가 아니라 candidate archetype이다. 실제 case는 §3.6 Gate A–H, 사용 목적, sector-appropriate method를 통과한 대상을 선택한다.

1. **상장 비금융사 + 공개 사채/대출:** 재무·만기·발행 당시 등급을 상대적으로 연결하기 쉽지만, 지속등급·거래 신호는 없거나 제한될 수 있다.
2. **현금흐름 변동성이 큰 회사:** revenue·margin·working capital·rate의 joint stress가 의미 있다.
3. **가까운 maturity wall 또는 대규모 refinancing:** 자금조달 가정과 cash timing을 보여준다.
4. **holdco/opco 또는 보증구조가 있는 회사:** structural subordination을 보여준다.
5. **담보부와 무담보 상품이 함께 있는 회사:** claim priority와 issue별 차이를 보여준다.
6. **신용 이벤트가 이미 종료된 historical case:** 당시 공개정보만으로 ex-ante pack을 만들고 outcome을 검증할 수 있다.

비금융 일반기업은 P4 core method의 기본 예시다. 은행·보험·NBFI·REIT·프로젝트파이낸스도 Gate와 §18 sector overlay를 먼저 충족하면 첫 case가 될 수 있으며, 비금융 framework를 선행 적용하지 않는다.

이미 종료된 신용사건은 outcome-known selection bias가 있다. 왜 그 case를 선택했는지 기록하고, 단일 case의 결과를 다른 기업·시기·업종으로 일반화하지 않는다.

### 3.6 비보상적 선정 Gate A–H

| Gate | 통과 질문 | 실패 시 |
|---|---|---|
| A — public rights | core source를 무료·합법적으로 접근·보존·인용 가능한가 | case 제외 또는 locator-only |
| B — as-of | 공개시각과 정정 이력을 고정할 수 있는가 | historical outcome 금지 |
| C — obligor | 법적 차입자·발행자·보증인을 식별 가능한가 | instrument 결론 제한 |
| D — cash | 현금흐름과 가용현금을 충분히 대사할 수 있는가 | cash capacity 미산출 |
| E — debt | principal·carrying amount·만기·금리를 구분 가능한가 | maturity/refi 결론 제한 |
| F — contract | 약정·담보·보증 핵심이 공개됐는가 | covenant/recovery 미산출 |
| G — stress | 핵심 driver와 역사·공식 anchor가 있는가 | reverse-only 또는 범위 제한 |
| H — outcome | 이후 공개결과를 같은 정의로 비교 가능한가 | outcome analysis 생략 |

Gate 실패를 다른 항목의 높은 점수로 상쇄하지 않는다.

### 3.7 case 선정 기록

~~~text
case_id:
case_title:
mode: A | B | C
decision_perspective:
obligor_legal_name:
instrument_id:
jurisdiction:
functional_currency:
debt_currency:
analysis_cutoff_timestamp:
horizon_end:
public_release_timestamp_known: yes | no
access_gates_A_to_H:
selected_reason:
excluded_alternatives:
known_limitations:
~~~

---

## 4. Credit object·법인·version semantic

### 4.1 분석 단위

| 객체 | 핵심 필드 |
|---|---|
| group | 연결범위, parent, 주요 segment |
| legal entity | 법인명, 관할, 소유관계, 자산·현금 위치 |
| obligor | 지급의무자, 계약·통화, 상환재원 |
| issuer | 증권 발행자; obligor와 다를 수 있음 |
| guarantor | 보증 범위, cap·조건·면책·만기 |
| collateral provider | 담보제공자, 자산, lien priority |
| instrument | principal, carrying amount, coupon, maturity, seniority, security |
| facility | commitment, drawn, LC, availability, borrowing base, maturity |
| claim | allowed amount, entity, priority, security, contingent status |

연결재무제표는 경제적 그룹의 출발점이지 법적 청구권 지도는 아니다.

### 4.2 관점

같은 숫자도 관점에 따라 의미가 다르다.

- **은행·대출심사:** 계약상 원리금, collateral, covenant, facility conditions.
- **채권투자:** issue price/yield, option, liquidity, seniority, recovery timing.
- **Treasury:** 전사 cash availability, maturity ladder, covenant, refinancing execution.
- **FP&A:** driver 변화가 cash/debt service와 capital allocation에 미치는 영향.
- **Counterparty risk:** exposure timing, netting·collateral, wrong-way risk; 별도 exposure module 필요.

P4는 한 case에서 주 관점을 하나 선택하고, 다른 관점은 appendix로 분리한다.

### 4.3 event taxonomy

| Event | 정의 | 혼동 금지 |
|---|---|---|
| cash shortfall | 모델상 필요한 시점의 가용현금 부족 | 법적 default와 동일하지 않음 |
| covenant breach | 공개된 실제 약정 계산이 threshold를 위반 | proxy breach와 구분 |
| draw stop | 조건 미충족으로 facility draw 불가 | commitment 총액과 구분 |
| payment default | 계약상 지급일에 원리금 미지급 | covenant breach와 구분 |
| event of default | 계약의 notice·cure·grace 후 정의 충족 | 즉시 acceleration과 구분 |
| acceleration | 채권자가 기한이익 상실을 실행 | EOD 존재만으로 자동 가정 금지 |
| insolvency | 적용 법률의 지급불능·과다채무 등 | 모델 cash gap과 구분 |
| restructuring | exchange, amend-and-extend, court process 등 | recovery date와 구분 |
| rating action | upgrade/downgrade/watch/outlook | default 또는 spread 이동과 구분 |

### 4.4 Version key

<code>case_id + perspective + obligor_id + instrument_id + cutoff_timestamp + scenario_version + model_version</code>

버전은 다음을 금지한다.

- 정정공시를 과거 cutoff에 소급해 사용
- 이후 rating·spread를 당시 정보처럼 사용
- 계약 amendment 이후 정의를 amendment 이전 test에 사용
- 같은 case의 현재 분석과 historical ex-ante outcome을 덮어쓰기

### 4.5 레이어 분리

| Layer | 내용 | 변경 규칙 |
|---|---|---|
| SOURCE | 원문·snapshot·hash·권리 | 불변 |
| FACT | 원문에서 추출한 값·문장 | 정정 시 새 version |
| NORMALIZED | 통화·단위·기간·scope 정규화 | rule version 기록 |
| MODEL | driver·cash·debt·stress 계산 | formula review 필요 |
| JUDGMENT | scenario·range·decision | 근거·owner·변경조건 |
| OUTCOME | 이후 실제 공개 결과 | ex-ante와 별도 저장 |

---

## 5. Source·evidence·license·vintage

### 5.1 Claim-specific source authority

모든 주장에 통하는 단일 source 순위는 두지 않는다. 어떤 source가 권위 있는지는 주장 유형, 관할, 효력일, 정정·amendment 상태에 따라 달라진다. 증거의 권위와 무료 접근·저장·가공·재배포 권리도 별도 판정한다.

| 주장 유형 | 우선 확인할 원문 | 대체 불가능한 이유 |
|---|---|---|
| 법적 권리·우선순위 | 기준시점의 적용 법령·법원명령·효력 있는 계약·amendment·intercreditor | 재무제표 요약만으로 집행가능성을 확정할 수 없음 |
| 회계 balance·cash flow | 당시 유효한 감사/검토 filing, 주석, restatement | 현재 API 값이나 IR 요약이 당시 원재무를 대체하지 않음 |
| 발행·만기·default event | 규제기관·거래소 filing과 계약상 notice, 해당 시 법원자료 | 보도기사의 사건일만으로 최초 공개시각·법적 상태를 확정할 수 없음 |
| issuer guidance·management action | 회사가 직접 무료 공개한 IR·release·transcript | 경영진 계획의 존재를 증명할 뿐 실행결과를 증명하지 않음 |
| 체결가격·수익률 | 권리 확인된 시장 인프라의 timestamped trade record | 회사 IR이나 평가가격은 실제 체결을 대체하지 않음 |
| 외부 rating | 해당 agency의 contemporaneous 공개 release와 scale 정의 | 제3자 표나 지연 history의 action date를 당시 공개로 볼 수 없음 |
| 데이터 이용권리 | 해당 source의 당시 이용조건·라이선스 | source의 공신력이 저장·재배포 권리를 자동 부여하지 않음 |

2차 자료는 원문 locator와 반대근거 탐색에 쓴다. 원문과 충돌하면 주장별 효력·scope·vintage를 대조하고, 어느 자료를 채택했는지 decision log에 남긴다. analyst judgment는 source가 아니라 별도 [JUDG] layer다.

### 5.2 Evidence/source ledger

~~~text
source_id:
claim_id:
source_class: official | issuer | contract | market | rating | secondary
publisher:
document_title:
document_type:
url:
accession_or_filing_id:
event_at:
reporting_period_end:
filed_or_released_at:
effective_date:
first_public_at:
public_time_basis: exact_source_timestamp | first_observed_capture | official_schedule_proxy | acceptance_proxy | date_only_next_session
timezone:
market_session_id:
revision_status: original | amended | restated | current
supersedes_id:
retrieved_at:
page_section_note:
quoted_words_if_needed:
analyst_paraphrase:
currency:
unit:
accounting_standard:
consolidation_scope:
original_file_hash_if_retention_permitted:
access_cost: free | paid | mixed
authentication: none | free_key | free_account | manual_ui
retention_right:
transformation_right:
redistribution_right:
commercial_use_right:
license_note:
terms_url:
terms_version:
terms_checked_at:
source_availability_capture:
cutoff_eligible: yes | no
availability_confidence:
~~~

모든 memo 숫자는 <code>claim_id → source_id → 원문 위치</code>로 역추적 가능해야 한다.

<code>first_public_at</code>이 없거나 cutoff보다 늦으면 해당 vintage에는 eligible하지 않다. “공개됐을 것”이라는 추정으로 unknown을 통과시키지 않는다.

### 5.3 Credit case register

~~~text
credit_case_id:
case_version:
perspective:
decision_question:
group_id:
primary_obligor_id:
instrument_id:
jurisdiction:
cutoff_timestamp:
horizon_start:
horizon_end:
base_currency:
publication_currency:
analysis_mode:
sector_overlay:
model_state:
personal_decision_state:
decision_policy_id:
limitation_state:
coverage_state: FULL_PUBLIC_PACK | LIMITED_PUBLIC_PACK | FEASIBILITY_ONLY
review_state: INDEPENDENTLY_REVIEWED | SELF_REVIEWED_LIMITED_USE
publication_state: RELEASED | WITHHELD
analysis_owner:
reviewer:
release_snapshot_hash:
~~~

### 5.4 Obligor·instrument register

~~~text
entity_id:
legal_name:
entity_type:
jurisdiction:
parent_entity_id:
restricted_group_status:
bankruptcy_remote_status_if_evidenced:
cash_pool_role:
upstream_restrictions:
obligor_for_instrument_ids:
guarantor_for_instrument_ids:
collateral_provider_for_ids:
public_evidence_ids:
unknown_fields:

instrument_id:
instrument_type:
legal_issuer_entity_id:
borrower_entity_id:
guarantor_entity_ids:
principal_currency:
face_principal:
carrying_amount:
fair_value_if_disclosed:
payoff_amount_if_disclosed:
issue_date:
maturity_date:
scheduled_amortization:
coupon_or_margin:
fixed_floating:
reference_rate:
floor_cap:
hedge_id:
put_call_convertible_terms:
seniority:
secured_status:
collateral_ids:
governing_law:
cross_default_or_acceleration:
source_ids:
~~~

face principal, 장부금액, fair value, market value, payoff amount는 서로 다른 필드다. 하나로 덮어쓰지 않는다.

### 5.5 Cash·facility·obligation register

| 객체 | 필수 필드 |
|---|---|
| cash account class | entity, currency, unrestricted/restricted/customer/regulatory/trapped, availability date |
| facility | lender-public label, commitment, drawn, LC, undrawn, committed/uncommitted, draw conditions |
| maturity | instrument, contractual principal date, put, mandatory amortization, balloon |
| interest | cash/accrual/PIK, reference curve, reset, margin, hedge, fees |
| lease | principal/carrying amount, cash classification, maturity, methodology inclusion |
| supplier finance | amount, financier-paid amount, due-date range, classification, duplication check |
| factoring/securitisation | recourse, derecognition, retained risk, cash proceeds, debt-like treatment |
| guarantee | guaranteed instrument, cap, expiry, trigger, contingent amount, entity |
| other obligation | pension, tax, ARO, deferred consideration, litigation, purchase commitment |

### 5.6 Covenant register

~~~text
covenant_id:
instrument_or_facility_id:
covenant_name:
type: maintenance | incurrence | springing | draw_condition
testing_entity_or_group:
test_frequency:
test_date:
measurement_period:
direction: maximum | minimum
exact_formula:
debt_definition:
cash_netting_definition:
ebitda_or_earnings_definition:
interest_or_fixed_charge_definition:
addbacks_and_caps:
step_up_or_step_down:
threshold:
springing_trigger:
baskets:
cure_or_equity_cure:
waiver_or_amendment:
notice_and_grace:
cross_default_effect:
effective_from:
source_ids:
public_testability: exact | partial | not_testable
proxy_definition_if_any:
~~~

공개된 “compliant” 문구와 계약상 headroom 계산을 별도 claim으로 둔다.

### 5.7 Collateral·guarantee·claim register

~~~text
claim_id:
creditor_class:
claim_entity_id:
instrument_id:
allowed_claim_basis:
principal:
accrued_amount:
contingent_amount:
currency:
priority_class:
contractual_subordination:
structural_subordination:
statutory_priority:
secured_status:
collateral_id:
guarantee_id:
intercreditor_terms:
setoff_or_netting:
jurisdiction:
source_ids:
legal_certainty: confirmed_public | partial_public | unknown

collateral_id:
asset_owner_entity_id:
asset_class:
asset_description:
included_in_going_concern_value:
lien_rank:
perfection_evidence:
valuation_date:
valuation_basis:
prior_liens:
enforcement_costs:
transfer_restrictions:
source_ids:

guarantee_id:
guarantor_entity_id:
guaranteed_instrument_id:
scope:
cap:
conditions:
expiry:
defences_or_limitations:
source_ids:
~~~

### 5.8 Rating·market observation

~~~text
observation_id:
instrument_id:
source:
observation_type: rating | outlook | watch | trade | price | yield | spread
agency_or_venue:
action_at:
executed_at:
reported_at:
corrected_at:
source_file_published_at:
first_public_at:
as_of_or_late_flag:
timezone:
issuer_or_issue:
global_or_national_scale:
local_or_foreign_currency:
rating_value:
action_type:
price_type:
yield_type:
benchmark_curve:
spread_type:
option_adjusted:
trade_volume:
staleness:
liquidity_note:
license_note:
cutoff_eligible:
~~~

### 5.9 Assumption·decision·change register

~~~text
assumption_id:
scenario_id:
driver:
value_or_path:
unit:
start_date:
end_date:
evidence_anchor_ids:
method: public_guidance | history | official_scenario | switching_value | judgment
analysis_owner:
rationale:
uncertainty:
decision_impact:
invalidate_when:
review_status:
reviewer:
version:
~~~

판단값에는 “왜 이 숫자인가”뿐 아니라 “어떤 공개사실이 나오면 바뀌는가”가 있어야 한다.

### 5.10 Cut-off와 vintage

1. published/filed/effective/retrieved timestamp를 분리한다.
2. 기준시점 이전에 실제 공개된 정보만 ex-ante model에 쓴다.
3. 공개시각을 알 수 없으면 cutoff 당일 자료를 제외하거나 다음 공개기간에 사용한다.
4. 정정·재작성은 새 vintage다. 과거 pack을 덮어쓰지 않는다.
5. rating history의 지연 공개 자료를 action date에 알고 있었던 것처럼 소급하지 않는다.
6. market observation은 거래·quote·valuation의 유형과 timestamp를 보존한다.
7. outcome 분석은 별도 outcome vintage에서 수행한다.

### 5.11 License·공개·재현성

- core workbook에는 해당 이용조건이 저장·가공·공개를 허용하는 input과, 이용조건이 명시적으로 허용하는 범위의 파생결과만 둔다.
- 화면의 값을 사람이 직접 옮겨 적거나 계산했다는 사실만으로 원자료·파생물의 라이선스 제한을 우회할 수 없다.
- 약관상 저장이 제한된 수치는 locator와 retrieval procedure만 남길 수 있다.
- 원문 전체 재배포가 금지되면 최소 인용, accession, 페이지·섹션, hash를 남긴다.
- 상용 cross-check를 제거해도 core 결론과 계산이 재현돼야 한다.
- 공개 artifact에는 API key, 개인식별정보, 비밀계약, 라이선스 제한 raw feed를 넣지 않는다.
- data license가 불명확하면 <code>QUARANTINED_SOURCE</code>로 격리하고 release에서 제외한다.

---

## 6. 모델 아키텍처와 통제

### 6.1 논리적 layer

| Layer | 파일·표 | 역할 |
|---|---|---|
| 00_README | 목적, as-of, 관점, 상태, 한계 | 사용자가 먼저 읽는 control page |
| 01_SOURCES | source·license·vintage ledger | 모든 사실의 출처 |
| 02_ENTITIES | group·obligor·guarantor·collateral map | 법적 scope |
| 03_FINANCIALS | 원재무·정규화·cash bridge | accounting-to-cash |
| 04_DEBT | instrument·facility·interest·maturity | 채무 우주 |
| 05_COVENANTS | actual definition·proxy·headroom | 계약상 제약 |
| 06_FORECAST | operating driver·3-statement·cash | base 경로 |
| 07_STRESS | downside·reverse·action ladder | failure path |
| 08_RECOVERY | legal-entity claims·waterfall | issue downside |
| 09_MARKET | rating·trade·spread observations | 외부 신호 |
| 10_MEMO | decision·conditions·triggers | 의사결정 산출물 |
| 11_CHECKS | reconciliation·known-answer·review | 통제 |
| 12_OUTCOME | 이후 공개결과 | ex-ante 검증 |

### 6.2 계산 흐름

1. cutoff와 source rights를 잠근다.
2. group·obligor·instrument·jurisdiction을 잠근다.
3. 원재무를 재현하고 cash·debt roll-forward를 대사한다.
4. debt-like item과 accessible cash를 목적별로 조정한다.
5. instrument·facility·maturity·interest schedule을 만든다.
6. business driver를 P&L·BS·cash에 연결한다.
7. cash available before debt service와 mandatory debt service를 정의한다.
8. 실제 공개 covenant만 계산한다.
9. base cash trough와 refinancing need를 계산한다.
10. joint downside와 reverse stress를 실행한다.
11. 법인·담보·보증 증거가 충분할 때만 recovery range를 실행한다.
12. rating·spread 관측과 독립 분석의 차이를 설명한다.
13. 조건부 memo와 monitoring action을 작성한다.
14. 독립 검토와 claim-level QA를 통과한 snapshot만 release한다.

### 6.3 Spreadsheet·code 구조

- raw input과 formula cell을 분리한다.
- 같은 경제적 정의는 한 번 계산하고 다른 sheet에서 참조한다.
- 숫자 상수는 formula 안에 숨기지 않고 source/assumption register에 둔다.
- 단위, 통화, 부호, 기간, entity scope를 각 열에 명시한다.
- manual override는 원값, override 값, 이유, analysis_owner, reviewer, timestamp를 모두 보존한다.
- scenario는 column 또는 explicit scenario key로 분리한다. formula 복사로 서로 다른 정의가 생기지 않게 한다.
- error를 0으로 치환하지 않는다. <code>UNKNOWN</code>, <code>NM</code>, <code>NOT_APPLICABLE</code>를 구분한다.
- workbook output을 memo에 수기 복사하지 않는다. release snapshot에서 자동 연결하거나 checksum을 대사한다.
- Python/R/SQL을 쓰더라도 사람이 원문과 핵심 formula를 검토할 수 있는 data dictionary와 audit output을 제공한다.

### 6.4 핵심 identity와 자동 check

| Check | Identity | 통과 조건 |
|---|---|---|
| reported cash | opening reported cash + CFO + CFI + CFF + FX/other − closing reported cash = 0 | source currency와 report currency에서 대사 |
| accessible cash | opening accessible cash + included cash inflows − included cash outflows − ending accessible cash = 0 | reported cash와 availability bridge로 연결 |
| debt face | opening face + draw/issue + PIK/FX/other − principal repayment = closing face | instrument 합계와 GL disclosure 대사 |
| debt carrying | opening carrying + new debt recognized + effective-interest expense + FX/other carrying change − cash coupon paid − carrying amount derecognized = closing carrying | cash paid와 derecognized carrying amount를 분리 |
| contractual cash interest | principal path × contract cash-rate function × day-count + periodic fee = gross cash interest/fee | benchmark floor/cap, all-in floor/cap, step/default margin 확인 |
| EIR·accrual·PIK | effective-interest expense, cash coupon, PIK, fee amortisation을 별도 bridge | cash와 accrual을 혼합하지 않음 |
| hedge cash flow | contractual debt cash flow와 hedge cash flow를 별도 산출 후 net view 연결 | notional·reset·maturity 불일치 확인 |
| maturity | instrument principal schedule 합계 = disclosed principal scope | IFRS 7 gross cash flow와 별도 |
| facility | commitment − drawn − LC − other usage = nominal undrawn | availability 조건 적용 전·후 분리 |
| cash availability | gross cash = Σ(unique cash-account balance); 계정마다 primary availability class 하나 | trapped·pledged·regulatory 등은 restriction-cause flag로 별도 |
| covenant | 공개된 계약 definition component 합계와 filing reconciliation | §14 testability state 범위에서만 |
| waterfall | distributed value + residual = available value | 음수·중복 없음 |
| claim | class distribution 합계 = instrument/claim distribution | 법인·통화 대사 |
| memo | memo 핵심숫자 = release snapshot | 완전 일치 |

### 6.5 Known-answer test

~~~text
Test D1 — debt roll-forward
opening face = 100
draw = 30
PIK = 5
repayment = 20
expected closing face = 115

Test C1 — cash
opening accessible cash = 40
pre-debt cash generation = 25
cash interest = 8
principal = 12
capex or other use already excluded from pre-debt cash generation = 0
expected ending accessible cash = 45

Test V1 — covenant direction
maximum leverage threshold = 4.0
calculated leverage = 3.4
expected headroom = 0.6

minimum coverage floor = 2.0
calculated coverage = 2.6
expected headroom = 0.6

Test W1 — waterfall
available value = 90
senior claim = 60
pari passu junior claims = 40 and 20
expected senior distribution = 60
remaining value = 30
expected junior distributions = 20 and 10
expected residual = 0

Test D2 — carrying amount
opening carrying amount = 98
effective-interest expense = 6
cash coupon paid = 5
new debt / FX / derecognition = 0
expected closing carrying amount = 99

Test I1 — coupon floor/cap
reference rate = 1
reference-rate floor = 2
margin = 3
all-in coupon cap = 4.5
expected contractual cash rate = min(max(1, 2) + 3, 4.5) = 4.5

Test R1 — committed proceeds reuse
settled proceeds with funding_source_id X already included in opening cash = 30
same funding_source_id X shown as committed proceeds = 30
expected additional eligible committed proceeds = 0

Test W2 — recovery cost treatment
gross value pool = 100
administrative cost assigned value_deduction = 10
same cost allowed as waterfall_claim = no
expected value available to claims = 90

Test G1 — guarantee state transition
obligation_id G starts as contingent exposure = 25
G crystallizes as funded debt or allowed claim = 25
expected combined amount across contingent/debt/cash-call/claim states = 25, not 50

Test L1 — RCF draw
RCF commitment = 100
opening drawn = 30
new draw = 20
expected cash inflow = 20
expected closing drawn debt = 50
expected nominal undrawn before other limits = 50
expected future interest and maturity principal to include the new 20

Test C2 — CFADS interest add-back
Post-WC operating cash after cash interest = 30
cash interest deducted in that bridge = 6
essential/committed capex = 10
expected CFADS = 26
expected cash interest in debt service = 6, recorded once

Test A1 — cash availability class
one cash account balance = 10
primary availability class = RESTRICTED
restriction flags = trapped and pledged
expected gross-cash contribution = 10, not 20 or 30
~~~

숫자는 formula 작동을 확인하기 위한 합성 fixture다. 실제 판단 threshold가 아니다.

### 6.6 통화·단위·기간 convention

- 거래통화, 기능통화, 표시통화를 분리한다.
- balance sheet는 시점환율, P&L·cash flow는 거래일 또는 일관된 평균환율을 쓴다.
- 외화부채 stress는 원금환산, 현금이자, hedge, 담보·margin call을 함께 반영한다.
- 외화 원리금의 liquidity cash outflow는 보고서 평균환율이 아니라 실제 지급일 환율 또는 scenario path FX로 환산한다.
- 연간 ratio가 월중 cash trough를 숨길 수 있으므로 지급주기와 계절성에 맞는 최소 time step을 선택한다.
- 분기공시만 있는데 월별 cash를 만들면 allocation rule과 uncertainty를 [A]로 표시한다.
- LTM, fiscal year, calendar year, test period를 명확히 분리한다.
- day count와 coupon frequency가 공개되지 않으면 정밀한 accrued interest를 사실처럼 표시하지 않는다.

---

## 7. Borrower·instrument·legal-entity scope

### 7.1 Entity tree

각 case는 다음 순서로 tree를 작성한다.

1. 최상위 parent와 연결범위
2. 주요 operating subsidiary
3. debt issuer와 borrower
4. guarantee 제공 법인
5. collateral 소유 법인
6. cash가 축적되는 법인
7. 규제·세금·소수주주·계약으로 upstream이 제한되는 법인
8. joint venture·associate·unrestricted subsidiary

~~~text
Parent / HoldCo
├─ OpCo A — operating assets, local cash, senior secured debt
├─ OpCo B — regulated subsidiary, upstream restriction
├─ FinanceCo — bond issuer, guaranteed by named entities only
└─ JV — not consolidated cash access unless distribution evidence exists
~~~

### 7.2 Consolidated group와 지급재원

연결 EBITDA와 연결현금이 곧 특정 obligor의 상환재원은 아니다.

검토 질문:

- obligor가 운영현금을 직접 창출하는가?
- 배당·intercompany loan·cash pooling으로 현금을 이전할 수 있는가?
- 현지 규제, 세금, minority interest, negative pledge, restricted payment가 막는가?
- 보증인이 모든 채무를 보증하는가, 일부 instrument만 보증하는가?
- collateral이 같은 법인에 있는가?
- upstream을 전제로 할 때 timing이 지급일과 맞는가?

공개증거가 없으면 연결현금 전액을 accessible cash로 쓰지 않는다.

### 7.3 Structural subordination

HoldCo creditor는 OpCo 자산에 직접 청구하지 못할 수 있다. OpCo의 외부채권과 법정우선청구가 먼저 가치를 흡수하고, 잔여 equity value만 HoldCo에 올라온다.

<code>Value upstreamable to HoldCo = residual OpCo value after OpCo-level claims and transfer constraints</code>

보증 또는 담보가 이 구조를 바꾸는지는 실제 문서로 확인한다.

### 7.4 Instrument scope

분석 대상 상품은 다음을 고정한다.

- legal issuer/borrower
- principal와 통화
- seniority와 security
- guarantee
- coupon/margin과 option
- scheduled maturity·put·amortization
- governing law
- covenant·cross-default
- 현재 outstanding과 payoff basis

공개 사채의 특징을 회사 전체 은행대출에 자동 적용하지 않는다.

### 7.5 Exposure scope

채권투자 관점이면 매수가격·dirty/clean·accrued·call을, 은행 관점이면 drawn·undrawn·LC·commitment와 security를, counterparty 관점이면 replacement exposure·netting·collateral을 별도 정의한다.

P4 기본값은 원리금 지급과 특정 instrument의 claim이다. counterparty EAD는 별도 자료가 없으면 scope 밖이다.

---

## 8. Qualitative credit assessment

### 8.1 목적

정성평가는 narrative scorecard가 아니라 stress driver와 monitoring trigger를 발견하는 과정이다. 각 항목은 다음 연결을 가져야 한다.

<code>공개 사실 → cash/debt transmission → 모델 driver → 관측 trigger → decision 영향</code>

### 8.2 Business model

| 질문 | 관측할 공개증거 | cash transmission |
|---|---|---|
| 고객이 왜 지불하는가 | 제품·서비스, 계약형태, 갱신, 가격 | volume·price·churn |
| 현금은 언제 들어오는가 | billing, receivable, deferred revenue | working capital·cash timing |
| 비용은 얼마나 고정인가 | 인력·공장·계약·임차 | margin operating leverage |
| 유지 capex는 무엇인가 | capacity·안전·규제·IT | essential capex |
| 공급자 의존은 어떤가 | 주요 원재료·single source | margin·inventory·continuity |
| 외화·원자재 노출은 | 매출·비용·부채 통화 | margin·debt service·collateral |
| 계절성은 | 분기 매출·재고·현금 | intra-year trough |

### 8.3 Industry risk

- 수요의 경기민감성·규제민감성
- 공급 증설·퇴출 장벽
- 가격결정 구조와 대체재
- 원재료·에너지·운송비 pass-through
- 기술·정책 전환과 stranded asset
- 산업의 운전자본·capex 주기
- 고객·공급자 협상력
- 업계 구조조정·default 사례

산업 평균을 기계적으로 적용하지 않는다. 회사의 계약·mix·cost position이 transmission을 바꾼다.

### 8.4 Competitive position

| 요소 | 증거 | 신용 연결 |
|---|---|---|
| scale·cost | unit economics, capacity, margin history | stress margin 방어 |
| differentiation | pricing, retention, IP, switching cost | revenue persistence |
| customer concentration | 주요 고객 비중·계약 | cliff risk |
| geographic diversity | 매출·자산 위치 | correlation·transfer |
| execution record | guidance miss, project delay | forecast credibility |
| asset quality | utilization, age, maintenance | capex·collateral range |

“시장 1위” 같은 표현은 정의·기간·출처가 없으면 삭제한다.

### 8.5 Governance와 financial policy

검토 항목:

- board·감사·related-party transaction
- 회계정정, 내부통제 취약점, 감사의견
- 반복되는 adjusted metric와 add-back
- 배당·자사주·M&A와 차입정책
- 만기 직전의 공격적 차환
- 담보 제공·보증·cross-default
- 경영진 guidance의 과거 적중과 변경
- 지배주주·sponsor의 지원능력과 지원의지 구분
- key-person·succession
- 규제·소송·부정·cyber event

지원의지는 공개 계약이 아니면 base liquidity source로 넣지 않는다.

### 8.6 Event risk

| Event | 즉시 확인 | 모델 반영 |
|---|---|---|
| 인수·대규모 투자 | price, funding, closing condition | debt, fees, integration cash |
| divestiture | binding 여부, closing, stranded cost | proceeds timing·lost cash |
| 소송·규제 | amount, timing, insurance | cash use·access restriction |
| cyber·운영중단 | duration, remediation | revenue·cost·WC |
| 회계정정 | affected period·covenant | fact vintage·headroom |
| downgrade | trigger, collateral, pricing | margin·draw availability |
| supplier finance 축소 | terms, provider | payable unwind·cash |

### 8.7 Qualitative output

~~~text
risk_id:
public_fact:
source_id:
cash_or_claim_transmission:
model_driver:
base_treatment:
stress_treatment:
monitoring_metric:
observable_trigger:
decision_effect:
counterevidence:
unknown:
~~~

점수 합계로 결론을 만들지 않는다. 어느 하나의 terminal liquidity·legal-claim risk가 전체 결론을 지배할 수 있다.

---

## 9. 회계 정규화와 cash conversion

### 9.1 원칙

신용분석의 중심은 회계이익이 아니라 지급시점에 실제 사용할 수 있는 현금이다. 그러나 현금을 예측하려면 회계정규화가 필요하다.

분리할 것:

- reported와 adjusted
- accrual interest와 cash interest
- recurring와 one-off 주장
- maintenance와 growth capex
- operating working capital과 financing성 payable
- unrestricted와 restricted/trapped cash
- P&L expense와 cash outflow timing
- consolidated와 obligor-level cash

### 9.2 Historical financial spine

| 구분 | 필수 항목 |
|---|---|
| P&L | revenue, gross profit, EBITDA bridge, EBIT, interest, tax, net income |
| BS | cash class, receivable, inventory, payable, debt, lease, provisions, pension |
| CF | CFO, capex, acquisitions, dividends, buybacks, borrowings, repayments |
| Notes | maturity, interest, covenant, guarantee, supplier finance, factoring, contingencies |

최소 history 길이는 고정하지 않는다. 사업주기·만기·공시가 허용하는 기간으로 정하고 이유를 쓴다.

### 9.3 EBITDA bridge

<code>Model EBITDA = reported operating result + D&A ± only evidence-backed classification adjustments</code>

다음은 자동 add-back이 아니다.

- recurring restructuring
- stock compensation
- litigation
- acquisition integration
- unrealized/realized FX
- fair-value change
- start-up loss
- pro forma synergy
- management의 “one-time” 비용

각 조정은 cash 여부, 반복성, 미래 회피 가능성, covenant 정의 포함 여부를 분리한다.

### 9.4 Cash-flow definitions

agency가 공개한 명칭을 그대로 빌리지 않는 자체 모델에는 [MODEL]을 붙인다.

<code>[MODEL] Post-interest operating cash = EBITDA − cash interest − cash tax ± 공개근거가 있는 비운전자본 operating adjustment</code>

<code>[MODEL] Post-WC operating cash = Post-interest operating cash − operating working-capital investment ± other operating cash items</code>

<code>[MODEL] Post-capex cash = Post-WC operating cash − capex</code>

<code>[MODEL] Post-distribution cash = Post-capex cash − dividends − buybacks</code>

이 정의는 S&P·Fitch 등 외부기관의 동일 명칭과 같다고 주장하지 않는다. 각 기관의 공식 정의는 해당 기관 자료를 직접 적용할 때만 쓴다.

### 9.5 CFADS

P4의 기본 debt-service metric은 cash interest·principal 차감 전으로 투명하게 정의한다.

<code>Cash interest deducted in Post-WC operating cash_t = 해당 bridge에 이미 반영된 cash interest; 반영되지 않았으면 0</code>

<code>CFADS_t = Post-WC operating cash_t + Cash interest deducted in Post-WC operating cash_t − essential/committed capex_t ± unavoidable pre-debt cash items not already in that bridge_t</code>

<code>Total principal due_t = Σ(unique principal-event amount_t: scheduled amortization, bullet maturity, holder put, mandatory prepayment or sweep)</code>

<code>Debt service_t = cash interest_t + Total principal due_t + same-scope contractual debt-service items not already included_t</code>

<code>DSCR_t = CFADS_t / Debt service_t</code>

주의:

- reported CFO 또는 Post-WC operating cash bridge에 cash interest가 이미 차감된 부분만 정확히 한 번 add-back한다. financing cash flow로 분류돼 해당 bridge에 없으면 add-back 값은 0이다.
- cash tax·working capital·capex와 다른 mandatory use도 어느 bridge에 포함됐는지 component flag로 관리한다.
- scheduled amortization, bullet, put, sweep는 각각 고유 event ID를 가지며 같은 principal을 둘 이상의 bucket에 넣지 않는다.
- lease cash를 debt service에 넣으면 CFADS·EBITDA·debt 정의와 대칭시킨다.
- discretionary dividend·buyback은 debt service가 아니지만 liquidity use와 decision condition에 반영한다.
- CFADS가 음수거나 debt service가 0에 가까우면 ratio보다 절대 cash gap을 우선한다.

### 9.6 Working capital

Driver 예:

<code>Receivable = revenue × collection days / period days</code>

<code>Inventory = relevant cost base × inventory days / period days</code>

<code>Payable = relevant purchase base × payable days / period days</code>

통제:

- 분모를 매출과 매출원가 중 실제 경제관계에 맞춘다.
- factoring으로 receivable이 줄었다면 cash proceeds와 retained recourse를 함께 본다.
- supplier finance는 운영 payable와 financing debt에 중복계상하지 않는다.
- quarter-end window dressing 가능성을 cash-flow와 평균 balance로 점검한다.
- stress에서 매출 감소가 receivable release를 만들더라도 bad debt·collection delay를 함께 본다.

### 9.7 Capex

| 구분 | 처리 |
|---|---|
| essential maintenance | 운영 지속·안전·규제에 필요; CFADS 전 차감 |
| committed growth | 취소 비용·계약·진척에 따라 pre-debt use |
| discretionary growth | action ladder에서 지연·축소 가능 |
| capitalized development | cash outflow와 회계분류를 분리 |
| acquisition | operating capex와 분리 |

maintenance capex 공개치가 없으면 감가상각의 일정 비율로 자동 대체하지 않는다. 자산 연령·capacity·회사 guidance·과거 패턴을 범위로 제시한다.

### 9.8 Cash tax·interest

- P&L tax expense와 cash tax를 분리한다.
- NOL·deferred tax benefit은 실제 사용시기·관할·수익능력이 있을 때만 반영한다.
- interest expense에서 non-cash accretion, PIK, capitalized interest, lease interest, hedge를 bridge한다.
- floating debt는 reset date·reference rate·margin·floor/cap을 반영한다.
- interest income은 accessible cash와 실제 재투자율에 맞춘다.

### 9.9 Cash availability

<code>Accessible cash = unrestricted cash legally and operationally available to the relevant obligor/group by the payment date</code>

각 <code>cash_account_id</code>에는 상호배타적인 primary <code>availability_class</code> 하나만 부여한다.

- ACCESSIBLE
- RESTRICTED
- CUSTOMER_OR_REGULATORY
- PLEDGED
- NONCONTROLLED_JV_OR_ASSOCIATE
- OTHER_NOT_ACCESSIBLE

<code>trapped, currency-control, contractual, regulatory, pledged, minority, timing</code>은 중복 가능한 <code>restriction_cause</code> flag다. trapped cash를 restricted cash와 별도 additive bucket으로 다시 더하지 않는다.

minimum operating cash는 계정 class가 아니라 decision constraint이고, excess cash는 accessible cash에서 그 constraint를 차감한 파생값이다.

최소 운영현금이 공개되지 않으면 값을 발명하지 않는다. 다음을 병렬 제시한다.

1. gross-debt view
2. all-unrestricted-cash net-debt view
3. evidence-backed accessible-cash view
4. minimum-cash switching range

### 9.10 Debt-like item

<code>Adjusted gross debt = reported interest-bearing debt + evidence-backed debt-like items − duplicated items</code>

검토 후보:

- lease liabilities
- supplier finance/reverse factoring
- recourse factoring/securitisation
- debt guarantees likely to crystallize
- deferred acquisition consideration·put obligation
- pension deficit·ARO·tax settlement
- preference shares with mandatory redemption

포함 여부는 목적에 따라 다르다. 포함한 항목은 EBITDA, cash flow, claim과 대칭이어야 한다.

Guarantee, pension, ARO, tax, put 등은 동일 <code>obligation_id</code>로 상태를 관리한다.

<code>contingent exposure → crystallized cash call or funded debt → allowed claim</code>

한 시점·scenario에서 상호배타적 상태만 활성화한다. adjusted debt ratio에 포함한 likely-to-crystallize guarantee를 stress cash call·funded debt·recovery claim으로 다시 더하지 않고, 상태전이와 amount bridge로 대사한다.

### 9.11 Financial reporting quality

red flag:

- cash와 earnings의 지속적 괴리
- repeated one-off add-back
- receivable·inventory가 driver보다 빠른 증가
- supplier finance·factoring 의존
- 잦은 분류변경·restatement
- interest capitalisation 급증
- related-party receivable·guarantee
- maturity disclosure와 debt balance 불일치
- audit qualification·going-concern emphasis

red flag는 즉시 부정결론이 아니라 추가 evidence와 stress를 요구한다.

### 9.12 Profitability·변동성·cash conversion

수익성은 equity-style “좋은 회사” 점수가 아니라 고정비·이자·원금을 흡수할 operating buffer의 출발점이다. reported와 model-normalized view를 함께 보며, 단일 margin이나 peer median을 신용 문턱으로 쓰지 않는다.

기본 지표:

<code>Gross margin = gross profit / revenue</code>

<code>Model EBITDA margin = model EBITDA / revenue</code>

<code>EBIT margin = EBIT / revenue</code>

<code>Cash-conversion bridge = Model EBITDA → cash interest → cash tax → operating working capital → other operating cash → essential/committed capex → CFADS</code>

분석:

- price·volume·mix와 gross-margin driver
- fixed/variable cost와 operating leverage
- margin trend·range·변동성; 관측기간은 사업주기와 공개자료로 정함
- guidance miss·restructuring·반복 add-back
- working capital·cash tax·capex 때문에 accounting margin이 현금으로 전환되지 않는 이유
- 정의를 맞춘 peer의 margin·cash conversion과 차이
- base·downside에서 coverage·cash trough까지의 transmission

분모가 0 또는 immaterial하면 ratio를 <code>NM</code>으로 두고 절대 gross profit·cash burn을 본다.

필수 output:

| Output | 내용 |
|---|---|
| profitability bridge | reported → normalized gross/EBITDA/EBIT margin |
| trend·volatility | 기간·driver·구조변화와 함께 표시 |
| cash conversion | EBITDA에서 CFADS까지 component별 bridge |
| peer context | 정의·기간·회계·scope가 맞을 때만 |
| downside transmission | margin 변화가 cash·debt service·covenant에 미치는 영향 |
| monitoring | price·volume·mix·input·WC의 observable trigger |

---

## 10. Debt·facility·claim register

### 10.1 Debt universe

다음 표를 instrument별로 만든다.

| 필드 | 설명 |
|---|---|
| entity·instrument | legal issuer/borrower와 고유 ID |
| face principal | 계약상 원금 |
| carrying amount | 재무제표 장부금액 |
| cash proceeds | 발행·인출 시 실제 유입 |
| payoff amount | call premium·accrued 등 포함 시 별도 |
| currency | 원리금 통화 |
| rate | fixed/floating, base, margin, floor/cap |
| hedge | notional, maturity, effectiveness, counterparty |
| maturity | bullet·amortization·put·call |
| priority | seniority, secured, structural position |
| guarantee | 보증인·scope·cap |
| covenant | actual document link |
| source | 원문·접수번호·effective amendment |

### 10.2 Face와 carrying amount bridge

<code>Closing face = Opening face + new issue/draw + capitalized principal/PIK + FX/other face movement − principal repayment</code>

<code>Closing carrying amount = Opening carrying amount + carrying amount of new debt recognized + effective-interest expense + FX/other carrying adjustment − cash coupon/interest paid − carrying amount derecognized on repayment, modification or extinguishment</code>

cash로 지급한 principal·premium·fee와 제거된 carrying amount는 같지 않을 수 있다. 차이는 적용 회계기준에 따른 modification/extinguishment gain or loss로 별도 bridge한다. fair-value 측정 부채는 해당 회계정책의 remeasurement component를 명시한다.

두 bridge가 다르는 이유를 설명한다. debt service와 maturity에는 원칙적으로 계약상 principal/payoff schedule을 사용하고, balance-sheet reconciliation에는 carrying amount를 사용한다.

### 10.3 Facility availability

<code>Nominal undrawn = commitment − drawn − LC usage − other reserved usage</code>

<code>Facility eligibility state_t = VERIFIED_ELIGIBLE | VERIFIED_INELIGIBLE | CONDITIONAL_UNKNOWN</code>

~~~text
If VERIFIED_ELIGIBLE:
  Drawable amount_t = min(nominal undrawn_t, borrowing-base amount_t,
                          covenant-limited amount_t, entity-accessible amount_t)
If VERIFIED_INELIGIBLE:
  Drawable amount_t = 0
If CONDITIONAL_UNKNOWN:
  Drawable amount_t = CONDITIONAL_UNKNOWN
~~~

시간과 금액을 같은 <code>min()</code>에 넣지 않는다. need date가 facility expiry 이후이거나 condition precedent가 미충족이면 drawable은 0이며, 조건이 비공개면 verified source가 아니라 conditional/unknown으로 둔다.

실제 공개되지 않은 borrowing base 또는 draw condition은 100% 가용으로 가정하지 않는다.

Facility 상태:

| 상태 | liquidity source 처리 |
|---|---|
| committed, conditions publicly satisfied | verified source |
| committed, conditions partially public | conditional source |
| committed, covenant/default status unknown | uncertain source |
| uncommitted | pre-mitigation source 제외 |
| expired/maturing before need | source 제외 또는 refinancing object |
| already drawn | 현금과 debt에 반영; undrawn에서 차감 |

### 10.4 Interest schedule

Fixed:

<code>Cash interest_t = opening/path principal × coupon × day-count fraction + cash fees</code>

Floating:

<code>Contract cash rate_t = contract_function(reference-rate observation/reset, reference-rate floor/cap, margin and step/default margin, all-in coupon floor/cap)</code>

<code>Gross debt cash interest_t = path principal × Contract cash rate_t × day-count fraction + contractual cash fees_t</code>

<code>Net interest-related cash outflow_t = Gross debt cash interest_t ± separately modeled hedge cash settlement_t</code>

benchmark floor/cap과 all-in coupon floor/cap의 적용순서는 실제 계약으로 정의한다. hedge는 채무계약상 gross coupon을 바꾸지 않으므로 별도 cash-flow line에서 합친다.

확인:

- reset lag와 observation date
- floor·cap
- default margin
- commitment fee·utilization fee
- hedge notional mismatch와 maturity
- PIK toggle
- accrued vs payment date
- leap year·day count

### 10.5 Maturity schedule

별도의 두 표를 만든다.

1. **Principal maturity schedule:** instrument별 contractual principal·put·amortization.
2. **Gross contractual cash-flow disclosure:** IFRS 7 등 공시된 undiscounted cash flow.

두 표를 합산하지 않는다. IFRS 7 표에는 미래이자나 파생 cash flow가 들어갈 수 있고 장부금액과 직접 대사되지 않을 수 있다.

공시가 “1년 이내, 1–5년, 5년 초과” bucket뿐이면 각 연도에 임의 배분하지 않는다. 개별 instrument 원문이 있을 때만 annual/monthly schedule을 만든다.

### 10.6 Lease

분석 관점에 따라 두 view를 제공한다.

- reported view
- lease-adjusted credit view

Lease liability를 debt에 더하면:

- lease interest와 depreciation/lease expense bridge
- cash lease payment의 operating/financing 분류
- debt service 포함 여부
- maturity

를 일관되게 조정한다.

### 10.7 Supplier finance·factoring

Supplier finance:

- payable 분류
- financier가 지급한 금액
- 회사 지급기한과 일반 trade payable 기한
- liquidity concentration
- unwind stress

Factoring:

- recourse 여부
- derecognition
- retained risk
- proceeds timing
- 고객 default·dilution

동일 의무를 payable와 debt, 동일 현금을 CFO와 financing inflow에 두 번 넣지 않는다.

### 10.8 Guarantees·contingent debt

Guarantee는 다음 세 층으로 분리한다.

1. contract상 최대 노출
2. public evidence에 근거한 crystallization path
3. stress cash call과 recovery claim

모회사와 자회사 waterfall에 동일 보증채무를 중복 배분하지 않는다. 보증인의 reimbursement/subrogation claim도 법적·경제적으로 별도 확인한다.

### 10.9 Debt completeness statement

모든 pack은 아래 문구 중 하나를 선택한다.

- “공개 공시상 material interest-bearing obligations를 원문과 대사했다.”
- “공개된 instrument만 포함하며 전체 사모차입·담보·side letter의 완전성을 보장하지 않는다.”
- “핵심 debt universe가 불완전하여 instrument-level 결론을 제한한다.”

“검색되지 않음”을 “존재하지 않음”으로 바꾸지 않는다.

---

## 11. Liquidity sources-and-uses

### 11.1 유동성의 정의

유동성은 balance-sheet cash가 아니라 필요한 시점에 법적·운영상 사용할 수 있는 확정 재원이다.

<code>Available liquidity_t = opening accessible cash_t + CFADS_t + drawable committed facilities_t + documented committed proceeds_t</code>

<code>Required liquidity uses_t = debt service_t + mandatory cash uses not already deducted in CFADS_t + required ending operating cash_t</code>

<code>Pre-mitigation liquidity surplus_t = Available liquidity_t − Required liquidity uses_t</code>

CFADS에 이미 working capital·cash tax·essential/committed capex가 반영됐다면 required uses에서 다시 차감하지 않는다. 최소 운영현금은 기간 비용이 아니라 요구 기말잔액이다. cash roll-forward 방식에서는 “기말 accessible cash가 floor 아래인지”로 같은 제약을 한 번만 적용한다.

### 11.2 Source 인정 규칙

| Source | pre-mitigation 인정 | 조건 |
|---|---|---|
| accessible opening cash | 예 | entity·currency·restriction 확인 |
| internally generated cash | 예 | driver model과 지급시점 일치 |
| committed undrawn facility | 조건부 | maturity·draw condition·LC·covenant 반영 |
| already committed asset-sale proceeds | 조건부 | binding·closing condition·tax·timing 반영 |
| announced but uncommitted sale | 아니오 | management action layer |
| uncommitted refinancing | 아니오 | refinancing scenario |
| planned equity raise | 아니오 | third-party action |
| sponsor support | 계약상 확정일 때만 | scope·cap·timing·enforceability |
| restricted/trapped cash | 아니오 | release 조건 충족 시 별도 |

### 11.3 Period cash roll-forward

<code>Ending accessible cash_t = Opening accessible cash_t + CFADS_t − Debt service_t + verified financing draws_t + verified other receipts_t − other mandatory uses_t − discretionary uses_t</code>

<code>Opening accessible cash_(t+1) = Ending accessible cash_t</code>

<code>Liquidity shortfall_t = max(0, minimum operating cash_t − Ending accessible cash before uncommitted actions_t)</code>

minimum operating cash가 공개되지 않으면 switching table을 낸다.

| assumed minimum cash | first shortfall date | peak shortfall | decision state |
|---:|---|---:|---|
| 공개·관측 anchor A | 계산 | 계산 | 조건부 |
| anchor B | 계산 | 계산 | 조건부 |
| break-even floor | 계산 | 0 | switching value |

### 11.4 Intra-period trough

연말 현금이 양수여도 급여·세금·이자·재고 build가 먼저 발생하면 지급실패가 생길 수 있다.

- cash payment calendar가 공개되면 월·주 단위로 맞춘다.
- 연간 공시만 있으면 계절성·지급일을 공개근거로 배분하고 [A]로 표시한다.
- 임의로 균등 분배했으면 stress 결론을 제한한다.
- lowest cash, date, source exhaustion order를 출력한다.

### 11.5 Source exhaustion order

기본 순서는 계약·실무에 맞춰 case별로 정한다. 예:

1. accessible cash above operating floor
2. recurring internal cash
3. dedicated committed facility
4. general committed facility
5. committed disposal/equity proceeds
6. execution-dependent management action
7. uncommitted third-party refinancing

순서는 보편 규칙이 아니다. facility fee, negative pledge, collateral, covenant, restricted payment가 달라질 수 있다.

### 11.6 RCF 이중계상 통제

RCF draw는:

- 현금 source 증가
- debt 증가
- undrawn availability 감소
- 향후 interest·fee 증가
- RCF maturity의 principal use 증가
- covenant·leverage 변화

를 동시에 만든다. 이미 draw된 RCF 현금과 총 commitment를 다시 더하지 않는다.

### 11.7 Liquidity output

필수 출력:

- opening/ending accessible cash
- cash trough와 날짜
- committed facility draw와 exhaustion
- mandatory uses by type
- pre-action와 post-action gap
- 최소현금 switching value
- first failure event와 정의
- source concentration·currency mismatch
- 공개되지 않아 제외한 source

---

## 12. Debt-service capacity·leverage·coverage

### 12.1 목적별 metric dictionary

~~~text
metric_id:
metric_name:
purpose:
numerator_definition:
denominator_definition:
cash_or_accrual:
gross_or_net:
lease_treatment:
supplier_finance_treatment:
factoring_treatment:
average_or_period_end_balance:
period:
entity_scope:
currency:
source_or_model:
zero_negative_rule:
external_methodology_reference:
~~~

같은 이름의 ratio라도 정의가 다르면 비교하지 않는다.

### 12.2 기본 ratio

<code>Gross debt / EBITDA = adjusted gross debt / model EBITDA</code>

<code>Net debt / EBITDA = (adjusted gross debt − eligible nettable cash after operating and contractual constraints) / model EBITDA</code>

eligible nettable cash는 accessible cash의 부분집합이다. 동일 법인·통화·시점에서 debt 상계에 쓸 수 있고 operating floor·restriction을 차감한 금액만 포함한다.

<code>Post-interest operating cash / debt = model Post-interest operating cash / average or end adjusted debt</code>

<code>CFO / debt = normalized CFO / defined debt</code>

<code>Post-capex cash / debt = model Post-capex cash / defined debt</code>

<code>EBITDA / accrual interest = model EBITDA / defined accrual interest</code>

<code>Cash-interest coverage = (model Post-interest operating cash + cash interest) / cash interest</code>

<code>CFADS / debt service = CFADS / mandatory debt service</code>

ratio는 단독 decision rule이 아니다.

### 12.3 NM 규칙

다음이면 ratio를 숫자로 rank하지 않는다.

- EBITDA ≤ 0
- denominator = 0
- denominator가 immaterial해 ratio가 폭발
- cash interest가 hedge·PIK 때문에 음수 또는 왜곡
- 기간·scope·통화가 불일치

표시값은 <code>NM</code>이며 절대 cash burn, maturity, liquidity gap을 보여준다.

### 12.4 Model-implied incremental debt boundary

<code>Model-implied incremental debt boundary = maximum defined incremental debt whose proceeds, fees, interest and repayment path allow all tested periods to satisfy accessible cash, mandatory debt service, publicly recalculable contractual covenants, facility availability and maturity/refinancing constraints</code>

계약 covenant가 공개 재계산 불가능하면 analyst proxy는 별도 sensitivity일 뿐 법적 debt-capacity constraint로 가장하지 않는다.

이 값은 선언한 가정 아래의 모델 경계이지 실제 lender appetite, committed availability, 승인가능액이 아니다. use of proceeds와 full interest·fee·amortization·maturity가 horizon 안에 없거나, horizon 밖 상환을 위한 documented terminal/refinancing condition을 정의하지 못하면 <code>NOT_MEASURABLE</code>로 둔다.

계산 순서:

1. incremental proceeds와 사용처를 넣는다.
2. draw·issue fee를 반영한다.
3. interest·amortization·maturity를 반영한다.
4. covenant debt와 EBITDA 정의를 반영한다.
5. minimum cash와 facility condition을 반영한다.
6. 첫 constraint가 binding할 때까지 solver 또는 switching table을 만든다.

고정 leverage cutoff에서 debt capacity를 역산하지 않는다. 계약 threshold가 실제 constraint라면 그 원문과 effective date를 쓴다.

### 12.5 Coverage 해석

- EBITDA/interest는 운전자본·capex·세금·principal을 보지 않는다.
- operating-cash/debt ratio는 상환시점을 보지 않는다.
- annual DSCR은 intra-year cash trough를 숨길 수 있다.
- net leverage는 현금의 접근 가능성을 과대평가할 수 있다.
- 높은 현재 coverage가 가까운 bullet maturity의 차환가능성을 보장하지 않는다.

따라서 ratio table과 period cash schedule을 함께 낸다.

### 12.6 Peer comparison

Peer ratio는 정의·회계·통화·기간·lease·cash treatment를 맞출 때만 쓴다. peer median은 승인 기준이 아니다.

비교 목적:

- 왜 현금전환이 다른가
- 왜 만기·담보·조달비용이 다른가
- stress transmission이 왜 다른가

### 12.7 Fixed-charge coverage — applicable할 때

계약상 fixed-charge coverage가 공개돼 있으면 §14의 정확한 정의를 우선한다. 독립 cash view가 필요하면 fixed charge universe를 case별로 선언한다.

<code>Defined cash fixed charges_t = Σ(unique cash charge event_t: cash interest, selected recurring lease/rent, preferred distribution or other charge that is contractually due and unavoidable as modeled)</code>

<code>Cash available before defined fixed charges_t = CFADS_t + Σ(defined fixed charges already deducted in the CFADS bridge_t)</code>

<code>[MODEL] Cash fixed-charge coverage_t = Cash available before defined fixed charges_t / Defined cash fixed charges_t</code>

통제:

- CFADS가 이미 cash interest를 add-back했으면 cash interest를 numerator에 다시 더하지 않는다.
- lease/rent를 add-back하면 debt·lease·cash-flow 처리와 대칭시킨다.
- principal event를 fixed charge와 debt service에 중복하지 않는다.
- charge마다 <code>included_in_cfads</code>, <code>included_in_debt_service</code>, <code>obligation_id</code>를 둔다.
- 공개자료로 recurring fixed charge를 분해할 수 없거나 중요하지 않으면 <code>NOT_APPLICABLE_OR_NOT_MEASURABLE</code>과 이유를 낸다.
- 이 metric의 numerator·denominator를 agency나 covenant 정의와 같다고 부르지 않는다.

출력은 current/path coverage, component bridge, downside trough, 계약 metric과 model metric의 차이, N/A 사유다. 고정 minimum을 발명하지 않는다.

---

## 13. Maturity·refinancing·funding risk

### 13.1 Maturity wall

Instrument별로 다음을 시간축에 놓는다.

- scheduled principal
- bullet maturity
- holder put
- mandatory prepayment·cash sweep
- lease payment if included
- RCF maturity와 cleanup
- hedge maturity·collateral
- guarantee expiry
- committed facility expiry

공시 bucket을 임의로 쪼개지 않는다.

### 13.2 Refinancing need

<code>Gross refinancing requirement_t = Σ(unique principal-event amount_t) + mandatory collateral/fees not already included_t</code>

<code>Eligible refinancing sources_t = internal cash specifically available after operating floor_t + committed proceeds not yet settled and not already included in opening cash or period financing inflow_t + scenario executable new financing_t</code>

<code>Refinancing gap_t = max(0, Gross refinancing requirement_t − Eligible refinancing sources_t)</code>

모든 principal use와 funding source는 고유 event/source ID를 가진다. settled proceeds가 opening cash 또는 해당 기간 financing inflow에 이미 있으면 committed proceeds로 다시 넣지 않는다. signed committed source와 scenario의 uncommitted new financing도 같은 조달건이면 동시에 쓰지 않는다. base case에서도 새 차입은 “현재 debt가 있으니 계속 가능”이 아니라 evidence-backed assumption이다.

### 13.3 New financing cost

Period cash schedule:

<code>Cash financing outflow_t = contractual cash interest_t + periodic commitment/utilization fees_t + principal repayment_t + hedge/FX cash flows_t</code>

Upfront underwriting·OID·legal·hedge 비용은 closing-date cash use로 기록한다. 회계상 transaction cost와 effective-interest amortisation은 carrying-amount bridge에 따로 둔다.

비교용 annualized all-in cost가 필요하면 같은 통화·valuation date에서 <code>net cash proceeds</code>와 모든 contractual financing cash flow의 IRR/EIR을 계산한다. reference rate, spread, upfront fee, hedge·FX를 서로 다른 단위인 채 단순 덧셈하지 않는다. 실제 liquidity·debt-service 모델은 annualized 숫자가 아니라 period cash schedule을 사용한다.

검토:

- 통화·만기와 맞는 공식 reference curve
- instrument seniority·security·option
- new-money vs secondary-market spread
- market liquidity·deal size
- rating trigger
- covenant package·collateral
- issuance lead time

secondary market의 한 번의 stale trade를 곧바로 primary issuance cost로 쓰지 않는다.

### 13.4 Refinancing availability

가용성 상태:

| 상태 | 근거 | 모델 |
|---|---|---|
| executed/settled | 계약·공시 | opening cash 또는 realized financing inflow 중 한 곳에만 |
| signed, unconditional or conditions satisfied, not settled | 원문·조건충족 | committed proceeds |
| signed with unmet conditions | 원문 조건 | condition별 haircut가 아니라 event tree |
| announced mandate | 회사 발표 | action layer |
| historical access | 과거발행 | evidence anchor일 뿐 확정 아님 |
| market open for peers | comparable deals | scenario evidence |
| no public evidence | 없음 | 0 확정재원; switching need 제시 |

### 13.5 Joint funding stress

Refinancing stress는 금리만 올리지 않는다.

- reference rate 상승
- issuer spread 확대
- tenor 단축
- principal haircut 또는 부분 차환
- 담보 요구·borrowing base 축소
- upfront fee 증가
- execution delay
- FX swap/hedge 비용
- rating-linked margin·collateral
- RCF availability 감소

각 path는 공개 역사·공식 시장자료·계약조건 또는 switching value로 anchor한다.

### 13.6 Refinancing break-even

산출:

- maximum all-in rate before cash/covenant failure
- minimum refinanced principal required
- latest executable closing date
- minimum tenor
- maximum collateral call
- maximum facility haircut

이 값들은 예측확률이 아니라 decision boundary다.

### 13.7 Funding concentration

확인:

- 한 은행·시장·통화·만기 집중
- secured debt 증가로 남은 collateral capacity 감소
- bank facility와 public bond의 cross-default
- short-term funding으로 long-lived asset financing
- supplier finance·factoring withdrawal
- intercompany funding 의존
- local cash와 offshore debt mismatch

---

## 14. Covenant·restriction module

### 14.1 Covenant taxonomy

| 유형 | 질문 |
|---|---|
| maintenance | 매 test date에 계속 충족해야 하는가 |
| incurrence | 신규 debt·배당·인수 시에만 test하는가 |
| springing | RCF 사용률 등 trigger에서만 작동하는가 |
| draw condition | facility를 인출할 때 필요한가 |
| negative covenant | debt, lien, restricted payment, disposal를 제한하는가 |
| reporting covenant | certificate·재무제표 제출이 필요한가 |
| event of default | breach 이후 notice·cure·grace·acceleration은 무엇인가 |

### 14.2 계산 원칙

Maximum-type:

<code>Headroom = Contractual maximum − Calculated actual</code>

Minimum-type:

<code>Headroom = Calculated actual − Contractual minimum</code>

Minimum liquidity:

<code>Headroom = Eligible liquidity under contract − Required minimum liquidity</code>

Headroom이 양수면 mathematical cushion이다. compliance의 법률적 결론은 amendment, certificate, cure, waiver를 함께 봐야 한다.

### 14.3 Exact definition 우선

반드시 계약 원문에서 확인:

- testing entity/restricted group
- gross/net debt와 eligible cash
- covenant EBITDA와 add-back·cap
- cash/accrual interest와 fixed charge
- LTM·quarter·annual period
- step-down/up 날짜
- basket와 grower
- acquisition pro forma
- cure·equity cure
- springing utilization
- amendment·waiver

Model EBITDA를 covenant EBITDA로 바꾸어 쓰지 않는다.

### 14.4 Public testability

| 상태 | 표현 |
|---|---|
| exact formula와 모든 component 공개 | PUBLIC_RECALCULATION |
| formula 공개, 일부 component 미공개 | ANALYST_PROXY_ONLY |
| 회사가 compliance만 공시 | ISSUER_REPORTED_COMPLIANT |
| threshold 또는 정의 불명 | NOT_TESTABLE_FROM_PUBLIC_DATA |
| covenant 존재 여부 자체 불명 | PUBLICLY_NOT_OBSERVABLE |

<code>PUBLIC_RECALCULATION</code>도 공개자료로 analyst가 재현한 값이지 법률의견이나 공식 compliance certificate가 아니다. <code>ANALYST_PROXY_ONLY</code>에서는 proxy를 만들 수 있지만 <code>proxy</code>로 크게 표시하고 headroom·breach라 부르지 않는다.

### 14.5 Breach-to-default path

<code>Public-recalculation threshold crossing or issuer-reported breach → contract-specific branches {notice/reporting; cure/grace; waiver/amendment; event of default} → acceleration/enforcement only if required consent, election and conditions are satisfied</code>

이는 선형 보편절차가 아니라 case별 decision tree다. 어떤 breach는 notice 없이 EOD가 될 수 있고 waiver/amendment는 대안 branch이며 acceleration은 채권자 선택·의결요건이 필요할 수 있다. 각 branch의 기간과 권리는 계약 원문이 있을 때만 적용한다. threshold crossing을 즉시 원리금 미지급·도산으로 서술하지 않는다.

### 14.6 Covenant stress output

- PUBLIC_RECALCULATION: 공개 재계산 headroom과 최초 forecast threshold crossing
- ANALYST_PROXY_ONLY: proxy distance와 switching value; breach·공식 headroom 표현 금지
- ISSUER_REPORTED_COMPLIANT: 회사의 point-in-time 공시만 표시; 미공개 headroom 산출 금지
- NOT_TESTABLE/PUBLICLY_NOT_OBSERVABLE: 필요한 원문·component와 decision limitation
- 각 상태 공통: driver contribution, 공개된 springing·cure·waiver·amendment, draw availability와 cross-default/cross-acceleration path

### 14.7 Restrictions

Debt service capacity 외에도 다음을 본다.

- restricted payment
- debt incurrence
- lien/negative pledge
- asset sale proceeds
- change of control
- subsidiary designation
- investment·acquisition basket
- cash upstream
- debt repurchase

좋은 cash flow가 있어도 현금을 해당 채권자에게 이동시키지 못할 수 있다.

---

## 15. Downside·reverse stress·management action

### 15.1 Stress 설계 원칙

1. driver shock는 P&L·BS·cash·debt·covenant·refinancing에 동시에 연결한다.
2. revenue, margin, working capital, rate, FX, refinancing을 독립 단일변수로만 보지 않는다.
3. stress 폭은 회사·산업의 공개 역사, 공식 거시자료, 실제 계약, 공개 principal risk 또는 reverse switching value에서 도출한다.
4. arbitrary probability와 false precision을 피한다.
5. adverse 결과와 strongest counterargument를 함께 낸다.
6. management action 전·후를 분리한다.

### 15.2 Scenario set

시나리오 수는 고정하지 않는다. applicable한 논리구조:

| Scenario | 목적 | input 근거 |
|---|---|---|
| ISSUER_GUIDANCE_PATH | 회사가 공개한 목표·전망을 cash path로 번역; 회사 statement의 기록이지 analyst best estimate가 아님 | contemporaneous company guidance |
| ANALYST_BASE | cutoff 이전 공개사실과 명시적 [A]로 만든 독립 best-estimate path | filing·공식 macro·driver history |
| EVIDENCE_DOWNSIDE | severe-but-plausible transmission | company/industry history·principal risk |
| REVERSE_STRESS | 지급실패 boundary 찾기 | solver·switching value |
| OPTIONAL_EVENT | M&A, 소송, supply shock 등 material event | event-specific evidence |

ISSUER_GUIDANCE_PATH와 ANALYST_BASE는 별도 scenario/version으로 freeze하고 revenue·margin·WC·cash·refinancing gap을 설명한다. guidance가 없으면 전자를 N/A로 둔다. guidance의 존재는 [F]이지만 실현가능성은 [JUDG]이며, 설명 없이 analyst base로 복사하지 않는다.

### 15.3 Driver path

| Driver | operating path | cash·credit path |
|---|---|---|
| volume | 고객·capacity·churn | revenue·receivable·inventory |
| price/mix | contract·competition | margin·cash tax |
| input/wage | pass-through lag | margin·payable |
| working capital | DSO/DIO/DPO | cash trough·facility draw |
| capex | essential/committed/discretionary | cash use·capacity |
| rate | base curve·margin·reset | cash interest·covenant |
| FX | revenue/cost/debt currency | margin·principal·collateral |
| refinancing | amount·rate·tenor·timing | maturity gap·future service |
| collateral | price·haircut·margin call | drawable facility·cash use |
| rating trigger | notch/action, if contractual | margin·collateral·access |

### 15.4 Correlation과 path consistency

예:

- recession에서 revenue 감소와 receivable release만 반영하지 말고 collection delay·bad debt를 함께 본다.
- commodity shock에서 매출가격과 input cost의 pass-through lag를 반영한다.
- downgrade에서 spread만 확대하지 말고 contractual margin·collateral·customer behavior를 확인한다.
- asset sale에서 proceeds만 넣지 말고 tax·fee·delay·lost EBITDA·stranded cost를 반영한다.
- capex cut에서 현금절감과 capacity·maintenance consequence를 함께 본다.

상호 배타적 action을 동시에 적용하지 않는다.

### 15.5 Reverse-stress endpoint

case에 맞는 endpoint를 선택한다.

- accessible cash가 evidence-backed operating floor 아래
- committed facility exhaustion
- 실제 covenant의 최초 failure
- scheduled debt service 미충족
- maturity/refinancing gap
- 특정 collateral call 미충족

출력:

<code>switching driver value, failure date, cash gap, constraint, required mitigation, lead time</code>

여러 driver가 함께 움직이면 2D/3D boundary 또는 path table을 사용한다. 확률분포를 발명하지 않는다.

### 15.6 Management action ladder

| Class | 정의 | base/pre-mitigation |
|---|---|---|
| A — contractual/already committed | 서명·조건·금액·시점 공개 | 조건 충족 시 반영 |
| B — management controlled but execution-dependent | 비용절감·discretionary capex·배당 중단 | post-action만 |
| C — third-party/uncommitted | 자산매각·증자·차환·sponsor support | post-action·조건부 |

각 action:

~~~text
action_id:
proposed_accountable_role:
classification:
public_evidence:
earliest_start:
cash_effect_by_period:
one-time_cost:
operating_consequence:
third_party_condition:
legal_or_covenant_constraint:
mutually_exclusive_with:
reversibility:
failure_mode:
~~~

### 15.7 Action credibility

다음을 확인한다.

- 공개된 board approval·binding agreement
- 과거 실행 기록
- lead time과 필요한 consent
- 비용·세금·working capital
- 고객·직원·공급자 영향
- 담보·negative pledge·asset-sale covenant
- sale price가 book value와 다른 이유
- 절감액이 cash로 실현되는 시점

장부가를 매각대금으로 자동 사용하지 않는다.

### 15.8 핵심 stress output

- minimum accessible cash와 날짜
- first cash gap, public-recalculation threshold crossing, scheduled-payment shortfall을 각각 구분한 날짜
- peak gross/net debt
- facility draw·exhaustion
- maturity/refinancing gap
- leverage peak와 coverage trough
- §14 testability state에 맞는 covenant output
- additional debt capacity
- stress-to-fail switching variable
- management action dependency
- pre-action와 post-action decision
- 판단을 뒤집는 공개 trigger

---

## 16. Collateral·guarantee·priority·recovery

### 16.1 사용 경계

P4가 산출하는 것은 <code>illustrative public-data recovery range</code>다. 법률의견, appraisal, rating agency recovery rating, 확정 배분이 아니다.

다음이 없으면 recovery를 제한하거나 보류한다.

- legal obligor와 asset owner
- instrument terms와 allowed claim basis
- 담보 범위·lien rank
- guarantee scope
- material prior claims
- 관할과 적용 절차
- 공개적으로 지지 가능한 valuation range

### 16.2 Claim map 조립 — priority 순서가 아님

먼저 법인별로 value pool, asset owner, 모든 pre-event claim, 절차 개시 후 생길 수 있는 비용·claim, guarantee, intercompany 관계를 빠짐없이 inventory한다. 이 조립 순서는 법적 우선순위가 아니다. 실제 배분 순서는 각 법인의 관할법, 담보, 계약, intercreditor, 절차상 명령으로 별도 결정한다.

- secured·unsecured·subordinated라는 명칭만으로 서로 다른 관할의 보편 순서를 만들지 않는다.
- guarantee claim은 원 obligor waterfall의 상위 항목이 아니라 guarantor 법인에 대한 별도 claim이다.
- guarantor에 대한 회수와 original obligor에 대한 회수의 총합은 원 allowed claim을 넘지 않게 cap한다.
- residual equity value만 해당 법인의 parent로 upstream한다.

연결 EV를 그룹 모든 채권자에게 한 번에 나누지 않는다.

### 16.3 Going-concern과 liquidation

Going-concern:

<code>Enterprise value range = post-distress normalized cash metric × evidence-supported market multiple or direct cash-flow valuation</code>

Liquidation:

<code>Gross liquidation proceeds range = Σ(asset-class realizable value)</code>

<code>Net distributable value range = Gross liquidation proceeds − value-level deductions not also recorded in the claim stack</code>

선택 원칙:

- 운영가치가 자산해체가치보다 높고 실행 가능한 사업이면 going-concern을 검토한다.
- 자산별 매각이 더 현실적이면 liquidation을 검토한다.
- 적용 절차와 사실이 불확실하면 두 범위를 병렬 제시한다.

임의 “4–8배” 또는 자산별 고정 haircut을 쓰지 않는다. 공개 거래, 회사 asset data, 산업 cycle, 실제 distress outcome, reverse break-even으로 범위를 뒷받침한다.

### 16.4 Value bridge

<code>Gross legal-entity value pool = supported post-restructuring enterprise/asset value + excess non-operating value not already included</code>

<code>Value available to claim waterfall = Gross legal-entity value pool − value-level deductions not also included as claims</code>

각 sale·admin·DIP·wind-down·tax 항목에는 <code>cost_treatment = value_deduction | waterfall_claim</code> 중 하나만 부여한다. 관할법과 절차가 요구하는 priority claim이면 value에서 미리 차감하지 않고 claim stack에서 한 번만 배분한다.

Pension, lease, environmental·other paid-over-time obligation은 <code>obligation_treatment = ongoing_cash_reduction | crystallized_claim</code> 중 하나만 선택한다. normalized going-concern cash metric에 계속비용으로 이미 반영했다면 동일 의무의 full claim을 waterfall에 다시 넣지 않는다. crystallized claim으로 전환하면 계속비용 처리와 valuation basis를 함께 조정한다.

통제:

- EV에 포함된 현금을 다시 더하지 않는다.
- going-concern asset를 collateral liquidation value로 다시 더하지 않는다.
- 여러 법인 보증이 같은 value pool을 두 번 만들지 않게 한다.
- tax·admin·DIP·wind-down 비용의 entity·priority·처리 layer를 분리한다.
- <code>Gross value pool = value-level deductions + claim distributions + residual</code>가 성립해야 한다.

### 16.5 Claim·cost inventory

Pre-event 또는 claims-at-default 후보:

- drawn revolver와 LC
- principal와 계약상 허용된 accrued amount
- hedge termination
- employee·tax·pension 등 적용 법률상 claim
- secured deficiency claim
- intercompany
- contingent litigation

절차 개시 후 발생 가능한 별도 항목:

- DIP/new-money financing
- administrative expense
- professional·sale·wind-down cost
- post-event tax·employee claim

guarantee는 guarantor 법인에 대한 별도 claim record로 만든다. 각 항목의 allowed amount, 발생시점, 법인, priority, value-deduction 여부는 법률·계약·절차에 따라 달라진다. public data가 없으면 range 또는 unknown으로 둔다.

### 16.6 Waterfall

각 legal entity에서:

1. applicable law와 계약으로 priority class를 정한다.
2. going-concern value와 중복되지 않는 collateral-specific value를 해당 secured claim에 배분한다.
3. 잔여가치와 deficiency를 적절한 pool에 연결한다.
4. 같은 순위는 계약·법에 따라 pari passu pro rata로 배분한다.
5. guarantee는 guarantor 법인의 별도 waterfall에서 계산하고, 원 obligor와 guarantor의 총회수가 allowed claim을 넘지 않게 cap한다.
6. residual만 equity 또는 parent로 이동한다.

<code>Class distribution = min(available value at class, allowed class claim)</code>

<code>Instrument recovery = total distribution attributable to instrument / allowed instrument claim</code>

<code>Residual value = available value − total distributions</code>

모든 legal entity에서 residual ≥ 0이고, value-level deduction을 포함한 가치 보존이 성립해야 한다.

### 16.7 Recovery 표현

구분:

- nominal recovery at distribution date
- present value of recovery at a declared valuation date
- cash vs new debt/equity securities
- expected vs realized distribution
- prepetition vs postpetition claim

새 증권을 face value로 cash recovery처럼 계산하지 않는다. 선택한 valuation date와 가격 근거를 쓴다.

<code>LGD = 1 − Recovery</code>는 같은 claim basis와 valuation date일 때만 성립한다.

PD가 없으면 recovery range를 expected loss로 바꾸지 않는다.

### 16.8 Jurisdiction

- 미국 case는 [11 U.S.C. §506](https://uscode.house.gov/view.xhtml?edition=prelim&num=0&req=granuleid%3AUSC-prelim-title11-section506), [§507](https://uscode.house.gov/view.xhtml?req=%28title%3A11+section%3A507%28a%29+edition%3Aprelim%29) 외에도 적용 가능한 subordination·setoff·plan·case law를 확인해야 한다.
- 한국 case는 [채무자 회생 및 파산에 관한 법률](https://www.law.go.kr/법령/채무자회생및파산에관한법률)의 기준시점 현행 조문과 실제 절차를 확인한다.
- 담보권 perfection, intercreditor, upstream guarantee 제한은 현지 법률 검토 없이 확정하지 않는다.
- 해외 법인·자산은 각 관할을 별도 node로 둔다.

### 16.9 Recovery state

| 상태 | 의미 |
|---|---|
| PUBLIC_RANGE_SUPPORTED | 법인·claim·가치 range에 공개근거 있음 |
| STRUCTURE_ONLY | priority 구조만 보이고 value range는 미산출 |
| PARTIAL_COLLATERAL_VIEW | 일부 담보만 공개 |
| NOT_OBSERVABLE | 핵심 claim/value가 비공개 |
| LEGAL_REVIEW_REQUIRED | 공개원문만으로 권리 판단 불가 |

NOT_OBSERVABLE은 0% recovery가 아니다.

---

## 17. Rating·spread·market signal comparison

### 17.1 외부 rating 기록

필수 구분:

- agency
- issuer vs issue
- global vs national scale
- local vs foreign currency
- senior secured/unsecured/subordinated
- rating, outlook, watch
- action date와 first public timestamp
- solicited/unsolicited 또는 이용 가능한 status

기관별 letter를 숫자로 평균하지 않는다. national scale을 global scale로 기계 변환하지 않는다.

### 17.2 Rating 사용 원칙

외부 rating은 다음에 쓴다.

- 당시 시장·기관의 공개 관점 기록
- upgrade/downgrade/outlook/watch의 monitoring
- 독립 분석과 차이의 원인 조사
- 공개 methodology의 factor taxonomy 참고

쓰지 않는 것:

- 특정 PD·LGD로 임의 변환
- 공개자료 모델의 agency-equivalent rating 주장
- issuer rating을 issue rating에 복사
- 현재 공개된 지연 rating history를 과거 cutoff에 소급

rating agency는 비공개 management information을 사용할 수 있으므로 P4와 정보집합이 다를 수 있다.

한국 case에서 DART의 발행 당시 등급은 해당 발행시점의 point-in-time 관측으로 쓸 수 있다. 그러나 무료·중앙화된 실시간 ongoing rating-history API가 있다고 가정하지 않는다. CRA 공개 release는 exact publication timestamp와 당시 이용조건을 확인하고, KOFIA의 transition·default 집계는 aggregate sanity check일 뿐 개별기업 rating·recovery input이 아니다.

### 17.3 Market observation

FINRA TRACE는 체결거래의 가격·수익률·거래량을 제공한다. quote가 아니며 거래가 없거나 늦게 보고·정정될 수 있다.

시장 관측마다 보존:

- execution·report·publication timestamp
- clean/dirty price
- accrued interest
- yield convention
- coupon·day count
- maturity·call schedule
- trade volume·flags
- benchmark curve
- currency·seniority
- staleness

### 17.4 Spread

Straight fixed-rate bond:

<code>Simple yield spread = instrument yield − same-currency similar-maturity benchmark yield</code>

settlement date, clean/dirty price와 accrued interest, yield convention, benchmark curve vintage, maturity 또는 duration matching, 필요한 curve interpolation 방법을 observation record에 남긴다.

Option-embedded bond는 OAS가 더 적절할 수 있으나 적절한 option model·curve·data rights가 없으면 계산하지 않는다.

Spread는 다음을 섞는다.

- expected default loss
- uncertainty/risk premium
- liquidity·bid-ask
- option
- tax·technical supply-demand
- benchmark mismatch

따라서 spread를 순수 PD로 해석하지 않는다. 관련 근거는 [CFA Institute, Fixed-Income Active Management: Credit Strategies](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/fixed-income-active-management-credit-strategies)를 참조한다.

### 17.5 Comparable selection

맞출 항목:

- currency
- tenor/duration
- seniority·security
- option
- issuer sector·size·geography
- trade date
- liquidity
- covenant·guarantee

완벽히 맞지 않으면 비교차이를 표로 설명한다. peer spread median을 fair value로 자동 선언하지 않는다.

### 17.6 독립 분석과 외부 신호 비교

| 축 | P4 독립분석 | 외부 rating | market spread |
|---|---|---|---|
| 정보집합 | cutoff 이전 공개자료 | 비공개 정보 포함 가능 | 거래 참여자 정보 |
| 대상 | 명시한 obligor·instrument | issuer/issue·scale별 | 특정 instrument |
| horizon | 명시한 만기·stress | agency 방법론 | 시장 duration·option |
| 결과 | cash gap·condition·range | ordinal opinion | price/yield/spread |
| 주요 한계 | 공개계약·담보 부족 | methodology·lag | liquidity·staleness·risk premium |

차이를 “누가 맞다”로 끝내지 않는다.

설명 후보:

- P4의 더 보수적 accessible cash
- agency가 가진 비공개 정보
- issue seniority·collateral
- market technical·liquidity
- event 이후 공개시차
- 서로 다른 horizon
- option·currency mismatch

### 17.7 Market state

| 상태 | 표현 |
|---|---|
| recent comparable trade | MARKET_SIGNAL_AVAILABLE |
| 오래된·소액 거래 | STALE_OR_THIN_SIGNAL |
| option/curve 불충분 | SPREAD_NOT_COMPARABLE |
| 공개 거래 없음 | NO_PUBLIC_MARKET_SIGNAL |
| license 불명 | QUARANTINED_MARKET_SOURCE |

NO_PUBLIC_MARKET_SIGNAL을 가치 0 또는 default로 해석하지 않는다.

---

## 18. 규제 금융회사·특수 issuer overlay

### 18.1 기본 원칙

은행, 보험, 증권, 여신전문, 자산운용, REIT, 프로젝트파이낸스에는 비금융사의 EBITDA·순차입금 framework를 자동 적용하지 않는다.

이유:

- 이자와 금융부채가 영업활동의 핵심일 수 있다.
- 예금·보험부채·고객자산의 법적 성격이 다르다.
- regulatory capital·liquidity가 지급능력과 영업허가를 좌우한다.
- resolution·policyholder/depositor priority가 일반기업 도산과 다르다.
- asset quality와 duration·market risk가 핵심이다.

### 18.2 은행 overlay

공개 공식자료가 있을 때만:

- CET1, Tier 1, total capital
- RWA와 density
- leverage ratio
- LCR·NSFR
- deposit composition·concentration
- wholesale funding·secured funding
- asset quality, NPL, coverage
- net interest margin·earnings
- securities duration·unrealized loss
- central-bank facility 의존
- resolution entity·TLAC/MREL, 적용 시

[BIS Basel Framework](https://www.bis.org/baselframework/BaselFramework.pdf)는 국제 기준의 reference다. 실제 minimum·buffer·규제조치는 현지 감독규정과 회사 공시를 우선한다.

### 18.3 보험 overlay

- regulatory solvency ratio와 local framework
- liability duration·guarantee
- asset-liability mismatch
- surrender·claim stress
- reinsurance recoverability
- liquidity of invested assets
- holding-company double leverage
- policyholder priority

### 18.4 NBFI·증권 overlay

- secured short-term funding
- margin·haircut·collateral calls
- client asset segregation
- liquidity of inventory
- counterparty concentration
- contingent liquidity
- regulatory net capital

### 18.5 REIT·project finance overlay

- asset/SPV legal ring fence
- debt yield·LTV·DSCR의 실제 계약 정의
- lease/contract tenor와 counterparty
- reserve account·cash waterfall
- completion·construction·offtake
- non-recourse/limited recourse
- valuation·cap rate·asset liquidation

### 18.6 적용 상태

| 상태 | 처리 |
|---|---|
| 공식 sector metric와 공개 원문 충분 | SECTOR_OVERLAY_APPLIED |
| 일부만 공개 | LIMITED_SECTOR_VIEW |
| 핵심 규제·liability 정보 부족 | OUT_OF_SCOPE_FOR_P4_CORE |

ECL allowance를 해당 금융회사 자체의 부도확률로 해석하지 않는다. 내부 PD·LGD·risk grade를 만들지 않는다.

---

## 19. Credit decision memo·monitoring

### 19.1 Decision memo가 답할 질문

1. 누구의 어떤 의무를 어떤 기준시점에서 보는가?
2. 지급재원과 취약성은 무엇인가?
3. base와 downside에서 언제 현금·facility·covenant·maturity constraint가 binding하는가?
4. 차환에 필요한 금액·가격·시점은 무엇인가?
5. 담보·보증·선후순위가 특정 instrument downside를 어떻게 바꾸는가?
6. 외부 rating·spread와 독립 분석은 왜 같은가 또는 다른가?
7. 어떤 조건에서 conclusion이 바뀌는가?
8. 공개자료로 알 수 없는 핵심은 무엇인가?

### 19.2 Memo template

~~~text
TITLE
Credit case / obligor / instrument / perspective / as-of / horizon

MODEL STATE
MODEL_CONDITIONS_MET | MODEL_CONDITIONS_MET_IF | MONITOR_BOUNDARY |
MODEL_CONDITIONS_NOT_MET | INSUFFICIENT_PUBLIC_EVIDENCE

PERSONAL DECISION MAPPING
NOT_MAPPED, 또는 declared mandate·decision policy·risk tolerance가 있을 때만
P4_SUPPORT | P4_SUPPORT_IF | P4_NO_SUPPORT
투자 관점이면 INVEST | WATCH | PASS와 적용 가격·규모·조건

ONE-SENTENCE THESIS
현금창출·만기·구조를 한 문장으로 요약

KEY CONDITIONS
선행조건, 규모, 가격, collateral, covenant, reporting, maturity

BASE
cash trough, facility usage, debt service, maturity/refi, §14 covenant testability state/output

DOWNSIDE / REVERSE
first failure, date, switching variable, gap, action dependency

STRUCTURE / RECOVERY
obligor, guarantee, collateral, priority, public-data recovery state/range

EXTERNAL SIGNALS
rating/outlook/watch, recent comparable market observation, 차이 설명

TOP RISKS
cash transmission과 evidence

STRONGEST COUNTERARGUMENT
결론과 반대되는 가장 강한 공개근거

MONITORING
metric, observable event, source, trigger, action, proposed monitoring role

EVIDENCE GAPS
무엇이 비공개이며 어떤 결론을 제한하는가

DISCLAIMER
개인 공개자료 분석, 실제 승인·rating·법률·투자 의견 아님
~~~

### 19.3 조건부 decision

Personal decision mapping을 할 때는 mandate·risk policy와 조건을 구체적으로 선언한다. MODEL STATE만 보고하는 case에는 “지원/거절”을 억지로 붙이지 않는다.

좋은 예:

- 특정 만기 전까지 문서화된 refinancing이 완료되고 all-in cost가 reverse-stress boundary 안에 있을 것
- PUBLIC_RECALCULATION 상태의 maintenance covenant headroom이 정의된 downside에서도 양수일 것
- 배당·자사주가 cash floor 회복 전까지 중단될 것
- collateral·guarantee 범위가 원문과 일치하고 legal review가 완료될 것
- maturity concentration을 줄이는 tenor가 확보될 것

나쁜 예:

- “시장 상황이 좋아지면”
- “경영진이 잘 실행하면”
- “rating이 유지되면”만 쓰고 contractual transmission을 설명하지 않는 것

### 19.4 Monitoring trigger register

~~~text
trigger_id:
risk_id:
metric_or_event:
definition:
source:
observation_frequency:
current_value:
trigger_basis: contract | public_guidance | history | reverse_boundary | event
trigger_value_or_event:
lead_time_to_failure:
action_on_trigger:
model_state_change:
personal_decision_change_if_mapped:
proposed_monitoring_role:
data_lag:
false_positive_risk:
last_checked:
~~~

### 19.5 Trigger 설계

Trigger는 임의 red/amber/green 숫자가 아니라 다음 중 하나에 연결한다.

- 실제 covenant threshold
- debt-service/maturity 날짜
- facility draw condition
- 공개 guidance 또는 company action
- reverse-stress switching value
- rating-linked margin/collateral
- 근거 있는 cash operating floor
- contract/customer/supplier event
- filing default·acceleration·restructuring event

### 19.6 Monitoring 예시

| Trigger | 관측 | Action |
|---|---|---|
| cash collection deterioration | DSO·receivable aging 공개치 | WC path 재전망, facility gap 갱신 |
| margin compression | price/input 공개 driver | CFADS·coverage 재계산 |
| facility utilization | 공시된 draw와 availability | springing covenant와 exhaustion 갱신 |
| refinancing delay | mandate·offering·settlement event | latest close boundary와 decision 하향 검토 |
| covenant amendment | 원문 effective amendment | old formula 보존, 새 vintage 생성 |
| downgrade/watch | agency release timestamp | 계약상 trigger와 market access 점검 |
| material debt event | DART/8-K/KIND | debt register·cross-default 갱신 |
| asset sale | binding·closing·proceeds | tax·lost cash 포함해 action 반영 |

### 19.7 Monitoring cadence

고정 주기를 보편화하지 않는다.

- payment·covenant·maturity가 가까우면 event-driven/short cadence
- 분기공시가 핵심이면 filing cadence
- 거래가 드문 채권은 “매일 변화 없음”을 신호로 보지 않음
- 공개자료 lag를 trigger register에 반영

### 19.8 Decision log

~~~text
decision_version:
date:
model_state_before:
model_state_after:
personal_decision_before_if_mapped:
personal_decision_after_if_mapped:
new_public_evidence:
model_change:
judgment_change:
quantitative_effect:
strongest_counterargument:
reviewer:
release_hash:
~~~

---

## 20. 검증·outcome analysis·effective challenge

### 20.1 검증 층

| 층 | 질문 |
|---|---|
| source validation | 숫자·문장이 정확한 원문·vintage인가 |
| transformation validation | 통화·단위·기간·scope가 올바른가 |
| accounting reconciliation | financial·cash·debt가 공시와 대사되는가 |
| formula validation | 알려진 input에서 예상 output이 나오는가 |
| stress validation | driver가 모든 재무제표·제약에 일관되게 반영되는가 |
| legal-structure validation | 법인·claim·담보·보증을 중복하지 않는가 |
| decision validation | memo가 model·evidence·한계와 일치하는가 |
| outcome validation | 이후 결과를 hindsight 없이 비교하는가 |

### 20.2 Validation test catalogue

#### A. Source·vintage

- cutoff 이후 자료 차단
- amendment가 원본을 덮지 않음
- source URL·accession·hash 대사
- exact/date-only 공개시각의 conservative rule
- license가 불명인 row release 제외

#### B. Accounting·cash

- cash flow statement와 현금 bridge
- non-cash debt movement
- cash interest와 accrual interest
- tax expense와 cash tax
- working-capital sign
- CFO 내 interest/tax의 이중계상

#### C. Debt·liquidity

- face와 carrying amount bridge
- principal maturity와 IFRS 7 gross cash flow 분리
- RCF draw의 cash/debt/interest/maturity 동시 반영
- restricted/trapped cash 제외
- facility commitment·LC·draw condition
- supplier finance·factoring·lease의 대칭

#### D. Covenant

- maximum/minimum 방향
- testing period·entity·currency
- step-up/down effective date
- add-back cap과 basket
- springing trigger
- public testability 상태
- breach와 EOD 분리

#### E. Stress

- revenue·margin·WC·rate·FX·refi 공동 경로
- P&L·BS·CF 동시 반영
- management action timing·cost
- mutually exclusive action
- reverse solver의 monotonicity가 없을 때 복수해 경고
- arbitrary probability 부재

#### F. Recovery

- legal-entity value conservation
- collateral와 GC EV 중복 방지
- guarantee double recovery cap
- pari passu pro rata
- distribution ≤ allowed claim
- nominal vs PV date
- LGD와 recovery basis 일치

#### G. Market·memo

- issuer/issue·scale·currency 구분
- trade/quote·timestamp·staleness
- curve·option·seniority 비교
- memo 숫자와 release snapshot
- strongest counterargument와 evidence gap 포함

### 20.3 Outcome design

Historical case는 두 파일을 분리한다.

1. <code>EX_ANTE</code>: cutoff 이전 정보와 당시 formula·judgment.
2. <code>OUTCOME</code>: 이후 공개된 실적·지급·차환·covenant·rating·spread·recovery.

Outcome event:

~~~text
outcome_id:
case_version:
event_type:
event_date:
first_public_timestamp:
source_id:
actual_value:
comparable_model_value:
definition_match:
timing_match:
anticipated_by_trigger:
decision_impact:
error_class:
lesson:
model_or_process_change:
~~~

### 20.4 Outcome metric

확률을 예측하지 않았다면 Brier score나 default probability accuracy를 만들지 않는다.

대신:

- cash trough direction과 timing error
- revenue·margin·WC·interest driver error
- actual refinancing amount·cost·tenor·date vs boundary
- subsequently disclosed covenant amendment/breach vs ex-ante trigger
- rating migration/outlook/watch
- comparable spread change와 timestamp
- payment/default/restructuring event
- public-data recovery range vs plan/market/realized distribution, 관측 가능할 때
- false positive·false negative trigger
- decision state가 실제 공개사실로 언제 바뀌었어야 하는가

### 20.5 Attribution

오차를 분리한다.

| Error class | 예 |
|---|---|
| data | source 추출·정정·scope 오류 |
| timing | 공개시각·지급일·closing 지연 |
| formula | cash·interest·covenant 계산 오류 |
| assumption | driver·refi·action 판단 오류 |
| structural | obligor·claim·guarantee 오류 |
| market | liquidity·option·curve mismatch |
| irreducible | 공개자료로 관측 불가능한 사건 |

### 20.6 Effective challenge

Independent reviewer는 core assumption과 model을 직접 만들지 않은 사람이어야 한다.

검토 질문:

- obligor·instrument를 잘못 잡지 않았는가
- cash를 실제보다 많이 쓸 수 있다고 보지 않았는가
- 만기·이자·RCF를 이중계상하지 않았는가
- covenant를 공개정보 이상으로 확정하지 않았는가
- downside를 임의로 골랐는가
- action을 과신했는가
- claim value를 중복했는가
- rating·spread를 결론처럼 복사했는가
- adverse evidence를 누락했는가
- 더 단순한 설명이 있는가

독립 검토자가 없으면 <code>review_state=SELF_REVIEWED_LIMITED_USE</code>로 표시한다. “독립 검증 완료”라고 쓰지 않는다.

### 20.7 Review finding

~~~text
finding_id:
severity: critical | material | improvement
model_or_claim:
evidence:
impact:
required_remediation:
analysis_owner:
due:
resolved:
reviewer:
resolution_evidence:
~~~

critical finding은 점수로 상쇄하지 않는다.

---

## 21. Dependency-based 실행 단계

### 21.1 단계와 선행조건

| 단계 | 작업 | 선행조건 | 산출물 | 종료조건 |
|---|---|---|---|---|
| P4-0 | 관점·case·cutoff 고정 | 목적 정의 | case register | Gate A–H 판정 |
| P4-1 | source·rights 수집 | P4-0 | evidence ledger | cutoff·license complete |
| P4-2 | entity·instrument map | P4-1 | entity/debt graph | obligor scope 잠금 |
| P4-3 | financial normalization | P4-1 | historical model | cash·debt 대사 |
| P4-4 | debt·facility·maturity | P4-2, P4-3 | debt register | principal·interest schedule 대사 |
| P4-5 | base cash model | P4-3, P4-4 | cash/debt-service model | accessible-cash identity residual=0 |
| P4-6 | covenant | current: P4-3·P4-4; projected: P4-5 추가 | testability/public-recalc/proxy register | testability 판정 |
| P4-7 | refi·stress | P4-5, P4-6 | joint/reverse pack | failure boundary 재현 |
| P4-8 | claim·recovery | structure-only: P4-2·P4-4; quantitative: P4-3·P4-7 추가 | structure state 또는 waterfall | quantitative면 value conservation |
| P4-9 | rating·market | P4-1, P4-4 | signal-availability state와 가능한 comparison | type·timestamp·rights 또는 NO_PUBLIC_SIGNAL |
| P4-10 | memo·triggers | 모든 applicable module 또는 N/A 사유 | decision memo·optional executive one-pager | evidence trace complete |
| P4-11 | validation·release | 모든 applicable module + N/A/withheld 사유 | snapshot | gate 결과가 coverage/review/publication state를 결정 |
| P4-12 | outcome | comparable한 이후 공개결과가 있을 때 | filled outcome pack; 없으면 protocol만 | hindsight 분리 |

### 21.2 한국 public-core implementation

| Source | 핵심 용도 | point-in-time·rights rule |
|---|---|---|
| [OpenDART 소개](https://opendart.fss.or.kr/intro/main.do) | 공시·재무·원문 | 무료 API key; 원문·정정 확인 |
| [DART 공시검색 API](https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS001&apiId=2019001) | 접수번호·날짜·정정 | 모든 원본·정정 수집 |
| [DART 원문 다운로드](https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS001&apiId=2019003) | filing 원문 | raw 재배포 권리는 별도 확인 |
| [채무증권 발행실적](https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS002&apiId=2020003) | 발행·금리·만기·등급 | 편의 API를 원문과 대조 |
| [주요사항보고서 API군](https://opendart.fss.or.kr/guide/main.do?apiGrpCd=DS005) | 부도·회생·보증·채무 event | 미발견≠부재 |
| [KIND](https://kind.krx.co.kr/main.do?method=loadInitPage&scrnmode=1) | 거래소 원문·공개시각 교차검증 | 공식 게시·접수시각이 표시될 때만 보강; 없으면 다음 세션 규칙 유지 |
| [KRX 정보데이터시스템](https://data.krx.co.kr/contents/MDC/MAIN/main/index.cmd) | 채권 종목·시세·수익률 | 저장·재배포 약관 확인 |
| [한국은행 통계 공표 일정](https://www.bok.or.kr/portal/main/contents.do?menuNo=200775) | 공식 금리·거시자료 | 원 공표자료·첨부표와 잠정/확정 상태 보존; 현재 시계열을 과거 vintage로 간주하지 않음 |

DART historical 수집은 <code>last_reprt_at=N</code>으로 원본·정정·첨부추가를 모두 보존한다. <code>rcept_dt</code>는 날짜만 제공하므로 정확한 KIND 또는 원문 게시시각 증거가 없으면 strict historical analysis에서 다음 KRX 거래세션부터 사용한다.

금융위원회·KSD 공공 API는 무료 API key와 활용신청이 필요한 비상업 supplement다. 공식 페이지가 밝힌 비실시간 갱신 규칙에 따라 해당 기준일 자료의 <code>first_public_at</code>은 <code>max(다음 영업일 13:00 KST, 실제 최초 성공 수집시각)</code>으로 둔다. 페이지별 공공누리 유형·제3자 권리·상업 이용 제한을 적용하고, P4 공개본에는 원자료를 미러링하지 않는다.

ECOS 현재 조회값은 후일 수정치를 포함할 수 있다. 과거 case에는 당시 보도자료·첨부표를 우선하고 속보·잠정·확정을 서로 다른 revision으로 보존한다. 원 vintage가 없으면 strict historical outcome test에서 제외한다.

### 21.3 미국 public core와 restricted supplement

| Tier | Source | 핵심 용도 | point-in-time·rights rule |
|---|---|---|---|
| core | [SEC EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) | submissions·XBRL fact | 원 accession·filing instance와 대사 |
| core | [SEC Item 601](https://www.ecfr.gov/current/title-17/chapter-II/part-229/subpart-229.600/section-229.601) | indenture·credit agreement·guarantee exhibit | 예외·redaction·미제출 가능성 |
| core | [SEC Item 303](https://www.ecfr.gov/current/title-17/chapter-II/part-229/subpart-229.300/section-229.303) | liquidity·cash requirement | 회사 설명과 수치 연결 |
| core | [Form 8-K](https://www.sec.gov/file/form8-kpdf) | debt·default·bankruptcy event | item·acceptance timestamp 보존 |
| restricted supplement | [FINRA TRACE](https://www.finra.org/filing-reporting/trace) | 체결거래·시장 신호 | trade≠quote; 무료 조회/API의 비상업 조건·정정·재배포 제한, 전체 historical product 유료 |
| core | [U.S. Treasury Daily Rates](https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?page=0&type=daily_treasury_yield_curve) | 공식 benchmark curve | 방법론·조회일 보존 |
| core | [Federal Reserve H.15](https://www.federalreserve.gov/datadownload/choose.aspx?rel=h15) | 공식 금리 cross-check | release timing 보존 |
| core candidate | [GLEIF Golden Copy](https://www.gleif.org/en/lei-data/gleif-golden-copy/download-the-golden-copy) | LEI·parent entity map | [GLEIF 이용조건](https://www.gleif.org/en/meta/lei-data-terms-of-use/)에 따라 필드별 권리 확인 |

EDGAR <code>ACCEPTANCE-DATETIME</code>은 availability proxy이지 실제 최초 공개시각 그 자체가 아니다. 당시 RSS·수집로그의 최초 관측시각이 없는 historical case에서는 동일 세션 장중 사용을 금지하고 다음 거래세션부터 사용한다. 현재 CompanyFacts로 과거 재무를 복원하지 않고 당시 accession의 filing instance를 쓰며, <code>/A</code>는 원본을 덮지 않는 별도 revision으로 둔다. [SEC Developer Resources](https://www.sec.gov/about/developer-resources)의 fair-access rate와 declared user-agent 규칙을 지킨다.

SEC Rule 17g-7 rating-history 파일은 issuer-paid action이 최대 12개월, 그 밖의 action이 최대 24개월 뒤 포함될 수 있다. contemporaneous agency release를 별도로 증명하지 못하면 action date가 아니라 history file의 실제 공개일을 <code>first_public_at</code>으로 쓴다.

### 21.4 Global coverage boundary

P4의 사전 검증된 기본 coverage는 한국 DART issuer, 미국 SEC registrant, SEC에 20-F/6-K를 제출하는 foreign private issuer다. 그 밖의 국가는 회사공시·법원·담보등록·시장자료·이용권리를 국가별로 다시 검증하기 전까지 core 범위로 확장하지 않는다. “글로벌 상장기업 전체 coverage”를 주장하지 않는다.

- ESMA European Rating Platform은 issuer-pay ratings 중심이며 모든 investor-pay rating을 포괄하지 않는다. CRA action date가 아니라 ERP에 실제 공개된 시점을 <code>first_public_at</code>으로 쓰고, 자동수집·재배포 권리는 당시 이용조건을 확인한다.
- GLEIF current Golden Copy의 현재 parent/status를 과거 cutoff에 소급하지 않는다. 당시 snapshot·delta·record history가 없으면 <code>CURRENT_MAPPING_NOT_POINT_IN_TIME</code>으로 표시한다.

### 21.5 core에 ingest·저장하지 않을 source

- [FRED API Terms of Use](https://fred.stlouisfed.org/docs/api/terms_of_use.html)와 [FRED Legal](https://fred.stlouisfed.org/legal/)의 현행 조건상 Content 저장·cache·archive 및 AI 연계가 제한되는 FRED/ALFRED ingest 전체; ICE BofA OAS를 포함한 제3자 시계열은 특히 제외하고 Treasury·Federal Reserve·BOK 등 원 제공기관을 사용
- KRX·SEIBro의 각 약관상 제한 원자료와, 금융위원회·KSD API의 페이지별 공공누리·제3자 권리가 공개를 허용하지 않는 원자료
- FINRA의 라이선스 범위를 넘는 historical feed
- rating report 전문
- issuer 계약서 전문이 공개 artifact 재배포에 부적절한 경우
- PACER와 주별 UCC 검색결과는 민간 접근이 가능해도 계정·건별 비용과 관할별 coverage가 달라 mandatory free core에서 제외

필요하면 사람이 확인할 URL locator만 문서에 남기고, 이용조건이 허용하지 않는 source를 자동 수집·모델 input·AI context로 넣지 않는다. 다른 restricted source는 해당 약관이 transformation·redistribution을 명시적으로 허용한 query, retrieval time, terms version, 최소 파생값만 기록한다. SEC/DART 원문에서 공개된 lien은 <code>disclosed_security</code>로만 기록하며, UCC/PACER 미사용 또는 검색 미발견은 unencumbered·perfected의 증거가 아니다.

### 21.6 Point-in-time eligibility

~~~text
known_at_cutoff =
    first_public_at is not null
    and first_public_at <= analysis_cutoff
~~~

<code>event_at</code>, reporting period end, rating action date를 <code>first_public_at</code> 대신 쓰지 않는다.

필수 필드는 §5.2의 canonical evidence/source ledger 하나에서 관리한다. 별도 축약 schema를 만들어 drift시키지 않는다.

### 21.7 첫 구현의 적정 범위

첫 구현은 [JUDG] Gate A–H를 통과한 기업 obligor case 하나에 집중해도 충분하다. 비금융 일반기업은 core example이고, 금융·REIT·PF를 택하면 §18 overlay가 선행한다. case 수는 통과기준이 아니라 scope control이며, instrument는 공개증거가 있는 범위만 포함한다.

- 공개 사채 또는 대출 instrument의 확인 가능한 universe
- 연간·중간 공시의 역사재무
- instrument별 debt·interest·maturity
- base, evidence-backed downside, reverse stress
- covenant public recalculation은 계약원문과 모든 material component가 공개될 때만
- recovery는 structure-only도 허용
- rating·market signal은 public/right-cleared observation만
- concise decision memo와 trigger register
- synthetic known-answer test와 independent review

“사례 수”를 성과로 과장하지 않는다. 한 case라도 evidence와 구조가 완전한 편이 낫다.

---

## 22. 비보상적 release gate

### R1 — Public access·rights

- 모든 core input이 민간 개인에게 무료·합법적으로 접근 가능
- access·retention·transformation·redistribution 기록
- 제한 source raw data가 release에 없음

실패: <code>QUARANTINED_SOURCE</code> 또는 release 중단.

### R2 — Cut-off·vintage

- 모든 material fact에 first_public_at
- amendment/restatement가 별도 version
- outcome data가 ex-ante에 없음

실패: historical claim과 outcome validation 금지.

### R3 — Credit scope

- perspective, obligor, instrument, legal entity, jurisdiction, currency 고정
- issuer와 issue risk 분리
- consolidated와 legal claim 구분

실패: instrument decision 금지.

### R4 — Accounting·cash integrity

- cash·financial statements 대사
- CFO/interest/tax/WC 이중계상 없음
- accessible cash classification 완료
- profitability trend·volatility와 EBITDA→CFADS cash-conversion bridge 완료

실패: capacity와 liquidity 결론 금지.

### R5 — Debt·maturity·facility

- face/carrying bridge
- principal maturity와 gross contractual cash flow 분리
- facility availability 조건 표시
- lease·supplier finance·factoring 대칭
- applicable fixed-charge coverage의 정의·component bridge 또는 N/A/미산출 사유

실패: refinancing 결론 제한.

### R6 — Covenant

- exact definition·amendment·test date 공개 또는 testability 명시
- analyst proxy가 PUBLIC_RECALCULATION·ISSUER_REPORTED 상태와 분리
- breach·EOD·acceleration 분리

실패: covenant headroom을 <code>NOT_TESTABLE</code>로 강등.

### R7 — Stress·reverse stress

- shock가 evidence-backed
- driver path와 correlation 일관
- management action 분리
- reverse boundary와 failure date 재현
- ISSUER_GUIDANCE_PATH와 ANALYST_BASE 분리·gap 설명

실패: downside decision 금지.

### R8 — Claim·recovery

- legal entity·collateral·guarantee·priority·jurisdiction 증거
- value·claim 이중계상 없음
- waterfall value conservation

실패: <code>STRUCTURE_ONLY</code> 또는 <code>NOT_OBSERVABLE</code>.

### R9 — Rating·market independence

- issuer/issue·scale·timestamp 구분
- trade/quote·option·liquidity·license 표시
- 외부 signal을 결론으로 복사하지 않음

실패: market comparison 제외.

### R10 — Validation·effective challenge

- known-answer·reconciliation·edge case 통과
- core builder와 분리된 reviewer
- finding 해결

실패: <code>review_state=SELF_REVIEWED_LIMITED_USE</code> 또는 <code>publication_state=WITHHELD</code>.

### R11 — Claim integrity·publication

- memo 숫자와 snapshot 일치
- adverse evidence·counterargument·한계 포함
- 실제 승인·등급·법률·투자성과 과장 없음
- FinDone 외부사용자 성과를 암시하지 않음
- issuer guidance를 analyst best estimate로 가장하지 않음

실패: 공개 금지.

Gate는 비보상적이다. 다른 강점이나 총점으로 critical failure를 덮지 않는다.

---

## 23. 산출물·폴더·release snapshot

### 23.1 권장 폴더

~~~text
P4_credit_stress_pack/
├─ README.md
├─ case/
│  ├─ case_register.csv
│  ├─ decision_log.csv
│  └─ limitations.md
├─ sources/
│  ├─ source_ledger.csv
│  ├─ license_ledger.csv
│  └─ locators/
├─ data/
│  ├─ entities.csv
│  ├─ financials_normalized.csv
│  ├─ debt_facilities.csv
│  ├─ maturities.csv
│  ├─ covenants.csv
│  ├─ collateral_claims.csv
│  └─ market_observations.csv
├─ model/
│  ├─ base/
│  ├─ stress/
│  ├─ recovery/
│  └─ checks/
├─ output/
│  ├─ credit_memo.md
│  ├─ monitoring_triggers.csv
│  ├─ charts/
│  └─ release_snapshot.json
├─ tests/
│  ├─ synthetic_known_answers/
│  └─ regression/
└─ review/
   ├─ review_findings.csv
   └─ release_checklist.md
~~~

### 23.2 필수 산출물

“필수”는 모든 모듈에서 상태·N/A 이유를 내야 한다는 뜻이다. 공개증거가 없는 exact calculator, market observation, quantitative recovery, filled outcome을 억지로 생성한다는 뜻이 아니다.

1. credit question·scope page
2. business·industry·governance risk map
3. legal entity·obligor·guarantor·security map
4. debt bridge·facility·maturity wall
5. historical financial·cash reconciliation
6. integrated cash/debt-service schedule
7. liquidity sources-and-uses
8. covenant testability register; 원문·input이 충분할 때만 PUBLIC_RECALCULATION, 근거가 있을 때만 명시된 proxy sensitivity
9. refinancing monitor와 external-signal availability state; rights-cleared rating·spread가 있을 때만 market monitor
10. joint downside·reverse stress
11. recovery evidence state; 조건이 충족될 때 public-data waterfall, 아니면 structure-only/NOT_OBSERVABLE note
12. 충분성 기준을 충족한 decision memo와 optional executive one-pager
13. monitoring trigger register
14. evidence·assumption·license·decision log
15. validation·review와 outcome protocol; 이후 comparable public outcome이 있을 때만 filled outcome pack

### 23.3 Release snapshot

~~~text
release_id:
case_version:
cutoff_timestamp:
model_version:
scenario_version:
coverage_state: FULL_PUBLIC_PACK | LIMITED_PUBLIC_PACK | FEASIBILITY_ONLY
review_state: INDEPENDENTLY_REVIEWED | SELF_REVIEWED_LIMITED_USE
publication_state: RELEASED | WITHHELD
source_snapshot_hash:
input_hash:
formula_or_code_hash:
output_hash:
memo_hash:
gate_results:
reviewer:
known_limitations:
released_at:
~~~

snapshot 이후 source·formula·judgment가 바뀌면 새 release다.

---

## 24. 관련 직무별 변형

### 24.1 Credit RA·대출심사

강조:

- obligor와 repayment source
- facility·collateral·guarantee
- covenant·condition precedent
- cash debt capacity
- conditional terms와 monitoring

산출물: lender-style memo와 conditions precedent/checklist. 실제 승인 권한은 주장하지 않는다.

### 24.2 Credit Risk

강조:

- risk identification
- early-warning trigger
- stress path
- exposure·concentration, 공개 가능한 범위
- model limitation·validation

PD·LGD를 임의 산출하지 않고 cash/covenant/recovery range로 제한한다.

### 24.3 채권 리서치

강조:

- issuer vs issue
- capital structure와 relative value
- option·liquidity·spread
- catalyst·rating migration
- downside recovery와 timing

시장가격은 투자추천이 아니라 비교관측으로 제시한다.

### 24.4 Corporate Treasury

강조:

- maturity ladder
- cash pooling·trapped cash
- committed facility
- interest·FX hedge
- covenant·rating trigger
- refinancing lead time와 action ladder

### 24.5 FP&A

강조:

- operating driver와 cash conversion
- WC·capex·minimum cash
- reforecast
- debt-service capacity
- capital allocation constraint

### 24.6 CEO Staff·Strategy RA

강조:

- operating decision이 liquidity·covenant·funding에 미치는 영향
- M&A·투자·배당·자산매각의 credit consequence
- downside에서 먼저 중단할 action
- CEO/Board용 조건부 의사결정과 monitoring

### 24.7 프로젝트가 주는 역량 신호

| 역량 | P4에서 증명하는 행동 |
|---|---|
| research | 원문·계약·시장자료를 cutoff 기준으로 연결 |
| finance | accounting earnings를 debt-service cash로 변환 |
| risk | joint/reverse stress와 trigger 설계 |
| judgment | 공개정보 한계에서 결론 범위를 통제 |
| structuring | obligor·guarantee·collateral·priority 구분 |
| communication | evidence와 조건을 압축한 decision memo |
| validation | reconciliation·known-answer·effective challenge |

---

## 25. 이력서·면접·FinDone 연결

### 25.1 사실에 맞는 이력서 표현

허용:

- “공개 공시와 채무 문서를 기반으로 기업의 현금흐름·만기·차환·약정·claim 구조를 연결하는 P4 credit stress pack을 설계”
- “고정 leverage/DSCR 문턱 대신 계약조건과 reverse-stress switching value로 failure boundary를 산출”
- “DART/EDGAR 원문, 공식 금리, 이용권한이 확인된 시장 관측을 point-in-time evidence ledger로 관리”
- “합성 known-answer test로 cash·debt·covenant·waterfall 계산을 검증”

금지:

- “실제 기업 대출을 승인”
- “기관 수준 내부등급 개발”
- “PD/LGD 모델 검증”
- “확정 회수율 산출”
- “Bloomberg 등 접근하지 않은 데이터 사용”
- “FinDone의 외부 사용자 성과”

### 25.2 면접 설명 구조

1. **문제:** 회계이익·외부등급만으로는 지급시점과 claim downside가 보이지 않는다.
2. **범위:** 민간이 확보 가능한 공개자료만 사용했다.
3. **구조:** obligor → cash → debt/maturity → covenant/refi → stress → recovery.
4. **판단:** 임의 threshold 대신 actual contract와 reverse boundary를 썼다.
5. **통제:** vintage·license·reconciliation·independent review.
6. **한계:** 비공개 covenant·lien·bank facility는 미산출했다.
7. **직무 연결:** Credit RA, risk, treasury, FP&A, CEO staff의 공통 의사결정 언어를 만들었다.

### 25.3 FinDone 연결

FinDone은 사용자가 자신을 위해 만든 제품이라는 사실만 쓴다.

가능한 연결:

- P4의 evidence ledger·versioning 원칙을 개인 금융 의사결정 기록에 적용
- cash·debt identity와 source trace를 제품 설계 역량의 예로 설명
- public-only·privacy-aware data handling을 설계 원칙으로 연결

연결하지 않을 것:

- 외부 고객의 신용평가
- 규제기관 승인
- 대출중개·투자자문 성과
- 외부 사용자 검증·성장지표

### 25.4 포트폴리오 공개 수준

공개본:

- 설계서
- source locator
- synthetic test
- 허용된 파생지표
- limitation·disclaimer

비공개 또는 제외:

- 라이선스 제한 raw data
- 대량 원문 미러
- 비밀키
- 법률결론으로 오인될 detail
- 개인식별정보

---

## 26. 첫 실행 체크리스트

### 26.1 Scope·권리

- [ ] 분석 관점 하나를 선택했다.
- [ ] obligor·issuer·instrument·jurisdiction·currency를 고정했다.
- [ ] cutoff timestamp와 정보공개 판정 규칙을 고정했다.
- [ ] core source가 모두 민간 개인에게 무료·합법적으로 접근 가능하다.
- [ ] 무료 API key·회원가입 절차를 README에 적었다.
- [ ] 저장·가공·재배포 권리를 source별로 확인했다.
- [ ] 상용자료 없이도 core output이 재현된다.
- [ ] 합성자료는 test fixture에만 있다.
- [ ] “공시에서 미발견”과 “존재하지 않음”을 구분했다.

### 26.2 Source·vintage

- [ ] 모든 material claim에 URL·accession·원문 위치가 있다.
- [ ] filed/published/effective/retrieved timestamp를 분리했다.
- [ ] <code>first_public_at</code>이 cutoff 이전인지 검사했다.
- [ ] 원본·정정·restatement를 덮어쓰지 않았다.
- [ ] SEC XBRL·OpenDART API를 원문 주석·exhibit와 대사했다.
- [ ] exact 공개시각이 없을 때 conservative next-session rule을 썼다.
- [ ] rating history 지연공개를 과거에 소급하지 않았다.
- [ ] 시장관측의 execution/report/correction 시각을 구분했다.

### 26.3 Entity·instrument

- [ ] group·parent·opco·financeco·JV를 구분했다.
- [ ] 실제 지급의무자와 증권 발행자를 구분했다.
- [ ] guarantor·collateral provider와 범위를 적었다.
- [ ] cash가 있는 법인과 debt가 있는 법인을 매핑했다.
- [ ] upstream restriction·minority·regulation을 확인했다.
- [ ] 연결자산을 모든 creditor의 공통 pool로 쓰지 않았다.
- [ ] structural subordination을 검토했다.

### 26.4 Accounting·cash

- [ ] 원재무가 filing과 대사된다.
- [ ] reported→normalized profitability와 trend·volatility driver가 있다.
- [ ] EBITDA→CFADS cash-conversion bridge가 component별로 대사된다.
- [ ] 현금 roll-forward가 0으로 대사된다.
- [ ] EBITDA adjustment마다 cash·recurrence·evidence가 있다.
- [ ] CFO에서 interest·tax·WC를 두 번 조정하지 않았다.
- [ ] cash interest와 accrual interest를 분리했다.
- [ ] cash tax와 tax expense를 분리했다.
- [ ] essential·committed·discretionary capex를 구분했다.
- [ ] restricted·trapped·customer·regulatory cash를 accessible cash에서 제외했다.
- [ ] 최소 운영현금을 발명하지 않고 range/switching으로 제시했다.

### 26.5 Debt·facility·maturity

- [ ] face principal와 carrying amount bridge가 각각 대사된다.
- [ ] draw·PIK·FX·repayment가 instrument별로 연결된다.
- [ ] fixed/floating·reset·margin·floor/cap·hedge를 반영했다.
- [ ] nominal undrawn과 drawable facility를 분리했다.
- [ ] LC·borrowing base·covenant·maturity 조건을 반영했다.
- [ ] principal maturity와 IFRS 7 gross contractual cash flow를 합산하지 않았다.
- [ ] broad bucket을 임의로 annualize하지 않았다.
- [ ] lease·supplier finance·factoring을 대칭적으로 처리했다.
- [ ] RCF draw가 cash/debt/interest/maturity에 동시에 반영된다.

### 26.6 Liquidity·capacity

- [ ] source와 use가 시점·법인·통화별로 대사된다.
- [ ] uncommitted refinancing·asset sale·equity를 pre-mitigation source로 넣지 않았다.
- [ ] cash trough와 first shortfall date를 출력했다.
- [ ] annual ratio와 intra-period cash를 함께 봤다.
- [ ] metric dictionary가 numerator·denominator·scope를 정의한다.
- [ ] applicable fixed-charge coverage의 unique charge, add-back, N/A 사유가 있다.
- [ ] EBITDA≤0 또는 denominator 불능을 <code>NM</code> 처리했다.
- [ ] additional debt의 proceeds뿐 아니라 interest·maturity·covenant를 반영했다.
- [ ] model-implied incremental debt boundary를 실제 financing availability로 표현하지 않았다.
- [ ] horizon 밖 maturity/terminal refinancing이 정의되지 않으면 NOT_MEASURABLE로 뒀다.

### 26.7 Covenant

- [ ] maintenance/incurrence/springing/draw condition을 구분했다.
- [ ] testing entity·period·definition·threshold·effective date를 원문으로 확인했다.
- [ ] add-back·cap·basket·step·cure·waiver를 확인했다.
- [ ] maximum/minimum headroom 방향이 맞다.
- [ ] PUBLIC_RECALCULATION·ISSUER_REPORTED·ANALYST_PROXY 상태를 분리했다.
- [ ] 불완전 공개 시 <code>NOT_TESTABLE_FROM_PUBLIC_DATA</code>를 썼다.
- [ ] breach·EOD·acceleration을 구분했다.
- [ ] issuer-disclosed compliance를 headroom 수치로 바꾸지 않았다.

### 26.8 Stress·refinancing

- [ ] revenue·margin·WC·rate·FX·refi를 공동 stress했다.
- [ ] ISSUER_GUIDANCE_PATH와 ANALYST_BASE를 별도 version으로 두고 gap을 설명했다.
- [ ] shock path가 공개 역사·공식자료·계약 또는 switching value에 근거한다.
- [ ] scenario가 P&L·BS·cash·debt·covenant에 동시에 반영된다.
- [ ] refinancing amount·cost·tenor·timing·fee·collateral을 반영했다.
- [ ] market closure 또는 partial refinancing 경로를 필요 시 검토했다.
- [ ] reverse endpoint와 failure date를 명시했다.
- [ ] management action을 A/B/C class로 나눴다.
- [ ] action의 비용·시차·선행조건·영업영향을 반영했다.
- [ ] 상호 배타적 action을 동시에 쓰지 않았다.
- [ ] arbitrary shock probability를 쓰지 않았다.

### 26.9 Recovery

- [ ] legal entity별 value와 claim을 분리했다.
- [ ] collateral asset owner·lien rank·prior claim을 확인했다.
- [ ] guarantee scope·cap·expiry를 확인했다.
- [ ] going-concern과 liquidation 근거를 구분했다.
- [ ] EV와 collateral value를 중복하지 않았다.
- [ ] 같은 guarantee를 두 entity에서 중복 회수하지 않았다.
- [ ] guarantee/debt-like obligation이 contingent와 crystallized state에 동시에 존재하지 않는다.
- [ ] ongoing cash reduction과 crystallized claim을 동시에 반영하지 않았다.
- [ ] distribution 합계가 available value를 넘지 않는다.
- [ ] instrument recovery가 allowed claim을 넘지 않는다.
- [ ] nominal과 PV recovery의 valuation date를 명시했다.
- [ ] 공개근거 부족 시 range를 보류했다.
- [ ] recovery range를 PD 없는 expected loss로 바꾸지 않았다.

### 26.10 Rating·market

- [ ] issuer/issue·scale·currency·seniority를 구분했다.
- [ ] rating/outlook/watch/action date를 구분했다.
- [ ] 외부 rating을 자체 결론이나 PD로 복사하지 않았다.
- [ ] trade와 quote를 구분했다.
- [ ] spread comparison의 curve·tenor·option·liquidity를 맞췄다.
- [ ] stale/thin/no-signal 상태를 표시했다.
- [ ] raw market data의 license를 확인했다.
- [ ] 외부 신호와 독립 분석의 차이를 설명했다.

### 26.11 Memo·review·outcome

- [ ] memo에 perspective·as-of·horizon이 있다.
- [ ] decision이 개인 분석 상태로 표현됐다.
- [ ] 조건·trigger·action·owner가 연결된다.
- [ ] strongest counterargument를 숨기지 않았다.
- [ ] evidence gap과 판단범위를 분리했다.
- [ ] memo 숫자와 release snapshot이 일치한다.
- [ ] synthetic known-answer test가 통과했다.
- [ ] 독립 reviewer가 core model을 만들지 않았다.
- [ ] 독립 reviewer가 없으면 limited-use라 표시했다.
- [ ] ex-ante와 outcome 파일이 분리됐다.
- [ ] 이후 실적·spread·rating migration에 hindsight가 없다.
- [ ] 실제 승인·rating·법률의견·투자성과를 주장하지 않았다.
- [ ] FinDone 외부 사용자·성장 성과를 만들지 않았다.

---

## 27. 참고문헌·공식 데이터

### 27.1 사용자 요구와 프로젝트 정의

- [Notion — 스타트업 지원](https://app.notion.com/p/3cc05897114081cf94f9e5cec240ab74) [USER]: P4의 핵심 질문, 산출물, 검증기준, 관련 직무를 정의한 private project provenance. public portfolio snapshot에서는 이 private link를 제거하고 본 문서에 요약된 사용자 제약만 남긴다.

### 27.2 Corporate credit·forecast·liquidity

- [CFA Institute — Credit Analysis for Corporate Issuers](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/credit-analysis-for-corporate-issuers) [STD]: business·industry·governance와 profitability·liquidity·leverage·coverage, issuer/issue 구분.
- [CFA Institute — Credit Risk](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/credit-risk) [STD]: PD·LGD·EAD·expected loss 개념과 한계.
- [CFA Institute — Credit Analysis Models](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/credit-analysis-models) [STD]: 신용모형·transition·spread 해석.
- [CFA Institute — Financial Analysis Techniques](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/financial-analysis-techniques) [STD]: ratio·trend·comparison의 계산과 해석.
- [CFA Institute — Working Capital and Liquidity](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/working-capital-and-liquidity) [STD]: 영업주기·유동성·working capital.
- [CFA Institute — Company Analysis: Forecasting](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/company-analysis-forecasting) [STD]: driver-based forecast.
- [CFA Institute — Fixed-Income Markets for Corporate Issuers](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/fixed-income-markets-for-corporate-issuers) [STD]: issuer funding instruments와 조달.
- [CFA Institute — Fixed-Income Active Management: Credit Strategies](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/fixed-income-active-management-credit-strategies) [STD]: spread·OAS·credit/liquidity signal.
- [CFA Institute — Financial Reporting Quality](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/financial-reporting-quality) [STD]: 회계정책·추정·보고품질.
- [CFA Institute — Analysis of Financial Institutions](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/analysis-of-financial-institutions) [STD]: 금융회사 별도 분석.

### 27.3 Accounting·disclosure

- [IFRS Foundation — IAS 7 Statement of Cash Flows](https://www.ifrs.org/issued-standards/list-of-standards/ias-7-statement-of-cash-flows/) [STD].
- [IFRS Foundation — IFRS 9 Financial Instruments](https://www.ifrs.org/issued-standards/list-of-standards/ifrs-9-financial-instruments/) [STD]: effective interest, modification·derecognition, carrying-amount bridge.
- [IFRS Foundation — IFRS 7 Financial Instruments: Disclosures](https://www.ifrs.org/issued-standards/list-of-standards/ifrs-7-financial-instruments-disclosures/) [STD].
- [IFRS Foundation — IAS 1 Presentation of Financial Statements](https://www.ifrs.org/issued-standards/list-of-standards/ias-1-presentation-of-financial-statements/) [STD].
- [IFRS Foundation — IFRS 16 Leases](https://www.ifrs.org/issued-standards/list-of-standards/ifrs-16-leases/) [STD].
- [IFRS Foundation — IAS 37 Provisions, Contingent Liabilities and Contingent Assets](https://www.ifrs.org/issued-standards/list-of-standards/ias-37-provisions-contingent-liabilities-and-contingent-assets/) [STD].
- [IFRS Foundation — Supplier Finance Arrangements amendments](https://www.ifrs.org/news-and-events/news/2023/05/iasb-increases-transparency-of-companies-supplier-finance/) [STD].
- [IFRS Foundation — Going concern educational material](https://www.ifrs.org/content/dam/ifrs/supporting-implementation/educational-materials/going-concern-2025.pdf) [STD]: going-concern assessment와 disclosure 참고.

### 27.4 공개 credit methodology 참고

- [S&P Global Ratings — Corporate Method](https://spratings.spglobal.com/ratings/en/regulatory/article/-/view/sourceId/10906146) [PROPRIETARY_METHODOLOGY_REFERENCE]: agency 정의를 직접 적용할 때만 사용; 적용본 날짜·scope를 ledger에 기록하고 P4 자체 metric과 동일하다고 주장하지 않음.
- [Fitch Ratings — Corporate Rating Criteria](https://assets.fitchratings.com/downloadFile?reportType=report&sfReport=false&slug=corporate-finance/corporate-rating-criteria-09-01-2026) [PROPRIETARY_METHODOLOGY_REFERENCE]: FFO·CFO·FCF·liquidity 등 agency framework 참고.
- [Fitch Ratings — Corporate Recovery Ratings and Instrument Ratings Criteria](https://assets.fitchratings.com/downloadFile?reportType=report&sfReport=false&slug=corporate-finance/corporate-recovery-ratings-instrument-ratings-criteria-02-08-2024) [PROPRIETARY_METHODOLOGY_REFERENCE]: going-concern/liquidation, claim·priority waterfall 참고.
- [Fitch Ratings — Rating Definitions](https://www.fitchratings.com/products/rating-definitions) [PROPRIETARY_METHODOLOGY_REFERENCE]: rating이 ordinal opinion이며 특정 PD/LGD·시장가격과 동일하지 않다는 경계; 조회일과 적용 edition 기록.

agency 자료는 locator와 허용된 짧은 해석만 남긴다. 숫자·문턱·adjustment를 출처 없이 복제하지 않고 적용본의 날짜·scope·license를 case별로 다시 확인한다.

### 27.5 Stress·model governance

- [UK Financial Reporting Council — Guidance on the Going Concern Basis of Accounting](https://www.frc.org.uk/library/standards-codes-policy/accounting-and-reporting/annual-corporate-reporting/guidance-on-going-concern-basis/) [STD]: stress·sensitivity·reverse-stress 기법 참고; 영국 외 법적 의무로 확장하지 않음.
- [HM Treasury — The Green Book 2026](https://www.gov.uk/government/publications/the-green-book-appraisal-and-evaluation-in-central-government/the-green-book-2026) [STD]: uncertainty와 switching-value 기법 참고.
- [ICAEW — 20 Principles for Good Spreadsheet Practice](https://www.icaew.com/technical/technology/excel-community/20-principles-for-good-spreadsheet-practice-2024-edition) [STD]: spreadsheet 구조·review.
- [Federal Reserve — Supervisory Guidance on Model Risk Management](https://www.federalreserve.gov/frrs/guidance/supervisory-guidance-on-model-risk-management.htm) [STD]: 목적·한계·validation·ongoing monitoring의 참고; P4에 직접 적용되는 규제의무라고 주장하지 않음.

### 27.6 한국 공식 public source와 restricted supplement

- [OpenDART 소개](https://opendart.fss.or.kr/intro/main.do) [EVID].
- [OpenDART 공시검색 API](https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS001&apiId=2019001) [EVID].
- [OpenDART 공시 원문 다운로드](https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS001&apiId=2019003) [EVID].
- [OpenDART 채무증권 발행실적](https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS002&apiId=2020003) [EVID].
- [OpenDART 채무증권 증권신고서 정보](https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS006&apiId=2020055) [EVID].
- [OpenDART 부도발생](https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS005&apiId=2020019) [EVID].
- [OpenDART 회생절차 개시신청](https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS005&apiId=2020021) [EVID].
- [OpenDART 주요사항보고서 API군](https://opendart.fss.or.kr/guide/main.do?apiGrpCd=DS005) [EVID].
- [OpenDART 이용약관](https://opendart.fss.or.kr/intro/terms.do) [STD].
- [KRX KIND](https://kind.krx.co.kr/main.do?method=loadInitPage&scrnmode=1) [EVID].
- [KRX 정보데이터시스템](https://data.krx.co.kr/contents/MDC/MAIN/main/index.cmd) [EVID] — restricted supplement.
- [KRX 정보이용 조건](https://data.krx.co.kr/contents/MDC/INFO/informationController/MDCINFO003.cmd) [STD].
- [금융위원회·KSD 채권기본정보 API](https://www.data.go.kr/data/15059592/openapi.do) [EVID] — restricted supplement; API key·다음 영업일 13시 갱신·비상업 조건 확인.
- [금융위원회·KSD 채권발행정보 API](https://www.data.go.kr/data/15043421/openapi.do) [EVID] — restricted supplement.
- [금융위원회·KSD 채권권리행사정보 API](https://www.data.go.kr/data/15059595/openapi.do) [EVID] — restricted supplement.
- [SEIBro 채권 일정](https://m.seibro.or.kr/cnts/bond/selectBondSchedule.do) [EVID] — restricted supplement.
- [한국은행 통계 공표 일정](https://www.bok.or.kr/portal/main/contents.do?menuNo=200775) [EVID].
- [KOFIA 신용평가 실적 공시 기준](https://law.kofia.or.kr/service/law/detailArticlePrint.do?contentSeq=301663&historySeq=1773&seq=342) [STD]: aggregate rating transition·default 자료의 범위 참고; 개별기업 input으로 대체하지 않음.

### 27.7 미국 공식 public core와 restricted supplement

- [SEC EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) [EVID].
- [SEC Developer Resources](https://www.sec.gov/about/developer-resources) [STD]: fair-access와 user-agent 규칙.
- [SEC Webmaster FAQ](https://www.sec.gov/about/webmaster-frequently-asked-questions) [STD]: filing availability timestamp·reuse 경계.
- [SEC Search Filings](https://www.sec.gov/search-filings) [EVID].
- [SEC Form 8-K](https://www.sec.gov/file/form8-kpdf) [STD].
- [SEC Regulation S-K Item 303](https://www.ecfr.gov/current/title-17/chapter-II/part-229/subpart-229.300/section-229.303) [STD].
- [SEC Regulation S-K Item 601](https://www.ecfr.gov/current/title-17/chapter-II/part-229/subpart-229.600/section-229.601) [STD].
- [SEC Non-GAAP Financial Measures C&DIs](https://www.sec.gov/rules-regulations/staff-guidance/corporation-finance-interpretations/non-gaap-financial-measures) [STD]: covenant non-GAAP disclosure와 reconciliation 참고.
- [FINRA TRACE](https://www.finra.org/filing-reporting/trace) [EVID] — restricted supplement.
- [FINRA — What Is TRACE?](https://www.finra.org/investors/insights/what-is-TRACE) [STD].
- [FINRA — About Trade Activity](https://www.finra.org/finra-data/fixed-income/about-trade-activity) [STD].
- [FINRA — Corporate and Agency Bond Data](https://www.finra.org/finra-data/fixed-income/about-cna-data) [STD].
- [FINRA Fixed Income Data Terms](https://developer.finra.org/specific-terms-fixed-income-data) [STD] — 비상업 이용·재배포 조건 확인.
- [U.S. Treasury Daily Treasury Rates](https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?page=0&type=daily_treasury_yield_curve) [EVID].
- [Federal Reserve H.15](https://www.federalreserve.gov/datadownload/choose.aspx?rel=h15) [EVID].
- [SEC — Current NRSROs](https://www.sec.gov/about/divisions-offices/office-credit-ratings/current-nrsros) [STD].
- [SEC — Disclosure of Credit Rating Histories](https://www.sec.gov/about/divisions-offices/office-credit-ratings/disclosure-of-credit-rating-histories) [STD].
- [SEC — Rating History Files Publication Guide](https://www.sec.gov/data-research/structured-data/rating-history-files-publication-guide) [STD].

### 27.8 Entity·global·market 보강

- [GLEIF Golden Copy](https://www.gleif.org/en/lei-data/gleif-golden-copy/download-the-golden-copy) [EVID].
- [GLEIF LEI Data Terms of Use](https://www.gleif.org/en/meta/lei-data-terms-of-use/) [STD].
- [ESMA Databases and Registers](https://www.esma.europa.eu/publications-and-data/databases-and-registers) [EVID].
- [ESMA European Rating Platform background](https://www.esma.europa.eu/press-news/esma-news/esma-provide-free-credit-ratings-information-public) [STD].
- [ESMA — Access and use of credit ratings opinion](https://www.esma.europa.eu/sites/default/files/library/esma80-196-5819_opinion_on_access_and_use_of_credit_ratings.pdf) [STD]: ERP coverage·공개시점 해석.
- [Bank of England — Decomposing corporate bond spreads](https://www.bankofengland.co.uk/quarterly-bulletin/2007/q4/decomposing-corporate-bond-spreads) [STD]: spread가 expected loss 외 요소를 포함하는 분석.
- [FRED API Terms of Use](https://fred.stlouisfed.org/docs/api/terms_of_use.html), [FRED Legal](https://fred.stlouisfed.org/legal/) [STD]: P4 core에 FRED/ALFRED를 ingest하지 않고 원 제공기관을 쓰는 exclusion 근거.

### 27.9 Claim·recovery 법적 reference

- [11 U.S.C. §506 — Determination of secured status](https://uscode.house.gov/view.xhtml?edition=prelim&num=0&req=granuleid%3AUSC-prelim-title11-section506) [STD].
- [11 U.S.C. §507 — Priorities](https://uscode.house.gov/view.xhtml?req=%28title%3A11+section%3A507%28a%29+edition%3Aprelim%29) [STD].
- [국가법령정보센터 — 채무자 회생 및 파산에 관한 법률](https://www.law.go.kr/법령/채무자회생및파산에관한법률) [STD].
- [PACER Case Locator](https://pacer.uspci.uscourts.gov/pcl/index.xhtml?faces-redirect=true), [New York UCC FAQ](https://dos.ny.gov/ucc-frequently-asked-questions), [Texas UCC fee schedule](https://www.sos.state.tx.us/ucc/formfees.shtml) [STD]: 민간 접근은 가능하지만 계정·비용·관할별 coverage 때문에 mandatory free core에서 제외.

적용 법령은 case cutoff의 현행본과 관할을 다시 확인한다. 이 설계서는 법률의견이 아니다.

---

## 28. 최종 주장 경계와 Disclaimer

### 28.1 Claim integrity 문구

완성본 첫 화면과 memo 끝에 다음을 넣는다.

> 이 자료는 기준시점까지 민간이 접근 가능한 공개정보로 수행한 개인 desktop credit analysis다. 실제 금융기관의 승인, 내부등급, 규제자본 산정, 법률의견, 담보평가 또는 투자권유가 아니다. 공개되지 않은 차입·약정·담보·보증·법적 권리 때문에 결론 범위가 제한될 수 있다. 외부 등급과 시장가격은 독립 분석을 보조하는 관측치이며 결론을 대체하지 않는다.

### 28.2 결과 표현

허용:

- 공개자료 기반 cash shortfall boundary
- 공개된 실제 covenant의 재현 가능한 headroom
- evidence-backed refinancing need와 break-even
- illustrative public-data recovery range
- external signal과 독립분석의 차이
- conditional personal analyst state

금지:

- 실제 승인·거절 결정
- agency-equivalent rating
- 근거 없는 PD·LGD·expected loss
- 확정 collateral priority·legal enforceability
- guaranteed refinancing·sponsor support
- public data로 완전한 debt universe를 복원했다는 주장
- 외부사용자 성과·정규직 전환 성과

### 28.3 P4의 완성 기준

P4는 예쁜 dashboard가 아니라 다음을 동시에 만족할 때 완성된다.

1. 공개 원문에서 obligor와 debt를 추적할 수 있다.
2. 회계이익을 지급 가능한 현금으로 대사한다.
3. 만기·이자·facility·covenant가 하나의 cash path에서 움직인다.
4. downside와 reverse stress가 근거 있고 재현된다.
5. claim과 recovery가 법인별로 가치 보존한다.
6. rating·spread를 독립적으로 해석한다.
7. 조건부 conclusion과 monitoring action이 연결된다.
8. 데이터 권리·vintage·한계를 숨기지 않는다.
9. 독립 검토와 outcome analysis가 가능하다.
10. 실제 권한과 성과를 과장하지 않는다.

---

**문서 끝**
