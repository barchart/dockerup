#!/usr/bin/python2.7

import os
import sys
import shutil
import json
import logging
import time

from dockerup.dockerpy import DockerPyClient

class DockerUp(object):

    """
    Service for synchronizing locally running Docker containers with an external
    configuration file. If available, EC2 user-data is used as the configuration file,
    otherwise dockerup looks in /etc/dockerup/dockerup.json by default (override with --config).

    This script can be run on-demand or via a cron job.

    Sample config file is shown below:

    {
        "containers": [
            {
                "type": "docker",
                "name": "historical-app",
                "image": "barchart/historical-app-alpha",
                "portMappings": [ 
                    {
                        "containerPort": "8080",
                        "hostPort": "8080"
                    }
                ]
            },
            {
                "type": "docker",
                "name": "logstash-forwarder",
                "image": "barchart/logstash-forwarder",
                "volumes": [
                    {
                        "containerPath": "/var/log/containers",
                        "hostPath": "/var/log/ext",
                        "mode": "ro"
                    }
                ]
            }
        ]
    }
    """

    def __init__(self, config, cache):

        self.config = config
        self.cache = cache
        self.docker = DockerPyClient(config['remote'], config['username'], config['password'], config['email'])

        self.log = logging.getLogger(__name__)

    def update(self, entry):

        if not 'image' in entry:
            self.log.warn('No image defined for container, skipping')
            return

        current = self.status(entry)
        updated = self.updated(entry)

        if current['Image'] is None or not 'pull' in self.config or self.config['pull']:
            updated = self.docker.pull(entry['image']) or updated

        if updated or not current['Running']:

            if current['Running']:
                return self.update_next_window(entry, current)
            else:
                return self.update_launch()(entry)

        return current

    def update_next_window(self, entry, status):
        if not 'rolling' in self.config:
            return self.update_replace(entry, status)
        else:
            # TODO use central coordinator service to wait for available update window
            return status

    def update_replace(self, entry, status):
        if 'name' in entry or 'portMappings' in entry:
            # If container specifies a name or port mappings, it should be stopped first
            # to avoid resource conflicts
            return self.update_stop(status, self.update_launch())(entry)
        else:
            # Else, start new container first (primarily to facilitate self-upgrade of
            # the dockerup management container itself)
            return self.update_launch(self.update_stop(status))(entry)

    def update_stop(self, status, callback=None):

        def actual(entry):

            self.log.debug('Stopping old container: %s' % status['Id'])
            self.stop(status)

            if callback:
                return callback(entry)

            return status

        return actual

    def update_launch(self, callback=None):

        def actual(entry):

            status = self.status(entry)

            if status['Image']:
                try:
                    self.log.debug('Starting new container')
                    self.run(entry)
                    status = self.status(entry)
                except Exception as e:
                    self.log.error('Could not run container: %s' % e)
            else:
                self.log.error('Image not found: %s' % entry['image'])

            if callback:
                callback(entry)

            return status
        
        return actual

    def status(self, entry):

        image = self.docker.image(entry['image'])
        container = self.docker.container(image['Id']) if image else None

        return {
            'Id': container['Id'] if container else None,
            'Tag': container['Image'] if container else None,
            'Image': image['Id'] if image else None,
            'Running': container['Running'] if container else False
        }

    def updated(self, entry):
        
        cachefile = '%s/%s.json' % (self.cache, self.__cache_name(entry))

        if not os.path.exists(cachefile):
            return True

        serialized = json.dumps(entry)

        with open(cachefile) as local:
            cached = local.read()

        if serialized != cached:
            return True

        return False

    def cache_config(self):
        
        if 'containers' in self.config:

            for entry in self.config['containers']:

                cachefile = '%s/%s.json' % (self.cache, self.__cache_name(entry))

                with open(cachefile, 'w') as local:
                    json.dump(entry, local)

    def __cache_name(self, entry):

        image_clean = entry['image'].replace(':', '_').replace('/', '_')

        if 'name' in entry:
            return '%s-%s' % (image_clean, entry['name'])

        return image_clean

    def run(self, config):

        if 'type' in config and config['type'] != 'docker':
            return False

        return self.docker.run(config)

    def stop(self, status, remove=True):

        self.docker.stop(status['Id'], remove)

        if remove:
            try:
                # Remove logs directory
                shutil.rmtree('/var/log/ext/%s' % status['Id'])
            except Exception as e:
                self.log.warn('Could not remove logs: %s' % e)

    # Shutdown containers with unrecognized images
    def shutdown_unknown(self, entries=None):

        existing = []

        # Match new configs
        if entries:
            
            for entry in entries:

                status = self.status(entry)
                
                if status['Id']:
                    existing.append(status['Id'])

        # Match old configs
        for entry in os.listdir(self.cache):

            if not entry.endswith('.json'):
                continue

            cachefile = '%s/%s' % (self.cache, entry)

            with open(cachefile) as local:
                cached = json.load(local)

            status = self.status(cached)
            
            if status['Id']:
                existing.append(status['Id'])

        self.log.debug('Cleaning up orphaned containers')

        # Iterate through running containers and stop them if they don't match a cached config
        [self.docker.stop(c['Id']) for c in self.docker.containers() if c['Running'] and not c['Id'] in existing]

    # Shutdown leftover containers from old configurations
    def cleanup(self, running):

        self.log.debug('Cleaning up missing configurations')

        for entry in os.listdir(self.cache):

            if not entry.endswith('.json'):
                continue

            cachefile = '%s/%s' % (self.cache, entry)

            with open(cachefile) as local:
                cached = json.load(local)

            status = self.status(cached)

            if status['Id'] and not status['Id'] in running:
                self.stop(status)

            os.unlink(cachefile)

    # Run a single sync cycle
    def sync(self):

        # Rare occurence, kill containers that have an unknown image tag
        # Usually due to manual updates, may be required to avoid port binding conflicts
        self.shutdown_unknown(self.config['containers'])

        # Process configuration and store running container IDs
        running = []
        if 'containers' in self.config:
            running = [self.update(container)['Id'] for container in self.config['containers']]

        # Cleanup containers with no config
        self.cleanup(running)

        # Cache config for next run
        self.cache_config()

        # Remove unused containers/images from Docker
        self.docker.cleanup()

    def start(self):
        if 'server' in self.config and self.config['server']:
            # TODO connect to control queue (SQS?) for update broadcasts
            while True:
                try:
                    self.sync()
                    time.sleep(self.config['interval'])
                except Exception as e:
                    self.log.error('Error in sync loop: %s' + e.message)
                    pass
        else:
            self.sync()
