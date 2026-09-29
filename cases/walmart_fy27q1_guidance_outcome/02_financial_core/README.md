# Shared financial core

M1·M2·M3가 공동으로 쓰는 historical normalization, driver, linked statements, cash, debt, version과 scenario를 둔다. 모듈 폴더에서 같은 계산을 다시 만들지 않는다.

`normalized_actuals.csv`는 raw fact ID와 source/snapshot ID·hash·공개/수집시점을 보존한다. `accounting_scope`와 economic/legal scope bridge를 확인한 뒤 같은 metric·기간·단위·통화·version에서만 비교한다. `versions.csv`의 actual version은 append-only이며 restatement를 이전 cutoff의 actual로 소급하지 않는다.

`mappings.csv`의 명시적 부호 규칙만 적용한다. 단위·통화 불일치는 승인된 변환 규칙 없이 자동 보정하지 않는다. Core output은 계산 ID와 재무 대사 결과를 유지하고, M1·M2·M3는 동일 baseline을 참조한다.

`cash_identity_checks.csv`는 하나의 cash roll-forward에 쓰는 raw fact ID 여섯 개와 `version_id`를 고정한다. Core가 각 ID를 `normalized_actuals.csv`의 행으로 해석하고 기간·scope·단위·통화·version을 검증한 다음 residual을 계산한다. 누락 또는 비호환 행은 대사 실패 상태로 남긴다.

이 case의 `normalized_actuals.csv`는 `reproduce_comparison.py`가 raw 숫자 fact 3개를 `normalize_actuals`로 다시 계산해 동일 여부를 검사한다. 전사 3개는 공개된 연결 고정환율 성장률 2개와 조정 EPS 1개다. 이 파일은 linked 재무제표가 아니다. 현금흐름표, balance sheet, cash identity가 준비되지 않아 `build-core`의 D0 cash-only 파이프라인이나 실제 release 준비 완료라고 주장하지 않는다.

