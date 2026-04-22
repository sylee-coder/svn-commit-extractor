# SVN Commit Extractor

SVN 특정 리비전에서 변경된 파일을 Working Copy로부터 타임스탬프 폴더로 자동 추출하는 Windows GUI 도구.

`.java` 파일 수정 시 컴파일된 `.class` 파일(내부 클래스 `$` 포함)도 함께 추출하고, `.xml` 파일은 `WEB-INF/classes` 트리 구조에 맞춰 자동 복사한다.

## 주요 기능

- SVN 리비전 단위 또는 범위(`100:200`) 지정 추출
- 삭제된 파일(`D` 상태) 자동 스킵
- `.java` 변경 시 대응하는 `.class` / `$InnerClass.class` 자동 탐색 및 복사
- `.xml` 변경 시 `WEB-INF/classes` 트리 구조로 패키지 경로 유지 복사
- 멀티 모듈 프로젝트에서 `WEB-INF/classes` 복수 탐색 및 Java 파일 위치 기준 자동 선택
- 실행 중 취소 기능
- 마지막 입력값(경로, 옵션) 자동 저장 및 복원

## 요구 사항

- **Windows** 전용
- Python 3.8 이상 (직접 실행 시)
- TortoiseSVN 또는 시스템 PATH에 `svn` 명령어

## 실행 방법

### Python으로 직접 실행

```bash
python svn_extractor.py
```

> 스크립트와 같은 위치에 `bin/svn.exe`가 있으면 우선 사용, 없으면 시스템 PATH의 `svn`으로 폴백.

### 단일 EXE로 패키징 (PyInstaller)

```bash
pyinstaller --noconfirm --onefile --windowed --add-data "bin;bin" svn_extractor.py
```

빌드된 EXE는 `dist/svn_extractor.exe`에 생성된다.

## 사용 방법

1. **프로젝트 경로** — SVN Working Copy 루트 경로 선택
2. **리비전 번호** — 단일(`123`) 또는 범위(`100:200`) 입력
3. **대상 폴더** — 추출 결과를 저장할 폴더 선택
4. **실행** 버튼 클릭

추출이 완료되면 `대상 폴더/YYYYMMDDHHmmSS/` 형태의 타임스탬프 폴더에 파일이 저장된다.

## 의존성

표준 라이브러리만 사용 — `tkinter`, `subprocess`, `shutil`, `threading`, `datetime`. 별도 `pip install` 불필요.
