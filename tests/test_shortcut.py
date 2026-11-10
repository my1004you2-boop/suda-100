from pathlib import Path

from talk.shortcut import ps_script, pythonw


def test_ps_script_points_at_main_pyw_and_escapes_quotes():
    s = ps_script(r"C:\Py\pythonw.exe", Path(r"C:\it's\main.pyw"), Path(r"C:\it's"), name="수다백단")
    assert "$s.TargetPath='C:\Py\pythonw.exe'" in s
    assert "$s.Arguments='\"C:\it''s\main.pyw\"'" in s        # 경로는 큰따옴표로 감싸고 ' 는 '' 로
    assert "$s.WorkingDirectory='C:\it''s'" in s
    assert "'수다백단.lnk'" in s and "GetFolderPath('Desktop')" in s


def test_pythonw_falls_back_when_missing(tmp_path):
    exe = tmp_path / "python.exe"
    assert pythonw(str(exe)) == str(exe)
    (tmp_path / "pythonw.exe").write_text("")
    assert pythonw(str(exe)) == str(tmp_path / "pythonw.exe")
