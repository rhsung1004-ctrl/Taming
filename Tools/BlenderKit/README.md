# BlenderKit — 배경 소품 제작 도구

`Assets/_Necro/Art/Environment/Graveyard` 의 모델(.fbx)과 텍스처를 만드는 Blender 스크립트. Unity는 이 폴더를 읽지 않는다.
Blender 4.0 배경 실행으로 돌린다 (Claude가 실행).

```
python3 atlas.py <출력>                     잎 아틀라스 foliage_atlas.png (한 번)
blender -b --python-exit-code 1 -P build.py -- <출력> <묶음> [이름,이름|all] [preview|nopreview]
```

- `kit.py` 공통 도구 · `preview.py` 확인 렌더 · `compare.py` 전후 비교 렌더 · `build.py` 실행기 · `atlas.py` 잎 아틀라스
- `assets_<묶음>.py` 묶음별 소품 정의: `BUILDERS`, `META`, `PREVIEWS`
- 결과: `<이름>.fbx` (LOD0, LOD1[, LOD2]), `<이름>_albedo.jpg`, `<이름>_normal.png`, `manifest_<묶음>.json`, 미리보기 `_pv_<묶음>_*.png`

## 미술 기준 (가장 중요)

애니풍 **다크 판타지**. "정으로 깎은 고급 스타일라이즈드" — 손칠 판타지 게임의 돌처럼 **큰 면은 평평하게, 모서리는 또렷하게**.
녹은 밀랍·점토처럼 울퉁불퉁하고 흐린 표면은 실패다. 가까이(1~2m)에서 봐도 아래 네 가지가 지켜져야 한다.

1. **형태**: 넓은 면은 평평하고 얕은 평면 끌 자국(chisel)으로 작은 평면들이 보인다. 모서리는 곧고 날카롭다. 깨진 곳은 평면으로 쳐낸
   각진 자국(chip, slice_rock, chunk). 큰 진폭의 둥근 굴곡(lumps)·고리 모양 금(fissure)·물결치는 턱은 쓰지 않는다.
2. **선명함**: 텍스처는 작은 소품도 2048. 텍셀 밀도는 작은 소품 **512 px/m 이상**(2048 이면 1000 안팎), 중간 300 px/m 이상,
   큰 구조물 200 px/m 이상 — 중간·큰 것의 1~2m 근접은 Unity 디테일 맵(`detailtex.py`, URP Lit Detail)이 맡는다. 빌드 로그 `TEXEL` 줄로 확인한다.
3. **색 (손칠)**: 위는 밝고 아래·틈은 깊은 보라, 닳은 모서리는 밝은 선, 블록마다 색조가 다르다(차가운 청색 ↔ 보랏빛·따뜻한 회색).
   이끼는 위를 향한 면과 위쪽 틈에 가장자리가 또렷한 덩어리로, 땅 쪽은 흙물과 기어오르는 이끼. 붓 자국·잔 점은 낮은 대비로.
4. **굽기 흠 없음**: 검은 얼룩·검은 줄·이음매·자홍 테두리가 없어야 한다 (로그 `BAKE ... miss 0.000%`).

- **실루엣**: 완벽한 직선·대칭 금지. 기울고, 깨지고, 빠지고, 무너진 곳이 있어야 한다. 단, 형태가 무엇인지는 한눈에 읽혀야 한다.
- **음산함 + 화려함**: 전체는 어둡고 낡았지만, 영혼 발광(보라 `Glow_Soul`, 창백한 청록 `Glow_Spirit`)이 군데군데 강하게 빛난다. 덩굴·이끼·거미줄로 버려진 세월을 보여 준다.
- 매 소품마다 **이전 판과 나란히 가까이·중간 거리로 렌더해서 직접 보고** 판단한다 (`compare.py`).
  "녹은 밀랍 같다", "흐리다", "검은 얼룩", "모서리가 뭉개졌다", "장난감 같다" 중 하나라도 보이면 고친다.

## 좌표·크기 규칙

