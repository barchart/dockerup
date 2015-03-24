#!/usr/bin/python2.7

import os
import sys
import shutil
import json
import logging
import time
import traceback
import signal

from dockerup import conf
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
        self.containers = []
        self.cache = cache
        self.docker = DockerPyClient(config['remote'], config['username'], config['password'], config['email'])

        self.log = logging.getLogger(__name__)

    def pull_allowed(self, entry):

        if 'pull' in self.config and not self.config['pull']:
            return False

        if not 'update' in entry or not 'pull' in entry['update'] or entry['update']['pull']:
            return True

        return False

    def update(self, entry):

        if not 'image' in entry:
            self.log.warn('No image defined for container, skipping')
            return

        current = self.status(entry)
        updated = self.updated(entry)

        if current['Image'] is None or self.pull_allowed(entry):
            updated = self.docker.pull(entry['image']) or updated

        if updated or not current['Running']:

            if 'links' in entry:
                # Has dependency on another container, let's give Docker time to bring
                # bring previous container up fully before attempting to launch
                time.sleep(5)

            if current['Running']:
                return self.update_next_window(entry, current)
            else:
                return self.update_launch()(entry)

        return current

    def update_next_window(self, entry, status):

        if 'update' in entry and 'rolling' in entry['update'] and entry['update']['rolling']:
            # TODO use central coordinator service to wait for available update window
            log.warn('Rolling updates not yet supported')

        return self.update_replace(entry, status)

    # Eager update: start new container first (primarily to facilitate self-upgrade
    # of the dockerup management container itself)
    def is_eager(self, entry):

        if 'update' in entry and 'eager' in entry['update'] and entry['update']['eager']:

            if 'name' in entry:
                log.warn('Skipping eager update due to container name conflict')
                return False

            if 'portMappings' in entry:
                for mapping in entry['portMappings']:
                    if 'hostPort' in mapping:
                        log.warn('Skipping eager update due to host port conflict')
                        return False

            return True

        return False

    def update_replace(self, entry, status):

        if self.is_eager(entry):
            return self.update_launch(self.update_stop(status))(entry)
    
        return self.update_stop(status, self.update_launch())(entry)

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
                    # Stop all dependencies, they will get updated/restarted
                    self.stop_dependencies(entry)
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
        
        updated = False

        cachefile = '%s/%s.json' % (self.cache, self.__cache_name(entry))

        if os.path.exists(cachefile):
            with open(cachefile) as local:
                if json.dumps(entry) != local.read():
                    updated = True
        else:
            updated = True

        if updated:
            with open(cachefile, 'w') as local:
                json.dump(entry, local)

        return updated

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

    # Shutdown containers with unrecognized images to avoid resource conflicts
    def shutdown_unknown(self, entries=None):

        existing = []
        catalog = []

        def cached_entry(cached):
            cachefile = '%s/%s' % (self.cache, cached)
            with open(cachefile) as local:
                return json.load(local)

        if entries:
            catalog.extend(entries)

        catalog.extend([cached_entry(cf) for cf in os.listdir(self.cache) if cf.endswith('.json')])

        for entry in catalog:
            status = self.status(entry)
            if status['Id']:
                existing.append(status['Id'])

        self.log.debug('Cleaning up orphaned containers')

        # Iterate through running containers and stop them if they don't match a cached config
        [self.docker.stop(c['Id']) for c in self.docker.containers() if c['Running'] and not c['Id'] in existing]

        # Remove old log files from last run shutdown (gives logstash some time to process final messages)
        ids = [c['Id'] for c in self.docker.containers() if c['Running']]
        if os.path.exists('/var/log/ext'):
            for entry in os.listdir('/var/log/ext'):
                if os.path.isdir('/var/log/ext/%s' % entry) and entry not in ids:
                    self.log.info('Removing old logs for %s' % entry)
                    shutil.rmtree('/var/log/ext/%s' % entry)

    # Shutdown leftover containers from old configurations
    def cleanup(self, valid):

        self.log.debug('Cleaning up missing configurations')

        for entry in os.listdir(self.cache):

            if not entry.endswith('.json'):
                continue

            cachefile = '%s/%s' % (self.cache, entry)

            with open(cachefile) as local:
                cached = json.load(local)

            status = self.status(cached)

            if status['Id'] and not status['Id'] in valid:
                os.unlink(cachefile)
                self.stop(status)

    def update_config(self):

        config = {}
        containers = []

        def merge(cfg):
            if 'containers' in cfg:
                containers.extend(cfg['containers'])
                del cfg['containers']
            config.update(cfg)

        if 'confdir' in self.config:
            merge(conf.files_config(self.config['confdir']))

        if 'aws' in self.config and self.config['aws']:
            merge(conf.aws_config())

        self.containers = DependencyResolver(containers).resolve()
        self.config.update(config)

    def stop_dependencies(self, entry):
        if 'name' in entry:
            for container in DependencyResolver(self.containers).downstream(entry['name']):
		self.log.info(container)
                status = self.status(container)
                if status['Id']:
                    self.log.info('Dependent container %s will be restarted to maintain link consistency' % status['Id'])
                    self.stop(status)

    # Run a single sync cycle
    def sync(self):

        # Update container config
        self.update_config()

        # Rare occurence, kill containers that have an unknown image tag
        # Usually due to manual updates, may be required to avoid port binding conflicts
        self.shutdown_unknown(self.containers)

        # Process configuration and store running container IDs
        running = [self.update(container)['Id'] for container in self.containers]

        # Cleanup containers with no config
        self.cleanup(running)

        # Remove unused containers/images from Docker
        self.docker.cleanup()

    def start(self):

        if 'server' in self.config and self.config['server']:

            signal.signal(signal.SIGTERM, self.handle_signal)

            # TODO connect to control queue (SQS?) for update broadcasts
            while True:

                try:

                    try:
                        self.sync()
                    except Exception as e:
                        self.log.error('Error in sync loop: %s' % e.message)
                        self.log.debug(traceback.format_exc())

                    # Separate sleep from sync loop to prevent logspam
                    time.sleep(self.config['interval'])

                except Exception as e:
                    # Sleep interrupted, just go to next loop
                    pass

        else:
            self.sync()

    def handle_signal(self, signo, stack):
        self.log.info('Received signal %s, shutting down' % signo)
        sys.exit(1)

    def shutdown(self):
        self.log.info('Shutting down')
        sys.exit(0)

