# 1장 오픈월드 데이터 규격 (월드 생성기 ↔ Unity 도구)

월드 생성기(`Tools/WorldGen`, Python)가 만들고 Unity 도구(`Tools → Necro → 월드 → 1. 1장 오픈월드 만들기`)가 읽는다.
두 쪽은 이 문서만 보고 서로 맞춘다. 바꿀 때는 이 문서를 먼저 고친다.

## 좌표

- Unity 월드: **X = 동쪽, Z = 북쪽, Y = 위**. 지형은 (0, 0, 0) ~ (2048, *, 2048). 단위 m
- Blender(미리보기·소품 제작): X = 동쪽, **Y = 북쪽, Z = 위**. Unity (x, y, z) = Blender (x, z, y)
- 소품 모델: Blender에서 앞면이 -Y. Unity로 가져오면 앞면이 Unity +Z (FBX 내보내기 축 변환 결과)
- 회전 변환: Blender 회전 행렬 M_b (소품의 Blender 로컬 → Blender 월드)에 대해
  `R_unity = C_w · M_b · C_o⁻¹`,  C_w: (x,y,z)→(x,z,y),  C_o: (x,y,z)→(−x,z,−y)
  - Z축 회전만 있을 때: Unity Y 회전(도) = **180 − rz(도)** (rz: Blender에서 위에서 봐 반시계)
  - 생성기는 이 공식으로 쿼터니언 (x, y, z, w) 을 계산해 넣는다 (`worldgen.unity_quat(M_b)`)

## 파일 위치

```
Assets/_Necro/Art/World/Ch1/
  Data~/                      Unity가 가져오지 않는 원본 데이터 (도구가 파일로 직접 읽는다)
    world.json                전체 설명 (아래)
    height.r16                높이: uint16 리틀엔디언, 2049 × 2049, 행 = Z(남→북), 열 = X(서→동). 0~65535 → 0~world.height m
    splat_0.png, splat_1.png  지형 층 무게 RGBA (층 0~3, 4~7). 2048 × 2048. PNG 맨 윗줄 = 북쪽 끝
    detail_0.png, detail_1.png 풀 밀도 RGBA (풀 종류 0~3, 4~7). 2048 × 2048 (1m 칸). 0~255 → 칸당 0~maxPerCell 개
                              화소 정렬: splat/detail 화소 (열 i, 아래에서 j 번째 줄) = 높이 격자점 (x = i, z = j) 의 값.
                              Unity 도구는 알파맵을 그 위치에서 읽고, 풀 칸 c([c, c+1) m)는 화소 c, c+1 (가로·세로 넷)의 평균을 쓴다
    trees.json                지형 나무 인스턴스
    objects.json              게임 오브젝트로 놓는 소품, 점광원, 물, 효과
  Terrain/                    지형 층 텍스처 (Unity가 가져온다)
    ground_<이름>_albedo.jpg, ground_<이름>_normal.png
  map.png                     게임 안 지도 그림 (1024 × 1024, 위 = 북쪽)
```

## world.json

