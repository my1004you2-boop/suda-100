import subprocess
import sys
import uuid

from talk.ui.app import already_running


def test_second_instance_detected():
    name = f"Local\\HoehwaTest{uuid.uuid4().hex}"
    holder = subprocess.Popen([sys.executable, "-c", (
        f"import time; from talk.ui.app import already_running; already_running({name!r}); "
        "print('ready', flush=True); time.sleep(5)")], stdout=subprocess.PIPE, text=True)
    try:
        assert holder.stdout.readline().strip() == "ready"
        assert already_running(name) is True
    finally:
        holder.kill()


def test_first_instance_not_detected():
    name = f"Local\\HoehwaTest{uuid.uuid4().hex}"
    out = subprocess.run([sys.executable, "-c",
                          f"from talk.ui.app import already_running; print(already_running({name!r}))"],
                         capture_output=True, text=True, timeout=30)
    assert out.stdout.strip() == "False"
