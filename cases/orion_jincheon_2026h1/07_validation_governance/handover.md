# 오리온 진천센터 공개자료 pilot: 재현·갱신·인계

**상태:** `FEASIBILITY_ONLY`, 공개 release `WITHHELD`. 개인 연구·학습용이며 AI 보조 작성이다. 독립적인 사람 검토와 프로젝트별 의사결정 근거 gate는 통과하지 않았다.

## 저장된 자료에서 현금 slice 재현

저장소 루트에서 새 build 경로를 지정한다. 아래 명령은 네트워크를 사용하지 않고 case의 locator, fact, mapping 및 정정 vintage를 읽어 Core 현금 대사를 다시 계산한다.

```powershell
$env:PYTHONPATH = 'src'
python -m versioned_finance_core validate-case cases/orion_jincheon_2026h1
python -m versioned_finance_core build-core cases/orion_jincheon_2026h1 --build-root build/orion_handover_recheck
python -m versioned_finance_core validate-case cases/orion_jincheon_2026h1 --release-ready
```

대사 대상은 2026년 상반기 ㈜오리온 모회사 **별도** 현금흐름표의 정정 vintage다. Core 결과의 closing cash는 254,143,639,226원이고 cash roll-forward residual은 0원이어야 한다. 마지막 `--release-ready`는 현재 차단 gate를 보고해야 정상이다. 새 build 경로와 결과 ID를 [판단 요약](../executive_summary.md)의 참조 ID와 대조한다. 결과 ID가 다르면 source/fact/config/code 또는 입력 순서가 변했는지 확인하고 자동으로 승인하지 않는다.

## 새 공시의 갱신

1. [공식 투자·재무 근거](../01_evidence_core/investment_evidence.md)에서 문서 ID, 최초 공개시각, 정정 관계, 법인·회계 범위와 권리를 확인한다. 보고기간 말일을 최초 공개시각으로 사용하지 않는다.
2. [DART 현금 수집기](../01_evidence_core/ingest_dart_cash.py)는 **헤더만 있는 새 case**에 최초 적재할 때 쓰는 고정 4문서 parser다. 저장된 이 case에 다시 실행하면 의도적으로 중단한다. 새로운 공시나 정정본은 기존 행을 덮어쓰지 않고 신규 source ID, receipt, fact ID, version으로 추가하고 parser와 원문 hash를 검토한다.
3. 원문 저장·재배포 권리가 확인되기 전에는 원문 HTML을 저장소에 넣지 않는다. 공식 locator, 수집 receipt, hash 및 허용된 최소 파생사실만 기록한다. 문서 byte hash가 기존 예상치와 다르면 재수집을 보류하고 정정·서식 변경 여부를 확인한다.
4. scope·단위·부호 mapping, 3표·현금·채무 대사와 M1/M2/M3 근거 gate를 재검토한다. 프로젝트별 지출·계약권·채무자 접근 가능 자금이 확인되지 않으면 결론과 release 상태를 계속 `WITHHELD`로 둔다.
5. `python -m pytest`, `python -m compileall -q src`, `python -m ruff check src tests`를 실행하고 새로운 build/stage 경로를 만든다. 독립 검토 finding에 대한 response와 retest를 기록한 뒤에만 publication gate를 다시 평가한다.

## Snapshot·release·rollback

`build/`는 재생성 가능한 staging이다. `releases/`는 모든 비보상적 gate가 통과한 경우에만 새 release ID로 발행하며 과거 release는 수정하지 않는다. 현재 case에 발행된 release는 없다. 향후 오류를 정정할 때는 새 fact/version과 `supersedes_release_id`가 있는 새 release를 만들고, rollback은 이전의 읽기 전용 release를 다시 가리키는 방식으로 처리한다. 기존 release 디렉터리의 내용은 고치지 않는다.

한 회사가 모든 모듈의 공개자료 gate를 충족할 필요는 없다. 이 case의 프로젝트 근거가 계속 부족하면 P0의 모듈별 case 허용 규칙에 따라 다른 회사를 선택하되 동일 계약과 테스트를 사용한다.
