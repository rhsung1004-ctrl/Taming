# 묘지 배경 소품 제작 스크립트

`Assets/_Necro/Art/Environment/Graveyard` 의 모델과 텍스처를 만든 Blender 스크립트입니다. Unity는 이 폴더를 읽지 않습니다.
소품을 고치거나 다른 지역의 소품을 같은 방식으로 만들 때 씁니다 (Claude가 실행).

- `kit.py` — 공통 과정: 도형 조립 → 복셀 리메시 → 닳은 표면 → 저폴리 복사본 → 색·굴곡 굽기 → FBX 내보내기
- `assets.py` — 소품 16종의 형태와 재질
- `ground.py` — 이어 붙는 흙바닥 텍스처
- `beauty.py` — 소품으로 장면을 조립해 미리보기 렌더
- `run.py` — 실행: `blender -b -P run.py -- <출력 폴더> <all 또는 이름,이름> none <렌더 파일 앞부분>`

Blender 4.0 기준. 전체를 다시 굽는 데 약 25분 걸립니다.
