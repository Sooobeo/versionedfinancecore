# P0 실행 상태

기준일: 2026-09-29. 이 표는 **재사용 가능한 코드 검증**과 **실제 공개자료 case의 release gate**를 구분한다. 합성 fixture의 통과를 오리온의 전망·투자·신용 판단으로 옮기지 않는다.

2026-10-03 실행 연결 보강: 다섯 공개자료 사례에 `build-case` recipe를 추가했다. 공통 명령으로 지원되는 계산을 재실행하고 output hash·검토 memo·남은 gate/finding을 immutable review stage에 묶는다. `verify-build`는 파일과 현재 코드/config 일치를 검사한다. Ford Credit은 같은 Core cash output을 M3의 채무자 현금·covenant 제한상태 평가에 연결했다. 모든 실제 의사결정 release는 계속 `WITHHELD`다. 상세 명령과 남은 작업은 [case build 안내](case_build.md)를 따른다.

같은 날 후속 보강으로 M1 과거 리스·세금 진단과 평가일 stub 통제, M2 공개근거 충족 검사, M3 공시 부채·만기·시설 조건 대사, 두 fresh build를 비교하는 `reproduce-case` / `verify-reproduction`을 연결했다. [후속 구현·제한사항 기록](nonhuman_followup_20261003.md)은 사람 검토와 공개자료 미확인을 구분한다. 이 작업이 아래 확장 기능 전체의 구현이나 실제 회사 release 완료를 의미하지는 않는다.

| 단계 | 구현·검증된 범위 | 오리온 진천센터 case |
|---|---|---|
| D0 — 공통 계약·release 골격 | source/fact lineage, cutoff·scope·version·지식상태, 정규화, 현금 포함 규칙, 결정적 build hash, fail-closed release staging | `FEASIBILITY_ONLY`; publication `WITHHELD` |
| R0 — Evidence & Control | append-only receipt/fact, 공개시점과 정정 vintage, 현금 4개 공시 표의 24개 사실 및 잔액 대사 | **현금 slice 재현**. 프로젝트별 미집행액·법적 실행 대안·접근 가능 재원은 확인되지 않아 의사결정 R0 gate `WITHHELD` |
| R1 — M1 | 합성 입력으로 기간 연결 P&L·BS·CF, driver 근거·cutoff를 확인하는 versioned model path, plan/actual variance·PVM, 구조적 DCF/claim bridge | 실물 driver forecast·과거 plan vintage·적격 valuation 근거가 없어 `WITHHELD` |
| R2 — M2 | 같은 Core cash output의 `option − status quo` 세후 FCFF, 효과별 근거, 검토 항목, NPV·추가 선행비용 switching value, closing sources/uses·확인된 funding gap | 프로젝트별 잔여 지출 일정·계약상 이연권·실행비용이 없어 `WITHHELD` |
| R3 — M3 | Core CFADS·debt service·liquidity를 쓰는 채무자 cash path, 시설·채무 이벤트, 현금 floor·DSCR·단조 reverse stress, 만기·차환 gap, covenant/회수 제한 상태 | 모회사 접근 가능 현금·시설 사용 조건·채무계약·청구권 근거가 부족해 `WITHHELD` |
| O1 — 금융업 overlay | opt-in 적격성 규칙 | 식품 제조 case에는 `NOT_APPLICABLE` |

## 모듈별 공개자료 사례 선택

오리온은 기존 R0 현금 검증 후보로 유지한다. P0의 같은 회사를 강제하지 않는 원칙에 따라 다른 모듈에는 [별도 사례](../cases/README.md)를 선정했다. 어느 사례도 실제 회사의 내부 계획·승인 판단을 주장하지 않는다.

| 모듈 | 공개자료 사례와 확인된 범위 | 현재 gate |
|---|---|---|
| M1 Performance | [Walmart FY27 Q1](../cases/walmart_fy27q1_guidance_outcome/): 2026-02-19 공개 가이던스와 2026-05-21 실제치의 동일 정의 3개 지표를 범위 기준으로 대조한다. 범위 중간값은 forecast로 만들지 않고 원인 미귀속 차이를 잔차로 둔다. | 연결 P&L·BS·CF, driver 귀속, 재전망과 독립 검토가 없어 `WITHHELD`. Valuation 비활성. |
| M2 | [South West Arkansas DFS](../cases/standard_lithium_swa_2025dfs/): 공개된 프로젝트 100% 기준 2025 실질 USD 세후 비차입 현금흐름·연차 합계를 재현한다. 공시 NPV의 할인 시점은 확정하지 않는다. | 미개발·보류 대안의 기회비용, 잔여 집행액·시점, JV 지분 귀속과 확약 자금 근거가 없어 FID·자본배분 결론 `WITHHELD`. |
| M3 | [Ford Credit 2025 연말](../cases/ford_credit_2025ye_m3/): 2026-02-11 기준으로 10-K 현금 대사와 공시 유동성·채무 만기 범위를 분리한다. 2026년 2분기 10-Q는 기준시점 이후 관찰값으로 분리한다. | 채무자별 가용 현금·시점별 CFADS·인출조건·covenant·청구권 근거가 부족해 `WITHHELD`. |