class DependencyResolver(object):

    def __init__(self, containers):

        self.containers = containers

        self.root = DependencyNode()
        self.named = {}

        nodes = []

        # Create nodes and map to names if available
        for container in self.containers:
            node = DependencyNode(container)
            nodes.append(node)
            if 'name' in container:
                self.named[container['name']] = node

        # Register dependencies on each node
        for node in nodes:

            # Root depends on everything
            self.root.depend(node)

            # Linked containers
            if 'links' in node.container:
                for link in node.container['links'].keys():
                    if link in self.named:
                        node.depend(self.named[link])

            # Data volume containers
            if 'volumes' in node.container:
                for vol in node.container['volumes']:
                    if 'from' in vol and vol['from'] in self.named:
                        node.depend(self.named[vol['from']])

            # Network stack sharing containers
            if 'network' in node.container:
                if node.container['network'].startswith('container:'):
                    target = node.container['network'].split(':')[1];
                    if target in self.named:
                        node.depend(self.named[target])

    # Return dependency-sorted list
    def resolve(self):
        return [r.container for r in self.walk(self.root, [], [])]

    # Return a list of containers that depend on a named container (directly or indirectly)
    def downstream(self, name):
        deps = []
        if name in self.named:
            node = self.named[name]
            for d in self.root.deps:
                if node in d.deps:
                    if 'name' in d.container:
                        deps.extend(self.downstream(d.container['name']))
                    deps.append(d.container)
        return deps

    def walk(self, node, resolved, seen):

        seen.append(node)

        for dep in node.deps:
            if dep not in resolved:
                if dep in seen:
                    raise Exception('Circular dependency reference detected: %s -> %s'
                        % (node.container['image'], dep.container['image']))
                self.walk(dep, resolved, seen)

        # Skip root node
        if node.container:
            resolved.append(node)

        return resolved

class DependencyNode(object):

    def __init__(self, container=None):
        self.container = container
        self.deps = []

    def depend(self, node):
        self.deps.append(node)
