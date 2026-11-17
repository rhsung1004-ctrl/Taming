# 사령술사 3D (가제)

쓰러뜨린 적의 시체를 일으켜 군단을 만들고, 고룡의 시체로 만든 본드래곤을 타고 싸우는 PC용 3D 액션 RPG.
스토리를 따라 진행하고, 엔딩 후에는 완성한 군단과 함께 오픈월드를 돌아다닙니다. 스팀 출시가 목표입니다.

모바일 2D 게임 **사령술사 키우기**와 같은 세계관의 별개 제품입니다 (지역·유닛·스토리 설정을 공유).

- 엔진: Unity 6 LTS + URP
- 플랫폼: PC (스팀), 키보드·마우스 + 게임패드
- 현재 단계: **룩 확정** — 애니풍 다크 판타지. 묘지 한 장면을 목표 품질로 ([docs/LOOK.md](docs/LOOK.md))
- 프로토타입(시체 지배, 군단 전투, 본드래곤 탑승)의 재미 검증은 플레이 테스트를 병행합니다

> 저장소 이름은 예전 프로젝트 이름인 `Taming` 그대로입니다. GitHub 설정에서 바꿔도 기존 주소는 자동으로 연결됩니다.

## 바로 해 보기

1. [docs/SETUP.md](docs/SETUP.md) 대로 Unity 프로젝트를 만들고 이 저장소와 연결
2. 기본 씬(SampleScene)에서 **Play** → 씬에 아무것도 놓지 않아도 프로토타입이 자동으로 만들어집니다
3. 조작과 진행 순서는 [docs/PROTOTYPE.md](docs/PROTOTYPE.md)

## 문서

| 문서 | 내용 |
| --- | --- |
| [docs/SETUP.md](docs/SETUP.md) | 처음 한 번: Unity 프로젝트 만들고 저장소 연결하기 |
| [docs/PROTOTYPE.md](docs/PROTOTYPE.md) | 프로토타입 조작, 진행 순서, 확인할 것 |
| [docs/LOOK.md](docs/LOOK.md) | 룩 확정: 묘지 테스트 장면, 주인공(VRoid) 가져오기, 툰 셰이더 |
| [docs/ROADMAP.md](docs/ROADMAP.md) | 단계별 로드맵 |
| [CLAUDE.md](CLAUDE.md) | 코드 규칙 (Claude와 함께 작업할 때 기준) |

## 폴더 구조

```
Assets/_Necro/
  Prototype/             프로토타입 (도형으로 만든 캐릭터, 코드로 만든 필드). 재미 검증용
  Scripts/Core/          본편용 유닛 데이터 형식 (ScriptableObject)
  Scripts/Player/        본편용 주인공 입력·이동·애니메이션 연결
  Scripts/CameraSystem/  본편용 3인칭 카메라
  Scripts/Look/          본편용 분위기 컴포넌트 (등불 일렁임)
  Scripts/Editor/        Tools → Necro 메뉴 (원클릭 세팅 도구)
  Shaders/               툰 셰이더, 밤하늘, 영혼 입자
Archive/Taming/          이전 프로젝트(몬스터 테이밍) 자료. 참고용, Unity가 읽지 않음
docs/                    문서
```

## 작업 방식

- 코드·도구·문서: Claude가 작성해 이 저장소에 커밋
- Unity 에디터 작업, 에셋 배치, 플레이 테스트: 직접
- 큰 파일(FBX, VRM, 이미지, 사운드)은 Git LFS로 자동 관리