- 단위 m, Z 위, **앞면은 -Y** (묘비 글자, 문, 석상 얼굴이 -Y를 향한다)
- 원점 = 바닥 중심 (z=0 이 땅). 땅에 묻히는 부분은 z<0 으로 조금 내려도 된다 (META.sink 로도 조절)
- Unity로 가면 앞면(-Y)이 Unity의 +Z를 향한다. 배치 회전은 월드 생성기와 Unity 도구가 처리한다

## 예산

| 크기 | 예 | LOD0 삼각형 | 텍스처 (v3) | 텍셀 목표 |
| --- | --- | --- | --- | --- |
| 작은 소품 (~1m) | 묘비, 해골, 양초 | 600~4,000 | 2048 | 1000 px/m 안팎 |
| 중간 (2~5m) | 기둥, 석상, 바위, 죽은 나무 | 3,000~9,000 | 2048 | 300~500 px/m + 디테일 맵 |
| 큰 구조물 (5m~) | 벽, 납골당, 성당 폐허, 절벽 | 10,000~30,000 | 2048 (주인공급만 4096) | 200 px/m 이상 + 디테일 맵 |
| 식물 (굽지 않음) | 풀 덤불, 꽃, 버섯 | 100~1,500 | 아틀라스 공유 | — |

LOD1 = 35%, 큰 것은 LOD2 = 12% (`finish(..., lod1=0.35, lod2=0.12)`).

## 만드는 과정 (kit.py, v3)

v3 함수는 새 이름으로만 들어 있다. 예전 함수(`sculpt`, `paint`, `STONE_LAYERS`, `finish` 기본 인자)는 그대로라 v3 로 바꾸지 않은 묶음도 그대로 빌드된다.

```python
from kit import *        # 주의: sc 는 init 뒤에 생기므로 kit.sc 또는 link(o) 를 쓴다
rng = random.Random(7)
# 1. 조립: 깨끗한 형태 (bmesh 상자·윤곽 기둥, 바위는 slice_rock). 모서리를 평면으로 쳐낸다
body = join([box(...), ...])
chip(body, rng, 14, (0.03, 0.08), bite=0.38)
low_src = copy(body)                          # (석물) 저폴리 바탕 = 큰 깨짐까지만, 새김·얇은 떨어짐은 노멀맵으로
cut(body, [...])                              # 새김·구멍 (boolean)
engrave_v(body, strokes, (0, -1, 0), 0.011, 0.007)   # 글자·선은 V 자 홈 (vgroove)
# 2. 조각: 블록 번호 → 리메시 + 원래 표면에 되붙임(평평한 면·날카로운 모서리) → 조각 층
carve(body, 0.0025, *STONE3(1.0, wear=1.1, cracks=0.45), seed=11)
# 3. 칠: 손칠 재질 (위 밝고 아래·틈 보라, 베벨로 찾은 닳은 모서리, 블록마다 색조, 이끼, 흙물)
set_mat(body, paint3("이름", 'stone', h=1.1, k=1.0, moss=0.45, moss_low=0.85, moss_low_h=0.4))
# 4. 저폴리 (석물: 깨끗한 형태에서. 붙은 조각은 union 으로 합쳐 속에 묻힌 면을 없앤다)
low = lowpoly(low_src, z=-0.015)
# 5. 굽기 우리(cage) + UV 다시 배치 + 빈 곳 메우기 + LOD + FBX
finish3("이름", [body], [low], extras=[...], size=2048, cage=0.006, hard=55)
```

### 종류별 권장값

