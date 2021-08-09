from sys import exc_info
import time
import logging
from enum import Enum
import requests
from pyvesync_v2.vesyncbasedevice import VeSyncBaseDevice
from pyvesync_v2.vesyncoutlet import VeSyncOutlet
from wyzeapy.base_client import Device
from clients.location import Location
from clients.vesync import  SmartVeSync
from clients.weather import OpenWeatherMap
from clients.wyze import WyzeClient

_LOGGER = logging.getLogger(__name__)

class Devices(Enum):
    #VeSync
    OFFICE_SENSOR = 'Office Sensor'
    OFFICE_LAMP = 'Office Lamp'
    NURSERY_SENSOR = 'Nursery Sensor'
    NURSERY_LAMP = 'Nursery Lamp'
    NURSERY_FEEDING_LAMP = 'Nursery Feeding Lamp'
    BATHROOM_DEHUMIDIFIER = 'Bathroom Dehumidifier'

    #Wyze
    NURSERY_BULB = 'Nursery Bulb'

UPDATE_DETAILS = [Devices.BATHROOM_DEHUMIDIFIER.value, Devices.NURSERY_FEEDING_LAMP.value]
CHECK_AMBIENT_ENABLED = [Devices.OFFICE_LAMP, Devices.NURSERY_BULB]

#Wyze
MIN_BRIGHTNESS = 30

class Runtime:
    def __init__(self, vesync_manager: SmartVeSync):
        self.vesync_manager = vesync_manager
        self._config = {}

    @property
    def configured_outlets(self) -> list:
        """Returns the names of all configured outlets"""
        devs = []
        for dev in self._config:
            devs.append(dev)
        return devs

    def add(self, outlet, max_time: int):
        """Adds an outlet to the runtime config, or updates the max time if it already exists"""
        if outlet is None or max_time is None:
            raise TypeError('Both args must be set')
        if int(max_time) < 1:
            raise ValueError('max_time must be greater than 0')
        name = get_device_name(outlet)

        if name in self._config:
            self._config[name]['max_time'] = max_time
        else:
            self._config[name] = {'max_time': max_time, 'start': 0}

    def check(self):
        """Checks all configured outlets against their max runtime"""
        for outlet in self.configured_outlets:
            outlet_vesync = self.vesync_manager.get_device_by_name(outlet)
            if not outlet_vesync.is_on:
                outlet_vesync.turn_on()
            if outlet_vesync.power <= 2:
                self._set_start_time(outlet, 0)
            else:
                if self.is_max_time_exceeded(outlet):
                    cycle_state(outlet_vesync)
                    self._set_start_time(outlet, 0)
                    _LOGGER.info(f'{outlet} run time exceeded')
                elif self._get_start_time(outlet) == 0:
                    self._set_start_time(outlet, time.time())
                    _LOGGER.info(f'{outlet} turned on')

    def _get_start_time(self, outlet) -> float:
        return self._config[get_device_name(outlet)]['start']

    def _set_start_time(self, outlet, time):
        self._config[get_device_name(outlet)]['start'] = time

    def _get_max_time(self, outlet) -> int:
        return self._config[get_device_name(outlet)]['max_time']

    def is_max_time_exceeded(self, outlet) -> bool:
        name = get_device_name(outlet)
        return self._get_start_time(name) > 0 and time.time() - self._get_start_time(name)  > self._get_max_time(name)

