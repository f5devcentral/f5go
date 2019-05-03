import configparser
import os
import logging


def get_config(path='go.cfg'):

    if not os.path.exists(path):
        logging.error('configuration path does not exist')
        return {}

    config = configparser.ConfigParser()
    config.read(path)
    if 'goconfig' in config:
        return config['goconfig']

    raise RuntimeError('goconfig section not found in configuration file')