```json
{
  "version": 1,
  "size": 2048,                       // 한 변 길이 (m)
  "height": 320,                      // height.r16 의 65535 가 몇 m 인지
  "heightRes": 2049,
  "tiles": 2,                         // 2 × 2 지형 타일 (타일 하나 1024m, 높이 해상도 1025, 이웃과 가장자리 공유)
  "splatRes": 2048, "detailRes": 2048,
  "seaLevel": 0,
  "spawn": {"p": [x, y, z], "yaw": 0},          // 주인공 시작 위치 (Unity 좌표, yaw = Unity Y 회전 도)
  "layers": [                         // 지형 층 (최대 8). 순서 = splat 채널 순서
    {"name": "grass", "albedo": "ground_grass_albedo.jpg", "normal": "ground_grass_normal.png", "tile": 6.0, "smoothness": 0.05}
  ],
  "details": [                        // 풀 종류 (최대 8). 순서 = detail 채널 순서
    {"asset": "grass_a", "maxPerCell": 3, "minScale": 0.8, "maxScale": 1.3}
  ],
  "pois": [                           // 이름 있는 장소 (발견 알림, 지도 표시)
    {"id": "altar", "name": "봉인의 제단", "p": [x, y, z], "r": 30, "map": true}
  ],
  "fog": {"color": [r, g, b], "density": 0.006},     // 월드 규모 안개 (선택)
  "bounds": {"min": [x, z], "max": [x, z]},          // 걸어 다닐 수 있는 범위 (바깥은 산)
  "map": {"min": [x, z], "max": [x, z]},             // 게임 안 지도(map.png)가 덮는 월드 범위 (선택. 정사각형, 걸어 다니는 범위 + 여유 약 60 m).
                                                     // 없으면 지형 전체 (0, 0) ~ (size, size). Unity 도구는 이 값을 PoiDiscovery 의 worldMin·worldSize 로 넘긴다
  "levels": {"swamp": 30.9, "lake": 28.1, "creekPool": 44.7}   // 수면 높이 (참고·확인 렌더용, Unity 도구는 읽지 않음. objects.json 의 water y 와 같다)
}
```

## trees.json (지형 나무 인스턴스: Y축 회전만, 대량)

```json
{
  "prototypes": ["dead_tree_a", "rock_a", "..."],     // manifest 에서 kind = "tree" 인 소품
  "instances": [[proto, x, z, yawDeg, scale], ...]    // Unity 좌표. y 는 지형 높이를 쓴다. yawDeg = Unity Y 회전
}
```

## objects.json (게임 오브젝트로 놓는 것)

```json
{
  "objects": [{"a": "crypt", "p": [x, y, z], "q": [qx, qy, qz, qw], "s": 1.0, "far": 140, "cull": 0.012}],   // Unity 좌표·쿼터니언. y 는 묻는 깊이(sink)까지 반영한 최종 높이. far·cull 은 선택 (아래)
  "lights":  [{"p": [x, y, z], "c": [r, g, b], "i": 6.0, "r": 10.0, "flicker": true, "far": 140}],   // far 는 선택 (아래)
  "water":   [{"p": [x, y, z], "size": [sx, sz], "yaw": 0}],                       // 물 평면 (y = 수면 높이)
  "fx":      [{"type": "mist" | "wisps" | "soulfire" | "fireflies", "p": [x, y, z], "r": 20}]
}
```

- 소품에 META.light 가 있으면 Unity 도구가 프리팹 안에 광원을 넣으므로 lights 에 다시 넣지 않는다
- lights 는 소품과 상관없는 광원 (예: 늪 위의 도깨비불, 장면을 떠도는 영혼 빛)
- `far` (선택, m): 멀리서 보여야 하는 '등대 빛' 의 끄는 거리. Unity 도구가 그 광원 오브젝트에 `LightCullDistance` (far) 를 붙이고,
  `LightCuller` 는 range × rangeFactor 대신 이 거리에서 끈다 (minRadius ~ maxRadius 안으로 자름). `Light.range` 는 그대로라 비추는 넓이·그리기 비용은 같다.
  없거나 0 이면 LightCuller 기본 규칙 (range × 12). 장면·장소마다 하나 이상 (지금 140 m)
- 아직 manifest 에 없는 장면용 새 소품(worldgen `NEW_PROPS`)을 대체 소품으로 놓았을 때, 예상 META 에 광원이 있는데 대체 소품에 없으면 그 광원도 lights 에 들어간다 (진짜 소품이 생기면 다음 생성부터 빠진다)
- objects 의 `far` (선택, m): 그 소품(발광 부품이 있는 소품: 등불 등)의 프리팹 광원을 등대 빛으로 쓴다. Unity 도구가 그 소품 안 모든 광원에
  `LightCullDistance` (far) 를 붙인다 (META.light 의 far 보다 앞선다). Unity 점광원은 광원 자체가 화면에 보이지 않으므로,
  생성기는 등대 빛(far)을 lights 에 맨 점광원으로 두지 않고 발광 소품의 광원으로만 둔다 (worldgen `beacon_emitters`:
  1.6 m 안에 키 0.9 m 넘는 발광 소품이 있으면 그 소품에 far 를 넘기고, 없으면 그 자리에 장면 틀에 맞는 발광 소품(등불·화로·영혼 수정)을 둔다).
  그래서 lights 에는 far 가 없는 작은 빛(들판의 약한 떠도는 빛, 늪 도깨비불 등)만 남는다.
  objects 의 `far` 는 META.light 의 far 보다 짧게도 쓴다: 수정 무리 곁의 작은 영혼 수정은 far 45 (가까이서만 켠다. 등대 빛은 큰 수정 하나)
