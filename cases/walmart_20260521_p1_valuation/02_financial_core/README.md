# Shared financial core

M1·M2·M3가 공동으로 쓰는 historical normalization, driver, linked statements, cash, debt, version과 scenario를 둔다. 모듈 폴더에서 같은 계산을 다시 만들지 않는다.

`normalized_actuals.csv`는 raw fact ID와 source/snapshot ID·hash·공개/수집시점을 보존한다. `accounting_scope`와 economic/legal scope bridge를 확인한 뒤 같은 metric·기간·단위·통화·version에서만 비교한다. `versions.csv`의 actual version은 append-only이며 restatement를 이전 cutoff의 actual로 소급하지 않는다.

`mappings.csv`의 명시적 부호 규칙만 적용한다. 단위·통화 불일치는 승인된 변환 규칙 없이 자동 보정하지 않는다. Core output은 계산 ID와 재무 대사 결과를 유지하고, M1·M2·M3는 동일 baseline을 참조한다.

`cash_identity_checks.csv`는 하나의 cash roll-forward에 쓰는 raw fact ID 여섯 개와 `version_id`를 고정한다. Core가 각 ID를 `normalized_actuals.csv`의 행으로 해석하고 기간·scope·단위·통화·version을 검증한 다음 residual을 계산한다. 누락 또는 비호환 행은 대사 실패 상태로 남긴다.

Walmart P1에서는 FY25 10-K, FY26 10-K와 FY27 Q1 8-K에서 추출한 205개 source fact를 Core가 정규화했다. 이 폴더의 `normalized_actuals.csv`는 출력 계약의 header만 보존한다. 실제 205개 canonical 값은 새 `build_core` staging의 `normalized_actuals.csv`에 생성되며, `historical_source_summary.json`은 그 normalized fact ID를 읽은 보조 색인이다. 같은 source/input/code의 서로 다른 staging root에서 파일 bytes와 output hash가 같다.

`cash_identity_checks.csv`는 FY26 10-K에 보고된 **현금·현금성자산·제한현금 합계**의 개시 9,536, CFO 41,565, CFI −26,350, CFF −13,553, 환율 효과 +123, 기말 11,321 million USD를 참조한다. Core residual은 0이다. FY27 Q1 8-K 같은 정의의 11,321 + 4,738 − 6,737 + 2,328 − 331 = 11,319도 integration test에서 대사된다. 재무상태표의 현금·현금성자산은 각각 FY26 10,727, Q1 10,729 million USD이므로 현금흐름표 잔액으로 바꾸지 않는다. 이 연결 자료로 부모법인 단독 가용 현금을 주장하지 않는다. source 및 출력 ID는 [evidence pilot](../01_evidence_core/evidence_pilot.md)을 참조한다.

`conditional_model_config.json`은 FY27 Q1 이후부터 FY31까지의 분석가 시나리오 가정과 Q1 재무상태표의 상세 계정→Core 집계표를 보존한다. `build_conditional_model.py`는 정규화된 Core fact를 고르고 공통 Core의 연결 3표·FCFF·cash component audit, M1의 WACC·terminal·청구권 함수를 호출한다. 결과인 [`conditional_linked_forecast.json`](conditional_linked_forecast.json)은 매 기간 손익·재무상태·현금흐름, FCFF/FCFE, 6개 roll-forward 잔차, source/assumption ID와 output ID를 기록한다. `conditional_scenario_drivers.csv`는 165개 기간별 driver 입력을 같은 scenario version으로 색인한다. 기존 `scenarios.csv`는 D0 cash-identity override 계약이므로 이 연결 전망의 driver를 넣지 않는다.

모든 조건부 3표 기간의 항등식 잔차는 0이다. 이는 실제 회사 예산이나 미래 lease·환율·인수·세금 움직임의 근거가 완성됐다는 뜻은 아니다. 특히 역사적 총 감가상각·상각을 PPE 감소에 적용하고 lease ROU/기타 장기자산은 고정한다. 현금흐름은 재무상태표 cash and equivalents 범위이며 보고된 cash plus restricted cash를 재현한다고 주장하지 않는다. 이 scenario는 2026-10-01에 소급 구성됐으므로 2026-05-21에 미리 동결한 독립 전망이나 out-of-time 예측 성능이 아니다. M1 산술과 한계는 [`conditional_valuation_screen.json`](../03_m1_operating_forecast_valuation/conditional_valuation_screen.json)에 있다. Release 적격성은 `WITHHELD`다.

`check_reported_statements.py`는 정규화된 Core staging만 읽어 `reported_statement_checks.json`을 배타적으로 생성한다. FY24·FY25·FY26 및 FY26·FY27 Q1 비교기간의 보고된 매출총계 − 매출원가 − 판매관리비 = 영업이익 5건과 보고된 자산총계 = 부채·자본총계 6건을 같은 source snapshot·version·scope·기간·통화·단위에서 검사했다. 11건 모두 exact residual 0이며, 결과마다 Core output ID와 출처 fact ID를 남겼다. FY24–FY26 순매출·영업이익·영업현금흐름·설비투자 지급액 12개 행은 Core 정규화 fact의 투영이며 수기 재계산값이 아니다. 별도 보고된 부채총액이 없어 이를 자산−자본으로 메우지 않았다. 이 검사 결과는 공시 산술 대사이며 forecast나 독립 review가 아니다.

