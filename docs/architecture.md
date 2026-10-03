# Architecture

P0를 authoritative source로 삼는다. P1~P4의 공통 ingestion·정규화·재무·scenario 기능은 `financial_core`에 합치고, 모듈에는 고유 판단만 둔다.

```text
public evidence
  -> evidence ledger + immutable snapshot
  -> normalized facts + semantic/version contract
  -> shared drivers + linked statements + cash/debt
  -> M1 performance/valuation
  -> M2 capital allocation
  -> M3 credit/liquidity/claims
  -> validation gates
  -> memo + immutable release manifest
```

## 코드 경계

- `contracts`: 공통 enum, ID, 상태값과 데이터 계약
- `evidence`: cutoff 판정, source hash, lineage
- `financial_core`: 모든 모듈이 공유하는 canonical 계산
- `modules/m1`: variance, reforecast, valuation, action
- `modules/m2`: alternatives, incremental cash flow, sources/uses
- `modules/m3`: obligor scope, liquidity, covenant, refinancing, recovery
- `validation`: identity, known-answer, release gate
- `reporting`: memo와 독자별 view
- `orchestration`: case 초기화, pipeline, immutable release 생성

모듈은 다른 모듈의 출력 계약을 소비할 수 있지만 공통 historical·cash 계산을 복제하지 않는다.

## P1 현금흐름과 가치평가 경계

`financial_core`는 같은 version·scenario·scope·cutoff의 운영모델에서 FCFE와 FCFF를 산출하고 각 기간의 현금흐름 및 baseline output ID를 소유한다. 필요한 무차입 현금세금처럼 관측되거나 근거가 붙은 입력이 없으면 FCFF를 `UNKNOWN`으로 유지한다. 회사가 별도로 발표한 `operating cash flow - capex`는 그 자체로 FCFF 또는 FCFE가 아니다.

`modules/m1`은 Core의 현금흐름 금액과 ID를 소비해 claim에 맞는 할인율, terminal 조건, 기업가치에서 자기자본가치로의 bridge, peer 적격성과 의사결정 민감도를 검토한다. M1은 현금흐름이나 연결 재무제표를 다시 계산하지 않는다. 할인율·terminal·peer·시장가격·독립 검토의 근거가 부족하면 수치 가치평가와 thesis-break 결론은 `WITHHELD`로 남긴다. 표현 계층은 M1의 적격 결과와 output ID만 표시한다.

M1의 날짜 기반 DCF 입력은 Core `FreeCashFlowPathResult`의 기간별 FCFF/FCFE 금액과 output ID를 그대로 참조한다. `ACT_365_FIXED`를 명시하면 `valuation_date`부터 각 기간 말일까지의 실제 일수/365로 할인하므로 첫 회계연도 잔여기간을 연간 현금흐름으로 환산하지 않는다. 연결 재무제표 현금흐름은 명목 금액이므로 명목 할인율만 허용한다. 할인율과 terminal 현금흐름에는 근거 source ID, 이용 가능 시각, 가정 ID와 설명을 붙이고 cutoff 이후 근거를 거부한다. Terminal FCFF는 마지막 전망 FCFF에 성장률을 기계적으로 곱해 만들지 않는다. 선택적인 `TerminalOperatingEconomics`를 쓰면 지속 가능한 차기 NOPAT와 `g/ROIC` 재투자의 결과가 terminal FCFF 가정과 정확히 일치해야 한다. Core 전망에서 만든 terminal 경제성은 마지막 Core FCFF와 output ID를 보존하고 차기 terminal FCFF와의 차이·배율을 노출한다. 전환 폭의 적정성은 자동 임계값 없이 별도 검토한다.

M1 `calculate_wacc`는 원천·관측일·공개 가능 시각이 붙은 무위험금리, beta, ERP, 한계 세율, 현재 한계 차입금리 또는 대응 만기 spread, 주가, 주식 수 및 부채가치를 입력으로 받는다. CAPM 자기자본비용, 세후 부채비용, 시장가중치와 WACC는 이 pure 함수에서 계산한다. 주식 수·부채가치 기준일이 평가일과 다르거나 부채가치가 장부가 proxy인 경우, 섹터 beta를 회사 고유값처럼 쓰는 경우 및 lease 정책이 불일치하는 경우 수치는 검토용으로 남기고 구조적 상태를 `WITHHELD`로 둔다. `terminal_operating_economics_from_forecast`는 마지막 **연간** Core EBIT와 근거가 붙은 정상화 EBIT 성장, 무차입 현금세율, 지속 가능한 ROIC 및 영구성장률로 차기 NOPAT·재투자·FCFF를 계산한다. 이 산술은 가정의 사실 적격성을 자동 승인하지 않는다.

날짜 기반 EV→equity bridge는 각 cash·non-operating asset·debt-like·minority·other senior claim의 금액, 원천, 잔액 기준일, 공개 가능 시각, 법인·회계 범위 및 단위를 요구한다. DCF 평가일과 청구권 잔액 기준일이 다르면 산술 결과는 검토용으로 보존하되 구조적 적격성은 `WITHHELD`다. Lease 비용을 FCFF에 포함하면서 동일 lease liability를 debt-like claim에도 더하는 등 lease·WACC 처리의 불일치도 `WITHHELD`다. 구조적 대사와 별도로 날짜 할인, 기준일 사이 현금 처리, terminal 경제성, 청구권과 lease 정책에 대한 독립 검토가 통과해야 수치를 release adapter에 전달할 수 있다.

일부 claim이 확인되지 않은 경우 `bridge_enterprise_to_equity_partial`은 해당 성분을 `UNKNOWN`으로 보존하고 확인된 성분의 `known_subtotal`만 계산한다. 이 소계는 자기자본가치가 아니며 `equity_value=None`, `WITHHELD`를 반환한다. 근거 없는 cash·비영업자산·기타 선순위 청구권을 0으로 채우지 않는다.

NCI 또는 부채·금융리스처럼 여러 원천 잔액을 하나의 claim으로 묶을 때는 `aggregate_dated_claim_balances`가 같은 잔액일·범위·통화·단위와 cutoff를 검증하고 정확한 합계 및 모든 구성 source ID를 가진 결정적 aggregate ID를 만든다. EV→equity bridge의 lineage에는 aggregate ID와 구성 source ID가 함께 남는다.

## 첫 수직 slice

첫 구현은 case 하나와 공개 원문 한 묶음으로 다음 경로를 닫는다.

```text
source -> raw fact -> normalized fact -> one financial identity
       -> one scenario result -> one memo number -> manifest hash
```

UI는 위 경로와 release gate가 안정된 뒤 reporting adapter로 추가한다.