- objects 의 `cull` (선택, 0~0.5, w4): 그 소품이 사라지는 화면 높이 (LODGroup 마지막 전환 높이) 덮어쓰기. 프리팹 값(META.cull)보다 클 때만
  Unity 도구가 그 놓인 소품의 LODGroup 을 고친다 (`NecroWorldBuilder.RaiseCull`: 마지막 LOD 를 cull 로, 앞 LOD 는 바로 뒤 LOD 보다 0.002 크게).
  사라지는 거리 ≈ 크기 × 배율 / (1.04 × cull). 생성기는 들판에 많이 놓는 돌담·깃발·선돌·쓰러진 나무·큰 바위·낮은 기둥에 쓴다
  (worldgen `WORLD_CULL`: 돌담 0.012 ≈ 330 m, 깃발 0.008 ≈ 510 m, 선돌 0.007 ≈ 435 m, 산기슭 절벽 바위 0.015 ≈ 1 km. 들판 무리(w5)의 작은 소품·움막 터 돌담 토막은
  `SINGLE_CULL` 0.016, 120~250 m). META.cull 로는 700~3,000 m 까지 그려져
  몇 화소로만 보이면서 그리는 물체 수 예산(2,000)을 넘겼다

## 소품 목록 (manifest)

`Assets/_Necro/Art/Environment/Graveyard/manifest.json` — `Tools/BlenderKit/build.py` 가 묶음별로 만든 `manifest_<묶음>.json` 을 합친 것.
`python3 Tools/BlenderKit/publish.py <빌드 출력 폴더>` 가 manifest_<묶음>.json 을 합쳐 manifest.json 으로 쓰고, 모델·텍스처·foliage_atlas.png 를 이 폴더로 복사한다.
`{ "이름": {"name", "group", "size": [x, y, z] (Blender 축), "tris_lod0", "meta": {kind, tags, collider, footprint, sink, tilt, align, scale, cull, shadows, light}} }`
META 항목은 `Tools/BlenderKit/README.md` 참고. 단 `kind` 는 다섯 가지다 (BlenderKit README 에는 scatter 가 빠져 있다):
`light` 에는 선택 키 `far` (m) 가 있다: `{"offset", "color", "intensity", "range", "far": 140}`. 있으면 프리팹의 광원(Glow Light)에
`LightCullDistance` 가 붙어 LightCuller 가 그 거리에서 끈다 (objects.json lights 의 far 와 같은 뜻. 화로·영혼 수정·모닥불·길가 사당·작은 납골당).

| kind | 월드 데이터 | Unity |
| --- | --- | --- |
| `prop` | objects.json | 일반 프리팹 |
| `scatter` | objects.json (작은 흩뿌림: 해골·초·꽃·버섯. 풀에 가리지 않게 둘레 풀을 조금 넓게 걷는다) | 일반 프리팹 (prop 과 같다) |
| `landmark` | objects.json (큰 구조물) | 일반 프리팹 (가림 컬링의 가리는 쪽) |
| `tree` | trees.json | 지형 나무 프로토타입 (충돌은 캡슐, `collider: none` 이면 없음) |
| `detail` | world.json `details` + detail_*.png | 지형 풀 (전용 재질 `Foliage_Detail`) |

## Unity 도구가 지키는 것

