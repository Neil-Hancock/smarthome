import datetime
from enum import Enum
import logging
import time
import requests
from clients.location import Location
from clients.wyze import PowerStates, WyzeClient

_LOGGER = logging.getLogger(__name__)

class Cameras(Enum):
    """Manage state of the following cameras"""
    LIVING_ROOM = 'Living Room'
    NURSERY = 'Nursery'

class Scheduler():
    def __init__(self) -> None:
        self._config = {}

    def add(self, camera: Cameras, on_time: str, off_time: str):
        """Adds a camera to the scheduler, or updates the schedule if it already exists"""
        if camera is None or on_time is None or off_time is None:
            raise TypeError('All 3 args must be set')
        assert on_time is not off_time
        if camera.value not in self._config:
            self._config[camera.value] = {'on_time': None, 'off_time': None}
        self._config[camera.value]['on_time'] = datetime.time(hour=int(on_time.split(':')[0]), minute=int(on_time.split(':')[1]))
        self._config[camera.value]['off_time'] = datetime.time(hour=int(off_time.split(':')[0]), minute=int(off_time.split(':')[1]))

    def is_scheduled_on(self, camera: Cameras) -> bool:
        assert camera.value in self._config
        now = datetime.datetime.now().time()
        on_time = self._config[camera.value]['on_time']
        off_time = self._config[camera.value]['off_time'] 
        assert on_time is not None and off_time is not None
        if on_time < off_time:
            return on_time < now and off_time > now
        else:
            return not (off_time < now and on_time > now)

def main(config: dict, wyze_client: WyzeClient, location: Location):
    cameras = config['cameras']
    UPDATE_FREQUENCY = cameras['update_frequency']
    scheduler = Scheduler()
    last_check = {}
    for key, val in cameras['scheduler'].items():
        scheduler.add(Cameras(key), val['on_time'], val['off_time'])
        last_check[key] = True

    while(True):
        for camera in Cameras:
            turn_on = not location.is_anyone_home() or scheduler.is_scheduled_on(camera)
            if last_check[camera.value] == turn_on:
                power_state = PowerStates.POWER_ON if turn_on else PowerStates.POWER_OFF
                try:
                    wyze_client.set_power_state(camera.value, power_state)
                except requests.exceptions.ConnectionError as conn_error:
                    _LOGGER.error(f'Connection Error, retrying next update cycle', exc_info=conn_error)
            last_check[camera.value] = turn_on
        time.sleep(UPDATE_FREQUENCY)
