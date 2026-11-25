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
2. **선명함**: 텍스처 크기와 텍셀 밀도는 아래 '예산' 표를 따른다 (작은 소품 1024 로 **550 px/m 이상**, 중간 350 px/m 이상,
   큰 구조물 200 px/m 이상) — 중간·큰 것의 1~2m 근접은 Unity 디테일 맵(`detailtex.py`, URP Lit Detail)이 맡는다. 빌드 로그 `TEXEL` 줄로 확인한다.
3. **색 (손칠)**: 위는 밝고 아래·틈은 깊은 보라, 닳은 모서리는 밝은 선, 블록마다 색조가 다르다(차가운 청색 ↔ 보랏빛·따뜻한 회색).
   이끼는 위를 향한 면과 위쪽 틈에 가장자리가 또렷한 덩어리로, 땅 쪽은 흙물과 기어오르는 이끼. 붓 자국·잔 점은 낮은 대비로.
4. **굽기 흠 없음**: 검은 얼룩·검은 줄·이음매·자홍 테두리·흰 보풀 테두리가 없어야 한다 (로그 `BAKE ... miss 0.000% steep 2% 미만`, `WARN BAKE` 없음).

- **실루엣**: 완벽한 직선·대칭 금지. 기울고, 깨지고, 빠지고, 무너진 곳이 있어야 한다. 단, 형태가 무엇인지는 한눈에 읽혀야 한다.
- **음산함 + 화려함**: 전체는 어둡고 낡았지만, 영혼 발광(보라 `Glow_Soul`, 창백한 청록 `Glow_Spirit`)이 군데군데 강하게 빛난다. 덩굴·이끼·거미줄로 버려진 세월을 보여 준다.
- 매 소품마다 **이전 판과 나란히 가까이·중간 거리로 렌더해서 직접 보고** 판단한다 (`compare.py`).
  "녹은 밀랍 같다", "흐리다", "검은 얼룩", "모서리가 뭉개졌다", "장난감 같다" 중 하나라도 보이면 고친다.

## 좌표·크기 규칙

- 단위 m, Z 위, **앞면은 -Y** (묘비 글자, 문, 석상 얼굴이 -Y를 향한다)
- 원점 = 바닥 중심 (z=0 이 땅). 땅에 묻히는 부분은 z<0 으로 조금 내려도 된다 (META.sink 로도 조절)
- Unity로 가면 앞면(-Y)이 Unity의 +Z를 향한다. 배치 회전은 월드 생성기와 Unity 도구가 처리한다

## 예산

| 크기 | 예 | LOD0 삼각형 | 텍스처 | 텍셀 목표 |
| --- | --- | --- | --- | --- |
| 작은 소품 (가장 긴 변 1.5 m 미만) | 묘비, 해골, 양초 | 600~4,000 | **1024** | 550~650 px/m (`uv_weight` 로 앞면에 더) |
| 중간 (1.5~5 m) | 기둥, 석상, 바위, 죽은 나무 | 750~9,000 | 2048 | 350~450 px/m, 나무 줄기 밑동 500 이상 + 디테일 맵 |
| 큰 구조물 (5 m~) | 벽, 납골당, 성당 폐허, 절벽 | 10,000~30,000 | 2048 | 200 px/m 이상 + 디테일 맵 |
| 식물 (굽지 않음) | 풀 덤불, 꽃, 버섯 | 100~1,500 | 아틀라스 공유 | — |

- **텍스처 크기 규칙** (저장소 Git LFS 1 GB, Graveyard 폴더 합계 300 MB 안): 가장 긴 변 1.5 m 미만 1024, 그 밖 2048, **4096 금지**.
  `finish3(size='auto')`(기본)가 규칙대로 고르고, 2048 보다 큰 값을 주면 2048 로 낮추고 `WARN tex` 를 찍는다.
