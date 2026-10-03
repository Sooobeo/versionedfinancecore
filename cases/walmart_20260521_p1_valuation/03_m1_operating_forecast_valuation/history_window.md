# 역사적 관측창과 비교가능성 — 2026-05-21 정보집합

분석 목적은 연결 그룹의 reported USD 실적·현금창출·재투자 관계를 점검하는 것이다. FY24–FY26 연간 손익·현금흐름, FY24–FY26 연말 재무상태와 FY27 Q1을 첫 관측창으로 택했다. [FY26 10-K](https://www.sec.gov/Archives/edgar/data/104169/000010416926000055/wmt-20260131.htm)는 세 연도의 연간 비교 수치를, [FY25 10-K](https://www.sec.gov/Archives/edgar/data/104169/000010416925000021/wmt-20250131.htm)는 FY24 연말 재무상태를 제공한다. [FY27 Q1 8-K 발표자료](https://www.sec.gov/Archives/edgar/data/104169/000010416926000095/earningsreleasefy27q1.htm)는 기준시점에 공개된 최신 분기다.

이 창은 최초 재무·현금흐름 대사에 필요한 최소 비교기간이다. 세 연도로 정상 마진, 완전한 경기순환, 투자수익률 또는 장기 terminal 상태를 추정하지 않는다. FY27 Q1의 단일 분기 현금흐름을 연율화하지 않으며 연간 flow와 instant balance를 같은 관측값으로 비교하지 않는다. 과거 한 해를 더 붙일 때에는 당시 SEC 원본의 해당 기간, segment·회계 정의, 정정 vintage와 범위를 추가 검증한다.

FY24 손익·현금흐름의 FY26 10-K 비교표는 **2026-05-21에 이용 가능했던 FY26 공시 vintage**다. FY24 당시 최초 공시값이라고 부르지 않는다. FY24 재무상태는 FY25 10-K에서 가져오므로 동일 공시 원본의 연속 시계열도 아니다. 이후 정정이나 FY27 Q1 10-Q의 더 상세한 수치를 과거 기준시점으로 소급하지 않는다. 구조적 변화·분류 변경·보고부문 차이와 국제사업 환율 영향을 완전히 대사하지 못했으므로 window sensitivity와 장기 예측 성능은 `NOT_TESTABLE_FROM_PUBLIC_DATA` 상태다.

정규화된 수치는 `01_evidence_core/source_ledger.csv`의 원천 접수번호·해시, `raw_facts.csv`의 fact ID, `mappings.csv`의 계정 대응, Core staging의 `normalized_actuals.csv`를 따라 확인한다. 현금 대사의 기초인 현금흐름표 **cash, cash equivalents and restricted cash**와 재무상태표 cash and cash equivalents는 범위가 다르다. 별도 bridge 없이 두 항목을 같다고 처리하지 않는다.
