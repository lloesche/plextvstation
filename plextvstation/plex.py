import os
import sqlite3
import platform
from abc import ABC
from datetime import timedelta, datetime
from dataclasses import dataclass, field
from typing import Optional, List, Tuple
from argparse import ArgumentParser, ArgumentTypeError, Namespace
from .utils import from_timestamp
from .logging import log


def add_args(parser: ArgumentParser) -> None:
    parser.add_argument(
        "--plex-db",
        dest="plex_db",
        help=(
            "Path to Plex database (default: ~/Library/Application Support/Plex Media Server/Plug-in"
            " Support/Databases/com.plexapp.plugins.library.db)"
        ),
        type=valid_plex_db,
        default=get_default_plex_db_path(),
    )
    parser.add_argument(
        "--path-translate",
        dest="path_translate",
        help="Translate paths to a different root (e.g. '/mnt/plex -> /data/plex')",
        type=path_translation,
    )


def validate_args(parser: ArgumentParser, args: Namespace) -> None:
    if args.plex_db is None:
        parser.error("the following arguments are required: --plex-db")


def get_default_plex_db_path() -> Optional[str]:
    current_platform = platform.system()
    default_path: Optional[str] = None
    if current_platform == "Windows":
        default_path = os.path.join(
            os.environ["LOCALAPPDATA"],
            "Plex Media Server",
            "Plug-in Support",
            "Databases",
            "com.plexapp.plugins.library.db",
        )
    elif current_platform == "Linux":
        default_path = (
            "/var/lib/plexmediaserver/Library/Application Support/Plex Media Server/Plug-in"
            " Support/Databases/com.plexapp.plugins.library.db"
        )
    elif current_platform == "Darwin":
        default_path = os.path.expanduser(
            "~/Library/Application Support/Plex Media Server/Plug-in Support/Databases/com.plexapp.plugins.library.db"
        )

    if isinstance(default_path, str) and not os.path.isfile(default_path):
        default_path = "com.plexapp.plugins.library.db"

    if isinstance(default_path, str) and not os.path.isfile(default_path):
        default_path = None
    else:
        try:
            valid_plex_db(default_path)
        except Exception:
            default_path = None

    return default_path


def valid_plex_db(plex_db_path: Optional[str]) -> str:
    """Check if the given path is a valid SQLite3 file with the required Plex tables."""

    if plex_db_path is None:
        raise ArgumentTypeError("Path to Plex database is required.")

    if not os.path.isfile(plex_db_path):
        raise ArgumentTypeError(f"'{plex_db_path}' does not point to a valid file.")

    required_tables = ["media_parts", "media_items", "metadata_items", "taggings", "tags"]

    try:
        conn = sqlite3.connect(f"file:{plex_db_path}?mode=ro", uri=True)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [table[0] for table in cursor.fetchall()]

        for required_table in required_tables:
            if required_table not in tables:
                raise ArgumentTypeError(f"'{plex_db_path}' does not have the required Plex table '{required_table}'.")

    except sqlite3.Error:
        raise ArgumentTypeError(f"'{plex_db_path}' does not appear to be a valid SQLite3 database.")

    finally:
        if conn:
            conn.close()

    return plex_db_path


def path_translation(pt: str) -> Tuple[str, str]:
    err = f"'{pt}' is not a valid path translation. Must be in the form '/mnt/plex -> /data/plex'."
    if "->" not in pt:
        raise ArgumentTypeError(err)

    src, dst = pt.split("->")
    src = src.strip()
    dst = dst.strip()
    if not src or not dst:
        raise ArgumentTypeError(err)

    return src, dst


@dataclass
class MediaFile:
    id: int
    file: str
    duration: timedelta


@dataclass
class Episode:
    id: int
    title: str
    summary: Optional[str]
    aired_at: Optional[datetime]
    media: MediaFile
    season_number: int
    episode_number: int


@dataclass
class Season:
    season_number: int
    episodes: List[Optional[Episode]] = field(default_factory=list)


@dataclass
class MediaBase(ABC):
    id: int
    title: str
    summary: Optional[str]
    tagline: Optional[str]
    genres: List[str]
    released_at: Optional[datetime]


@dataclass
class TVShow(MediaBase):
    seasons: List[Season] = field(default_factory=list)
    first_aired: Optional[datetime] = None
    last_aired: Optional[datetime] = None


@dataclass
class Movie(MediaBase):
    media: MediaFile


