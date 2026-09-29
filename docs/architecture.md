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

## 첫 수직 slice

첫 구현은 case 하나와 공개 원문 한 묶음으로 다음 경로를 닫는다.

```text
source -> raw fact -> normalized fact -> one financial identity
       -> one scenario result -> one memo number -> manifest hash
```

UI는 위 경로와 release gate가 안정된 뒤 reporting adapter로 추가한다.

