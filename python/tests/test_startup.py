import json
import signal
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

import pytest

from main import bind_local


def test_exhausted_range():
    with bind_local(0, 0) as occupied:
        port = occupied.getsockname()[1]
        with pytest.raises(RuntimeError, match="No available"):
            bind_local(port, port)


def test_real_process_fallback_and_shutdown():
    with bind_local(0, 0) as occupied:
        first = occupied.getsockname()[1]
        proc = subprocess.Popen(
            [
                sys.executable,
                str(Path(__file__).parents[1] / "main.py"),
                "--first-port",
                str(first),
                "--last-port",
                str(first + 10),
            ],
            stdout=subprocess.PIPE,
            text=True,
        )
        try:
            assert proc.stdout
            endpoint = proc.stdout.readline().split()[-1]
            port = int(endpoint.rsplit(":", 1)[1])
            assert first < port <= first + 10
            assert f":{port}/ws" in proc.stdout.readline()
            assert "Ready" in proc.stdout.readline()
            for _ in range(40):
                try:
                    with urlopen(endpoint + "/api/info", timeout=1) as response:
                        assert json.load(response)["port"] == port
                    break
                except URLError:
                    time.sleep(0.025)
            else:
                pytest.fail("server never became ready")
        finally:
            proc.send_signal(signal.SIGINT)
            proc.wait(timeout=5)
