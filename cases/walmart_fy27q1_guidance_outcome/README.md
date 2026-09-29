# Walmart FY27 Q1 공개 가이던스 결과 대조

상태: **FEASIBILITY_ONLY / release WITHHELD**. 개인 연구·학습·포트폴리오용 공개자료 사례다. 실제 Walmart의 내부 계획, 사후 경영 성과 평가, 투자·대출 의견이 아니다.

- 판단 질문: 2026-05-21 공개된 FY27 Q1 연결 실적 중 2026-02-19에 먼저 공개한 동일 정의의 회사 가이던스 범위를 벗어난 것은 무엇이고, 원인 중 무엇이 아직 설명되지 않는가?
- 대상 기간: 2026-02-01~2026-04-30. 분석 기준시점: `2026-05-21T23:59:59-04:00`.
- 관할·통화·범위: 미국, USD, Walmart Inc. 연결 그룹. 법인별 현금 접근성과 채권 청구권은 분석하지 않는다.
- 활성 범위: M1의 **공개 가이던스 결과 대조만**. P0의 완전한 M1 Performance 활성·release gate는 통과하지 못했다. M1 Valuation, M2, M3, O1은 이 사례에서 비활성이다.
- 원천: Walmart가 SEC 8-K에 furnished한 [2026-02-19 자료](https://www.sec.gov/Archives/edgar/data/104169/000010416926000032/0000104169-26-000032-index.htm)와 [2026-05-21 자료](https://www.sec.gov/Archives/edgar/data/104169/000010416926000095/0000104169-26-000095-index.htm). 수치의 직접 locator와 해시·권리 상태는 `01_evidence_core/source_ledger.csv`에 있다.

`python cases/walmart_fy27q1_guidance_outcome/reproduce_comparison.py`는 local 사실·version을 Core로 정규화하고 M1 범위 비교 JSON을 표준출력으로 재생성한다. 그 결과를 `03_m1_operating_forecast_valuation/guidance_range_comparison.json`과 비교한다. 외부 네트워크나 원문 PDF 저장은 필요하지 않다.

원인 귀속, linked P&L·BS·CF, 독립 분석가 forecast와 reforecast, valuation, 독립 인간 검토가 없으므로 공개 가능한 최종 M1 release로 승격하지 않는다.
