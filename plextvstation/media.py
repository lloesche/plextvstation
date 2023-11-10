from __future__ import annotations
from abc import ABC
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, List


@dataclass(eq=True)
class MediaFile:
    id: int
    file: str
    duration: timedelta


@dataclass(eq=True)
class Episode:
    id: int
    number: int
    title: str
    summary: Optional[str]
    aired_at: Optional[datetime]
    media: MediaFile
    season: Season
    tv_show: TVShow


@dataclass(eq=True)
class Season:
    number: int
    episodes: List[Optional[Episode]] = field(default_factory=list)


@dataclass(eq=True)
class MediaBase(ABC):
    id: int
    title: str
    summary: Optional[str]
    tagline: Optional[str]
    genres: List[str]
    released_at: Optional[datetime]


@dataclass(eq=True)
class TVShow(MediaBase):
    seasons: List[Season] = field(default_factory=list)
    first_aired: Optional[datetime] = None
    last_aired: Optional[datetime] = None


@dataclass(eq=True)
class Movie(MediaBase):
    media: MediaFile
