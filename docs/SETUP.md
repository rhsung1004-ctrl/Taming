# 처음 설정 (한 번만)

Unity가 만드는 기본 파일(ProjectSettings, Packages)은 직접 만든 URP 프로젝트에서 가져오고, 게임 코드는 이 저장소에서 받아 합칩니다.

## 1. 프로그램 설치

1. **Git for Windows** — https://git-scm.com (설치 시 기본값 그대로, Git LFS 포함)
2. **Unity Hub** → Installs → **Unity 6 LTS** 설치. 모듈에서 **Android Build Support** + 그 아래 **OpenJDK, Android SDK & NDK Tools** 체크

## 2. URP 프로젝트 만들기

1. Unity Hub → New project → 템플릿 **Universal 3D**
2. Project name: `Taming`, 위치: 예) `D:\Projects`
3. 프로젝트가 한 번 열리면 **Unity를 닫습니다**

## 3. 저장소 연결

`D:\Projects\Taming` 폴더에서 마우스 오른쪽 → **Open Git Bash here** → 아래를 한 줄씩 실행:

```bash
git lfs install
git init
git remote add origin https://github.com/rhsung1004-ctrl/Taming.git
git fetch origin
git checkout -b main --track origin/main
git add -A
git commit -m "Unity 6 URP 프로젝트 기본 파일 추가"
git push
```

처음 push할 때 GitHub 로그인 창이 뜨면 로그인하세요.

`git checkout` 단계에서 "would be overwritten" 오류가 나면, 오류에 나온 파일(보통 `.gitignore`)을 지우고 그 줄부터 다시 실행하세요.

## 4. 확인

1. Unity Hub에서 `Taming` 프로젝트를 엽니다.
2. 상단 메뉴에 **Tools → Taming** 이 보이면 성공.
3. **Tools → Taming → 0. 폴더 구조 만들기** 를 실행합니다.
4. Git Bash에서 `git add -A && git commit -m "폴더 구조" && git push`

## 이후 작업 흐름

- Claude가 코드를 올린 뒤: `git pull`
- 에디터에서 작업한 뒤: `git add -A && git commit -m "무엇을 했는지" && git push`
- GitHub Desktop(https://desktop.github.com)을 쓰면 위 명령을 버튼으로 할 수 있습니다.
