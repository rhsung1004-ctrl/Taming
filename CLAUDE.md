# CLAUDE.md — 이 저장소에서 작업할 때의 규칙

## 프로젝트

- 원신풍 애니 그래픽의 오픈월드 몬스터 테이밍 RPG (Unity 6 LTS, URP, 안드로이드 가로 모드, 최저 사양 갤럭시 S20)
- 사용자는 한국어로 소통한다. 문서·주석·커밋 메시지·에디터 메뉴·로그는 한국어.
- 사용자는 코드를 직접 거의 쓰지 않는다. 에디터 작업은 원클릭 도구(Tools → Taming 메뉴)로 최대한 줄여 준다.
- 현재 단계는 README.md에 적는다. 단계를 건너뛰는 기능을 먼저 만들지 않는다 (docs/ROADMAP.md).

## 코드 규칙

- 모든 런타임 코드는 `Assets/_Taming/Scripts/` 아래, 네임스페이스 `Taming`. 에디터 코드는 `Scripts/Editor/`, 네임스페이스 `Taming.EditorTools`.
- 게임 데이터(몬스터, 스킬, 아이템, 먹이)는 ScriptableObject. 몬스터 추가에 코드 수정이 필요하면 설계가 잘못된 것.
- 입력은 Input System. 구 `Input` 클래스 사용 금지.
- 튜닝 값은 `[Header]`로 묶어 Inspector에 노출하고 한국어 Tooltip을 단다.
- Update에서 `Find`, `GetComponent`, LINQ, 할당(new List 등) 금지. 캐시해서 쓴다.
- 모바일 성능 우선: 물리 쿼리는 NonAlloc, 그림자·후처리 비용 의식.
- 원신의 디자인·이름·UI를 복제하지 않는다.

## 검증

- Unity를 실행할 수 없는 환경이면, Unity API 스텁으로 컴파일 검사를 하고 그 사실을 사용자에게 밝힌다.
- 실제 동작 확인은 사용자의 플레이 테스트로 한다. 테스트할 항목을 구체적으로 알려 준다.

## Git

- 큰 바이너리는 .gitattributes의 LFS 규칙을 따른다.
- `Archive/` 는 참고용 프로토타입. Unity가 읽지 않으며 수정하지 않는다.
