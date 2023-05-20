import datetime
from json.decoder import JSONDecodeError
import time
import logging
from random import randint
import requests
from pyvesync.vesyncbasedevice import VeSyncBaseDevice
from pyvesync.vesyncoutlet import VeSyncOutlet
from wyzeapy.exceptions import UnknownApiError
from wyzeapy.base_client import Device
from clients.location import Location
from clients.vesync import  SmartVeSync
from clients.weather import OpenWeatherMap
from clients.wyze import WyzeClient

_LOGGER = logging.getLogger(__name__)
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

    def add(self, outlet: str, max_time: int):
        """Adds an outlet to the runtime config, or updates the max time if it already exists"""
        if outlet is None or max_time is None:
            raise TypeError('Both args must be set')
        if int(max_time) < 1:
            raise ValueError('max_time must be greater than 0')
        
        if outlet in self._config:
            self._config[outlet]['max_time'] = max_time
        else:
            self._config[outlet] = {'max_time': max_time, 'start': 0}

    def check(self):
        """Checks all configured outlets against their max runtime"""
        for outlet, times in self._config.items():
            assert times['max_time'] is not None and times['start'] is not None
            outlet_vesync = self.vesync_manager.get_device_by_name(outlet)
            if not outlet_vesync.is_on:
                outlet_vesync.turn_on()
            if outlet_vesync.power <= 2:
                times['start'] = 0
            else:
                if self.is_max_time_exceeded(times):
                    cycle_state(outlet_vesync)
                    times['start'] = 0
                    _LOGGER.info(f'{outlet} run time exceeded')
                elif times['start'] == 0:
                    times['start'] = time.time()
                    _LOGGER.info(f'{outlet} turned on')

    def is_max_time_exceeded(self, times: dict) -> bool:
        return times['start'] > 0 and time.time() - times['start']  > times['max_time']

class AwayAutoOff:
    def __init__(self, time_variance: int, new_day_time, vesync_manager: SmartVeSync) -> None:
        if int(time_variance) < 0:
            raise ValueError('time_variance must be positive')
        self.time_variance = time_variance
        self.new_day_time = datetime.time(hour=int(new_day_time.split(':')[0]), minute=int(new_day_time.split(':')[1]))
        self.vesync_manager = vesync_manager
        self._config = {}

    def _vary_time(self, time: datetime.time) -> time:
        date = datetime.datetime(1970, 1, 1, time.hour, time.minute, time.second, tzinfo=datetime.timezone.utc)
        delta = datetime.timedelta(seconds=randint(-self.time_variance, self.time_variance))
        return (date + delta).time()

    def add(self, lamp: str, off_time: str):
        """Adds a lamp to the away auto off scheduler, or updates the off time if it already exists"""
        if lamp is None or off_time is None:
            raise TypeError('Both args must be set and not None')
        if lamp not in self._config:
            self._config[lamp] = {'off_time': None, 'actual_off_time': None}
        off_time = datetime.time(hour=int(off_time.split(':')[0]), minute=int(off_time.split(':')[1]))
        self._config[lamp]['off_time'] = off_time
        self._config[lamp]['actual_off_time'] = self._vary_time(off_time)
        _LOGGER.info(f"added {lamp} to away auto off, {self._config[lamp]}")

    def check(self) -> None:
        """Checks all configured lamps against their off time, only call in away mode"""
        now = datetime.datetime.now().time()
        for lamp, times in self._config.items():
            outlet_vesync = self.vesync_manager.get_device_by_name(lamp)
            if not outlet_vesync.is_on:
                continue
            assert times['off_time'] is not None and times['actual_off_time'] is not None
            if (times['actual_off_time'] > self.new_day_time and times['actual_off_time'] < now) or \
               (times['actual_off_time'] < now and self.new_day_time > now):
                outlet_vesync.turn_off()
                _LOGGER.info(f'turned off {lamp} as per away auto off schedule')
                times['actual_off_time'] = self._vary_time(times['actual_off_time'])

class Lights:
    def __init__(self, check_ambient_enabled: list, ambient_config: dict, vesync_manager: SmartVeSync, wyze_client: WyzeClient, weather_client: OpenWeatherMap) -> None:
        self.check_ambient_enabled = check_ambient_enabled
        self.ambient_config = ambient_config
        self.vesync_manager = vesync_manager
        self.wyze_client = wyze_client
        self.weather_client = weather_client
        
    def check_sensor(self, sensor: str, lamp: str) -> None:
        sensor_vesync = self.vesync_manager.get_device_by_name(sensor)
        lamp_vesync = self.vesync_manager.get_device_by_name(lamp)
        if is_connected(sensor_vesync) and not lamp_vesync.is_on and self.check_ambient(lamp):
            lamp_vesync.turn_on()
            _LOGGER.info(f'turned on {lamp_vesync.device_name}')

        if not is_connected(sensor_vesync) and lamp_vesync.is_on:
            lamp_vesync.turn_off()
            _LOGGER.info(f'turned off {lamp_vesync.device_name}')
            
    def check_sensor_power(self, sensor: str, lamp: str):
        sensor_vesync = self.vesync_manager.get_device_by_name(sensor)
        lamp_vesync = self.vesync_manager.get_device_by_name(lamp)
        if not lamp_vesync.is_on:
            lamp_vesync.turn_on()
        if not is_connected(sensor_vesync) and lamp_vesync.power > 2:
            cycle_state(lamp_vesync)
            _LOGGER.info(f'turned off {lamp_vesync.device_name}')

    def check_sensor_wyze(self, sensor: str, bulb: str):
        sensor_vesync = self.vesync_manager.get_device_by_name(sensor)
        bulb_wyze = self.wyze_client.get_device_by_nickname(bulb)
        if is_connected(sensor_vesync) and not self.wyze_client.is_on(bulb_wyze):
            self.configure_wyze_bulb(bulb_wyze)
            _LOGGER.info(f'turned on {bulb_wyze.nickname}')

        if not is_connected(sensor_vesync) and self.wyze_client.is_on(bulb_wyze):
            self.wyze_client.set_brightness(bulb_wyze, MIN_BRIGHTNESS)
            self.wyze_client.turn_off(bulb_wyze)
            _LOGGER.info(f'turned off {bulb_wyze.nickname}')

    def check_ambient(self, lamp: str) -> bool:
        if lamp not in self.check_ambient_enabled:
            return True
        if self.weather_client.is_cloudy:
            _LOGGER.debug(f"it is cloudy ({self.weather_client.weather_description} with cloud coverage {self.weather_client.cloud_coverage}%), {lamp} not turing on")
            return False
        if not self.weather_client.is_sun_up:
            _LOGGER.debug(f"it is dark, {lamp} not turing on")
            return False
        return True   

    def configure_wyze_bulb(self, bulb: Device):
        if bulb.nickname not in self.check_ambient_enabled:
            self.wyze_client.turn_on(bulb)
            return

        #fixed shedule based config
        if self.is_bed_time():
            _LOGGER.info('configuring bulb for feeding time...')
            self.wyze_client.set_color(bulb, 'FF2000')
            self.wyze_client.set_brightness(bulb, 75)
            return

        #config based on ambient conditions
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
    
    def is_bed_time(self) -> bool:
        """Check if it's bed time
           TODO load start/stop time from yaml"""

        start = datetime.time(hour=19, minute=00)
        stop = datetime.time(hour=21, minute=30)
        now = datetime.datetime.now().time()

        return start < now and stop > now

