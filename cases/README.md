# Cases

각 분석대상은 `_template`을 복제한 독립 디렉터리다. 한 case 안에서 source, normalized data, model input, 판단 기록과 release 준비물을 함께 추적한다.

```powershell
$env:PYTHONPATH = "src"
python -m versioned_finance_core init-case my_case
```

`raw_snapshots`에는 이용권리가 확인된 자료만 둔다. credential, 개인정보, 고용주·계약상 비공개 자료, 재배포가 금지된 feed는 저장하지 않는다.

