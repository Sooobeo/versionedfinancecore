# P1 후보 선정 기록: Walmart Inc.

이 기록은 `outline/P1_상장사_운영모델_가치평가_투자메모_설계서.md`의 Gate A–E를 **자료수집 전 후보 선정 단계**에 적용한다. 공식 원천의 존재를 확인한 것과 source snapshot·재무모델 gate 통과는 별개다.

| 필드 | 선정 기록 |
|---|---|
| Candidate | Walmart Inc. (WMT), 미국 Nasdaq 상장, Delaware 법인. [FY26 10-K 표지](https://www.sec.gov/Archives/edgar/data/104169/000010416926000055/wmt-20260131.htm). |
| Role/domain evidence | [CFA Institute의 기업 전망](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/company-analysis-forecasting)과 [현금흐름 가치평가](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/free-cash-flow-valuation) 절차에 맞게, 공개된 사업·재무 driver와 가치·위험의 연결을 검토할 수 있다. |
| Decision question | 2026-05-21에 공개된 근거만으로 연결 기업가치를 지탱하는 영업·재투자 경로 및 판단을 바꾸는 조건은 무엇인가? |
| Official sources | [FY26 10-K](https://www.sec.gov/Archives/edgar/data/104169/000010416926000055/0000104169-26-000055-index.htm), [FY25 10-K](https://www.sec.gov/Archives/edgar/data/104169/000010416925000021/0000104169-25-000021-index.html), [FY27 Q1 8-K와 부속자료](https://www.sec.gov/Archives/edgar/data/104169/000010416926000095/0000104169-26-000095-index.htm). 공식 문서의 수집 영수증·해시·시각과 최소 수치 사실은 [source ledger](../01_evidence_core/source_ledger.csv)에 기록했다. Q1 HTML의 해시 정의는 [수집 pilot](../01_evidence_core/evidence_pilot.md)에 명시했다. 원문 저장·재배포는 하지 않는다. |
| Forecast objects | 연결 reported USD 순매출, 영업이익, 운전자본·세금·투자·현금흐름을 후보로 둔다. 세그먼트 매출과 영업이익, 경영진 FY27 가이던스는 근거가 되는 범위에서만 사용한다. 공개된 constant-currency·adjusted 지표를 reported GAAP 값으로 취급하지 않는다. |
| Structural breaks | [FY26 10-K](https://www.sec.gov/Archives/edgar/data/104169/000010416926000055/wmt-20260131.htm)의 세 보고부문과 국제 사업의 한 달 연결시차, 환율, 비GAAP 조정을 우선 점검한다. 재작성·구조적 단절은 아직 전기간 대사하지 않았다. |
| Valuation candidates | 적격성이 확인되면 FCFF–WACC DCF를 검토한다. FCFE–자기자본비용은 현금흐름·자본구조 근거가 확보되기 전 비활성이다. trading comps는 사업·회계·가격 비교가능성 입증 전 비활성이다. 어떤 방법도 아직 수치 실행하지 않았다. |
| Material limitations | 공식 발표의 주요 연결 재무 line을 수집했으나 실제 회사의 완전한 3재무제표 전망과 재투자·무차입 현금세금 schedule은 없다. 할인율·terminal 근거, 순부채와 비영업자산의 EV→equity bridge, 시점이 맞는 주가·주식수, 독립 검토도 없다. |

## Gate A–E 상태

| Gate | 현 단계 판단 | 근거와 다음 검증 |
|---|---|---|
| A — 금융 의사결정 관련성 | **후보 적합** | 사업 실적→재투자→FCFF→조건부 가치라는 질문을 정의했다. 이는 분석 목적의 적합성이지 투자 근거 통과가 아니다. |
| B — 원천·provenance | **제한된 source gate 통과** | 세 공식 SEC 문서의 accession, 보수적 공개시각, 수집시각, 수신 바이트 SHA-256, 원천→raw fact→정규화 ID를 기록했다. 원문 보관·재배포 권리는 확보하지 않아 locator-only다. |
| C — 비교가능성 | **역사적 재무 line pilot, 전체 gate 미완료** | FY24–FY26 연간 및 FY27 Q1 연결 line을 기간·통화·단위로 정규화했다. FY24 재무상태는 FY25 10-K vintage다. 국제 환율·부문 재분류·GAAP/adjusted bridge 및 실제 3표 전망 적격성은 별도 검토가 필요하다. |
| D — 의사결정 가능성 | **미완료** | 공개자료로 매출·마진·capex·현금흐름 질문을 설계할 수 있다. 미래 연결 현금흐름·WACC·terminal·주당 bridge·시장가격의 합리적 근거가 아직 없다. |
| E — 실행 가능성 | **재무 수집·대사 pilot 완료, valuation 보류** | 이 case에서 공식 자료의 주요 재무 line을 Core로 정규화하고 FY26 현금 대사를 재현했다. 별도 [Performance case](../../walmart_fy27q1_guidance_outcome/)는 정의가 맞는 과거 가이던스 3개 지표의 제한된 비교만 제공한다. 실제 Walmart DCF는 실행하지 않았다. |

따라서 이 회사는 **P1 공개자료 pilot 후보**로 유지한다. Gate C–E와 P1 release R1–R6을 완료하기 전에는 valuation 결론과 release를 내지 않는다. [2026-05-29 접수 FY27 Q1 10-Q](https://www.sec.gov/Archives/edgar/data/104169/000010416926000102/0000104169-26-000102-index.htm)는 기준시점 뒤의 자료이므로 5월 21일 model fact로 사용하지 않는다.
