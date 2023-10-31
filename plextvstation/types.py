from enum import Enum


class Platform(Enum):
    LINUX = "Linux"
    WINDOWS = "Windows"
    MACOS = "MacOS"
    UNKNOWN = "Unknown"


class Architecture(Enum):
    X86_64 = "x86_64"
    ARM64 = "arm64"
    UNKNOWN = "Unknown"
