# Case release staging

case 내부의 release 준비영역이다. gate 통과 후 고정 snapshot은 저장소 루트의 `releases/<case_id>/<release_id>/`로 생성한다.

manifest 계약은 schema/contract version 2다. source·input·config·code·output의 hash, cutoff, gate·review·limitation, 실행환경과 재현 명령을 보존한다. `content_hash`는 생성시각과 분리된 계산 결과 identity이며, material gate가 통과하기 전 `publication_state`는 `WITHHELD`다. 기존 release는 덮어쓰지 않고 새 ID와 `supersedes_release_id`로 정정한다.

공통 gate와 활성 모듈 gate ID는 `config/defaults/release_gates.json`에서 읽는다. M1은 case의 `perspective_id`에 맞는 performance 또는 valuation gate 하나를 평가한다.

**이 case에는 공개 release가 없다.** `release_manifest.json`의 `publication_state=WITHHELD`는 비교 artifact가 완전한 M1 판단·재무모델·독립 검토 gate를 통과하지 못했음을 뜻한다. 가이던스 결과 대조 파일은 연구용 case artifact이며 immutable publication이 아니다.

