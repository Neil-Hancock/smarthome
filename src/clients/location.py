import logging
import platform
import subprocess
from pushbullet import Pushbullet

_LOGGER = logging.getLogger(__name__)

class Location:
    MOCK_NMAP = 'F0:AA:BB:CC:DD:EE, F0:5C:77:FB:13:7F'

    def __init__(self, pushbullet_key, retry_count, ip_range, phone_macs):
        self.PUSHBULLET_API_KEY = pushbullet_key
        self.RETRY_COUNT = retry_count
        self.ip_range = ip_range
        self.phone_macs = phone_macs
        self._last_check = True

    def get_nmap(self) -> str:
        if 'macOS' in platform.platform():
            return Location.MOCK_NMAP

        output = subprocess.run(["sudo", "nmap", "-sn", self.ip_range], capture_output=True)
        return output.stdout.decode('utf-8')

    def is_anyone_home(self, cached=False) -> bool:
        if cached:
            return self._last_check

        for i in range(self.RETRY_COUNT):
            nmap_out = self.get_nmap()
            for mac in self.phone_macs:
                if mac in nmap_out:
                    if i == self.RETRY_COUNT - 1:
                        _LOGGER.info(f'Someone is home, took {i} iterations to check')
                    else:
                        _LOGGER.debug(f'Someone is home, took {i} iterations to check')
                    self._last_check = True
                    return self._last_check

        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug('No one is home')
            pb = Pushbullet(self.PUSHBULLET_API_KEY)
            pb.push_note('Wyze', 'No one is home')

        self._last_check = False
        return self._last_check