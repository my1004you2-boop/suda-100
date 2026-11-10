"""바탕화면에 '수다백단' 바로가기를 만든다.

실행: make_shortcut.bat 더블클릭 (또는 회화앱 폴더에서 python -m talk.shortcut)
콘솔 창 없이 열리도록 pythonw.exe로 main.pyw를 실행하는 바로가기를 만든다.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAME = "수다백단"


def pythonw(exe: str = sys.executable) -> str:
    w = Path(exe).with_name("pythonw.exe")
    return str(w if w.exists() else exe)


def _q(s) -> str:
    """PowerShell 작은따옴표 문자열."""
    return "'" + str(s).replace("'", "''") + "'"


def ps_script(target: str, script: Path, workdir: Path, name: str = NAME) -> str:
    lnk = f"(Join-Path ([Environment]::GetFolderPath('Desktop')) {_q(name + '.lnk')})"
    return (f"$p={lnk};$s=(New-Object -ComObject WScript.Shell).CreateShortcut($p);"
            f"$s.TargetPath={_q(target)};$s.Arguments={_q(chr(34) + str(script) + chr(34))};"
            f"$s.WorkingDirectory={_q(workdir)};$s.Description={_q(name)};$s.Save();Write-Output $p")


def main() -> None:
    cmd = ps_script(pythonw(), ROOT / "main.pyw", ROOT)
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", cmd],
                       capture_output=True, text=True, errors="replace")  # PowerShell 5.1은 시스템 코드페이지로 출력
    if r.returncode != 0:
        print("바로가기를 만들지 못했어요:", r.stderr.strip())
        sys.exit(1)
    print("바탕화면에 바로가기를 만들었어요:", r.stdout.strip())


if __name__ == "__main__":
    main()