- 노멀 PNG 는 저장할 때 최대 압축한다 (`save_png` → `png_max`: PIL optimize + compress_level 9, Blender 기본보다 15~20% 작다). 로그 `FILES` 줄에 kB.
  v3b 시범 파일 크기(albedo / normal): 묘비 1024 136 kB / 1.1 MB, 바위 2048 0.5 / 2.7 MB, 벽 2048 0.9 / 4.6 MB, 나무 2048 0.7 / 5.2 MB.
  잔결이 많은 노멀맵(껍질·벽)이 크다 — 소품 하나 평균 4 MB 로 잡으면 62종 ≈ 250 MB.
- **LOD 규칙** (`finish3` 의 `lod_rule`, 기본 켬. 로그 `LODRULE`): 본체(Main) 삼각형이
  - 1,000 미만(깨끗한 저폴리 석물·바위): LOD1 은 본체를 줄이지 않고 잎·덩굴·풀 카드만 뺀다. 잎이 없으면 LOD1 을 만들지 않는다
    (깨끗한 저폴리를 35% 로 줄이면 실루엣·단단한 모서리·UV 이음매가 무너진다).
  - 1,000~3,000: LOD1 비율을 0.6 이상으로.
  - 그 밖: LOD1 0.35, 큰 것은 LOD2 0.12 (`finish3(..., lod1=0.35, lod2=0.12)`).

## 만드는 과정 (kit.py, v3b · v3c)

v3 함수는 새 이름으로만 들어 있다. 예전 함수(`sculpt`, `paint`, `STONE_LAYERS`, `finish` 기본 인자)는 그대로라 v3 로 바꾸지 않은 묶음도 그대로 빌드된다.
v3b 는 시범 4종(grave_slab_a, rock_b, wall_ruin_a, dead_tree_a)을 검토 지적에 맞춰 다시 만들며 고친 판이다. 새 기능은 모두 선택 인자·새 함수다.
v3c 는 그 마무리다: 묘비에 세월(큰 깨짐·빗물 때·이끼·흙물), 바위의 위장무늬·모서리 보풀 제거, 나무 골의 흰 보풀·검은 점 제거.

```python
from kit import *        # 주의: sc 는 init 뒤에 생기므로 kit.sc 또는 link(o) 를 쓴다
rng = random.Random(7)
# 1. 조립: 깨끗한 형태 (bmesh 상자·윤곽 기둥, 바위는 facet_mass). 모서리를 평면으로 쳐낸다
body = join([box(...), ...])
chip(body, rng, 14, (0.03, 0.08), bite=0.38)
low_src = copy(body)                          # (석물) 저폴리 바탕 = 큰 깨짐까지만, 새김·얇은 떨어짐은 노멀맵으로
cut(body, [...])                              # 판 면·십자가 (boolean)
esrc = copy(body)                             # 닳은 모서리를 찾을 형태 (글자·금 새기기 전)
engrave_v(body, strokes, (0, -1, 0), 0.011, 0.007)   # 글자·선·긴 금은 V 자 홈 (vgroove)
# 2. 조각: 블록 번호 → 리메시 + 원래 표면에 되붙임(평평한 면·날카로운 모서리) → 조각 층
carve(body, 0.0025, *STONE3(1.0), seed=11, edge_from=esrc)
# 3. 칠: 손칠 재질 (위 밝고 아래·틈 보라, 닳은 모서리, 블록마다 색조·밝기, 이끼, 흙물, 지의류)
set_mat(body, paint3("이름", 'stone', h=1.1, k=1.0, edge_mode='attr', moss=0.45, moss_low=0.7, moss_low_h=0.4))
# 4. 저폴리 (석물: 깨끗한 형태에서. 붙은 조각은 union 으로 합쳐 속에 묻힌 면을 없앤다)
low = lowpoly(low_src, z=-0.015)
# 5. 굽기 우리(cage, 단단한 모서리에서 쪼갬) + UV 다시 배치 + 빈 곳 메우기 + LOD 규칙 + FBX
finish3("이름", [body], [low], extras=[...], cage=0.006, hard=55)     # size='auto' → 1024/2048
```

