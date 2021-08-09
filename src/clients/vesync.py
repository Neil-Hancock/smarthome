from itertools import chain
import logging
import time
import threading
from pyvesync_v2 import VeSync
from pyvesync_v2.vesyncbasedevice import VeSyncBaseDevice

_LOGGER = logging.getLogger(__name__)

class SmartVeSync(VeSync):
    def __init__(self, username, password, time_zone, update_details):
        super().__init__(username, password, time_zone=time_zone)
        self.update_details = update_details
        self._devices_lock = threading.Lock()
        self._devices = {}

    def get_device_by_name(self, name: str) -> VeSyncBaseDevice:
        with self._devices_lock:
            return self._devices[name]

    def _build_devices_dict(self):
        devices = {}
        for device in self.device_chain:
            devices[device.device_name] = device
        with self._devices_lock:
            self._devices = devices

    def update(self):
        super().update()
        self._build_devices_dict()

    def smart_update(self):
        """Fetch updated information about devices."""
        if self.device_time_check():

            if not self.in_process and self.enabled:
                self.clear_devices()
                outlets, switches, fans, bulbs = self.get_devices()
                self.outlets.extend(outlets)
                self.switches.extend(switches)
                self.fans.extend(fans)
                self.bulbs.extend(bulbs)

                for device in self.device_chain:
                    if (device.device_name in self.update_details):
                        device.update()

                self.last_update_ts = time.time()
                self._build_devices_dict()
            else:
                _LOGGER.error('You are not logged in to VeSync')

    @property
    def device_chain(self):
        devices = [self.outlets, self.bulbs, self.switches, self.fans]
        return chain(*devices)

    def clear_devices(self):
        self.outlets = []
        self.switches = []
        self.fans = []
        self.bulbs = []

