import os
import pickle
import hashlib
from dataclasses import dataclass
from datetime import timezone
from typing import Optional
from .schedule import StationSchedule
from .logging import log
from .config import Config


@dataclass
class TVStation:
    name: str
    description: Optional[str]
    schedule: StationSchedule
    country: Optional[str]
    language: Optional[str]
    tags: Optional[list[str]]
    active: bool
    timezone: timezone = timezone.utc


@dataclass
class Network:
    name: str
    stations: list[TVStation]
    last_save_sha: Optional[str] = None


def load_network(config: Config) -> Network:
    conf_dir = config["conf_dir"]
    network_name = config["network"]
    network_file = os.path.join(conf_dir, "network.db")
    log.debug(f"Loading network from {network_file}")
    if not os.path.exists(network_file):
        log.warning(f"Network file not found: {network_file} - initializing new network")
        return Network(network_name, [])
    with open(network_file, "rb") as f:
        pickled_stations = f.read()
    stations = pickle.loads(pickled_stations)
    if not isinstance(stations, list):
        raise Exception(f"Invalid network file: {network_file}")
    sha256 = hashlib.sha256()
    sha256.update(pickled_stations)
    network = Network(network_name, stations, sha256.hexdigest())
    return network


def save_network(config: Config, network: Network) -> None:
    conf_dir = config["conf_dir"]
    network_file = os.path.join(conf_dir, "network.db")
    tmp_network_file = f"{network_file}.tmp"
    backup_file = f"{network_file}.bak"
    pickled_stations = pickle.dumps(network.stations)

    sha256 = hashlib.sha256()
    sha256.update(pickled_stations)
    hash = sha256.hexdigest()

    if hash == network.last_save_sha:
        log.debug("No changes to network, skipping save")
        return

    network.last_save_sha = hash

    log.debug(f"Saving network to {network_file}")
    with open(tmp_network_file, "wb") as f:
        f.write(pickled_stations)
    if os.path.exists(network_file):
        log.debug(f"Backing up existing stations file to {backup_file}")
        os.rename(network_file, backup_file)
    os.rename(tmp_network_file, network_file)
