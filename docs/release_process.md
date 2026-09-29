# Release Process

release는 build 결과를 복사한 폴더가 아니라 특정 cutoff·입력·코드·결론을 함께 고정한 검토 단위다.

## 순서

1. case와 분석 cutoff를 잠근다.
2. source rights와 point-in-time eligibility를 확인한다.
3. normalization과 재무 identity를 통과시킨다.
4. 활성 모듈의 전용 gate를 판정한다.
5. adverse evidence, counterargument, unknown과 limitation을 기록한다.
6. memo 숫자와 model output을 대사한다.
7. 파일 hash와 gate 결과를 manifest에 저장한다.

gate 하나가 material하게 실패하면 다른 점수로 상쇄하지 않는다. 실패한 lens는 비활성화하거나 `WITHHELD`로 공개 상태를 낮춘다. 독립 reviewer가 없으면 `SELF_REVIEWED_LIMITED_USE`를 사용한다.

## 코드 경로와 판정

`build_manifest(case_dir)`와 CLI `build-manifest`는 항상 `WITHHELD` 초안을 만든다. CLI 기본 출력은 `build/<case_id>/<staging_id>/release_manifest.json`이며, 같은 경로를 다시 쓰려 하면 오류가 난다. `write_manifest(..., output=...)`도 기존 파일을 덮어쓰지 않는다.

공통 gate 목록과 활성 모듈별 gate ID는 `config/defaults/release_gates.json`에서 읽는다. M1은 case의 `perspective_id`에 맞는 Performance 또는 Valuation gate를 선택한다. case activation gate와 선택된 모듈 activation state도 `PASS`여야 한다. `gate_results.csv`에서는 필수 gate가 각각 `PASS`이고 근거가 있어야 한다. 누락, 중복, `NOT_EVALUATED`, `FAIL`, `WITHHELD`, 필수 gate의 `NOT_APPLICABLE`, 근거 없는 판정은 발행을 막는다.

`review_findings.csv`의 `BLOCKING`·`CRITICAL`·`MATERIAL` finding은 gate 표기가 `PASS`여도 미해결이면 발행을 막는다. 해결로 기록한 중대 finding에는 reviewer, finding·evidence, response, resolution, retest_result가 있어야 한다. 선택한 memo는 선택한 비 memo JSON output의 `output_id`를 참조해야 한다. 참조 누락이나 오래된 ID는 `WITHHELD`로 남는다. 이 검사는 ID 연결을 확인하며 memo 문장의 모든 숫자를 재계산하지는 않는다.

`validate-case <case_dir> --release-ready`는 구조·case 계약에 더해 source cutoff/권리, activation 및 release gate, 미해결 중대 finding을 검사하고 실패 시 종료 코드 1과 차단 ID를 출력한다. 선택 output·memo·재현 명령과 code/config hash는 `stage-release`/`publish-release`에서 추가 검사한다.

`stage_release(case_dir, stage_root, output_paths=..., memo_paths=..., external_outputs=..., reproduction_command=...)`는 지정된 새 경로에 case 파일, 외부 build output과 manifest를 복사한다. 외부 output은 snapshot 상대경로와 실제 파일 경로의 매핑으로 전달한다. 단계별 입력·출력·memo의 SHA-256을 따로 기록하고, 검증된 source receipt의 `source_id`·`snapshot_id`·원문 hash로 source fingerprint를 만든다. `raw_snapshots/`, `private/`, `quarantine/`, secret 파일은 snapshot에 포함하지 않는다. 공개 권한이 확인되지 않은 원문은 locator와 hash만 기록한다. symlink는 거부한다.

source receipt는 권리·cutoff의 `YES`/`NO` 형식과 receipt ID를 검증한다. `PUBLIC_OFFICIAL`·`PUBLIC_COMPANY`·`PUBLIC_REGULATORY` 이외의 자료, cutoff 이후 공개자료, cutoff 미적격 자료, 변환권리 없는 파생 fact는 발행할 수 없다. licensed·account/fee·confidential source가 있으면 raw fact가 섞인 case를 staging으로 복사하지 않는다. 합성 fixture는 통제 테스트의 staging까지만 허용하며 실제 case release에는 사용하지 않는다.

`publish_release(stage_dir, releases_root)`는 stage의 파일 hash와 현재 code/config hash를 다시 확인하고, gate 및 case 준비 상태를 재평가한다. 모두 통과한 경우에만 `releases/<case_id>/<release_id>/`를 새로 만든다. 같은 release ID가 있으면 실패하며 기존 release를 수정하지 않는다. release 파일은 읽기 전용으로 설정한다. 정정은 새 content/release ID와 `supersedes_release_id`로 연결한다.

`content_hash`는 cutoff와 source/input/config/code/output/memo hash로 계산한다. `release_id`에는 content hash와 gate·review·limitation 판정이 포함된다. `generated_at`과 `released_at`은 이 식별자에서 제외되므로 같은 계산 입력과 코드에서 같은 결과 hash를 재현할 수 있다. `runtime_environment`, `reproduction_command`, review 상태와 알려진 제한사항은 manifest에 남긴다.

현재 실제 분석 case 상태는 `SCAFFOLD_ONLY`다. 합성 D0 실행 경로가 있어도 템플릿의 미평가 gate와 빈 source ledger로는 발행할 수 없으며, 실제 회사 결론이나 release는 없다.