### 종류별 권장값 (v3b·v3c 시범에서 확인한 값)

| 종류 | 형태·저폴리 | carve | 칠 (paint3) | finish3 |
| --- | --- | --- | --- | --- |
| 작은 석물 ~1m (묘비·십자가) | `lowpoly(새김 전 형태)`, **큰 깨짐 한 군데**(들쭉날쭉한 윤곽 기둥을 앞뒤로 기울여 cut, 저폴리 전에) | 0.0025, `edge_from=새김 전 사본` | `edge_mode='attr'`, edge 0.8 / edge_w 0.009 / edge_gain 0.85, cavity 1.0, stains 0.7, **moss 0.95 / moss_patch 1.7, rain 0.9 / rain_h 0.75, splash 0.85 (splash_z = 받침 윗면)**, streaks 0.35 + `blotch`(물때) | cage 0.006, hard 55, `uv_weight`(앞면 1.0, 뒷면 0.65, 받침 0.7) |
| 블록 많은 석조 (벽·아치·계단) | `ashlar(..., damage=(0.14, rng))` → `carve(base=True)` → `low_of` | 0.009, `STONE3(1.25, 1.2, 0.6)` | piece_var 1.0, **piece_val 0.15**, **grime 0.85** (grime_h 0.16), edge_w 0.022 / edge_gain 1.35, ao 0.45, lichen 0.4 | cage 0.01 / reach 0.1, **uv_margin 0.001**, lod2 0.12 |
| 바위 2~4m | `facet_mass` + `chip_convex` + `step_spalls` → `lowpoly(그 형태)` | 0.005, **`mode='octree'`**, `ROCK3(k, 0.7, chisel=0.25)`, pieces=False | cells 0.7, facet_var 0.3, **edge 0, lichen 0, strata 0.8**, moss 1.0 / **moss_patch 1.5** | cage 0.012 / reach 0.1, **hard 38, flat_hard 6**, uv_angle 40, uv_margin 0.002 |
| 죽은 나무 | `tree_build(..., low_mode='tube', rho=tree_rho)` | 0.006, `BARK3(1.0, depth=0.8)` | BARK_GREY, **edge 0, lichen 0, cavity 0.55 / cavity_s 0.2**, dirt_h 0.85, moss_low_h 0.95 (blotch 는 작고 어둡게) | `fin=dict(cage=0.006, cage_reach=0.06, samples=8, margin=0, uv_margin=0.002)` |

- **석물 (묘비)**: 다듬은 앞면에는 칸 무늬 층(plates, chisel 칸)을 쓰지 않는다 — 거북등·유약 금처럼 읽힌다. 앞면은 긴 금 2~3줄(`crack_strokes` →
  `engrave_v` 0.0075/0.005) + 칠의 `tooling`(끌 자국 결). 뒷면은 조각 층에 `'face': (0, 1, 0)`(그 방향 면에만, `face_lo`/`face_hi` 로 경계)을 붙여
  거친 다듬 자국(chisel 5.5·16) + 잔 구멍. 글자·금 입술이 밝게 빛나면 흰 외곽선 장난감이 되므로 `carve(edge_from=새기기 전 사본)`.
- **블록 석조 (벽)**: 형태는 그대로 두고 칠로 세월을 넣는다. `piece_val` 블록마다 밝기 ±15%, 색조 띠(차가운 청색 ↔ 따뜻한 회색), `grime` 줄눈 바로 아래
  흙물·그을음(블록 꼭대기에서 흘러내린 세로 줄), 넓게 밝은 닳은 모서리, 오목한 곳 AO, 이끼·지의류 포인트. `ashlar(damage=(비율, rng))` 로 깨지고 이 빠진 블록.
