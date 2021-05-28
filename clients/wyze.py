from enum import Enum
import logging
import math
import time
import threading
import requests
import threading
from wyzeapy.client import Client
from wyzeapy.base_client import *

_LOGGER = logging.getLogger(__name__)

class PowerStates(Enum):
    POWER_ON = 'power_on'
    POWER_OFF = 'power_off'

class WyzeClient(Client):

    UPDATE_INTERVAL = 8

    def __init__(self, email, password):
        super().__init__(email, password)
        self.update_interval = WyzeClient.UPDATE_INTERVAL
        self._devices_lock = threading.Lock()
        self._last_update_ts = None
        self.update_devices()

    def update_devices(self):
        if not self._time_check():
            return
        try:
            devs = self.get_devices()
        except AccessTokenError as error:
            _LOGGER.warn('AccessTokenError, refreshing token...' + str(error))
            self.refresh_token()
            self.update_devices()
        else:
            devices = {}
            for dev in devs:
                devices[dev.nickname] = dev
            with self._devices_lock:
                self._devices = devices
            
            self._last_update_ts = time.time()

    def _time_check(self) -> bool:
        """Test if update interval has been exceeded."""
        if self._last_update_ts is None or (
                time.time() - self._last_update_ts) > self.update_interval:
            return True
        return False

    def get_device_by_nickname(self, nickname) -> Device:
        with self._devices_lock:
            return self._devices[nickname]

    def is_on(self, device: Device) -> bool:
        device_type = DeviceTypes(device.product_type)
        if device_type not in [
            DeviceTypes.CAMERA,
            DeviceTypes.MESH_LIGHT
        ]:
            raise ActionNotSupported(device.product_type)

        self.update_devices()
        if device_type == DeviceTypes.CAMERA:
            return bool(int(device.device_params['power_switch']))
        if device_type == DeviceTypes.MESH_LIGHT:
            return bool(int(device.device_params['switch_state']))

    def set_power_state(self, nickname, power_state: PowerStates):
        device = self.get_device_by_nickname(nickname)
        if device is None:
            _LOGGER.error(f'No device with nickname {nickname} was found')
            return
        if power_state == PowerStates.POWER_ON and self.is_on(device):
            return
        elif power_state == PowerStates.POWER_OFF and not self.is_on(device):
            return
        _LOGGER.info(f'Setting {power_state.value} for {device.nickname}')
        try:
            #self.run_action(device, power_state.value)
            self.turn_on(device) if power_state == PowerStates.POWER_ON else self.turn_off(device)
        except AccessTokenError as error:
            _LOGGER.warn('AccessTokenError, refreshing token...' + str(error))
            self.refresh_token()
            self.set_power_state(nickname, power_state)

    # def run_action(self, device: Device, action_key: str):
    #     if DeviceTypes(device.product_type) not in [
    #         DeviceTypes.CAMERA
    #     ]:
    #         raise ActionNotSupported(device.product_type)

    #     payload = {
    #         "phone_system_type": PHONE_SYSTEM_TYPE,
    #         "app_version": APP_VERSION,
    #         "app_ver": APP_VER,
    #         "sc": "9f275790cab94a72bd206c8876429f3c",
    #         "ts": int(time.time()),
    #         "sv": "9d74946e652647e9b6c9d59326aef104",
    #         "access_token": self.client.access_token,
    #         "phone_id": PHONE_ID,
    #         "app_name": APP_NAME,
    #         "provider_key": device.product_model,
    #         "instance_id": device.mac,
    #         "action_key": action_key,
    #         "action_params": {},
    #         "custom_string": '',
    #     }

    #     response_json = requests.post("https://api.wyzecam.com/app/v2/auto/run_action", json=payload).json()

    #     NetClient.check_for_errors(response_json)

    def refresh_token(self):
        payload = {
            "phone_system_type": PHONE_SYSTEM_TYPE,
            "app_version": APP_VERSION,
            "app_ver": APP_VER,
            "sc": "9f275790cab94a72bd206c8876429f3c",
            "ts": int(time.time()),
            "sv": "9d74946e652647e9b6c9d59326aef104",
            "access_token": self.client.access_token,
            "phone_id": PHONE_ID,
            "app_name": APP_NAME,
            "refresh_token": self.client.refresh_token,
        }

        response_json = requests.post("https://api.wyzecam.com/app/user/refresh_token", json=payload).json()
        NetClient.check_for_errors(response_json)
        try:
            self.client.access_token = response_json['data']['access_token']
            self.client.refresh_token = response_json['data']['refresh_token']
            return True
        except KeyError:
            raise UnknownApiError(response_json)

    def set_color_temp(self, device: Device, temp: int):
        self.set_color(device, WyzeClient._get_rgb_from_color_temp(temp))

    @staticmethod
    def _get_rgb_from_color_temp(temp: int) -> str:
        """
        Converts from K to RGB hex
        Based on: http://www.tannerhelland.com/4435/convert-temperature-rgb-algorithm-code/
        """

        red = 0
        green = 0 
        blue = 0
        t = temp / 100

        if t <= 66:
            red = 255
        else:
            red = 329.698727446 * (t - 60) ** -0.1332047592
            if red < 0: red = 0
            if red > 255: red = 255

        if t <= 66:
            green = 99.4708025861 * math.log(t) - 161.1195681661
            if green < 0: green = 0
            if green > 255: green = 255
        else:
            green = 288.1221695283 * (t - 60) ** -0.0755148492
            if green < 0: green = 0
            if green > 255: green = 255

        if t >= 66:
            blue = 255
        else:
            if t <= 19:
                blue = 0
            else:
                blue = 138.5177312231 * math.log(t - 10) - 305.0447927307
                if blue < 0: blue = 0
                if blue > 255: blue = 255

        return f'{hex(int(red))[2:].zfill(2)}{hex(int(green))[2:].zfill(2)}{hex(int(blue))[2:].zfill(2)}'.upper()