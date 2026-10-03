# 2026-10-03 공개근거 후속 점검

이 기록은 사람 검토가 아니라 공식 원문 재확인이다. 기존 raw fact·receipt·가이던스 vintage 및 gate를 덮어쓰거나 변경하지 않았다. 새 숫자를 fact로 추가하지 않았고 원문도 보관하지 않았다.

## 확인한 원문

- [2026-02-19 SEC 8-K 실적 발표 첨부](https://www.sec.gov/Archives/edgar/data/104169/000010416926000032/earningsreleasefy26q4.htm): Guidance 절의 FY27 Q1 연결지표 범위와 조정·고정환율 정의를 확인했다.
- [2026-05-21 SEC 8-K 실적 발표 첨부](https://www.sec.gov/Archives/edgar/data/104169/000010416926000095/earningsreleasefy27q1.htm): 이후 공개된 실적과 영업 맥락은 actual/outcome 자료다.

## 해소되지 않은 항목과 이유

`wmt_m1_001`: 조사한 발표자료는 가이던스 작성 당시의 예상 연료비·판매 mix·수량·가격별 경로를 제공하지 않는다. 사후 회사 설명이나 실제 전년 대비 효과를 **가이던스 대비 surprise**로 치환할 수 없다. 따라서 근거 없는 driver effect를 추가하지 않고 범위 밖 차이를 미설명 잔차로 유지한다. 이는 모든 가능한 공개자료에 해당 정보가 없다는 단정이 아니라 이번에 확인한 자료의 한계다.

`wmt_m1_002`: 별도 Walmart 가치평가 case의 연결 재무자료와 사후 조건부 forecast는 이 case의 과거 동결 analyst plan이 아니다. 가이던스 범위를 임의 중간값 plan으로 만들거나 사후 모델을 당시 예측으로 연결하지 않는다. 이 비교의 질문과 horizon은 공식 범위의 실적 대조에 고정한다. 전체 M1 release에는 당시 비교가능 driver·계획 vintage와 별도 재전망 근거가 여전히 필요하다.

`wmt_m1_003`: 사용자의 이번 작업 범위에서 독립적인 사람 검토는 수행하지 않는다. 자동 재현과 입력·출력 무결성 검사 결과가 이 finding의 해소 근거가 되지 않는다.

자동 인수인계는 `reproduce-case`와 `verify-reproduction`으로 실행할 수 있다. 결과는 두 fresh build의 일치만 증명하며 `FEASIBILITY_ONLY` / `WITHHELD` 상태를 바꾸지 않는다.
