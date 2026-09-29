# M1 — Operating, Forecast and Valuation

P1의 운영·가치평가와 P2의 실적차이·재전망을 한 모듈로 구현한다. Performance와 Valuation은 각각 activation gate를 통과할 때만 활성화한다.

예정 계산: linked forecast, actual-to-plan/prior-forecast variance, residual, reforecast, eligible valuation, thesis-break와 action trigger.

이 case에서 실행한 범위는 2026-02-19 공개된 FY27 Q1 **가이던스 범위**와 2026-05-21 실제 발표값의 동일 정의 결과 대조다. `reproduce_comparison.py`가 Core 정규화값을 읽고 M1 `compare_actual_to_public_guidance_range`를 실행한다. `guidance_range_comparison.json`이 canonical 결과다.

공개 driver의 가이던스 대비 정량 차이, 독립 forecast/reforecast, linked P&L·BS·CF가 없어 P0의 완전한 Performance 활성 gate는 보류한다. Valuation은 비활성이다.

