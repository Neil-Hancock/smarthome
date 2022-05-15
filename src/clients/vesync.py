from itertools import chain
import logging
import time
import threading
from pyvesync import VeSync
from pyvesync.vesyncbasedevice import VeSyncBaseDevice

_LOGGER = logging.getLogger(__name__)

class SmartVeSync(VeSync):
    def __init__(self, username, password, time_zone, update_details):
        super().__init__(username, password, time_zone=time_zone)
        self.update_details = update_details
        self._devices_lock = threading.Lock()
        self._devices = {}

    def get_device_by_name(self, name: str) -> VeSyncBaseDevice:
        self.smart_update()
        with self._devices_lock:
            return self._devices[name]

    def _build_devices_dict(self):
        devices = {}
        for device in chain(*list(self._dev_list.values())):
            devices[device.device_name] = device
        with self._devices_lock:
            self._devices = devices

    def update(self):
        if self.device_time_check():
            super().update()
            self._build_devices_dict()

    def smart_update(self):
        """Fetch updated information about devices."""
        if self.device_time_check():

            if not self.enabled:
                _LOGGER.error('Not logged in to VeSync')
                return
            self.get_devices()

            devices = list(self._dev_list.values())

            for device in chain(*devices):
                 if (device.device_name in self.update_details):
                     device.update()

            self.last_update_ts = time.time()
            self._build_devices_dict()


