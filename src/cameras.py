import datetime
import logging
import time
import requests
from clients.location import Location
from clients.wyze import PowerStates, WyzeClient

_LOGGER = logging.getLogger(__name__)

class Scheduler():
    def __init__(self) -> None:
        self._config = {}

    def add(self, camera: str, on_time: str, off_time: str):
        """Adds a camera to the scheduler, or updates the schedule if it already exists"""
        if camera is None or on_time is None or off_time is None:
            raise TypeError('All 3 args must be set and not None')
        if on_time == off_time:
            raise ValueError('on_time and off_time must be different values')
        if camera not in self._config:
            self._config[camera] = {'on_time': None, 'off_time': None}
        self._config[camera]['on_time'] = datetime.time(hour=int(on_time.split(':')[0]), minute=int(on_time.split(':')[1]))
        self._config[camera]['off_time'] = datetime.time(hour=int(off_time.split(':')[0]), minute=int(off_time.split(':')[1]))

    def is_scheduled_on(self, camera: str) -> bool:
        """Checks if the camera is schedules to be on, or returns True if no schedule is configured"""
        if  camera not in self._config:
            return True
        on_time = self._config[camera]['on_time']
        off_time = self._config[camera]['off_time'] 
        assert on_time is not None and off_time is not None
        now = datetime.datetime.now().time()
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
        scheduler.add(key, val['on_time'], val['off_time'])
        last_check[key] = True

    while(True):
        for camera in cameras['device_names']:
            turn_on = not location.is_anyone_home() or scheduler.is_scheduled_on(camera)
            if last_check[camera] == turn_on:
                power_state = PowerStates.POWER_ON if turn_on else PowerStates.POWER_OFF
                try:
                    wyze_client.set_power_state(camera, power_state)
                except requests.exceptions.ConnectionError as conn_error:
                    _LOGGER.error(f'Connection Error, retrying next update cycle', exc_info=conn_error)
            last_check[camera] = turn_on
        time.sleep(UPDATE_FREQUENCY)
