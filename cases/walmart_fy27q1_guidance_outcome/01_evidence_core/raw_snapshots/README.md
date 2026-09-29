# Raw snapshots

이용권리가 확인된 원문만 저장한다. 원문은 `raw_snapshots/{source_id}/{content_sha256}`에 내용 주소로 보존한다. `snapshot_id`와 retrieval timestamp는 `source_ledger.csv`의 불변 접수 기록에 보존한다. 동일 원문을 다시 조회해도 새 접수 기록은 남기며 이전 원문을 덮어쓰지 않는다.

공개 저장소에 넣으면 안 되는 자료는 이 폴더로 복사하지 않는다. locator만 보존하거나 별도의 격리 저장소를 사용한다.

Walmart FY27 Q1 case의 원문 PDF는 회사 사이트 이용약관상 재배포 권한이 확인되지 않았다. 이 폴더에는 PDF/HTML을 넣지 않고 `source_ledger.csv`의 locator와 해시만 사용한다.

