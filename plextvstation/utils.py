import os
import requests
import ipaddress
import platform
import secrets
import time
import sys
import psutil
import threading
import subprocess
import pandas as pd
from dataclasses import asdict, is_dataclass, fields
from typing import Optional, Callable, Union, Any
from types import FrameType
from signal import signal, Signals, SIGTERM, SIGINT
from datetime import datetime, timedelta, timezone


try:
    import resource
    import fcntl
except ImportError:
    pass

try:
    from psutil import cpu_count
except ImportError:
    from os import cpu_count

from email.utils import parsedate
from time import mktime
from pkg_resources import resource_filename
from .types import Platform, Architecture
from .logging import log
from . import __title__ as base_package_name


def get_os_and_arch() -> tuple[Platform, Architecture]:
    os = Platform.UNKNOWN
    arch = Architecture.UNKNOWN

    match platform.system():
        case "Linux":
            os = Platform.LINUX
        case "Windows":
            os = Platform.WINDOWS
        case "Darwin":
            os = Platform.MACOS
        case _:
            os = Platform.UNKNOWN

    match platform.machine():
        case "arm64":
            arch = Architecture.ARM64
        case "x86_64":
            arch = Architecture.X86_64
        case _:
            arch = Architecture.UNKNOWN

    return os, arch


