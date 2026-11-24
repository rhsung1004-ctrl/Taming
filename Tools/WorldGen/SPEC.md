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
  "objects": [{"a": "crypt", "p": [x, y, z], "q": [qx, qy, qz, qw], "s": 1.0}],   // Unity 좌표·쿼터니언. y 는 묻는 깊이(sink)까지 반영한 최종 높이
  "lights":  [{"p": [x, y, z], "c": [r, g, b], "i": 6.0, "r": 10.0, "flicker": true}],
  "water":   [{"p": [x, y, z], "size": [sx, sz], "yaw": 0}],                       // 물 평면 (y = 수면 높이)
  "fx":      [{"type": "mist" | "wisps" | "soulfire" | "fireflies", "p": [x, y, z], "r": 20}]
}
```

- 소품에 META.light 가 있으면 Unity 도구가 프리팹 안에 광원을 넣으므로 lights 에 다시 넣지 않는다
- lights 는 소품과 상관없는 광원 (예: 늪 위의 도깨비불, 장면을 떠도는 영혼 빛)
- 아직 manifest 에 없는 장면용 새 소품(worldgen `NEW_PROPS`)을 대체 소품으로 놓았을 때, 예상 META 에 광원이 있는데 대체 소품에 없으면 그 광원도 lights 에 들어간다 (진짜 소품이 생기면 다음 생성부터 빠진다)

## 소품 목록 (manifest)

`Assets/_Necro/Art/Environment/Graveyard/manifest.json` — `Tools/BlenderKit/build.py` 가 묶음별로 만든 `manifest_<묶음>.json` 을 합친 것.
`python3 Tools/BlenderKit/publish.py <빌드 출력 폴더>` 가 manifest_<묶음>.json 을 합쳐 manifest.json 으로 쓰고, 모델·텍스처·foliage_atlas.png 를 이 폴더로 복사한다.
`{ "이름": {"name", "group", "size": [x, y, z] (Blender 축), "tris_lod0", "meta": {kind, tags, collider, footprint, sink, tilt, align, scale, cull, shadows, light}} }`
META 항목은 `Tools/BlenderKit/README.md` 참고. 단 `kind` 는 다섯 가지다 (BlenderKit README 에는 scatter 가 빠져 있다):

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
