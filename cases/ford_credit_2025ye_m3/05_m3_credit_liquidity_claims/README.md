# M3 — Credit, Liquidity and Claims

issuer capacity, instrument loss severity와 market signal을 분리한다. 연결재무를 특정 obligor의 자유로운 지급재원으로 간주하지 않는다.

Covenant는 원문 정의와 material input이 공개될 때만 재계산한다. Recovery는 증거가 부족하면 `STRUCTURE_ONLY`, market signal이 없으면 `NO_PUBLIC_MARKET_SIGNAL`이 정상 상태다.

이 case의 `debt_facilities.csv`는 2025년 말 그룹 기준 공시 aggregate와 FCE/Ford Bank의 개별 시설을 구분한다. 무담보 aggregate는 특정 채권이나 단일 법적 obligor가 아니다. ABS aggregate는 여러 유동화 법인의 채무다. 공시된 미사용 약정액은 자산 적격성·헤지·성과·차입 법인 조건을 확인하지 않은 즉시 인출 가능액으로 취급하지 않는다.

`maturities.csv`의 숫자는 2025-12-31 현재 연도별 **bucket**이고 실제 지급일이 아니다. 그래서 `event_date`를 비워 두었다. 장기채무의 이자는 원금과 별도 행에 보관하며 채무자별로 배분하지 않는다. `covenants.csv`는 공개된 조건만 기록하며 headroom을 계산하지 않는다. `claims_recovery.csv`와 `stress_cases.csv`는 법적 가치 풀과 날짜별 현금 경로가 부족해 비어 있다.

[신용 메모](credit_memo.md)와 [공식 근거](../01_evidence_core/evidence_notes.md)를 참조한다. M3 판단은 `WITHHELD`다.