def download_binary(
    binary_uri: str, binary_path: str, make_executable: bool = True, force_download: bool = False
) -> bool:
    """Download executable if changed."""
    log.debug(f"Checking for {binary_uri} updates")

    # Check the headers of the URL, follow redirects if necessary
    r = requests.head(binary_uri, allow_redirects=True)

    remote_file_size = int(r.headers.get("Content-Length", 0))
    remote_file_last_modified = r.headers.get("Last-Modified")

    local_file_size = None
    local_file_last_modified = None
    local_file_access_time = None

    if os.path.isfile(binary_path):
        local_file_size = os.path.getsize(binary_path)
        local_file_last_modified = os.path.getmtime(binary_path)
        local_file_access_time = os.path.getatime(binary_path)

    # Convert 'Last-Modified' time to Unix timestamp
    parsed_date = parsedate(remote_file_last_modified)
    assert parsed_date is not None
    remote_last_modified_timestamp = mktime(parsed_date)

    log.debug(f"Remote file size: {remote_file_size}, last modified: {remote_last_modified_timestamp}")
    log.debug(f"Local file size: {local_file_size}, last modified: {local_file_last_modified}")

    # Download the file if size or last modified time differs
    if (
        force_download
        or remote_file_size != local_file_size
        or remote_last_modified_timestamp != local_file_last_modified
    ):
        log.debug(f"New version of {binary_uri} found, downloading...")
        r = requests.get(binary_uri, stream=True, allow_redirects=True)
        r.raise_for_status()
        with open(binary_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        if make_executable:
            os.chmod(binary_path, 0o755)

        # Update the local file's last modified time to match the server's time
        if local_file_access_time is None:
            local_file_access_time = remote_last_modified_timestamp
        os.utime(binary_path, (local_file_access_time, remote_last_modified_timestamp))
        return True
    else:
        log.debug(f"No new version of {binary_uri} found.")
        return False


def get_template(template_name: str) -> str:
    template_file = resource_filename(base_package_name, f"templates/{template_name}")
    with open(template_file, "r") as f:
        return f.read()


def make_dirs(config: dict[str, str]) -> None:
    for dir in [config["env_dir"], config["bin_dir"], config["tmp_dir"], config["conf_dir"]]:
        log.debug(f"Creating directory {dir}")
        os.makedirs(dir, exist_ok=True)


def is_valid_ipv4(ip: str) -> bool:
    try:
        ipaddress.IPv4Address(ip)
        return True
    except Exception:
        pass
    return False


def is_valid_ipv6(ip: str) -> bool:
    try:
        ipaddress.IPv6Address(ip)
        return True
    except Exception:
        pass
    return False


def generate_password(length: int = 16) -> str:
    alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    password = "".join(secrets.choice(alphabet) for i in range(length))
    return password


parent_pid: Optional[int] = None
initial_dir: str = os.getcwd()


def restart() -> None:
    python_args = []
    if not getattr(sys, "frozen", False):
        python_args = subprocess._args_from_interpreter_flags()  # type: ignore
    args = python_args + sys.argv

    path_prefix = "." + os.pathsep
    python_path = os.environ.get("PYTHONPATH", "")
    if sys.path[0] == "" and not python_path.startswith(path_prefix):
        os.environ["PYTHONPATH"] = path_prefix + python_path

    try:
        close_fds()
    except Exception:
        log.exception("Failed to FD_CLOEXEC all file descriptors")

    kill_children(SIGTERM, ensure_death=True)

    os.chdir(initial_dir)
    os.execv(sys.executable, [sys.executable] + args)
    log.fatal("Failed to restart - exiting")
    os._exit(1)


def delayed_exit(delay: int = 3) -> None:
    time.sleep(delay)
    os._exit(0)


def close_fds(safety_margin: int = 1024) -> None:
    """Set FD_CLOEXEC on all file descriptors except stdin, stdout, stderr

    Since there is a race between determining the max number of fds to close
    and actually closing them we are adding a safety margin.
    """
    if sys.platform == "win32":
        return

    open_fds = [f.fd for f in psutil.Process().open_files()]
    if len(open_fds) == 0:
        return

    num_open = max(open_fds)

    try:
        sc_open_max = os.sysconf("SC_OPEN_MAX")
    except AttributeError:
        sc_open_max = 1024

    num_close = min(num_open + safety_margin, sc_open_max)

    for fd in range(3, num_close):
        fd_cloexec(fd)


def fd_cloexec(fd: int) -> None:
    try:
        flags = fcntl.fcntl(fd, fcntl.F_GETFD)
    except IOError:
        return
    fcntl.fcntl(fd, fcntl.F_SETFD, flags | fcntl.FD_CLOEXEC)


def initializer(handler: Callable[[int, Optional[FrameType]], None]) -> None:
    signal(SIGINT, handler)
    signal(SIGTERM, handler)
    increase_limits()


def set_thread_name(thread_name: str = "plextvstation") -> None:
    threading.current_thread().name = thread_name


def kill_children(
    signal: Signals = SIGTERM, ensure_death: bool = False, timeout: int = 3, process_pid: Optional[int] = None
) -> None:
    procs = psutil.Process(process_pid).children(recursive=True)
    num_children = len(procs)
    if num_children == 0:
        return
    elif num_children == 1:
        log_suffix = ""
    else:
        log_suffix = "ren"

    log.debug(f"Sending {signal.name} to {num_children} child{log_suffix}.")
    for p in procs:
        try:
            if signal == SIGTERM:
                p.terminate()
            else:
                p.send_signal(signal)
        except psutil.NoSuchProcess:
            pass

    if ensure_death:
        _, alive = psutil.wait_procs(procs, timeout=timeout)
        for p in alive:
            log.debug(f"Child with PID {p.pid} is still alive, sending SIGKILL")
            try:
                p.kill()
            except psutil.NoSuchProcess:
                pass


def increase_limits() -> None:
    if sys.platform != "linux":
        return
    for limit_name in ("RLIMIT_NOFILE", "RLIMIT_NPROC"):
        soft_limit, hard_limit = resource.getrlimit(getattr(resource, limit_name))
        log.debug(f"Current {limit_name} soft: {soft_limit} hard: {hard_limit}")
        try:
            if soft_limit < hard_limit:
                log.debug(f"Increasing {limit_name} {soft_limit} -> {hard_limit}")
                resource.setrlimit(getattr(resource, limit_name), (hard_limit, hard_limit))
        except ValueError:
            log.error(f"Failed to increase {limit_name} {soft_limit} -> {hard_limit}")


def num_default_threads(num_min_threads: int = 2) -> int:
    count = num_min_threads
    try:
        # try to get the number of usable cores first
        count = len(os.sched_getaffinity(0))  # type: ignore
    except AttributeError:
        try:
            count = cpu_count()
        except Exception:
            pass
    if not isinstance(count, int):
        count = num_min_threads
    return max(count, num_min_threads)


def from_timestamp(
    ts: Optional[Union[int, float]], cutoff: datetime = datetime(1910, 1, 1, tzinfo=timezone.utc)
) -> Optional[datetime]:
    if ts is None or not isinstance(ts, (int, float)) or not ts:
        return None
    reference_date = datetime(1970, 1, 1, tzinfo=timezone.utc)
    likely_timestamp = reference_date + timedelta(seconds=ts)
    return likely_timestamp if likely_timestamp > cutoff else None


def safe_asdict(obj: Any, max_depth: int = 100, _depth: int = 0, _seen: Optional[set[int]] = None) -> Any:
    """Convert a dataclass to a dictionary, handling circular references."""
    if _seen is None:
        _seen = set()

    if not is_dataclass(obj):
        return obj

    obj_id = id(obj)
    if obj_id in _seen:
        return f"Circular Reference to {obj.__class__.__name__}({obj_id})"
    _seen.add(obj_id)

    if _depth >= max_depth:
        return "Max depth reached"

    result = {}
    for field in fields(obj):
        value = getattr(obj, field.name)
        if is_dataclass(value):
            result[field.name] = safe_asdict(value, max_depth, _depth + 1, _seen)
        elif isinstance(value, list):
            result[field.name] = [
                safe_asdict(item, max_depth, _depth + 1, _seen) if is_dataclass(item) else item for item in value
            ]
        else:
            result[field.name] = value

    return result


def dataclass2html_table(data_objects: list[Any]) -> str:
    if not all(map(is_dataclass, data_objects)):
        raise ValueError("All elements in the list should be dataclass instances.")

    # Convert dataclasses to dictionaries
    data_dicts = [safe_asdict(obj) for obj in data_objects]

    df = pd.DataFrame(data_dicts)

    # Format datetime fields
    for column in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[column]):
            df[column] = df[column].dt.strftime("%Y-%m-%d %H:%M:%S")

    return str(df.to_html(classes="data-table", border=0))
