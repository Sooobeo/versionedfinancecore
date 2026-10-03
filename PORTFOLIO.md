# 공개자료 기업재무 의사결정 시스템 — 포트폴리오 요약

**개인 연구·학습용 프로젝트이며 코드와 조사에 AI 보조를 사용했다. 독립적인 사람 검토는 완료되지 않았다.** 실제 회사의 내부 계획, 승인된 투자·대출 판단, 외부 신용등급 또는 자문 결과가 아니다. 공개자료로 확인되지 않는 판단은 `WITHHELD`로 남긴다.

## 무엇을 검증했나

공개 **시점**에 이용 가능했던 원천을 고정하고, 법인·연결 범위와 숫자의 정의를 대사한 뒤, 계산 가능한 결과만 출력하는 경로를 만들었다. `financial_core`가 공통 정규화·현금·버전 계산을 소유하고 M1·M2·M3는 그 출력을 소비한다. 합성 fixture는 연결 P&L·BS·CF와 시나리오 계산의 known-answer 테스트에만 사용한다. 실제 회사의 전망·성과나 예측력을 입증하는 자료로 쓰지 않는다.

| 공개자료 사례 | 기준시점과 재현된 결과 | 판단 경계 |
|---|---|---|
| [오리온 진천센터 R0](cases/orion_jincheon_2026h1/executive_summary.md) | 2026-08-18 23:59:59 KST. 원공시·정정공시, 연결·별도 현금흐름의 24개 사실을 보존했다. 모회사 **별도** 현금 대사 잔차는 0원이다. | 2026-06-30 장부상 현금은 진천센터에 자유롭게 쓸 수 있는 잔여 재원이 아니다. 프로젝트 지출·이연 판단 `WITHHELD`. |
| [Walmart M1](cases/walmart_fy27q1_guidance_outcome/README.md) | 2026-05-21 23:59:59 EDT. 분기 **중** 2월 19일 공개 가이던스 대비 같은 정의의 실제치: 고정환율 순매출 성장률은 상단보다 +1.2%p, 비조정 고정환율 영업이익 성장률은 하단보다 −1.5%p, 조정 EPS는 상단보다 USD 0.01 높다. | 차이의 원인 귀속, 연결 3표·재전망 검증이 없다. M1 전체 release `WITHHELD`, Valuation 비활성. |
| [Walmart P1 가치평가 pilot](cases/walmart_20260521_p1_valuation/README.md) | 2026-05-21 23:59:59 EDT. 기존 SEC 문서 3건·receipt 4개의 205개 연결 재무 fact와 공시 산술을 검증했다. 후속 리스·현금세금 진단용 HTML receipt는 별도로 보존했다. 조건부 연결 3표·FCFF/FCFE·WACC·DCF·부분 claim bridge를 재현한다. | 사후 작성 시나리오이며 입력 적격성·미래 리스·세금·terminal·평가일 현금과 claim·독립 검토가 미해결이다. 기업가치·투자의견·release `WITHHELD`. |
| [South West Arkansas M2](cases/standard_lithium_swa_2025dfs/04_m2_capital_allocation/decision_memo.md) | 2025-10-15 23:59:59 EDT. DFS의 프로젝트 **100%** 기준 세후 비차입 현금흐름 중 숫자가 있는 23개 연차를 대조해 표시 합계 USD 4,701.5 million을 재현했다. | 보고서의 NPV는 전체 건설 경로의 저자 전망이다. 보유·미개발 대안, 잔여 투자와 자금 귀속이 없어 증분 NPV·최종투자결정 `WITHHELD`. |
| [Ford Credit M3](cases/ford_credit_2025ye_m3/executive_summary.md) | 2026-02-11 23:59:59 EST 공개정보로 2025-12-31 연결 현금 대사 잔차 0 USD million을 재현했다. 공시 순유동성 USD 24.6 billion과 2026년 채무 만기 USD 51,806 million의 범위를 분리했다. | 순유동성은 조건부 시설을 포함한 회사 정의이고 만기는 연간·복수 법인 합계다. 두 수치의 차이는 현금 부족액이 아니다. 채무자별 지급능력 `WITHHELD`. |