- **바위**: 구(타원체)에서 출발하지 않는다 — `facet_mass`(20면체를 늘여 깊은 평면 16개로 깎고 모서리 모따기). 떨어진 자국은 **평면 바닥 + 40~45° 벽**
  (`spall_flat`, `step_spalls`)으로 파고 **저폴리에도 넣는다** (큰 면을 저폴리가 그대로 따라가 굽기 광선이 스치지 않는다). 조각은
  `carve(mode='octree')`(옥트리 리메시 = 모서리 위에 정점, 곧은 모서리) + `ROCK3`(아주 얕은 큰 굴곡 + 굵은 금 몇 줄 + 큰 평면 끌 면 `chisel=0.25`).
  칠은 `facet_var`(깨진 면마다 다른 톤)와 `edge_mode='attr'`(깨끗한 형태의 볼록 모서리까지 거리 = 곧고 고른 닳은 모서리).
- **나무**: `low_mode='tube'` — 저폴리를 가지마다 관 하나로 다시 찍고 원통으로 편다(이음매 하나, 섬 = 가지 하나, 이음매는 줄기 뒤·뿌리 아래·가지 위).
  `tree_rho` 로 텍셀 배율(줄기 밑동 1.0 → 위·뿌리 끝·가지·잔가지 0.22), 원본은 가지마다 따로 깎고 서로 닿지 않는 가지끼리 무리를 지어 따로 굽는다
  (`bake_groups`: 가지 이음매의 극단 법선·검은 점 방지). `BARK3` = 세로로 긴 껍질판(폭 15 cm, 길이 그 5~6배) + 깊은 골(2~5 m 에서 읽히는 굵기).
  잔결은 Unity 디테일 맵(wood). 회색 큰 얼룩(blotch 0.9) 은 솜뭉치처럼 보여 쓰지 않는다.
- `paint3` 의 v3b 인자: `piece_val`(블록 밝기 ±), `grime`/`grime_h`(줄눈 아래 그을음), `edge_gain`, `contrast`/`gain`/`pivot`(명암 대비·전체 밝기),
  `facet_var`/`facet_scale`(면마다 톤), `edge_mode`('bevel' | 'attr'), `lichen`/`lichen_color`/`lichen_scale`(지의류: 작고 가장자리가 또렷한 반점),
  `moss_patch`(이끼 덩어리 크기). 기본 `contrast=0.15, gain=1.1` 은 albedo 를 sRGB(Standard)로 저장하게 된 뒤 이전 판 밝기에 맞춘 값이다.
- `paint3` 의 v3c 인자: `strata`/`strata_scale`/`strata_tilt`(자연석 돌 결 줄무늬, 큰 잡음으로 짙어졌다 옅어졌다), `rain`/`rain_h`/`rain_color`
  (꼭대기에서 흘러내린 빗물 때: 줄마다 길이가 다른 3~5 cm 세로 줄, 옆면만, 곱하기), `splash`/`splash_z`/`splash_h`(받침·땅과 만나는 곳 위로 튄 흙물 띠),
  `cavity_s`(좁은 AO 그늘 세기 — 깊은 골 입술의 AO 표본 잡음이 검은 점이 되면 낮춘다).
- `finish3(..., flat_hard=화소)` (v3c): 단단한 모서리(= UV 이음매) 둘레 그 폭의 띠를 두 그림 모두 그 섬 안쪽 값으로 다시 메운다(`regrow_hard_band`,
  로그 `FLATHARD`). 옥트리 리메시 원본의 모서리는 복셀 톱니라 광선이 스치며 띠 안에 빗살이 생긴다 — 저폴리 모서리가 단단하니 띠를 지워도 모서리는
  또렷하다. 칠한 모서리 빛(edge)도 함께 지워지므로 모서리 빛이 필요한 석물(묘비)에는 쓰지 않는다. 각진 바위·절벽 6 (2048 기준).