def is_connected(device: VeSyncBaseDevice) -> bool:
    """Return true if VeSync device is connected."""
    if device.connection_status == 'online':
        return True
    return False

def cycle_state(outlet: VeSyncOutlet) -> None:
    outlet.turn_off()
    time.sleep(2)
    outlet.turn_on()
    
#def get_device_name(device) -> str:
    #if isinstance(device, Enum):
        #return device.value
    #if isinstance(device, VeSyncBaseDevice):
        #return device.device_name
    #if isinstance(device, str):
        #return device
    #raise TypeError(f'Type {type(device)} is unsupported')

def main(config: dict, wyze_client: WyzeClient, location: Location):
    lights_config = config['lights']
    HOME_UPDATE_FREQUENCY = lights_config['update_frequency']['home']
    AWAY_UPDATE_FREQUENCY = lights_config['update_frequency']['away']
    

    #figure out which vesync devices require details
    update_details = []
    for _, val in lights_config['method_device_mapping']['vesync-vesync_power'].items():
        update_details.append(val)
    if config['runtime'] is not None:
        for key, _ in config['runtime'].items():
            update_details.append(key)

    vesync = config['vesync']
    vesync_manager = SmartVeSync(vesync['username'], vesync['password'], vesync['time_zone'], update_details)
    vesync_manager.update_interval = HOME_UPDATE_FREQUENCY
    vesync_manager.login()
    vesync_manager.update()
    _LOGGER.info('VeSync devices updated')
    weather = config['open_weather_map']
    weather_client = OpenWeatherMap(weather['api_key'], weather['lattitude'], weather['longitude'])
    lights = Lights(lights_config['check_ambient_enabled'], lights_config['ambient'], vesync_manager, wyze_client, weather_client)
    runtime = Runtime(vesync_manager)

    if config['runtime'] is not None:
        for key, val in config['runtime'].items():
            runtime.add(key, val)

    away_config = lights_config['away_auto_off']
    away_auto_off = AwayAutoOff(away_config['time_variance'], away_config['new_day_time'], vesync_manager)
    for key, val in away_config['devices'].items():
            away_auto_off.add(key, val)

    while True:
        try:
            #lights.check_sensor(Devices.OFFICE_SENSOR, Devices.OFFICE_LAMP)
            for sensor, light in lights_config['method_device_mapping']['vesync-vesync_state'].items():
                lights.check_sensor(sensor, light)

            #lights.check_sensor_power(Devices.NURSERY_SENSOR, Devices.NURSERY_FEEDING_LAMP)
            for sensor, light in lights_config['method_device_mapping']['vesync-vesync_power'].items():
                lights.check_sensor_power(sensor, light)

            #lights.check_sensor_wyze(Devices.NURSERY_SENSOR, Devices.NURSERY_BULB)
            for sensor, light in lights_config['method_device_mapping']['vesync-wyze_state'].items():
                lights.check_sensor_wyze(sensor, light)

            runtime.check()
            if not location.is_anyone_home(cached=True) and not location.is_anyone_home():
                away_auto_off.check()
        except KeyError as key_error:
            _LOGGER.error(f'KeyError, device missing for key "{key_error.args[0]}"')
        except requests.exceptions.ConnectionError as conn_error:
            _LOGGER.error(f'Connection Error, retrying after a delay', exc_info=conn_error)
            time.sleep(AWAY_UPDATE_FREQUENCY)
        except JSONDecodeError as json_error:
            _LOGGER.error(f'JSON Decode Error, retrying after a delay', exc_info=json_error)
            time.sleep(AWAY_UPDATE_FREQUENCY)
        except UnknownApiError as unknown_api_error:
            _LOGGER.error(f'Unknown Wyze API Error, retrying after a delay', exc_info=unknown_api_error)
            time.sleep(AWAY_UPDATE_FREQUENCY)


        time.sleep(HOME_UPDATE_FREQUENCY if location.is_anyone_home(cached=True) else AWAY_UPDATE_FREQUENCY)
