import json
import os
import re
import sys
import subprocess
import shutil
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import datetime

def get_svn_path():
    """PyInstaller 환경에서도 svn.exe 경로를 찾을 수 있도록 처리"""
    if getattr(sys, 'frozen', False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))

    svn_exe_path = os.path.join(base_path, 'bin', 'svn.exe')
    return svn_exe_path

def get_config_path():
    """설정 파일 경로 반환 (실행 파일 또는 스크립트 옆)"""
    if getattr(sys, 'frozen', False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, 'svn_extractor_config.json')

class SVNExtractorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("SVN 커밋 파일 자동 추출 프로그램")
        self.root.geometry("700x480")
        self.root.minsize(600, 450)

        self._cancel_event = threading.Event()

        self.create_widgets()
        self.load_config()

    def create_widgets(self):
        main_frame = ttk.Frame(self.root, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(main_frame, text="프로젝트 경로 (Working Copy):").grid(row=0, column=0, sticky=tk.W, pady=(0, 5))
        self.var_project_path = tk.StringVar()
        ttk.Entry(main_frame, textvariable=self.var_project_path).grid(row=1, column=0, sticky=tk.EW, padx=(0, 5))
        ttk.Button(main_frame, text="찾아보기", command=self.browse_project_path).grid(row=1, column=1)

        ttk.Label(main_frame, text="리비전 번호 (-c) 또는 범위 (예: 100:200):").grid(row=2, column=0, sticky=tk.W, pady=(10, 5))
        self.var_revision = tk.StringVar()
        entry_revision = ttk.Entry(main_frame, textvariable=self.var_revision)
        entry_revision.grid(row=3, column=0, sticky=tk.EW, padx=(0, 5))
        entry_revision.bind('<Return>', lambda e: self.run_extraction_thread())

        ttk.Label(main_frame, text="대상 폴더 경로 (저장 위치):").grid(row=4, column=0, sticky=tk.W, pady=(10, 5))
        self.var_target_path = tk.StringVar()
        ttk.Entry(main_frame, textvariable=self.var_target_path).grid(row=5, column=0, sticky=tk.EW, padx=(0, 5))
        ttk.Button(main_frame, text="찾아보기", command=self.browse_target_path).grid(row=5, column=1)

        # 옵션: .class 단일 경로 추출
        self.var_extract_class = tk.BooleanVar(value=True)
        ttk.Checkbutton(main_frame, text=".java/.xml 리비전 시 실제 WEB-INF/classes 경로 트리에 Class/XML 동시 복사", variable=self.var_extract_class).grid(row=6, column=0, columnspan=2, sticky=tk.W, pady=(10, 0))

        self.btn_run = ttk.Button(main_frame, text="실행", command=self.run_extraction_thread)
        self.btn_run.grid(row=7, column=0, columnspan=2, pady=(15, 10))

        ttk.Label(main_frame, text="로그 출력:").grid(row=8, column=0, sticky=tk.W)
        self.text_log = tk.Text(main_frame, height=10, width=65, state=tk.DISABLED, wrap=tk.WORD)
        self.text_log.grid(row=9, column=0, columnspan=2, sticky=tk.NSEW, pady=(5, 0))

        scrollbar = ttk.Scrollbar(main_frame, command=self.text_log.yview)
        scrollbar.grid(row=9, column=2, sticky=tk.NS, pady=(5, 0))
        self.text_log['yscrollcommand'] = scrollbar.set

        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(9, weight=1)

    def load_config(self):
        """저장된 설정을 불러와 UI에 적용"""
        try:
            config_path = get_config_path()
            if not os.path.exists(config_path):
                return
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            self.var_project_path.set(config.get('project_path', ''))
            self.var_target_path.set(config.get('target_path', ''))
            self.var_extract_class.set(config.get('extract_class', True))
        except Exception:
            pass  # 설정 로드 실패는 무시하고 기본값 사용

    def save_config(self):
        """현재 UI 상태를 설정 파일에 저장"""
        try:
            config = {
                'project_path': self.var_project_path.get().strip(),
                'target_path': self.var_target_path.get().strip(),
                'extract_class': self.var_extract_class.get(),
            }
            with open(get_config_path(), 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception:
            pass  # 설정 저장 실패는 무시

    def browse_project_path(self):
        path = filedialog.askdirectory(title="프로젝트 경로 (SVN Working Copy) 선택")
        if path:
            self.var_project_path.set(path)

    def browse_target_path(self):
        path = filedialog.askdirectory(title="대상 폴더 위치 (저장 위치) 선택")
        if path:
            self.var_target_path.set(path)

    def log(self, message):
        """스레드 안전하게 로그를 UI 스레드에서 업데이트"""
        def _update():
            self.text_log.config(state=tk.NORMAL)
            self.text_log.insert(tk.END, message + "\n")
            self.text_log.see(tk.END)
            self.text_log.config(state=tk.DISABLED)
        self.root.after(0, _update)

    def validate_revision(self, revision):
        """리비전 형식 검증. 유효하면 (is_range, revision_str) 반환, 무효면 None 반환"""
        # 범위 형식: 100:200
        if ':' in revision:
            parts = revision.split(':')
            if len(parts) == 2 and all(p.strip().isdigit() and int(p.strip()) > 0 for p in parts):
                return (True, f"{parts[0].strip()}:{parts[1].strip()}")
            return None
        # 단일 리비전: 양의 정수
        if revision.isdigit() and int(revision) > 0:
            return (False, revision)
        return None

    def _request_cancel(self):
        """취소 요청 — 현재 파일 처리 완료 후 루프 중단"""
        self._cancel_event.set()
        self.btn_run.config(state=tk.DISABLED)
        self.log("[알림] 취소 요청됨. 현재 파일 처리 후 중단됩니다...")

    def _set_running(self, running: bool):
        """실행 상태에 따라 버튼 텍스트/커맨드 전환"""
        if running:
            self.btn_run.config(text="취소", command=self._request_cancel, state=tk.NORMAL)
        else:
            self.btn_run.config(text="실행", command=self.run_extraction_thread, state=tk.NORMAL)

    def show_done_dialog(self, target_path, count):
        """완료 다이얼로그 — 닫기 / 폴더 열기 버튼 제공"""
        dlg = tk.Toplevel(self.root)
        dlg.title("완료")
        dlg.resizable(False, False)
        dlg.grab_set()

        ttk.Label(dlg, text=f"파일 추출이 완료되었습니다.\n(총 {count}개 생성)\n\n추출 폴더:\n{target_path}",
                  padding="20 15", justify=tk.CENTER).pack()

        btn_frame = ttk.Frame(dlg, padding="0 0 15 15")
        btn_frame.pack()

        def open_folder():
            subprocess.Popen(['explorer', os.path.normpath(target_path)])

        ttk.Button(btn_frame, text="폴더 열기", command=open_folder).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="닫기", command=dlg.destroy).pack(side=tk.LEFT, padx=5)

        dlg.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - dlg.winfo_width()) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - dlg.winfo_height()) // 2
        dlg.geometry(f"+{x}+{y}")

    def run_extraction_thread(self):
        project_path = self.var_project_path.get().strip()
        revision = self.var_revision.get().strip()
        base_target_path = self.var_target_path.get().strip()

        if not project_path or not revision or not base_target_path:
            messagebox.showwarning("입력 오류", "프로젝트 경로, 리비전 번호, 대상 폴더 경로를 모두 입력해 주세요.")
            return

        revision_info = self.validate_revision(revision)
        if revision_info is None:
            messagebox.showwarning(
                "입력 오류",
                "리비전 번호는 양의 정수(예: 123) 또는 범위(예: 100:200) 형식이어야 합니다."
            )
            return

        self.save_config()

        self._cancel_event.clear()
        self._set_running(True)

        self.text_log.config(state=tk.NORMAL)
        self.text_log.delete(1.0, tk.END)
        self.text_log.config(state=tk.DISABLED)

        thread = threading.Thread(
            target=self.extract_files,
            args=(project_path, revision_info, base_target_path)
        )
        thread.daemon = True
        thread.start()

    def find_web_inf_classes_all(self, project_path):
        """프로젝트 내 모든 WEB-INF/classes 경로를 리스트로 반환"""
        found = []
        for root_dir, dirs, files in os.walk(project_path):
            dirs[:] = [d for d in dirs if d not in ('.svn', '.git')]
            if 'WEB-INF' in dirs:
                classes_path = os.path.join(root_dir, 'WEB-INF', 'classes')
                if os.path.exists(classes_path):
                    found.append(classes_path)
        return found

    def select_best_web_inf_classes(self, java_file_path, all_web_inf_classes):
        """Java 파일 경로와 가장 가까운(공통 경로가 긴) WEB-INF/classes를 선택"""
        best = None
        best_len = -1
        for wic in all_web_inf_classes:
            try:
                common = os.path.commonpath([java_file_path, wic])
                common_len = len(common)
                if common_len > best_len:
                    best_len = common_len
                    best = wic
            except ValueError:
                continue
        return best

    def extract_class_files(self, java_file_path, project_path, target_path, web_inf_classes):
        """Java 파일에서 패키지명을 찾아 실제 WEB-INF/classes 경로와 동일한 트리에 class 파일 복사"""
        package_path = ""
        try:
            with open(java_file_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('package '):
                        pkg = line.replace('package', '').replace(';', '').strip()
                        package_path = pkg.replace('.', os.sep)
                        break
        except Exception as e:
            self.log(f"[경고] {java_file_path} 내부 패키지명 확인 실패: {e}")

        if not package_path:
            self.log(f"[경고] package 선언을 찾을 수 없어 클래스 추출을 건너뜁니다: {os.path.basename(java_file_path)}")
            return 0

        class_name = os.path.splitext(os.path.basename(java_file_path))[0]
        expected_class_dir = os.path.join(web_inf_classes, package_path)

        if not os.path.exists(expected_class_dir):
            self.log(f"[경고] 컴파일된 경로가 존재하지 않습니다: {expected_class_dir}")
            return 0

        rel_web_inf_classes = os.path.relpath(web_inf_classes, project_path)
        dest_class_dir = os.path.join(target_path, rel_web_inf_classes, package_path)
        os.makedirs(dest_class_dir, exist_ok=True)

        copied_count = 0
        for file_in_dir in os.listdir(expected_class_dir):
            if file_in_dir == f"{class_name}.class" or (file_in_dir.startswith(f"{class_name}$") and file_in_dir.endswith(".class")):
                src_class = os.path.join(expected_class_dir, file_in_dir)
                dest_class = os.path.join(dest_class_dir, file_in_dir)
                try:
                    shutil.copy2(src_class, dest_class)
                    rel_dest = os.path.relpath(dest_class, target_path)
                    self.log(f"[클래스 추출(WEB-INF)] {rel_dest}")
                    copied_count += 1
                except OSError as e:
                    self.log(f"[경고] 클래스 파일 복사 실패: {file_in_dir} -> {e}")

        return copied_count

    def extract_xml_to_classes(self, xml_file_path, project_path, target_path, web_inf_classes):
        """XML 파일의 원본 경로에서 소스 루트 영역을 분리하여 WEB-INF/classes 트리에 패키지 구조로 복사"""
        rel_xml_path = os.path.relpath(xml_file_path, project_path).replace('\\', '/')

        source_roots = [
            'src/main/java/',
            'src/main/resources/',
            'src/java/',
            'src/resources/',
            'src/'
        ]

        package_like_path = None
        for root in source_roots:
            if rel_xml_path.startswith(root):
                package_like_path = rel_xml_path[len(root):]
                break
            elif f"/{root}" in rel_xml_path:
                idx = rel_xml_path.find(f"/{root}")
                package_like_path = rel_xml_path[idx + len(f"/{root}"):]
                break

        if not package_like_path:
            return 0

        rel_web_inf_classes = os.path.relpath(web_inf_classes, project_path)
        dest_xml_path = os.path.join(target_path, rel_web_inf_classes, package_like_path)

        os.makedirs(os.path.dirname(dest_xml_path), exist_ok=True)
        try:
            shutil.copy2(xml_file_path, dest_xml_path)
            rel_dest = os.path.relpath(dest_xml_path, target_path)
            self.log(f"[XML 추출(WEB-INF)] {rel_dest}")
            return 1
        except OSError as e:
            self.log(f"[경고] XML 파일 복사 실패: {os.path.basename(xml_file_path)} -> {e}")
            return 0

    def extract_files(self, project_path, revision_info, base_target_path):
        is_range, revision_str = revision_info
        target_path = None
        extracted_count = 0
        cancelled = False
        try:
            # 경로 사전 검증
            if not os.path.isdir(project_path):
                self.log(f"[에러] 프로젝트 경로가 존재하지 않습니다: {project_path}")
                return
            if not os.path.isdir(base_target_path):
                self.log(f"[에러] 대상 폴더가 존재하지 않습니다: {base_target_path}")
                return

            self.log(f"작업을 시작합니다... (리비전: {revision_str})")

            timestamp_foldername = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
            target_path = os.path.join(base_target_path, timestamp_foldername)
            os.makedirs(target_path, exist_ok=True)
            self.log(f"[알림] 최종 추출 폴더 생성됨:\n -> {target_path}")

            svn_exe = get_svn_path()
            if not os.path.exists(svn_exe):
                self.log(f"[경고] 번들된 svn.exe 존재하지 않음. 시스템 svn을 시도합니다.")
                svn_exe = 'svn'

            # 범위 리비전(100:200)은 -r 옵션, 단일 리비전은 -c 옵션 사용
            # 범위 입력 시 시작 리비전도 포함되도록 start-1:end 로 변환
            if is_range:
                start, end = revision_str.split(':')
                adjusted_range = f"{int(start) - 1}:{end}"
                cmd = [svn_exe, 'diff', '--summarize', '-r', adjusted_range]
            else:
                cmd = [svn_exe, 'diff', '--summarize', '-c', revision_str]

            creationflags = 0
            if sys.platform == 'win32':
                creationflags = getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000)

            process = subprocess.Popen(
                cmd,
                cwd=project_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=creationflags,
                encoding='utf-8',
                errors='replace'
            )

            stdout, stderr = process.communicate()

            if process.returncode != 0:
                self.log(f"[에러] SVN 명령 실행 실패:\n{stderr}")
                return

            if not stdout.strip():
                self.log("[알림] 해당 리비전에 변경된 파일이 존재하지 않습니다.")
                return

            # SVN diff --summarize 출력 형식: "M       path/to/file"
            raw_lines = stdout.strip().split('\n')
            parsed_files = []
            for line in raw_lines:
                if not line.strip():
                    continue
                match = re.match(r'^([A-Z?!~C])\s{6}(.+)$', line)
                if not match:
                    self.log(f"[경고] 파싱 실패한 줄 (건너뜀): {line}")
                    continue
                parsed_files.append((match.group(1), match.group(2).strip()))

            total = len(parsed_files)

            extract_class = self.var_extract_class.get()
            all_web_inf_classes = []
            if extract_class:
                self.log("\n프로젝트 내 'WEB-INF/classes' 폴더 탐색 진행중...")
                all_web_inf_classes = self.find_web_inf_classes_all(project_path)
                if all_web_inf_classes:
                    for wic in all_web_inf_classes:
                        rel_wic = os.path.relpath(wic, project_path)
                        self.log(f"[탐색 완료] 발견된 경로: {rel_wic}")
                    if len(all_web_inf_classes) > 1:
                        self.log(f"[알림] WEB-INF/classes가 {len(all_web_inf_classes)}개 발견됨. Java 파일별로 가장 가까운 경로를 자동 선택합니다.")
                else:
                    self.log("[경고] WEB-INF/classes 폴더를 찾지 못하여 추가 패키징이 스킵됩니다.")
                self.log("-" * 40)

            for idx, (status, file_path) in enumerate(parsed_files, start=1):
                # 취소 요청 확인
                if self._cancel_event.is_set():
                    self.log("[알림] 사용자 요청으로 작업이 중단되었습니다.")
                    cancelled = True
                    break

                if status == 'D':
                    self.log(f"[{idx}/{total}] [스킵(삭제됨)] {file_path}")
                    continue

                abs_file_path = os.path.normpath(os.path.join(project_path, file_path))

                if os.path.isdir(abs_file_path):
                    continue

                if not os.path.exists(abs_file_path):
                    self.log(f"[{idx}/{total}] [경고] 워킹 디렉터리 내 파일 없음: {abs_file_path}")
                    continue

                rel_path = os.path.relpath(abs_file_path, project_path)
                dest_path = os.path.join(target_path, rel_path)

                os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                try:
                    shutil.copy2(abs_file_path, dest_path)
                    self.log(f"[{idx}/{total}] [원본 복사] {rel_path}")
                    extracted_count += 1
                except OSError as e:
                    self.log(f"[{idx}/{total}] [경고] 파일 복사 실패: {rel_path} -> {e}")
                    continue

                if extract_class and all_web_inf_classes:
                    if abs_file_path.endswith('.java'):
                        web_inf_classes = self.select_best_web_inf_classes(abs_file_path, all_web_inf_classes)
                        if web_inf_classes:
                            cls_count = self.extract_class_files(abs_file_path, project_path, target_path, web_inf_classes)
                            extracted_count += cls_count

                    elif abs_file_path.endswith('.xml'):
                        web_inf_classes = self.select_best_web_inf_classes(abs_file_path, all_web_inf_classes)
                        if web_inf_classes:
                            xml_count = self.extract_xml_to_classes(abs_file_path, project_path, target_path, web_inf_classes)
                            extracted_count += xml_count

            if not cancelled:
                self.log(f"\n작업 완료! 대상 폴더에 총 {extracted_count}개의 파일이 추출되었습니다.")
                tp = target_path
                cnt = extracted_count
                self.root.after(0, lambda: self.show_done_dialog(tp, cnt))

        except Exception as e:
            self.log(f"[예외 발생] {str(e)}")
            self.root.after(0, lambda: messagebox.showerror("오류", f"프로그램 실행 중 치명적 오류:\n{str(e)}"))
        finally:
            self.root.after(0, lambda: self._set_running(False))

if __name__ == "__main__":
    root = tk.Tk()
    app = SVNExtractorApp(root)
    root.mainloop()
