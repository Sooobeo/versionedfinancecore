# Cases

각 분석대상은 `_template`을 복제한 독립 디렉터리다. 한 case 안에서 source, normalized data, model input, 판단 기록과 release 준비물을 함께 추적한다.

```powershell
$env:PYTHONPATH = "src"
python -m versioned_finance_core init-case my_case
```

`raw_snapshots`에는 이용권리가 확인된 자료만 둔다. credential, 개인정보, 고용주·계약상 비공개 자료, 재배포가 금지된 feed는 저장하지 않는다.

## P0 공개자료 사례 선택

P0는 한 회사로 M1~M3를 강제하지 않는다. 필요한 공개근거가 다른 만큼 모듈별로 대상을 고르고, 같은 schema와 gate를 적용한다. 아래 사례는 개인 연구용이며 `FEASIBILITY_ONLY`다. 모듈 판단과 release는 각 사례의 gate가 통과할 때까지 `WITHHELD`다.

| 관점 | 사례 | 공개정보 기준시점 | 검증 가능한 범위 | 남은 중요 근거 |
|---|---|---|---|---|
| 초기 R0 후보 | [오리온 진천센터](orion_jincheon_2026h1/) | 2026-08-18 23:59:59 KST | 원공시·정정공시의 현금 fact vintage와 별도 현금 대사 | 프로젝트별 미집행액, 집행 일정, 이연 권리, 자유롭게 쓸 수 있는 현금 |
| M1 Performance | [Walmart FY27 Q1](walmart_fy27q1_guidance_outcome/) | 2026-05-21 23:59:59 EDT | 분기 중 2월 19일 공개된 가이던스 범위와 같은 정의의 5월 실제 3개 지표 비교 | 차이의 계량적 driver 귀속, 재전망, 연결 P&L·BS·CF 통합 검증 |
| M2 Capital Allocation | [South West Arkansas DFS](standard_lithium_swa_2025dfs/) | 2025-10-15 23:59:59 EDT | 프로젝트 100% 기준 연도별 세후 비차입 현금흐름과 공개 DFS 수치 대사 | 미개발·보류 세계의 기회비용, 남은 capex·집행시점, JV 지분 현금 귀속, 확약 자금·계약 |
| M3 Credit & Liquidity | [Ford Credit 2025 연말](ford_credit_2025ye_m3/) | 2026-02-11 23:59:59 EST | 공시된 현금·차입금·만기·유동성 시설과 채무자 범위 | 시점 이후 실제 현금, 계약별 draw 조건·covenant, 담보·청구권과 차환 가능성 |

M2의 [Simulations Plus 합병 공시](https://www.sec.gov/Archives/edgar/data/1023459/000102345926000051/defm14a.htm)도 후보로 검토했다. 독립기업의 FCFF와 주주에게 제시된 현금 인수가격은 서로 다른 청구권 단위이므로 두 숫자를 직접 빼서 프로젝트 증분 NPV로 사용하지 않는다.

## P1 가치평가 착수

[Walmart 2026-05-21 가치평가 후보](walmart_20260521_p1_valuation/)는 기존 실적 비교와 별도의 `CORPORATE_VALUE` case다. 공식 SEC 자료 3건의 locator·문서 해시와 161개 재무 fact를 기록했고, 동일 source vintage의 reported 손익·재무상태 11개 항등식과 FY26·FY27 Q1 현금 대사를 확인했다. 실제 Walmart 연결 전망·FCFF·WACC·terminal·청구권 bridge와 독립 검토는 아직 없다. M1 Valuation과 release는 `WITHHELD`다.
