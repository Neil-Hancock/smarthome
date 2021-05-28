import time
import logging
import requests

_LOGGER = logging.getLogger(__name__)

class OpenWeatherMap():

    CLOUDY_THRESHOLD = 75
    CLOUDY_DESCRIPTIONS = ['rain']
    SUNNY_DESCRIPTIONS = []
    MIN_UPDATE_INTERVAL = 10 * 60

    def __init__(self, api_key, lat, lon):
        self._API_KEY = api_key
        self._LAT = lat
        self._LON = lon
        self.update_interval = OpenWeatherMap.MIN_UPDATE_INTERVAL
        self.weather_data = None
        self._update_weather_data()


    def _update_weather_data(self):
        if not self._time_check():
            return
        try:
            payload = {'lat': self._LAT, 'lon': self._LON, 'units': 'imperial', 'appid': self._API_KEY}
            response = requests.get('https://api.openweathermap.org/data/2.5/weather', params=payload)
        except requests.exceptions.RequestException as e:
            _LOGGER.warning(e)
        else:
            if response.status_code == requests.codes.ok and response.json() is not None:
                self.weather_data = response.json()
                _LOGGER.info('Weather data updated')
            else:
                _LOGGER.warning(f'Unable to fetch weather data, status_code = {response.status_code}')

    def _time_check(self) -> bool:
        """Test if update interval has been exceeded."""
        if self.weather_data is None or (
                time.time() > (self.weather_data['dt'] + self.update_interval)):
            return True
        return False

    @property
    def is_cloudy(self) -> bool:
        self._update_weather_data()
        for sunny in OpenWeatherMap.SUNNY_DESCRIPTIONS:
            if sunny in self.weather_description:
                return False
        for cloudy in OpenWeatherMap.CLOUDY_DESCRIPTIONS:
            if cloudy in self.weather_description:
                return True        
        return self.cloud_coverage > OpenWeatherMap.CLOUDY_THRESHOLD

    @property
    def weather_description(self) -> str:
        self._update_weather_data()
        return self.weather_data['weather'][0]['description'].lower()

    @property
    def cloud_coverage(self) -> int:
        self._update_weather_data()
        return self.weather_data['clouds']['all']

    @property
    def is_sun_up(self) -> bool:
        return self.is_sun_in_range()

    def is_sun_in_range(self, rise_offset=0, set_offset=0) -> bool:
        """With no params this method checks if the sun is up. Optional offsets can be provided to check a custom range.
        Offset values are in seconds."""
        self._update_weather_data()
        if time.time() > self.weather_data['sys']['sunrise'] - rise_offset \
            and time.time() < self.weather_data['sys']['sunset'] + set_offset:
                return True

        return False
