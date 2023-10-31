import os
from plextvstation.utils import make_dirs


def test_make_dirs(mocker):
    mocker.patch("os.makedirs")
    config = {
        "env_dir": "/path/to/env",
        "bin_dir": "/path/to/bin",
        "tmp_dir": "/path/to/tmp",
        "conf_dir": "/path/to/conf",
    }
    make_dirs(config)
    os.makedirs.assert_has_calls(
        [
            mocker.call("/path/to/env", exist_ok=True),
            mocker.call("/path/to/bin", exist_ok=True),
            mocker.call("/path/to/tmp", exist_ok=True),
            mocker.call("/path/to/conf", exist_ok=True),
        ]
    )
