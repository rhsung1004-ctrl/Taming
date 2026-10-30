# 에셋 넣기 가이드 (v0.2)

v0.2부터 **폴더에 FBX를 넣기만 하면** 도형 캐릭터가 실제 3D 모델로 바뀝니다.
모델이 없는 몬스터는 기존 도형 그대로 나오니, 하나씩 바꿔 가도 됩니다.

## 추천 에셋 (전부 CC0 — 상업 출시 가능, 출처 표기 불필요)

모두 Quaternius 제작으로 저폴리 스타일이 통일되어 있고, S20급 폰에서도 가볍습니다.

| 용도 | 에셋 | 가격 | 넣을 폴더 |
| --- | --- | --- | --- |
| 주인공 (여성) | Universal Base Characters — 여성 모델 1개 | 무료 (Standard) | `player` |
| 주인공 애니메이션 | Universal Animation Library — 걷기·달리기·공격 등 | 무료 (Standard) | `player` |
| 몬스터 | LowPoly Animated Monsters — 걷기·공격·비행 애니메이션 포함 | 원하는 만큼 (0원 가능) | 몬스터별 폴더 |
| 나무·바위 | Stylized Nature MegaKit — 나무 40종, 바위 27종 등 | Standard 무료 (팩의 60~70%) | `nature` |

다운로드 링크:
- https://quaternius.com/packs/universalbasecharacters.html
- https://quaternius.com/packs/universalanimationlibrary.html
- https://quaternius.itch.io/lowpoly-animated-monsters
- https://quaternius.com/packs/stylizednaturemegakit.html

## 넣는 방법

1. Unity 메뉴 **Tools → Taming → 모델 폴더 만들기** → `Assets/TamingModels/` 아래에 폴더 8개가 생깁니다.
2. 다운로드한 압축을 풀고 **FBX 파일**을 해당 폴더에 끌어다 놓습니다.

| 폴더 | 넣을 것 | 고르는 기준 |
| --- | --- | --- |
| `player` | 여성 베이스 캐릭터 FBX 1개 + 애니메이션 FBX | 자동으로 Humanoid 설정 |
| `slime` | 몬스터 팩에서 둥글고 작은 녀석 | 탱커 느낌 |
| `fox` | 작고 빠른 네발 몬스터 | 스타터 펫 |
| `wolf` | 큰 네발 몬스터 | 지상 탈것이 됨 |
| `bird` | 날개 달린 작은 몬스터 | 첫 비행 탈것 |
| `lizard` | 꼬리 달린 원거리형 | 불 속성 |
| `griffon` | 가장 크고 멋진 날개 몬스터 | 2단계 비행 탈것 |
| `nature` | 이름에 tree / pine / rock / stone 이 들어간 FBX | 섞어서 무작위 배치 |

3. 끝. 넣는 순간 자동으로 연결표(`Assets/Resources/TamingModelLibrary`)가 갱신됩니다. Play를 누르면 바뀐 모델이 나옵니다.

## 자동으로 처리되는 것

- 크기: 종류별 기준 키(작은 몬스터 0.85m, 일반 1.25m, 주인공 1.75m)에 자동으로 맞춤
- 애니메이션: 클립 이름으로 자동 연결 — idle(대기), walk(걷기), run·jog(달리기), fly(비행), attack·punch·bite(공격), sit·ride(탑승)
- 반복 재생 설정, Humanoid/Generic 설정
- 주인공 오른손에 지팡이 장착

## 모델이 이상할 때

`Assets/Resources/TamingModelLibrary`를 클릭하면 Inspector에서 몬스터별로 조정할 수 있습니다.
- **Yaw**: 모델이 뒤를 보고 걸으면 `180`, 옆을 보면 `90` 또는 `-90`
- **Height Mul**: 크기 배율 (1.5 = 1.5배)

값은 FBX를 다시 넣어도 유지됩니다.