공통 `validate-case`는 이제 source receipt와 raw fact의 ID·hash·시점 계보를 CSV 계약으로 파싱하고 case 내부 draft manifest의 case ID·cutoff·`WITHHELD` 상태를 확인한다. 이 구조 검사와 모듈별 계산 검증은 최종 release gate 또는 독립적인 사람 검토를 대신하지 않는다.

## 실제 case에서 확인된 것

1. [차터](../cases/orion_jincheon_2026h1/00_charter/decision_object.md)는 ㈜오리온의 진천센터 계획 지속과 적법하게 가능한 단계화·이연을 비교하는 질문을 2026-08-18 23:59:59 KST 기준으로 고정한다. 경제적 관점은 모회사 별도이고, 연결 현금과 섞지 않는다.
2. [공식 근거 메모](../cases/orion_jincheon_2026h1/01_evidence_core/investment_evidence.md)는 최초 반기보고서(2026-08-14 12:36 KST)와 기재정정본(2026-08-18 17:38 KST)을 별도 vintage로 기록한다. 시각은 공시 목록의 분 단위 정밀도다. 원문 재배포권이 확인되지 않아 원문 HTML 대신 locator·hash·허용된 최소 사실만 보관한다.
3. [DART cash 수집기](../cases/orion_jincheon_2026h1/01_evidence_core/ingest_dart_cash.py)는 연결·별도 × 최초·정정 현금흐름표를 범위·기간·버전별로 분리한다. 24개 정규화 사실의 현금흐름 대사 차액은 0원이다. 모회사 별도 2026-06-30 현금은 254,143,639,226원이다. 이는 2026-08-18 현재 자유롭게 사용할 수 있는 프로젝트 자금액이라는 뜻이 아니다.
4. [최종 판단 요약](../cases/orion_jincheon_2026h1/executive_summary.md), [gate 기록](../cases/orion_jincheon_2026h1/07_validation_governance/gate_results.csv), [미해결 finding](../cases/orion_jincheon_2026h1/07_validation_governance/review_findings.csv)은 M1/M2/M3 판단을 `WITHHELD`로 유지한다. 계획 총액 4,600억 원, 건설 부분 2,280억 원 및 물리적 공정률 36%는 미집행 프로젝트 현금흐름이나 이연권을 계산하는 입력이 아니다.

## 오리온 case의 다음 공개자료 gate

- **M1:** 같은 범위의 역사적 재무·운영 driver와 공개시점이 확인된 과거 plan/forecast, 예측·valuation 가정 근거가 필요하다.
- **M2:** 프로젝트별 이미 지급한 금액과 남은 지급 일정, 취소·이연 가능 범위, 지연의 비용·편익을 확인해야 한다.
- **M3:** 법인별 사용 가능 현금, 제한·담보·해외 이전 제약, 채무 지급·만기·시설 draw 조건과 covenant 정의를 확인해야 한다.
- **Publication:** material gate 대사와 독립적인 challenge·response, memo/output 일치 및 재현 handover가 있어야 한다. 현재 실제 case에 이를 충족했다고 주장하지 않는다.

P0는 하나의 회사를 모든 모듈에 강제하지 않는다. 오리온에서 해당 근거가 계속 공개되지 않으면 모듈별로 더 적합한 공개자료 case를 골라 같은 계약과 검증 절차를 적용한다. 합성 데이터는 이 문서의 재사용 코드 테스트에만 쓰인다.

## 구현 범위의 한계

- 기간 연결 Core는 매출·현금 운영비·운전자본·세금·유형자산·차입·배당의 단일 통화 모델이다. FX·OCI·인수·처분 등 다른 중요 계정이 있으면 모델을 확장하고 대사해야 한다.
- M1의 공식 자료 기반 rolling reforecast, out-of-time 예측 검증 및 실제 기업의 적격 valuation은 완료되지 않았다. DCF 수치 함수의 출력은 별도의 근거·방법 적격성 검토를 통과해야 release용 값이 된다.
- M2의 기간별 자금조달·희석·pro forma와 IRR/ROIC, 계약상 실물 옵션의 실행 가능성은 실제 case 입력과 adapter가 없다. Closing funding 계산은 M3의 채무자 유동성·cash trough 결론을 대신하지 않는다.
- M3의 비선형·복합 충격, 계약상 cure 경로, 담보의 법적 유효성 및 외부 rating/spread 결론은 구현·입증하지 않았다. 공개 근거 부족 시 recovery·covenant는 제한 상태다.
- 현재 release 통제는 선택된 memo의 output ID와 Core 출력 ID, 중대 review finding의 해소·재검증을 확인한다. 모든 서술문 속 숫자를 재계산하거나 검토자의 독립성을 기술적으로 증명하지는 않는다.

## 재현

기존 build 경로를 덮어쓰지 않도록 새 경로를 지정한다.

```powershell
$env:PYTHONPATH = 'src'
python -m versioned_finance_core build-core cases/orion_jincheon_2026h1 --build-root build/recheck
python -m versioned_finance_core validate-case cases/orion_jincheon_2026h1 --release-ready
python -m pytest
python -m compileall -q src
python -m ruff check src tests
```

`validate-case --release-ready`는 현 자료 상태에서 gate 미통과를 보고해야 정상이다. 새로운 공시를 수집할 때는 기존 ledger 항목을 덮어쓰지 않고 receipt와 fact vintage를 추가한다.
