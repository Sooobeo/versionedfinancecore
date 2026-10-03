# P1 사업·전망 객체 검토 — 2026-05-21 cutoff

이 문서는 가치평가에 사용할 driver의 **후보와 제약**을 기록한다. 원천 locator를 읽고 작성한 연구 메모이며, 아래 서술 자체가 정규화 fact, Core 전망 또는 투자 결론은 아니다. 최종 숫자는 source ledger와 Core output ID로 대사해야 한다.

## 사업과 분석 범위

- `[F]` [FY26 Form 10-K](https://www.sec.gov/Archives/edgar/data/104169/000010416926000055/wmt-20260131.htm)는 Walmart U.S., Walmart International, Sam's Club U.S.를 보고부문으로 제시한다. 연결 그룹을 가치평가 단위로 사용하고 부문 매출을 연결 매출에 중복 합산하지 않는다.
- `[F]` Walmart U.S.의 기존점 매출에는 매장에서 이행하는 온라인 주문도 포함된다. 온라인 매출 기여와 기존점 매출을 별개 연결 매출원처럼 더하지 않는다. 10-K의 *Company Performance Metrics*와 *Segment Operations*를 참조한다.
- `[F]` 국제 부문에는 환율 변동과 보고 시차가 있다. 10-K는 FY26 국제 순매출 증가에 환율이 부정적으로 작용했다고 설명한다. [FY27 Q1 실적 발표](https://www.sec.gov/Archives/edgar/data/104169/000010416926000095/earningsreleasefy27q1.htm)의 constant-currency 가이던스를 연결 reported USD·GAAP 수치로 바로 변환하지 않는다.

## 전망 객체와 초기 기간

연결 reported USD 순매출·영업이익, 영업현금흐름의 주요 구성요소, capex, 현금·부채·자본을 우선 모델 객체로 둔다. FY24–FY26 연간 비교정보와 FY27 Q1을 같은 회계 범위·vintage에서 대사해야 한다. 첫 분기의 현금흐름과 운전자본은 계절성이 있으므로 연율화하지 않는다.

`[F]` 10-K는 FY27 capex 예상 범위를 제시하고, 5월 21일 발표는 FY27 순매출·조정 영업이익·세율·capex 가이던스를 제시한다. 순매출·영업이익 성장 가이던스는 **고정환율**, 영업이익과 EPS의 일부는 **조정** 기준이다. 차이를 설명하는 FX 및 GAAP 조정 bridge가 확인되기 전까지 reported GAAP forecast의 입력값으로 사용하지 않는다.

## 가치평가에 중요한 가설과 반대 근거

| 구분 | 검증할 조건 | 원천과 모델 경계 |
|---|---|---|
| `[I]` 매출·마진 | 기존점 거래·구매액, 회원·광고 등 수익구성 변화가 연결 reported 매출과 영업마진을 얼마나 움직이는가 | 10-K의 부문·기존점 정의와 연결 합계를 대사한다. 공개되지 않은 연결 unit volume·price를 사실로 만들지 않는다. |
| `[I]` 재투자 | 공급망·기술·점포 투자 증가가 현금창출과 장기 수익성에 어떤 시차로 반영되는가 | 10-K의 capex 목적·현금흐름표와 FY27 capex 가이던스를 사용한다. 투자수익률·정상화 기간은 아직 입증되지 않았다. |
| `[I]` downside | 가격 경쟁, 국제 환율, 비용·보험청구 및 운전자본의 불리한 변화가 가치범위를 줄이는가 | [10-K 위험요인과 MD&A](https://www.sec.gov/Archives/edgar/data/104169/000010416926000055/wmt-20260131.htm)를 검토하되 충격폭은 역사적 자료·공식 가이던스 등에서 별도 도출한다. |

`[F]` 회사의 비GAAP free cash flow 정의는 영업현금흐름에서 유형자산 지급액을 뺀 것이다. [10-K의 조정표](https://www.sec.gov/Archives/edgar/data/104169/000010416926000055/wmt-20260131.htm)는 이 수치가 채무 지급과 인수 지출 등 모든 의무를 차감한 잔여 현금을 뜻하지 않는다고 명시한다. 이 값을 FCFF 또는 FCFE로 이름만 바꿔 DCF에 넣지 않는다.

## 현재 결론

이 case의 공개자료는 연결 재무·사업 driver **검토의 출발점**이다. reported/constant-currency, GAAP/adjusted, 이자·세금·현금흐름 claim, 투자 재원과 비지배지분을 대사하고 Core 기준전망을 생성하기 전에는 DCF·상대가치·목표주가 및 투자 결론을 `WITHHELD`로 둔다.
