# 오리온 진천센터 — 공개자료 case 판단 상태

**개인 연구·학습·포트폴리오용, AI 보조 작성. 독립적인 사람 검토 미완료.**
이는 회사 내부 계획, 투자·대출·예산 승인, 외부등급 또는 자문이 아니다.
합성 자료는 코드 검증에만 사용했고 아래 회사 사실에 섞지 않았다.

| 항목 | 상태 |
|---|---|
| 대상·관할 | ㈜오리온 진천센터, 대한민국, KRW |
| 기준일·공개정보 cutoff | 2026-08-18 23:59:59 KST |
| 판단 질문 | 기준시점 이후 미집행 진천센터 지출을 공시 계획대로 진행할 때와 법적으로 가능한 범위에서 단계화·이연할 때의 모회사 증분 세후현금흐름과 유동성 비교 |
| 활성 검토 모듈 | M1 가치·운영, M2 자본배분, M3 유동성·신용. O1 금융서비스 overlay는 해당 없음 |
| 조건부 결론 | `WITHHELD`. 두 대안의 금액·실행 가능성을 공개자료만으로 계산할 수 없음 |
| Cross-lens 상태 | [`DEFER_FOR_EVIDENCE`](07_validation_governance/cross_lens.json) (`cross_lens_a48b8fa08704df4c5c6e91e9ef61105c70f0ab7ba9f08bc332f37a1b657d67ae`), M2=`UNKNOWN`, M3=`UNKNOWN` |
| 검토 상태 | source·cutoff·현금 slice 자체 검증; 독립적인 사람 review 및 M1/M2/M3 release gate 미통과 |

가장 강한 확인 근거는 [DART 원공시](https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260814001054)와
[정정공시](https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260818000305)의
연결·별도 현금흐름, 별도 범위의 Core 현금 대사 output ID
`cash_5a2dbeb461384a36d33d28100c75ec0eec0df06104884b276c9ca360fa60740b`다.
이는 회사 전체 역사적 현금흐름에 대한 검산이다. 진천센터 전용 미래 현금흐름을
입증하지 않는다.

가장 강한 반대 근거는 [투자 근거 메모](01_evidence_core/investment_evidence.md)의
계획 총액과 물리적 공정률이 **미집행액·지급 일정·이연권**을 알려주지 않는다는
점이다. 모회사 별도 현금도 모든 목적의 즉시 접근 가능 현금이라는 증거가 없다.
새 공식 공시에서 프로젝트별 집행·지급 내역과 계약상 일정 변경권,
모회사 사용 가능 재원이 확인되면 판단을 다시 연다. 확보되지 않으면
P0 원칙에 따라 다른 공개자료 case를 선정한다.

재현 명령은 저장소 루트에서 `PYTHONPATH=src`를 설정하고
`python -m versioned_finance_core build-core cases/orion_jincheon_2026h1 --build-root <비어 있는 경로>`를
실행하는 것이다. 상세 gate와 제한은 [검증 기록](07_validation_governance/gate_results.csv),
[미해결 finding](07_validation_governance/review_findings.csv) 및
[판단 기록](07_validation_governance/decisions.csv)에 있다. 갱신 시 기존 근거를
덮어쓰지 않는 절차는 [재현·인계 문서](07_validation_governance/handover.md)에 적었다.
