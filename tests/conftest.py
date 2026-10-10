"""Keep tests hermetic: never pick up a locally trained sentinel or cached SLM weights."""

import os
import re
import tempfile
from pathlib import Path

_DEFAULT = Path(__file__).resolve().parents[1] / "policies" / "default.toml"
_policy = Path(tempfile.mkdtemp(prefix="viveka-test-")) / "policy.toml"
_policy.write_text(
    re.sub(
        r'(?m)^path = "models/weights/sentinel\.joblib"',
        f'path = "{(_policy.parent / "no-sentinel.joblib").as_posix()}"',
        _DEFAULT.read_text(encoding="utf-8"),
    ),
    encoding="utf-8",
)
os.environ["VIVEKA_POLICY"] = str(_policy)
os.environ["VIVEKA_SLM"] = "off"
