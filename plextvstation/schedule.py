from dataclasses import dataclass
from typing import List, Union
from datetime import datetime
from .media import TVShow, Movie, MediaFile, Episode


@dataclass
class ScheduledProgram:
    start_time: datetime
    end_time: datetime
    content: Union[Episode, Movie]


@dataclass
class StationSchedule:
    date: datetime
    programs: List[ScheduledProgram]

    def add_program(self, content: Union[Episode, Movie], start_time: datetime) -> None:
        end_time = start_time + content.media.duration
        self.programs.append(ScheduledProgram(start_time, end_time, content))