공식 원천은 [오리온 공시 근거](cases/orion_jincheon_2026h1/01_evidence_core/investment_evidence.md), Walmart의 [FY26 10-K](https://www.sec.gov/Archives/edgar/data/104169/000010416926000055/wmt-20260131.htm)와 [2월](https://www.sec.gov/Archives/edgar/data/104169/000010416926000032/0000104169-26-000032-index.htm)·[5월](https://www.sec.gov/Archives/edgar/data/104169/000010416926000095/0000104169-26-000095-index.htm) 8-K, [SWA DFS](https://www.sec.gov/Archives/edgar/data/1537137/000110465925099044/tm2528539d1_ex99-1.htm), [Ford Credit 10-K](https://www.sec.gov/Archives/edgar/data/38009/000003800926000010/fmcc-20251231.htm)에서 확인할 수 있다.

각 사례의 `01_evidence_core/source_ledger.csv`는 locator, 원문 hash, 최초 공개 확인 시각 또는 보수적인 공개 확인 경계, 수집시각과 이용권리 상태를 기록한다. 권리가 확인되지 않은 원문 PDF·HTML은 저장소에 넣지 않았다. 결과는 [사례별 gate와 미해결 finding](docs/p0_execution_status.md)에 연결된다.

## 재현 순서

Python 3.11 이상에서 저장소 루트를 기준으로 실행한다. 아래 명령은 고정된 로컬 사실·fixture를 사용하며 live network를 요구하지 않는다.

```powershell
$env:PYTHONPATH = 'src'
python -m pytest
python -m compileall -q src
python -m ruff check src tests
python -m versioned_finance_core validate-case cases/orion_jincheon_2026h1
python -m versioned_finance_core validate-case cases/walmart_fy27q1_guidance_outcome
python -m versioned_finance_core validate-case cases/walmart_20260521_p1_valuation
python -m versioned_finance_core validate-case cases/standard_lithium_swa_2025dfs
python -m versioned_finance_core validate-case cases/ford_credit_2025ye_m3
```

사례 숫자를 다시 계산하려면 다음 명령을 실행한다. 새 build 경로는 실행마다 고유하게 생성한다.

```powershell
python cases/walmart_fy27q1_guidance_outcome/reproduce_comparison.py
python -m versioned_finance_core build-core cases/walmart_20260521_p1_valuation --build-root "build/portfolio_walmart_p1_$([guid]::NewGuid().ToString('N'))"
python -m pytest tests/integration/test_swa_public_model.py
$portfolioOrionRoot = "build/portfolio_orion_$([guid]::NewGuid().ToString('N'))"
python -m versioned_finance_core build-core cases/orion_jincheon_2026h1 --build-root $portfolioOrionRoot
$portfolioFordRoot = "build/portfolio_ford_$([guid]::NewGuid().ToString('N'))"
python -m versioned_finance_core build-core cases/ford_credit_2025ye_m3 --build-root $portfolioFordRoot
```

Walmart 실적 대조 표준출력을 [고정 결과 JSON](cases/walmart_fy27q1_guidance_outcome/03_m1_operating_forecast_valuation/guidance_range_comparison.json)과 대조한다. P1의 Core 출력은 [역사적 검사 결과](cases/walmart_20260521_p1_valuation/02_financial_core/reported_statement_checks.json)와 [인계서](cases/walmart_20260521_p1_valuation/07_validation_governance/handover.md)를 따른다. SWA 테스트는 [상대 연차 계산 JSON](cases/standard_lithium_swa_2025dfs/04_m2_capital_allocation/dfs_reproduction.json)과 원천 추출 계약을 검사한다. `build-core` 명령은 출력 경로를 표시하며 그 안의 `core_outputs.json`에 현금 대사가 있다. 상세 갱신 절차는 [오리온](cases/orion_jincheon_2026h1/07_validation_governance/handover.md), [Walmart 실적](cases/walmart_fy27q1_guidance_outcome/07_validation_governance/handover.md), [SWA](cases/standard_lithium_swa_2025dfs/07_validation_governance/README.md), [Ford Credit](cases/ford_credit_2025ye_m3/07_validation_governance/handover.md) 인계서를 따른다. `validate-case --release-ready`가 막힌 gate를 보고하는 것은 현재 정상 결과다.

## 현재 완료 기준

- 공통 계산·계약·release 통제와 위 공개자료의 제한된 재현 경로를 테스트한다. 2026-10-03에는 다섯 사례의 공통 `build-case`·`verify-build`, 검토 보고서 gate, atomic staging과 오프라인 CI를 추가했다. 실행 명령과 범위는 [case build 안내](docs/case_build.md)에 기록한다. 이전 235개라는 테스트 수는 2026-09-29 시점의 기록이며 현재 전체 테스트 수가 아니다.
- 다섯 사례는 모두 `FEASIBILITY_ONLY`이며 의사결정 release는 `WITHHELD`다. `build/`의 staging은 검토용이고 `releases/`에 발행된 실제 사례 release는 없다.
- 실제 의사결정 release에는 대안별 증분 현금흐름, 법인·계약상 가용 자금과 지급일별 채무 경로, 독립적인 사람의 challenge·response가 추가로 필요하다. 해당 근거가 없으면 gate를 통과 처리하지 않는다.

검토용 산출물은 `python -m versioned_finance_core build-case cases/<case_id> --build-root <fresh-root>`로 새로 계산한다. 출력 경로의 `outputs/review_memo.md`에서 완료된 계산과 남은 gate·finding을 확인한다. 같은 입력을 별도 root에서 재실행해 output hash를 비교할 수 있고 `verify-build`로 무결성을 검사할 수 있다. 이 검토 bundle은 실제 회사의 의사결정 release와 구분한다.

후속 `reproduce-case cases/<case_id> --output-dir <new-directory>`는 두 번의 fresh build와 hash 비교를 자동으로 묶고 `verify-reproduction <directory>`로 검증한다. [2026-10-03 후속 기록](docs/nonhuman_followup_20261003.md)에 M1 리스·세금·평가일 통제, M2 공개근거 충족 검사, M3 공시 부채·만기·조건 대사와 남은 자료·구현 한계를 구분했다. 자동 재현은 독립 사람 검토가 아니다.

[설계 원본](outline/P0_통합_기업재무_의사결정_시스템_마스터_설계서.md) · [구현 경계](docs/architecture.md) · [상세 실행 상태](docs/p0_execution_status.md) · [사례 목록](cases/README.md)
