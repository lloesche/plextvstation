import os
import argparse
from typing import Optional
from .utils import get_os_and_arch
from .types import Platform, Architecture


helm_version = "3.13.1"


helm_uris = {
    (
        Platform.LINUX,
        Architecture.X86_64,
    ): f"https://get.helm.sh/helm-v{helm_version}-linux-amd64.tar.gz",
    (
        Platform.MACOS,
        Architecture.X86_64,
    ): f"https://get.helm.sh/helm-v{helm_version}-darwin-amd64.tar.gz",
    (
        Platform.MACOS,
        Architecture.ARM64,
    ): f"https://get.helm.sh/helm-v{helm_version}-darwin-arm64.tar.gz",
}


def helm_uri() -> Optional[str]:
    return helm_uris.get(get_os_and_arch())


def get_config(args: argparse.Namespace) -> dict[str, str]:
    validate_args(args)
    env_dir = os.path.expanduser(args.directory)
    conf_dir = os.path.join(env_dir, "conf")
    bin_dir = os.path.join(env_dir, "bin")
    tmp_dir = os.path.join(env_dir, "tmp")
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"

    config = {
        "env": env,
        "env_dir": env_dir,
        "conf_dir": conf_dir,
        "bin_dir": bin_dir,
        "tmp_dir": tmp_dir,
    }
    return config


def validate_args(args: argparse.Namespace) -> None:
    pass
