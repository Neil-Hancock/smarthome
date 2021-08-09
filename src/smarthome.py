import datetime
import re
import threading
from os import path
import logging
from typing import Any
logging.basicConfig(
        level = logging.INFO,
        format = '%(asctime)s - %(levelname)5s - %(name)s: %(message)s'
    )

from ruamel.yaml import YAML

import cameras, lights
from clients.location import Location
from clients.wyze import WyzeClient

_LOGGER = logging.getLogger(__name__)

def eval_numeric(val) -> Any:
    if isinstance(val, int):
        return val

    if re.search(r'[^0-9*\s-]', val) == None:
        return eval(val)
    
    return val

def check_numeric(config) -> dict:
    """Calls eval on select numeric values"""
    cams = config['cameras']
    cams['update_frequency'] = eval_numeric(cams['update_frequency'])
    
    l_up = config['lights']['update_frequency']
    l_up['home'] = eval_numeric(l_up['home'])
    l_up['away'] = eval_numeric(l_up['away'])

    amb = config['lights']['ambient']
    amb['daytime']['rise_offset'] = eval_numeric(amb['daytime']['rise_offset'])
    amb['daytime']['set_offset'] = eval_numeric(amb['daytime']['set_offset'])
    amb['dawn']['rise_offset'] = eval_numeric(amb['dawn']['rise_offset'])
    amb['dusk']['set_offset'] = eval_numeric(amb['dusk']['set_offset'])
    
    for k, v in config['runtime'].items():
        config['runtime'][k] = eval_numeric(v)

def load_config() -> dict:
    yaml = YAML(typ='safe')

    config = None
    with open(path.dirname(__file__) + '/config.yaml') as file:
        config = yaml.load(file)
    check_numeric(config)
    return config

def main():
    _LOGGER.info('Starting smarthome...')
    config = load_config()
    wyze = config['wyze']
    wyze_client = WyzeClient(wyze['username'], wyze['password'])
    _LOGGER.info('Wyze devices updated')

    loc = config['location']
    location = Location(config['pushbullet']['api_key'], loc['retry_count'], loc['ip_range'], loc['phone_macs'])

    _LOGGER.info('Starting lights thread...')
    threading.Thread(target=lights.main, args=(config, wyze_client, location,)).start()

    _LOGGER.info('Starting cameras thread...')
    threading.Thread(target=cameras.main, args=(config, wyze_client, location,)).start()

    _LOGGER.info('Both threads started')

if __name__ == "__main__":
   main()