| 종류 | carve voxel | 조각 층 | 저폴리 | cage (push / cage_reach) | hard | uv_margin |
| --- | --- | --- | --- | --- | --- | --- |
| 작은 석물 ~1m (묘비·십자가) | 0.0025 | `STONE3(1.0)` | `lowpoly(새김 전 형태)` | 0.006 / 0.2 | 55 | 0.003 |
| 블록 많은 석조 (벽·기둥·계단) | 0.008~0.009 | `STONE3(1.25)` | `carve(..., base=True)` → `low_of` | 0.01 / 0.1 | 없음 | **0.001** |
| 바위 2~4m | 0.009 + `relax=2` | `ROCK3(k=크기/2)` 를 모두 fine 에 | spall 전 `copy` → `low_from` | 0.015 / 0.12 | 없음 | 0.003 |
| 죽은 나무 | 0.0075 | `BARK3` (guide 필요) | `tree_build(..., fin=dict(cage=…, pack=True, margin=0, …))` | 0.006 / 0.03 | 없음 | 0.001 |

- `carve(o, voxel, coarse, fine, seed, snap=True, pieces=True, base=False, relax=0)`: `relax` = 되붙인 리메시의 오목한 꺾임에 남는 잔 톱니를 편다
  (깊은 벽이 있는 바위는 2, 석물은 0). `pieces` = 떨어진 조각(블록)마다 'piece' 값 → `paint3` 가 블록마다 색조를 바꾼다.
  `base=True` 면 저폴리 바탕(되붙이지 않은 리메시 + coarse)을 돌려준다. coarse 는 저폴리 바탕에도 들어가니 몇 mm 이하만.
- 조각 층 (`surface`): **chisel**(평면 끌 자국, v3 의 주력), **cracks**(곧게 꺾인 금, `warp` 0.08, cover 0.15~0.3 으로 드물게), pits, grain,
  bark, strata, lumps(아주 약하게). terrace 는 `soft` 0.35(기본) 그대로만.
- `paint3(name, pal, h=높이, k=무늬 배율, ...)`: `cells=` 를 주면 블록 번호 대신 큰 칸(m)으로 색조를 나눈다 (바위). `edge_w` 닳은 모서리 폭,
  `ao` 그늘 거리(틈 그늘은 그 1/10), `stains` 삭은 얼룩(곱하기), `tooling` 끌 자국 결(노멀). 묶음의 덧칠(blotch, grad_dark, top_cover, moss_low)도 그대로 얹을 수 있다.
- `finish3(..., size=2048, cage=push, cage_reach=…, hard=각도, uv_margin=…, samples=8)`:
  - 굽기 우리: 저폴리 정점·면 가운데에서 법선으로 광선을 쏴 원본이 바깥에 있으면 그만큼 + push 부풀린 사본. extr 하나로 맞추던 때의 검은 얼룩·줄이 없어진다.
  - 저폴리·우리는 광선에 안 보이게 하고, `paint3` 의 AO 는 자기 객체만 본다 (저폴리에 가려 그늘이 검게 번지던 원인).
  - 여백 없이 굽고(자홍으로 채워 둔 그림) 빈 곳을 둘레 색으로 메운다 → 섬 가장자리에 자홍·검정 테두리가 없다.
  - 노멀맵에서 70도 넘게 누운 법선은 세운다 (`clamp_normals`, 로그 `steep %`). 깊은 골·겹친 부품에서 검은 점이 되던 것.
  - `hard`: UV 섬 경계이면서 그 각도보다 꺾인 모서리를 단단하게 → 평평한 면의 노멀맵이 휘지 않아 중간 거리에서 또렷하다. 깨끗한 저폴리(석물)에만.
  - albedo 는 sRGB 그대로 저장한다 (예전 `_save_jpg` 는 AgX 보기 변환이 입혀져 밝은 색이 바래 있었다 → 다시 만들면 조금 밝고 진해진다).
- 로그 읽기: `TEXEL 이름 px/m … uv_fill …` (uv_fill 0.45 미만이면 uv_margin·저폴리를 의심), `UVPACK`, `CAGE … max`,
  `BAKE … miss % steep %` (miss 는 0, steep 은 1% 안팎이 정상), `PIECES`.
- 비교 렌더: `blender -b -P compare.py -- <이전 폴더> <새 폴더> <이름> <출력 접두사> [near=x,y,z,거리,방위,앙각]` → `_near.png`, `_mid.png`.

### 피할 것 (v3 를 만들며 겪은 것)