- **밝기 맞추기**: 소품마다 `compare.py` 게임 시점 로그 `LUM` 의 평균을 이전 판 ±10% 안으로 (`gain` 으로). 대비(p90)는 이전보다 크게.
- `finish3(..., size='auto', cage=push, cage_reach=…, hard=각도, uv_margin=…, uv_weight=…, samples=8, split_cage=True)`:
  - 굽기 우리: 저폴리 정점·면 가운데에서 법선으로 광선을 쏴 원본이 바깥에 있으면 그만큼 + push 부풀린 사본.
  - **split_cage** (기본 켬, hard 가 있을 때): 단단한 모서리에서 저폴리 사본을 쪼갠 뒤 우리를 만들어 굽는다. 쪼개지 않으면 모서리 정점의 우리가 양쪽 면 법선의
    평균으로 부풀어, 좁은 면(모따기·떨어진 자국 벽)에서 광선이 옆 면으로 비껴 맞아 빗살 무늬(흰 점선 + 검은 점)가 생긴다.
  - 저폴리·우리는 광선에 안 보이게 하고, `paint3` 의 AO 는 자기 객체만 본다. 여백 없이 굽고(자홍으로 채워 둔 그림) 빈 곳은 섬마다 자기 가장자리 색으로 넓힌 뒤 메운다.
  - 노멀맵에서 70도 넘게 누운 법선은 세운다 (`clamp_normals`, 로그 `steep %`).
  - `uv='keep'`(저폴리에 이미 있는 UV, 나무 원통 전개), `uv_weight`(섬마다 텍셀 배율), `bake_groups`(무리별 굽기), `probe`(로그 줄 더).
  - albedo 는 sRGB 그대로 저장한다 (예전 `_save_jpg` 는 AgX 보기 변환이 입혀져 밝은 색이 바래 있었다).
- **로그 읽기** (빌드 로그에서 확인할 것):
  - `TEXEL 이름 px/m … uv_fill … tex … low1.5m …` — uv_fill 0.45 이상. 나무는 `TEXEL_TRUNK … base px/m` 500 이상.
  - `BAKE … miss % steep % rim % rim_soft % inner %` — miss 는 0, **steep 2% 미만**. rim = UV 섬 경계 4 화소 띠 안에서 노멀 z<0.6 인 비율
    ('miss 0%' 가 못 잡는, 비스듬히 스친 광선의 흰·검은 테두리), rim_soft = 그 가운데 단단한 모서리 둘레를 뺀 것, inner = 섬 안쪽의 같은 비율.
  - `WARN BAKE …` — steep 2% 초과, 또는 rim_soft 5% 초과이면서 inner 의 1.5배 초과(테두리가 안쪽보다 나쁘다). 고칠 때까지 결과물로 쓰지 않는다.
  - `UVPACK`, `CAGE … max`, `SPLITCAGE … sharp`, `LODRULE`, `FILES … albedo_kb … normal_kb`, `PIECES`.
- **비교 렌더** (`compare.py`): `blender -b -P compare.py -- <이전 폴더> <새 폴더> <이름> <출력 접두사> [near=x,y,z,거리,방위,앙각] [views=near,mid,game,back] [ref=이름]`
  → `_near.png`(1~2 m), `_mid.png`(전체), `_back.png`(뒤), `_game.png`(**게임 시점**: 눈높이 1.7 m 카메라, 3 m·6 m, 월드 룩 도구의 달빛·주변광·노출,
  `ref=` 로 이전 폴더의 다른 소품을 옆에 세워 붕 뜨는지 본다). 여러 장 모으기: `compare.py -- --sheet <출력> <그림…>`.
- 빠른 반복: 환경 변수 `KIT_FAST=1` 이면 텍스처 512·표본 4로 굽는다 (칠·밝기만 볼 때, 결과물로 쓰지 않는다).

### 피할 것 (v3·v3b 를 만들며 겪은 것)

