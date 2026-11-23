# BlenderKit — 배경 소품 제작 도구

`Assets/_Necro/Art/Environment/Graveyard` 의 모델(.fbx)과 텍스처를 만드는 Blender 스크립트. Unity는 이 폴더를 읽지 않는다.
Blender 4.0 배경 실행으로 돌린다 (Claude가 실행).

```
python3 atlas.py <출력>                     잎 아틀라스 foliage_atlas.png (한 번)
blender -b --python-exit-code 1 -P build.py -- <출력> <묶음> [이름,이름|all] [preview|nopreview]
```

- `kit.py` 공통 도구 · `preview.py` 확인 렌더 · `build.py` 실행기 · `atlas.py` 잎 아틀라스
- `assets_<묶음>.py` 묶음별 소품 정의: `BUILDERS`, `META`, `PREVIEWS`
- 결과: `<이름>.fbx` (LOD0, LOD1[, LOD2]), `<이름>_albedo.jpg`, `<이름>_normal.png`, `manifest_<묶음>.json`, 미리보기 `_pv_<묶음>_*.png`

## 미술 기준 (가장 중요)

애니풍 **다크 판타지**. 손으로 칠하고 정으로 깎은 듯한 고급 스타일라이즈드 (매끈한 점토 느낌 금지).

- **표면**: 돌은 모서리가 평평하게 깨져 나가고(chip), 겹겹이 떨어져 나간 턱(terrace)과 구불구불한 금(fissure), 잔 구멍(pits)이 실제 형태로 있어야 한다. 넓은 면이 밋밋하게 남으면 실패.
- **실루엣**: 완벽한 직선·대칭 금지. 기울고, 깨지고, 빠지고, 무너진 곳이 있어야 한다. 단, 형태가 무엇인지는 한눈에 읽혀야 한다.
- **색**: 차가운 청회색 돌 + 보랏빛 그늘(틈은 깊은 보라), 청록 이끼, 흙물 든 아래쪽, 빗물 자국. 닳은 모서리는 밝게.
- **음산함 + 화려함**: 전체는 어둡고 낡았지만, 영혼 발광(보라 `Glow_Soul`, 창백한 청록 `Glow_Spirit`)이 군데군데 강하게 빛난다. 덩굴·이끼·거미줄로 버려진 세월을 보여 준다.
- 매 소품마다 **가까이 렌더해서 직접 보고** 판단한다. "매끈하다", "장난감 같다", "형태가 안 읽힌다" 중 하나라도 해당하면 고친다.

## 좌표·크기 규칙

- 단위 m, Z 위, **앞면은 -Y** (묘비 글자, 문, 석상 얼굴이 -Y를 향한다)
- 원점 = 바닥 중심 (z=0 이 땅). 땅에 묻히는 부분은 z<0 으로 조금 내려도 된다 (META.sink 로도 조절)
- Unity로 가면 앞면(-Y)이 Unity의 +Z를 향한다. 배치 회전은 월드 생성기와 Unity 도구가 처리한다

## 예산

| 크기 | 예 | LOD0 삼각형 | 텍스처 |
| --- | --- | --- | --- |
| 작은 소품 (~1m) | 묘비, 해골, 양초 | 1,500~4,000 | 1024 |
| 중간 (2~5m) | 기둥, 석상, 바위, 죽은 나무 | 3,000~9,000 | 1024 (석상·나무는 2048 가능) |
| 큰 구조물 (5m~) | 납골당, 성당 폐허, 절벽 | 10,000~30,000 | 2048 |
| 식물 (굽지 않음) | 풀 덤불, 꽃, 버섯 | 100~1,500 | 아틀라스 공유 |

LOD1 = 35%, 큰 것은 LOD2 = 12% (`finish(..., lod1=0.35, lod2=0.12)`).

## 만드는 과정 (kit.py)

