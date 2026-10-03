# 사람 검토를 제외한 후속 구현·공개근거 보강

기준일: 2026-10-03 KST. 개인 연구용 자동 검증과 공식 공개자료 후속 조사다. 독립적인 사람의 검토는 수행하지 않았고 `REVIEW`를 PASS로 변경하지 않았다. 공개되지 않은 과거 값·계약조건·현금 접근성을 만들어 채우지 않는다.

## 이번에 연결한 기능

| 영역 | 구현·자료 보강 | 여전히 별도 근거가 필요한 것 |
|---|---|---|
| M1 Walmart 가치평가 | 과거 리스·D&A·현금세금 진단, 평가일을 가로지르는 cash-flow stub 적격성 통제, 발행수익률 proxy의 시점 한계 분리 | 전방 리스 roll-forward·무차입 현금세금, 평가일 이전 현금, 당시 시장 입력의 권리·시점, terminal 경제성과 완전한 claim bridge |
| M1 Walmart 실적 비교 | 공식 사전 가이던스와 사후 실적의 역할을 재확인하고 미설명 잔차 경계를 유지 | 당시 예상 연료비·수량·가격·mix 경로 및 동결 analyst forecast. 사후 회사 설명으로 대체할 수 없음 |
| M2 SWA | 공시된 임대 유지비·JV 개발비 분담·보조금 관련 부분 근거를 receipt와 연결, 증거 충족 상태를 DFS 재현 output에 통합 | cutoff 현재 잔여 CAPEX·지급일·완전한 no-build/defer 경로·보조금 draw/회수 조건·capital call/FID |
| M2 오리온 | `capital_evidence` 단계를 공통 build에 추가, 물리 공정률과 현금 집행률을 구분 | 프로젝트별 잔여 지출·지급일, 계약상 이연/해지권·위약금, 접근 가능 자금과 세후 현금흐름 |
| M3 Ford Credit | Core fact를 참조한 공시 유동성·부채·만기 독립 대사, 법인·시설·공개조건·만기 bucket 출력과 단위·receipt·cutoff 검증 | 법적 obligor 가용현금, 실제 지급일별 CFADS, 조건부 시설의 실제 drawability, covenant headroom, 담보가치·회수순위 |
| 자동 인수인계 | `reproduce-case`로 두 fresh build와 비교 receipt 생성, `verify-reproduction`으로 양쪽 계산물·보고서·memo·파일 목록 검사 | 독립 사람 검토, 실제 외부 이용자의 인수인계와 다른 운영체제에서의 원격 CI 확인 |

M2 증거 상태는 같은 criterion에 상충하는 COMPLETE와 PARTIAL/MISSING이 있으면 보수적인 상태를 유지한다. 계약 일부를 확인했다고 전체 no-build 경로, 남은 지원금 또는 현금 접근성을 완성된 것으로 취급하지 않는다. M3 nominal facility 대사도 실제 인출 가능액을 만들지 않는다.

새 receipt는 기존 receipt·raw fact를 수정하지 않고 추가했다. 같은 SEC accession을 재조회한 본문 hash가 이전 것과 다른 경우 그 차이와 과거 본문 동일성 미검증을 별도로 표시한다. 공식 locator 접근 가능성과 historical byte identity는 같은 검증이 아니다.

## 근거와 구현 연결

- [Walmart M1 후속 점검](../cases/walmart_20260521_p1_valuation/07_validation_governance/evidence_followup_20261003.md)
- [Walmart 실적 비교 후속 점검](../cases/walmart_fy27q1_guidance_outcome/07_validation_governance/evidence_followup_20261003.md)
- [SWA 추가 공개근거](../cases/standard_lithium_swa_2025dfs/01_evidence_core/m2_public_evidence_note.md)
- [오리온 추가 공개근거](../cases/orion_jincheon_2026h1/01_evidence_core/m2_public_evidence_note.md)
- [Ford Credit 추가 공개근거](../cases/ford_credit_2025ye_m3/07_validation_governance/evidence_followup_20261003.md)
- [명령·검증 범위](case_build.md), [데이터 계약](data_contract.md), [release 통제](release_process.md)

