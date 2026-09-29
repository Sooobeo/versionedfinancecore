# Evidence core

모든 사실의 원문, 공개시점, retrieval, 권리, scope와 변환 lineage를 관리한다. snapshot과 raw fact는 append-only이며 정정본이 원본을 덮지 않는다.

- `source_ledger.csv`: 원천 `source_id`와 불변 수집본 `snapshot_id`, 공개·수집시점, 권리, SHA-256을 기록한다.
- `raw_facts.csv`: 각 fact의 원문 snapshot/hash, `raw_account_id`, 공개·수집시점, 회계·경제·법적 범위와 실제값 `version_id`를 보존한다.
- `mappings.csv`: 원문 계정에서 metric으로 가는 versioned mapping과 명시적 `sign_multiplier`(`+1`/`-1`)를 기록한다.
- `scope_bridges.csv`: 경제적 범위와 법인 범위의 근거 있는 관계를 기록한다. 관계가 필요한 fact는 `economic_legal_scope_bridge_id`로 이를 참조한다.

시간대가 있는 `first_public_at`을 cutoff와 비교한다. `event_at`, 보고기간 말일, `retrieved_at`을 공개시각으로 대체하지 않는다. 단위·통화 변환에는 별도 승인된 규칙이 필요하며, 첫 D0 normalizer는 불일치를 거부한다.