```python
from kit import *        # 주의: sc 는 init 뒤에 생기므로 kit.sc 또는 link(o) 를 쓴다
rng = random.Random(7)
body = join([box(...), cyl(...)])            # 1. 조립 (box, cyl, sphere, torus, prism, pointed_arch, mesh_from)
remesh(body, 0.01)                            #    (여러 도형이면 먼저 한 덩어리로)
chip(body, rng, 16, (0.04, 0.1), bite=0.35)   # 2. 모서리를 평평하게 쳐낸다 — 새김(cut)보다 먼저!
cut(body, [box(...), ...])                    #    새김·구멍 (boolean)
sculpt(body, 0.005, STONE_LAYERS(1.0), seed=1)  # 3. 리메시 + 조각 (돌: STONE_LAYERS, 바위: ROCK_LAYERS, 직접 층 목록도 가능)
set_mat(body, paint("이름", 'stone', moss=0.7))  # 4. 칠하기 (PAL: stone, stone_pale, stone_warm, stone_dark, marble, iron, rust, bark, bark_pale, wood, bone, earth, cloth)
low = decimated(body, 3200)                   # 5. 저폴리
finish("grave_slab_a", [body], [low], extras=[...], size=1024, extr=0.03)   # 6. 굽기 + LOD + FBX
```

- 바위·절벽: `slice_rock(o, rng, planes, depth)` 로 평면으로 깎은 각진 덩어리를 먼저 만든다 (구를 그대로 쓰면 달걀이 된다)
- 나무: 뼈대 메쉬(각 점에 'dir' 속성) + Skin 수정자 → `surface(..., [{'t':'bark',...}], guide=뼈대)` 로 가지 방향을 따라 껍질 균열
- 조각 층 (`surface`): lumps, terrace(겹겹이 떨어진 턱), fissure(자연스러운 금), cracks(그물 금, 덜 자연스러움), plates, pits, grain, strata(절벽 층리), bark
- voxel 크기: 작은 소품 0.004~0.006, 중간 0.008~0.012, 큰 구조물 0.02~0.04. 작을수록 날카롭지만 느리다
- `extr`(굽기 거리): 작은 소품 0.02~0.03, 바위·큰 것 0.05~0.12. 굽기 결과에 검은 얼룩이 생기면 키운다
- 발광 부품: `glow(o, 'Glow_Soul')` 후 `extras` 로 넘긴다. 잎·덩굴: `ivy(...)` 결과나 Foliage 재질 부품을 `extras` 로
- 식물(풀·꽃·버섯): 굽지 않는다. `mesh_from` + `vcolor`(정점 색, 알파 = 흔들림 0 뿌리~1 끝) + `set_uv(..., atlas_uv('칸',u,v))` + `set_mat(o, foliage_mat())` → `finish_foliage(name, parts)`
- 아틀라스 칸: solid, ivy_a, ivy_b, leaf_dead, fern, grass_card, moss_hang, petal, web, cloth, thorn_leaf, stem, lily, mushroom_gill, reed, web_corner

## META (manifest 에 들어가 월드 생성기와 Unity 도구가 쓴다)

```python
META = {
  "grave_slab_a": {
    "kind": "prop",          # prop: 게임 오브젝트로 배치 / tree: 지형 나무 인스턴스(Y축 회전만, 대량) / detail: 지형 풀(대량, 콜라이더 없음) / landmark: 큰 구조물
    "tags": ["grave"],       # 배치 규칙용: grave, ruin, nature, rock, cliff, foliage, bone, light, landmark, swamp, path
    "collider": "box",       # mesh / box / capsule / none
    "footprint": 0.6,        # 배치 간격 반지름 (m)
    "sink": 0.04,            # 땅에 묻는 깊이 (m)
    "tilt": 8,               # 무작위 기울기 최대 (도)
    "align": false,          # 지형 경사에 맞춰 눕힐지 (바위 true, 건물 false)
    "scale": [0.9, 1.2],     # 무작위 크기 범위
    "cull": 0.012,           # LOD 컬링 화면 높이 비율 (작은 것 0.02, 큰 것 0.003)
    "shadows": true,
    "light": {"offset": [0.5, 0, 2.28], "color": [0.62, 0.35, 1.0], "intensity": 9, "range": 9}   # 선택: 발광 부품 자리에 점광원
  },
}
```
