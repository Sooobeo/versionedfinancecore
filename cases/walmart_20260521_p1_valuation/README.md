# Walmart P1 가치평가 공개자료 후보

상태: **FEASIBILITY_ONLY / M1 Valuation WITHHELD / release WITHHELD**. 이 case는 개인 연구·학습·포트폴리오용이며, Walmart에 대한 투자 의견이나 실제 경영 의사결정이 아니다.

- 기준시점: 2026-05-21 23:59:59 EDT (`-04:00`).
- 분석 단위: Walmart Inc. 연결 그룹, 미국 공시, USD. M1의 P1 Valuation 관점만 활성화 대상으로 삼는다.
- 질문: 당시 공개자료로 뒷받침할 수 있는 영업 현금흐름·재투자 경로와 조건부 기업가치 범위는 무엇이며, 어떤 성장·마진·재투자·할인율 조건에서 결론이 바뀌는가?
- 조건부 전망 기간: FY27 잔여기간(2026-05-01~2027-01-31)과 FY28~FY31. FY31 말일은 DCF의 명시적 예측 종료일이다.

[후보 선정 기록](00_charter/candidate_selection.md)과 [SEC 원천 수집 pilot](01_evidence_core/evidence_pilot.md)을 참조한다. FY25·FY26 10-K와 FY27 Q1 8-K 부속자료의 원천 영수증 4개와 연결 재무 fact 205개를 기록했고, Core staging에서 정규화와 FY26 현금흐름 대사를 재현했다. Q1 HTML은 SEC가 삽입하는 요청별 전송 요소를 제외한 공시 본문 해시와 최초 수신 바이트 해시를 구분한다. 원문은 저장·재배포하지 않는다.

[기존 FY27 Q1 Performance case](../walmart_fy27q1_guidance_outcome/)는 같은 회사와 기준일을 쓰지만 다른 의사결정 질문이다. 그 case의 3개 비교 지표는 이 case의 연결 재무 baseline이나 valuation 결과가 아니다. P1 산출물은 `financial_core`가 만드는 version 고정 operating baseline을 소비해야 한다.

[조건부 연결 3표 전망](02_financial_core/conditional_linked_forecast.json)과 [FCFF·WACC·terminal·청구권 계산](03_m1_operating_forecast_valuation/conditional_valuation_screen.json)은 검토 가능하다. 2026-10-01에 소급 구성한 분석가 시나리오이고, 일부 시장자료의 최초 공개시각, lease 처리와 평가일 청구권이 미확정이다. [P1 판단 메모](03_m1_operating_forecast_valuation/memo.md)와 공개 release는 `WITHHELD`다. [관측창](03_m1_operating_forecast_valuation/history_window.md), [방법 적격성](03_m1_operating_forecast_valuation/method_screen.md), [기준시점 이후 결과 점검](out_of_time_evaluation/README.md)을 구분해서 읽는다.
