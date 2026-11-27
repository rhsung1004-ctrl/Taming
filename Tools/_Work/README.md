# 작업 보관 (2단계)

Unity·게임에는 쓰이지 않는 작업용 보관 폴더입니다. Claude 작업 세션의 임시 폴더가 지워져도 다음 작업을 이어 갈 수 있게 둡니다.

- `stage2_tools.tar.gz`: 2단계(소품 품질·월드 채움) 작업 기록과 검사 도구 사본
  - `stage2/` 방향 메모(direction.md)·작업자 보고·검토 보고
  - `qa_checks/`, `wf_world/`, `world_v3_qa/`, `w4s2/`, `w5/`, `w6a/`, `s2c/`: 월드 검사(탈출·도달·길·다리·성능·배치·묻힘)와 생성·렌더 스크립트
  - `review_*`: 소품·월드 검토용 렌더 스크립트
  - `realstub/`: Unity API 흉내 컴파일 검사 (`check.sh`). 참조 어셈블리는 NuGet 의 `UnityEngine.Modules` 2021.3.33 과 `Unity3D.SDK` 2021.1.14.1 을 받아 `nuget/mods`, `nuget/sdk` 에 풀어 쓴다
- 스크립트 안의 경로는 그때의 임시 폴더(`/tmp/claude-0/…/scratchpad`) 기준입니다. 풀어서 쓸 때 경로를 바꿉니다.