- **값이 뚝 끊기는 조각 층**(plates, soft 를 줄인 terrace): 복셀 격자에 톱니. 다듬은 면의 plates 는 거북등처럼 읽힌다 → 이어지는 층(chisel, cracks)이나 V 홈 금.
- **fissure**: 잡음 등고선이라 작은 고리(녹은 밀랍 무늬) → cracks.
- **벽이 수직인 새김 상자**(stroke_box): 글자 테두리가 1화소 검은 점선 → `vgroove` / `engrave_v`.
- **바위에 잔 주파수 chisel**(scale 7 이상)·pits: 칸 경계마다 접힌 능선 → 구겨진 종이·은박지, 물집 같은 고리. 바위는 `ROCK3`(chisel 은 큰 칸만).
- **구(타원체) 바탕 바위**: 깎아도 둥근 덩어리에 판을 붙인 모양 → `facet_mass`.
- **구 커터 spall + 저폴리는 spall 전 형태**: 벽이 수직인 깊은 자국을 광선이 비스듬히 스쳐 흰 보풀·검은 톱니 → 평면 spall(벽 40~45°)을 저폴리에도 넣는다.
- **바위에 복셀 리메시 + 되붙이기**: 비스듬한 모서리가 계단처럼 놓여 닳은 모서리 빛이 찢어진 종이 테두리 → `carve(mode='octree')`.
- **모든 모서리를 같은 굵기로 밝게**: 외곽선을 그린 장난감 → edge 0.45~0.8, edge_w 1 cm 안팎, 글자·금은 `edge_from` 으로 뺀다.
- **큰 지의류·회색 큰 얼룩**: 흰 물감 자국·솜뭉치 → lichen_scale 20 안팎, 어두운 색.
- **넓은 면에 고르게 찍힌 지의류 반점**(바위 lichen 0.55): 위장무늬 → 바위·나무는 lichen 0. 이끼는 윗면·틈에 큰 덩어리(moss_patch 1.5),
  넓은 옆면은 `strata`(줄무늬)·stains(얼룩)로 돌색만 바꾼다.
- **각진 바위 모서리 빛 + 옥트리 원본 모서리**: 모서리마다 얇은 밝은 보풀 줄 → edge 0 + `flat_hard`.
- **나무껍질에 베벨 모서리 빛**(edge_mode 'bevel', 표본 8): 골을 따라 들쭉날쭉한 흰 보풀 줄. 좁은 AO 를 세게 쓰면 골 입술에 검은 점 → edge 0, cavity_s 0.2.
- **깨끗하게 다듬기만 한 묘비**: 버려진 묘지에서 새것처럼 보인다 → 큰 깨짐 한 군데(실루엣, 저폴리에도) + 깨짐에서 뻗은 가는 금 + 윗변·받침 이끼 +
  빗물 때(rain) + 받침과 만나는 곳 흙물(splash) + 물때 blotch. 빗물 줄이 1 cm 로 잘면 가까이서 나뭇결처럼 읽힌다 (3~5 cm).
- **둥근 윗변의 어깨를 커터 하나로 깨기**: 어깨가 이미 낮아 거의 물지 못한다 → 윗변에서 10~15 cm 안쪽까지 들어가는 윤곽으로.
- **나무 저폴리를 리메시 + smart_project**: 섬이 수천 개, 텍셀 반토막, 껍질 결이 섬마다 끊긴다 → `low_mode='tube'`.
- **나무 원본을 하나로 합쳐 한 번에 굽기**: 가지 이음매에 극단 법선 → 검은 점 → `bake_groups`.
- **큰 조각(수 cm)까지 들어간 리메시에서 저폴리 줄이기**: 면이 구겨져 UV 섬이 수천 개 → 조각 전 바탕(`carve(base=True)`)에서.
- **섬이 수백 개인데 uv_margin 0.003 이상**: 여백이 텍스처를 절반 넘게 먹는다 (벽 0.27 → 0.001 로 0.47~0.52).
- **우리를 쪼개지 않고 단단한 모서리 굽기**: 좁은 면에 빗살 → `split_cage`(finish3 기본).

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