- 지형 2 × 2 타일, 타일마다 TerrainData 에셋, 이웃 연결, `drawInstanced`
- splat/detail PNG 는 `ImageConversion.LoadImage` 로 읽는다. `Texture2D.GetPixels32()` 는 아래 줄부터 → 행 0 = 남쪽 = Z 0 (PNG 맨 윗줄 = 북쪽 규칙과 맞다)
- 풀: 인스턴스 수 모드(InstanceCountMode, Unity 2022.2+), 인스턴싱 메쉬 (`Necro/Foliage` 셰이더, 거리 축소가 켜진 지형 풀 전용 재질 `Foliage_Detail`)
- 소품: 프리팹으로 만들어 `PrefabUtility.InstantiatePrefab`, 256m 칸마다 부모 오브젝트로 묶는다
- 광원 끄는 거리 덮어쓰기: objects.json lights 의 `far`, objects 의 `far` (그 소품 안 모든 광원), META.light 의 `far` → 광원 오브젝트에 `LightCullDistance.far`
- 사라지는 거리 덮어쓰기: objects 의 `cull` → 그 놓인 소품의 LODGroup (`RaiseCull`, 프리팹 값보다 클 때만)
- 지도: world.json `map` 이 있으면 PoiDiscovery.worldMin = map.min, worldSize = map.max − map.min (map.png 도 그 범위로 그린다)

## 확인용 파일 (생성기 출력 폴더, Unity 는 읽지 않는다)

- `_scenes.json`: 작은 장면 목록. 틀(type), 자리(p), 반지름(r), 방향(yaw), 소품 수(props), 자리 특징(feature: junction·bend·crest·bridge·forest_entry·
  hilltop·ridge·creek·forest_edge·hollow …), 길까지 거리(road_d), 무리 번호(hamlet, 없으면 −1), 가장 키 큰 세로 요소 꼭대기(top [x, y, z], 높이 tall),
  등대 빛(beacon [x, y, z, far])
- `_zones.json`: 구역 표시. `hamlets` (장면 2~3 개 + 장소가 서로 보이는 조밀한 무리: 가운데, 반지름, 장면 번호, 보이는 장소),
  `quiet` (조용한 구역: 장면에서 70 m 넘게 떨어진 걸을 수 있는 땅 덩어리. 16 m 칸 목록 cells, 가운데, 넓이 ha, 가장 가까운 장면·장소).
  다음 단계(채움: 밭 경계 돌담·나무 무리·노두·둔덕)가 이 구역을 쓴다
- `_roads.json`: 길 중심선 (점 목록, 반폭, 이름). 시선 검사가 읽는다
- `_boxground.json`: 바닥 상자 접지로 놓은 소품 번호 (objects 순서)와 의도된 묻힘 여부. 묻힘·뜸 검사가 읽는다
- `_fill.json` (v3 채움): `counts` (줄 소품 수), `lines` (밭 경계·길가 줄의 구간. `t` = 모양 wall/fence/hedge/stones/scarp/ditch,
  `src` = field(밭 턱·둑)/cross(가로 줄)/road(길가)/spur(길에서 뻗는 줄)/foot(산기슭 경계 줄, w4)/relief(도랑), `kind` = 줄 성격, `pts` = 놓인 소품 자리 [x, z] (scarp·ditch 는 줄 점)),
  `items` (grove 나무 무리, outcrop 바위 노두, boulders/thicket/deadwood 작은 덩이, barrow 작은 무덤 둔덕, stone 외딴 선돌, stone_row 선돌 줄,
  milestone 이정표, shrine 길가 사당, cart 부서진 수레, banner 들판 깃발 (w4), crystal 들판 영혼 수정 무리 (w4): `p` [x, z] 와 크기 정보). 눈높이 지표·렌더 확인이 읽는다. 데이터 규격(Unity 가 읽는 파일)은 바뀌지 않았다:
  밭 턱·도랑·둔덕은 height.r16 에, 줄·무리는 objects.json·trees.json 에 들어간다