## 완료 판단의 경계

코드로 검증할 수 있는 계산·입력 계약·재현성 문제와 실제 공개되지 않은 입력은 구분한다. 미확인 입력이 남은 현재 상태에서는 사람 검토만 하면 곧바로 발행 가능한 것이 아니다. 미래 자료를 과거 cutoff에 소급하거나 근거 없는 가정을 실제 회사 사실로 승격하지 않는다. 새로운 공개근거를 확보하면 새 receipt/fact/config version으로 추가하고 새 build를 만든다.

설계서의 모든 확장 기능을 구현했다는 뜻도 아니다. 기간별 M2 자금조달·희석·pro forma와 IRR/ROIC, M3 비선형·복합 충격과 계약별 cure 경로, 실제 공개자료 기반 rolling reforecast·동결 예측의 out-of-time 검증은 [P0 구현 범위와 한계](p0_execution_status.md)에 남아 있다. 현재 사례에는 이를 경제적으로 정의할 입력·계약·baseline이 부족하다. 이번에는 해당 결과를 가상의 회사 숫자로 생성하지 않고, 입력이 부족한 위치를 재현 가능한 output에 연결했다. UI·대규모 저장소·성능 최적화도 아직 완성된 제품 기능으로 주장하지 않는다.

전체 사례는 `FEASIBILITY_ONLY` / `WITHHELD`다. 실제 투자·자본배분·신용 결론, 공개 release, 외부 reviewer 승인, 회사 도입은 주장하지 않는다.

## 최종 로컬 검증 기록

Windows / Python 3.12.10에서 다음을 확인했다.

- `python -m pytest`: **389 passed in 42.49s**.
- `python -m compileall -q src`: 통과.
- `python -m ruff check src tests`: 통과.
- 다섯 case의 일반 `validate-case`: 구조·lineage 통과. SWA는 실제 달력 기준 `horizon_end` 미확정 경고를 유지한다.
- 다섯 case의 `validate-case --release-ready`: 모두 차단(exit 1). SWA는 미확정 `horizon_end`에서 먼저 차단되므로 이 명령이 그 뒤의 모든 release gate를 평가했다고 주장하지 않는다.
- 각 case에 `reproduce-case ... --output-dir build/nonhuman_20261003/<case_id>`와 `verify-reproduction`을 실행했다. 총 10회 fresh build, 5개 bundle의 stable identity·파일별 hash 일치와 무결성 검증을 통과했다.

| Case | 동일하게 재현된 stage ID | 로컬 자동 인수인계 메모 |
|---|---|---|
| 오리온 | `3448fb733bb3132cb1cbc3e7` | [memo](../build/nonhuman_20261003/orion_jincheon_2026h1/reproduction_memo.md) |
| Walmart 실적 비교 | `d8c22be125bb69f625a34c30` | [memo](../build/nonhuman_20261003/walmart_fy27q1_guidance_outcome/reproduction_memo.md) |
| Walmart 가치평가 v2 | `aea0dc5d18056583f8214bd7` | [memo](../build/nonhuman_20261003/walmart_20260521_p1_valuation/reproduction_memo.md) |
| SWA | `a344637071fb7fb10c2dbd60` | [memo](../build/nonhuman_20261003/standard_lithium_swa_2025dfs/reproduction_memo.md) |
| Ford Credit | `e82a96df459f470a437f164e` | [memo](../build/nonhuman_20261003/ford_credit_2025ye_m3/reproduction_memo.md) |

각 memo 옆 `reproduction_report.json`에 전체 비교 hash와 source/config/code identity가 있다. 위 `build/` 링크는 로컬 재생성 산출물이며 commit 대상 또는 공개 release가 아니다. 기존 `build/review_20261003`의 v1 실행은 덮어쓰지 않았다. 원격 GitHub Actions 실행, 교차 플랫폼 검증, 독립 사람 검토는 이 기록에 포함하지 않는다.
