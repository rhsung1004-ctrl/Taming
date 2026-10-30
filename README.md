# Taming (가제)

원신풍 애니메이션 그래픽의 오픈월드 몬스터 테이밍 RPG. 직접 길들인 드래곤을 타고 하늘을 나는 것이 핵심 경험입니다.

- 엔진: Unity 6 LTS + URP
- 플랫폼: 안드로이드 우선 (최저 사양 갤럭시 S20), 가로 모드
- 현재 단계: **1단계 · 룩 확정** — 애니풍 주인공이 예쁜 들판을 뛰어다니는 30초 화면 만들기

## 문서

| 문서 | 내용 |
| --- | --- |
| [docs/SETUP.md](docs/SETUP.md) | 처음 한 번: Unity 프로젝트를 만들고 이 저장소와 연결하기 |
| [docs/PHASE1_LOOK.md](docs/PHASE1_LOOK.md) | 1단계 작업 순서: VRoid 주인공 → 룩 세팅 → 움직이기 |
| [docs/ROADMAP.md](docs/ROADMAP.md) | 전체 로드맵 요약 |
| [CLAUDE.md](CLAUDE.md) | 코드 규칙 (Claude와 함께 작업할 때 기준) |

## 폴더 구조

```
Assets/_Taming/          ← 게임 본편 (모든 작업은 여기 안에서)
  Scripts/Core/          속성, 몬스터 데이터 등 기반
  Scripts/Player/        주인공 입력·이동·애니메이션 연결
  Scripts/CameraSystem/  3인칭 카메라
  Scripts/Editor/        Tools → Taming 메뉴 (원클릭 세팅 도구)
  Art/ Data/ Prefabs/ Scenes/ Settings/   ← Tools → Taming → 0. 폴더 구조 만들기
Archive/Prototype_v0.2/  재미 검증용 프로토타입 (Unity가 읽지 않음, 참고용)
docs/                    문서
```

## 작업 방식

- 코드·도구·문서: Claude가 작성해 이 저장소에 커밋
- Unity 에디터 작업, 에셋 배치, 플레이 테스트: 직접
- 큰 파일(FBX, VRM, 이미지, 사운드)은 Git LFS로 자동 관리
