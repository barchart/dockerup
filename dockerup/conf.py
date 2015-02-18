import os
import json
import logging
from dockerup.proc import read_command

def settings(args):

    settings = {
        'confdir': '/etc/dockerup/containers.d',
        'remote': 'unix://var/run/docker.sock',
        'interval': 60,
        'aws': False,
        'pull': True,
        'username': None,
        'password': None,
        'email': None
    }

    if os.path.exists(args.config):
        settings.update(properties(args.config))

    if args.confdir:
        settings['confdir'] = args.confdir

    if args.aws is not None:
        settings['aws'] = args.aws

    if args.pull is not None:
        settings['pull'] = args.pull

    if args.server is not None:
        settings['server'] = args.server

    return settings

def properties(filename):

    config = {}

    with open(filename, 'r') as f:

        for line in f:
            if line[:1] == '#':
                continue
            (key, value) = line.split('=')
            value = value.strip()
            if value.lower() in ['true', 'yes', '1']:
                value = True
            elif value.lower() in ['false', 'no', '0']:
                value = False
            config[key.strip()] = value

    return config


def files_config(directory):

    if not os.path.exists(directory):
        raise Exception('Configuration directory not found: %s' % directory)

    logging.debug('Loading configuration from %s' % directory)

    containers = []
    for entry in os.listdir(directory):
        if entry.endswith('.json'):
            with open('%s/%s' % (directory, entry)) as local:
                containers.append(json.load(local))

    return { 'containers': containers }

def aws_config():

    try:
        logging.debug('Loading configuration from EC2 user-data')
        return json.loads(read_command(['ec2metadata', '--user-data'], timeout=5.0))
    except Exception as e:
        return {}
