# M1 공개 가이던스 결과 대조 — 제한적 메모

**상태: FEASIBILITY_ONLY / WITHHELD.** 기준시점은 2026-05-21 23:59:59 EDT다. 아래 수치는 `guidance_range_comparison.json`의 output ID를 표시한 것이며, 공개 가이던스를 내부 계획이나 독립 분석가 예측으로 해석하지 않는다.

| 동일 정의의 연결 지표 | 2월 공개 범위 | 5월 실제 표시값 | 범위 밖 거리 | canonical output ID |
|---|---:|---:|---:|---|
| 순매출 성장률, 고정환율 | +3.5~+4.5% | +5.7% | 상단보다 +1.2pp | `m1_guidance_range_65d2601b1d4328eb80047eddbe458aa5e29dc817a45aefc5320860d96accb033` |
| 비조정 영업이익 성장률, 고정환율 | +4.0~+6.0% | +2.5% | 하단보다 −1.5pp | `m1_guidance_range_fc832da83723062bddeddfa8b6bc3bb0acf6cd858788b675613cc49ec509d128` |
| 조정 희석 EPS | USD 0.63~0.65 | USD 0.66 | 상단보다 USD 0.01/주 | `m1_guidance_range_c74f227eae9e9bdde16417c6395df600c2c8b9a756bfbddda033936ac5d7999a` |

차이는 발표된 반올림 수치와 가이던스 **가장 가까운 경계**를 기준으로 한다. 중간값을 임의 예측값으로 만들지 않는다. `variance_bridge.csv`의 `driver_effect`는 공란이며 잔차가 범위 밖 거리 전체다. 이는 확인된 driver 효과가 0이라는 뜻이 아니다.

[공식 원천과 비교 정의](../01_evidence_core/guidance_actual_evidence.md)에 따라 헤드라인 매출 증가율 +5.9%와 조정 영업이익 고정환율 증가율 +5.1%를 이 표의 실제치로 사용하지 않는다. 회사는 연료비의 보고 영업이익 성장률 영향 약 250bp를 설명했지만, 2월 가이던스에 포함된 연료비 기대가 공개되지 않아 가이던스 대비 miss의 원인으로 정량 배분하지 않는다.

조건부 해석 `[I]`: 매출 성장률은 공개 범위를 웃돌았고, 비조정 고정환율 영업이익 성장률은 범위에 못 미쳤다. 이것만으로 영업 효율 저하의 지속성이나 회사의 계획 집행 실패를 판정할 수 없다. 다음 공식 분기 실적에서 비용·매출 mix와 고정환율 영업이익을 다시 점검할 수 있다. 이는 Walmart에 제안·집행한 행동이 아니다.

Linked P&L·BS·CF, working capital·cash reconciliation, driver-attributed variance, 독립 forecast/reforecast, valuation과 독립 인간 검토가 없다. 따라서 P0의 전체 M1 Performance 활성·release gate는 보류하고 M1 Valuation은 비활성화한다.