class Lights:
    def __init__(self, ambient_config: dict, vesync_manager: SmartVeSync, wyze_client: WyzeClient, weather_client: OpenWeatherMap) -> None:
        self.ambient_config = ambient_config
        self.vesync_manager = vesync_manager
        self.wyze_client = wyze_client
        self.weather_client = weather_client
        
    def check_sensor(self, sensor: Devices, lamp: Devices) -> None:
        sensor_vesync = self.vesync_manager.get_device_by_name(get_device_name(sensor))
        lamp_vesync = self.vesync_manager.get_device_by_name(get_device_name(lamp))
        if is_connected(sensor_vesync) and not lamp_vesync.is_on and self.check_ambient(lamp):
            lamp_vesync.turn_on()
            _LOGGER.info(f'turned on {lamp_vesync.device_name}')

        if not is_connected(sensor_vesync) and lamp_vesync.is_on:
            lamp_vesync.turn_off()
            _LOGGER.info(f'turned off {lamp_vesync.device_name}')
            
    def check_sensor_power(self, sensor: Devices, lamp: Devices):
        sensor_vesync = self.vesync_manager.get_device_by_name(get_device_name(sensor))
        lamp_vesync = self.vesync_manager.get_device_by_name(get_device_name(lamp))
        if not lamp_vesync.is_on:
            lamp_vesync.turn_on()
        if not is_connected(sensor_vesync) and lamp_vesync.power > 2:
            cycle_state(lamp_vesync)
            _LOGGER.info(f'turned off {lamp_vesync.device_name}')

    def check_sensor_wyze(self, sensor: Devices, bulb: Devices):
        sensor_vesync = self.vesync_manager.get_device_by_name(get_device_name(sensor))
        bulb_wyze = self.wyze_client.get_device_by_nickname(get_device_name(bulb))
        if is_connected(sensor_vesync) and not self.wyze_client.is_on(bulb_wyze):
            self.configure_wyze_bulb(bulb_wyze)
            _LOGGER.info(f'turned on {bulb_wyze.nickname}')

        if not is_connected(sensor_vesync) and self.wyze_client.is_on(bulb_wyze):
            self.wyze_client.set_brightness(bulb_wyze, MIN_BRIGHTNESS)
            self.wyze_client.turn_off(bulb_wyze)
            _LOGGER.info(f'turned off {bulb_wyze.nickname}')

    def check_ambient(self, lamp: Devices) -> bool:
        if lamp not in CHECK_AMBIENT_ENABLED:
            return True
        if self.weather_client.is_cloudy:
            _LOGGER.debug(f"it is cloudy ({self.weather_client.weather_description} with cloud coverage {self.weather_client.cloud_coverage}%), {lamp.value} not turing on")
            return False
        if not self.weather_client.is_sun_up:
            _LOGGER.debug(f"it is dark, {lamp.value} not turing on")
            return False
        return True   

    def configure_wyze_bulb(self, bulb: Device):
        if Devices(bulb.nickname) not in CHECK_AMBIENT_ENABLED:
            self.wyze_client.turn_on(bulb)
            return

        if self.weather_client.is_sun_in_range(self.ambient_config['daytime']['rise_offset'], self.ambient_config['daytime']['set_offset']):
            _LOGGER.info('configuring bulb for daytime...')
            self.wyze_client.set_color_temp(bulb, 3469)
            if self.weather_client.is_sun_up and not self.weather_client.is_cloudy:
                self.wyze_client.set_brightness(bulb, 100)
            else:
                self.wyze_client.set_brightness(bulb, 85)
        elif self.weather_client.is_sun_in_range(self.ambient_config['dawn']['rise_offset'], self.ambient_config['daytime']['set_offset']):
            _LOGGER.info('configuring bulb for dawn...')
            self.wyze_client.set_color_temp(bulb, 1700)
            self.wyze_client.set_brightness(bulb, 35)
        else:
            self.wyze_client.set_color(bulb, 'FF2000')
            if self.weather_client.is_sun_in_range(self.ambient_config['daytime']['rise_offset'], self.ambient_config['dusk']['set_offset']):
                _LOGGER.info('configuring bulb for dusk...')
                self.wyze_client.set_brightness(bulb, 40)
            else:
                _LOGGER.info('configuring bulb for nighttime...')
                self.wyze_client.set_brightness(bulb, 30)

def is_connected(device: VeSyncBaseDevice) -> bool:
    """Return true if VeSync device is connected."""
    if device.connection_status == 'online':
        return True
    return False

def cycle_state(outlet: VeSyncOutlet) -> None:
    outlet.turn_off()
    time.sleep(2)
    outlet.turn_on()
    
def get_device_name(device) -> str:
    if isinstance(device, Enum):
        return device.value
    if isinstance(device, VeSyncBaseDevice):
        return device.device_name
    if isinstance(device, str):
        return device
    raise TypeError(f'Type {type(device)} is unsupported')

def main(config: dict, wyze_client: WyzeClient, location: Location):
    lights = config['lights']
    HOME_UPDATE_FREQUENCY = lights['update_frequency']['home']
    AWAY_UPDATE_FREQUENCY = lights['update_frequency']['away']
    vesync = config['vesync']
    vesync_manager = SmartVeSync(vesync['username'], vesync['password'], vesync['time_zone'], UPDATE_DETAILS)
    vesync_manager.update_interval = HOME_UPDATE_FREQUENCY
    vesync_manager.login()
    vesync_manager.update()
    _LOGGER.info('VeSync devices updated')
    weather = config['open_weather_map']
    weather_client = OpenWeatherMap(weather['api_key'], weather['lattitude'], weather['longitude'])
    lights = Lights(lights['ambient'], vesync_manager, wyze_client, weather_client)
    runtime = Runtime(vesync_manager)
    for key, val in config['runtime'].items():
        runtime.add(Devices(key), val)

    while True:
        try:
            lights.check_sensor(Devices.OFFICE_SENSOR, Devices.OFFICE_LAMP)
            #lights.check_sensor(Devices.NURSERY_SENSOR, Devices.NURSERY_LAMP)
            lights.check_sensor_wyze(Devices.NURSERY_SENSOR, Devices.NURSERY_BULB)
            lights.check_sensor_power(Devices.NURSERY_SENSOR, Devices.NURSERY_FEEDING_LAMP)
            runtime.check()
        except KeyError as key_error:
            _LOGGER.error(f'KeyError, device missing for key "{key_error.args[0]}"')
        except requests.exceptions.ConnectionError as conn_error:
            _LOGGER.error(f'Connection Error, retrying after a delay', exc_info=conn_error)
            time.sleep(AWAY_UPDATE_FREQUENCY)

        time.sleep(HOME_UPDATE_FREQUENCY if location.is_anyone_home(cached=True) else AWAY_UPDATE_FREQUENCY)
        vesync_manager.smart_update()