class PlexDB:
    def __init__(self, args: Namespace) -> None:
        self.plex_db_path = args.plex_db
        self.path_translate = args.path_translate
        self.movies: List[Movie] = []
        self.tv_shows: List[TVShow] = []
        self.load_db()

    def _execute_query(self, query: str) -> List[sqlite3.Row]:
        with sqlite3.connect(f"file:{self.plex_db_path}?mode=ro", uri=True) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(query)
            return cursor.fetchall()

    def load_db(self) -> None:
        log.debug("Loading Plex database")
        self.movies = self.fetch_all_movies()
        self.tv_shows = self.fetch_all_tv_shows()
        self.fetch_all_episodes()
        log.debug("Loaded Plex database")

    def fetch_all_movies(self) -> List[Movie]:
        log.debug("Fetching all movies")
        query = """
        SELECT
            mi.id AS movie_id,
            mi.title,
            GROUP_CONCAT(t.tag, ',') AS genres,
            mi.tagline,
            mi.summary,
            mi.originally_available_at,
            mp.file,
            m.id AS media_id,
            COALESCE(m.duration, 0) AS duration
        FROM metadata_items AS mi
        LEFT JOIN media_items AS m ON mi.id = m.metadata_item_id
        LEFT JOIN media_parts AS mp ON m.id = mp.media_item_id
        LEFT JOIN taggings tg ON mi.id = tg.metadata_item_id
        LEFT JOIN tags AS t ON tg.tag_id = t.id AND t.tag_type = 1
        WHERE mi.library_section_id = 1 AND mi.metadata_type = 1
        GROUP BY mi.id;
        """
        rows = self._execute_query(query)
        movies = []
        for row in rows:
            genres: List[str] = []
            if row["genres"]:
                genres = row["genres"].split(",")
            movie = Movie(
                id=row["movie_id"],
                title=row["title"],
                tagline=row["tagline"],
                summary=row["summary"],
                genres=genres,
                released_at=from_timestamp(row["originally_available_at"]) if row["originally_available_at"] else None,
                media=MediaFile(
                    id=row["media_id"],
                    file=self.__path_translate(row["file"]),
                    duration=timedelta(milliseconds=row["duration"]),
                ),
            )
            movies.append(movie)
        return movies

    def fetch_all_tv_shows(self) -> List[TVShow]:
        log.debug("Fetching all TV shows")
        query = """
        SELECT
            mi.id AS show_id,
            mi.title AS show_title,
            GROUP_CONCAT(t.tag, ', ') AS genres,
            mi.tagline AS show_tagline,
            mi.summary AS show_summary,
            mi.originally_available_at AS show_release_date
        FROM metadata_items AS mi
        LEFT JOIN taggings tg ON mi.id = tg.metadata_item_id
        LEFT JOIN tags AS t ON tg.tag_id = t.id AND t.tag_type = 1
        WHERE mi.library_section_id = 2 AND mi.metadata_type = 2
        GROUP BY mi.id;
        """
        rows = self._execute_query(query)
        tv_shows = []
        for row in rows:
            genres: List[str] = []
            if row["genres"]:
                genres = row["genres"].split(",")
            tv_show = TVShow(
                id=row["show_id"],
                title=row["show_title"],
                tagline=row["show_tagline"],
                genres=genres,
                summary=row["show_summary"],
                released_at=from_timestamp(row["show_release_date"]) if row["show_release_date"] else from_timestamp(0),
                seasons=[],
            )
            tv_shows.append(tv_show)
        return tv_shows

    def fetch_all_episodes(self) -> None:
        log.debug("Fetching all episodes")
        tv_shows = {show.id: show for show in self.tv_shows}
        query = """
        SELECT
            mi.id AS episode_id,
            mi.parent_id AS season_id,
            mip.parent_id AS show_id,
            mi.title AS episode_title,
            mi.summary AS episode_summary,
            mi.originally_available_at AS aired_at,
            mi."index" AS episode_number,
            mip."index" AS season_number,
            m.duration AS episode_duration,
            mp.file AS episode_file
        FROM metadata_items AS mi
        JOIN metadata_items AS mip ON mi.parent_id = mip.id
        LEFT JOIN media_items AS m ON mi.id = m.metadata_item_id
        LEFT JOIN media_parts AS mp ON m.id = mp.media_item_id
        WHERE mi.library_section_id = 2 AND mi.metadata_type = 4
        ORDER BY show_id, season_number, episode_number;
        """
        rows = self._execute_query(query)

        for row in rows:
            episode = Episode(
                id=row["episode_id"],
                title=row["episode_title"],
                summary=row["episode_summary"],
                aired_at=from_timestamp(row["aired_at"]) if row["aired_at"] else None,
                media=MediaFile(
                    id=row["episode_id"],
                    file=row["episode_file"],
                    duration=timedelta(milliseconds=row["episode_duration"])
                    if row["episode_duration"]
                    else timedelta(milliseconds=0),
                ),
                season_number=row["season_number"],
                episode_number=row["episode_number"],
            )

            tv_show = tv_shows[row["show_id"]]
            if len(tv_show.seasons) <= episode.season_number:
                for i in range(len(tv_show.seasons), episode.season_number + 1):
                    tv_show.seasons.append(Season(season_number=i))

            if len(tv_show.seasons[episode.season_number].episodes) <= episode.episode_number:
                for _ in range(len(tv_show.seasons[episode.season_number].episodes), episode.episode_number + 1):
                    tv_show.seasons[episode.season_number].episodes.append(None)
            tv_show.seasons[episode.season_number].episodes[episode.episode_number] = episode
            if episode.aired_at is not None:
                if tv_show.first_aired is None or tv_show.first_aired > episode.aired_at:
                    tv_show.first_aired = episode.aired_at
                if tv_show.last_aired is None or tv_show.last_aired < episode.aired_at:
                    tv_show.last_aired = episode.aired_at

    def __path_translate(self, path: str) -> str:
        if self.path_translate is None:
            return path

        src, dst = self.path_translate
        if path.startswith(src):
            path = path.replace(src, dst)

        return path
