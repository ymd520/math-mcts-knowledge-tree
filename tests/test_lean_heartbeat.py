"""Liveness metrics must not corrupt the Lean source-evidence stream."""
from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.run_full_lean_worker import _run_with_heartbeat


class LiveHeartbeatTests(unittest.TestCase):
    def test_captured_lean_stdout_is_separate_from_progress(self):
        with tempfile.TemporaryDirectory() as directory:
            messages=io.StringIO()
            with contextlib.redirect_stdout(messages):
                result=_run_with_heartbeat([sys.executable,"-c",
                    "import time,sys;print('{\"source_id\":\"MTH01\"}',flush=True);"
                    "print('diagnostic',file=sys.stderr);time.sleep(.08)"],
                    cwd=Path(directory),worker=3,phase="extract:trial",
                    timeout=2,interval=.01)
            events=[json.loads(x) for x in messages.getvalue().splitlines()]
            self.assertEqual(result.returncode,0)
            self.assertEqual(json.loads(result.stdout)["source_id"],"MTH01")
            self.assertIn("diagnostic",result.stderr)
            self.assertEqual(events[0]["event"],"subprocess_start")
            self.assertTrue(any(e["event"]=="heartbeat" for e in events))
            self.assertEqual(events[-1]["event"],"subprocess_end")
            self.assertTrue(all(e["worker"]==3 for e in events))

    def test_subprocess_deadline_remains_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            with contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(subprocess.TimeoutExpired):
                    _run_with_heartbeat([sys.executable,"-c",
                                         "import time;time.sleep(5)"],
                                        cwd=Path(directory),worker=0,
                                        phase="prepare:trial",timeout=1,
                                        interval=.05)


if __name__=="__main__":
    unittest.main()
