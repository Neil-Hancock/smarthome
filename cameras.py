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
    def __init__(self, on_time: str, off_time: str) -> None:
        self.on_time = datetime.time(hour=int(on_time.split(':')[0]), minute=int(on_time.split(':')[1]))
        self.off_time = datetime.time(hour=int(off_time.split(':')[0]), minute=int(off_time.split(':')[1]))

    def is_scheduled_on(self) -> bool:
        now = datetime.datetime.now().time()
        return self.on_time < now and self.off_time  > now

def main(config: dict, wyze_client: WyzeClient, location: Location):
    cameras = config['cameras']
    UPDATE_FREQUENCY = cameras['update_frequency']
    scheduler = Scheduler(cameras['on_time'], cameras['off_time'])
    last_check = True

    while(True):
        turn_on = not location.is_anyone_home() or scheduler.is_scheduled_on()
        if last_check == turn_on:
            power_state = PowerStates.POWER_ON if turn_on else PowerStates.POWER_OFF
            try:
                wyze_client.set_power_state(Cameras.LIVING_ROOM.value, power_state)
                wyze_client.set_power_state(Cameras.NURSERY.value, power_state)
            except requests.exceptions.ConnectionError as conn_error:
                _LOGGER.error(f'Connection Error, retrying next update cycle', exc_info=conn_error)
        last_check = turn_on
        time.sleep(UPDATE_FREQUENCY)
