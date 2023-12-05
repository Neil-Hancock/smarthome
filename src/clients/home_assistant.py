from enum import Enum
import logging
import requests

_LOGGER = logging.getLogger(__name__)


class PowerStates(Enum):
    POWER_ON = 'turn_on'
    POWER_OFF = 'turn_off'


class HomeAssistant:

    BASE_URL = 'http://pi.adsb:8123/api'

    def __init__(self, access_token):
        self._access_token = access_token

    def get_device_by_entity_id(self, entity_id: str) -> dict:
        result = {}
        try:
            headers = {'Authorization': f'Bearer {self._access_token}', 'Accept': 'application/json'}
            response = requests.get(f'{HomeAssistant.BASE_URL}/states/{entity_id}', headers=headers)
        except requests.exceptions.RequestException as e:
            _LOGGER.warning(e)
        else:
            if response.status_code == requests.codes.ok and response.json() is not None:
                _LOGGER.debug(f'Got response for {entity_id}, {response.json()}')
                result = response.json()
            else:
                _LOGGER.warning(f'Unable to fetch entity id, status_code = {response.status_code}')
        finally:
            return result

    def is_on(self, entity_id: str) -> bool:
        device = self.get_device_by_entity_id(entity_id)
        return device['state'] == 'on'

    def set_power_state(self, entity_id: str, power_state: PowerStates, **kwargs):
        if power_state == PowerStates.POWER_ON and self.is_on(entity_id):
            return
        elif power_state == PowerStates.POWER_OFF and not self.is_on(entity_id):
            return
        # self.turn_on(entity_id) if power_state == PowerStates.POWER_ON else self.turn_off(entity_id)
        self.run_action(entity_id, power_state, **kwargs)

    def run_action(self, entity_id: str, power_state: PowerStates, **kwargs):
        payload = {}
        if kwargs is not None:
            payload = kwargs

        payload['entity_id'] = entity_id
        service_type = entity_id.split('.')[0]
        try:
            headers = {'Authorization': f'Bearer {self._access_token}', 'Accept': 'application/json'}
            _LOGGER.info(f'Setting {power_state.value} for {entity_id} with settings {kwargs}')
            response = requests.post(f'{HomeAssistant.BASE_URL}/services/{service_type}/{power_state.value}', json=payload, headers=headers)
        except requests.exceptions.RequestException as e:
            _LOGGER.warning(e)
        else:
            if response.status_code == requests.codes.ok and response.json() is not None:
                _LOGGER.debug(f'Got response for {entity_id}, {response.json()}')
                return response.json()
            else:
                _LOGGER.warning(f'Unable to update entity id, status_code = {response.status_code}')

    # def set_color_temp(self, device: Device, temp: int):
    #     self.set_color(device, WyzeClient._get_rgb_from_color_temp(temp))
    #
    # @staticmethod
    # def _get_rgb_from_color_temp(temp: int) -> str:
    #     """
    #     Converts from K to RGB hex
    #     Based on: http://www.tannerhelland.com/4435/convert-temperature-rgb-algorithm-code/
    #     """
    #
    #     red = 0
    #     green = 0
    #     blue = 0
    #     t = temp / 100
    #
    #     if t <= 66:
    #         red = 255
    #     else:
    #         red = 329.698727446 * (t - 60) ** -0.1332047592
    #         if red < 0: red = 0
    #         if red > 255: red = 255
    #
    #     if t <= 66:
    #         green = 99.4708025861 * math.log(t) - 161.1195681661
    #         if green < 0: green = 0
    #         if green > 255: green = 255
    #     else:
    #         green = 288.1221695283 * (t - 60) ** -0.0755148492
    #         if green < 0: green = 0
    #         if green > 255: green = 255
    #
    #     if t >= 66:
    #         blue = 255
    #     else:
    #         if t <= 19:
    #             blue = 0
    #         else:
    #             blue = 138.5177312231 * math.log(t - 10) - 305.0447927307
    #             if blue < 0: blue = 0
    #             if blue > 255: blue = 255
    #
    #     return f'{hex(int(red))[2:].zfill(2)}{hex(int(green))[2:].zfill(2)}{hex(int(blue))[2:].zfill(2)}'.upper()
    #

class Device:
    # product_type: str
    # product_model: str
    # mac: str
    # nickname: str

    def __init__(self, dictionary):
        for k, v in dictionary.items():
            setattr(self, k, v)

    # @property
    # def type(self) -> DeviceTypes:
    #     try:
    #         return DeviceTypes(self.product_type)
    #     except ValueError:
    #         return DeviceTypes.UNKNOWN
    #
    # def __repr__(self):
    #     return "<Device: {}, {}>".format(DeviceTypes(self.product_type), self.mac)