- **값이 뚝 끊기는 조각 층**(plates, soft 를 줄인 terrace): 복셀 격자에 톱니가 생겨 굽은 뒤 테두리 잡음. 이어지는 층(chisel, cracks)을 쓴다.
- **fissure**: 잡음 등고선이라 작은 고리(녹은 밀랍 무늬)가 생긴다 → cracks.
- **벽이 수직인 새김 상자**(stroke_box): 글자 테두리가 1화소 검은 점선 → `vgroove` / `engrave_v`.
- **큰 조각(수 cm)까지 들어간 리메시에서 저폴리 줄이기**: 면이 구겨져 UV 섬이 수천 개, 텍셀이 반토막 → 조각 전 바탕에서.
- **깊은(3cm↑) spall 을 저폴리가 따라가게**: 벽이 검은 톱니 테두리 → 저폴리는 spall 전 형태, spall 은 2~4cm 로 얕게, `carve(relax=2)`.
- **섬이 수백 개인데 uv_margin 0.003 이상**: 여백이 텍스처를 절반 넘게 먹는다 (벽 0.27 → 0.001 로 0.52).
- **되붙인(snap) 리메시를 그대로 줄여 저폴리 만들기**: 모서리에 접힌 잔 삼각형 → UV 가 쪼개진다 (`carve(base=True)` 는 알아서 피한다).
- 나무는 cage_reach 를 작게 (0.03): 껍질 조각은 거의 안쪽으로 파이므로 그 이상 부풀릴 까닭이 없고, 크면 줄기에 박힌 잔가지까지 우리가 부푼다.
  깊은 껍질 골·잔가지가 박힌 곳의 검은 점은 극단 법선 때문이라 `clamp_normals` 가 고친다.

### 예전 방식 (v2, 아직 v3 로 바꾸지 않은 묶음)

- `sculpt(body, voxel, STONE_LAYERS(...))` + `paint(...)` + `finish(..., size=1024, extr=0.03)`. `finish` 의 기본 동작은 그대로이고,
  광선이 빗나가 검게 남은 화소는 이제 둘레 색으로 메운다 (`fill_holes`), albedo 는 sRGB 로 저장한다.
- 바위·절벽: `slice_rock(o, rng, planes, depth)` 로 평면으로 깎은 각진 덩어리를 먼저 만든다 (구를 그대로 쓰면 달걀이 된다)
- 나무: 뼈대 메쉬(각 점에 'dir' 속성) + Skin 수정자 → `surface(..., [{'t':'bark',...}], guide=뼈대)` 로 가지 방향을 따라 껍질 균열
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
    "light": {"offset": [0.5, 0, 2.28], "color": [0.62, 0.35, 1.0], "intensity": 9, "range": 9},  # 선택: 발광 부품 자리에 점광원
    "detail": "stone",       # 선택: Unity Main 재질의 근접 디테일 — stone / wood / bone / metal / none
  },
}
```

`detail` 을 빼면 Unity 도구가 이름 → tags 순으로 정한다 (`NecroProps.DetailKindFor`):
이름에 mushroom·lotus·candle → none, lantern·iron·cage·chain → metal, bone·skull·dragon·rib·spine·claw → bone,
tree·stump·log·root·coffin·cart·plank → wood, grave·ruin·rock·cliff·statue·pillar·wall·stair·altar·crypt·tomb·obelisk·rubble → stone.
이름으로 못 정하면 tags: bone → bone, rock·cliff·grave·ruin·landmark → stone, nature → wood, 그 밖에는 stone.
재료가 섞인 소품은 겉넓이가 큰 쪽으로 적는다 (돌 기둥 + 쇠창살인 fence 는 stone). 잔무늬 텍스처는 `python3 Tools/BlenderKit/detailtex.py` 로 만든다
(`Assets/_Necro/Art/Materials/Detail/detail_<종류>_albedo.png`·`_normal.png`, 이어 붙는 1024, 한 장 = 실제 0.6~0.9 m).
