# 1단계 · 룩 확정

목표: **애니풍 여성 주인공이 들판을 뛰어다니는 30초 화면.** 이 화면이 원하는 느낌이면 1단계 통과입니다.

## A. 주인공 만들기 (VRoid Studio)

1. VRoid Studio(무료) 설치 → 새 캐릭터 → 여성
2. 얼굴·헤어·의상 편집. **기본 프리셋을 그대로 쓰지 말고** 헤어와 의상 색·텍스처를 직접 바꿔 오리지널로 만듭니다.
   - 직접 만든 텍스처와 헤어는 내 것, 기본 메시·프리셋은 pixiv 소유. 판매용 게임 사용은 가능합니다 (VRoid Studio 가이드라인).
3. 내보내기 → **VRM 1.0** 형식, 폴리곤 수는 모바일 기준으로 줄이기 (머티리얼 수도 줄이기)

## B. Unity로 가져오기 (UniVRM)

1. UniVRM 최신 릴리스: https://github.com/vrm-c/UniVRM/releases → `.unitypackage` 다운로드 → Unity로 끌어다 놓아 Import
2. `.vrm` 파일을 `Assets/_Taming/Art/Characters/Player/` 에 넣으면 프리팹이 자동 생성됩니다.
3. 머티리얼이 **분홍색**으로 보이면 URP 셰이더 문제입니다:
   - VRM 1.0 모델은 URP용 셰이더 `VRM10/Universal Render Pipeline/MToon10` 이 있습니다.
   - Project Settings → Graphics → Always Included Shaders에 위 셰이더를 추가
   - UniVRM의 URP 지원은 버전마다 달라지니, 막히면 https://vrm.dev 의 URP 지원 현황을 확인하고 저에게 화면을 보여 주세요.

## C. 애니메이션 준비

1. 무료 CC0 휴머노이드 애니메이션: Quaternius **Universal Animation Library** (https://quaternius.com/packs/universalanimationlibrary.html)
2. FBX를 `Assets/_Taming/Art/Animations/Player/` 에 넣으면 **자동으로 Humanoid + 반복 설정**됩니다.
3. **Tools → Taming → 3. 플레이어 애니메이터 만들기** → 대기/걷기/달리기/점프/낙하 클립을 이름으로 찾아 자동 연결

## D. 씬과 플레이어

1. `Assets/_Taming/Scenes/` 에 새 씬 `FieldTest` 만들기
2. **Tools → Taming → 1. 룩 기본 세팅** → 블룸, 색 보정, 따뜻한 햇빛, 하늘색 원경 안개가 한 번에 적용
3. 지형: GameObject → 3D Object → Terrain (또는 큰 Plane으로 시작)
4. 주인공 프리팹을 씬에 끌어다 놓고 선택 → **Tools → Taming → 2. 선택한 모델로 플레이어 만들기**
   - 이동·점프·카메라·애니메이션 연결이 자동으로 붙습니다.
5. Play: WASD 이동, Shift 질주, Space 점프, **마우스 오른쪽 드래그로 카메라**, 휠 줌

## E. 들판 꾸미기 (원신 느낌의 핵심)

- 스타일라이즈드 나무·풀 에셋 (Asset Store 검색: "stylized nature", "anime grass")
- 풀은 많이, 키 크게, 바람에 흔들리게. 하늘은 밝은 하늘색, 멀리 산은 안개로 푸르게
- 조절할 값: `Assets/_Taming/Settings/LookProfile` (블룸·채도·대비)

## 통과 기준 (체크)

- [ ] 주인공이 애니메이션처럼 보인다 (얼굴 그림자가 지저분하지 않음)
- [ ] 달리기·점프 조작감이 부드럽다
- [ ] 화면을 캡처해서 SNS에 올려도 될 만큼 예쁘다
- [ ] 갤럭시 S20급에서 30fps 이상 (빌드해서 확인)

통과하면 30초 영상을 찍어 공유해 주세요. 그 화면을 기준으로 2단계(전투·테이밍)를 시작합니다.
