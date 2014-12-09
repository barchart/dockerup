#!/usr/bin/python2.7

import json
import os
import shutil
import logging
import dockerup.docker

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
		self.docker = docker.Docker()

		self.log = logging.getLogger(__name__)

	def update(self, container):

		if not 'image' in container:
			self.log.warn('No image defined for container, skipping')
			return

		updated = self.docker.pull(container['image']) or self.updated(container)
		status = self.status(container)

		if updated or not status['running']:

			if status['running']:
				self.stop(status)

			if status['image']:
				try:
					self.run(container, status)
				except Exception as e:
					self.log.error('Could not run container: %s' % e)
			else:
				self.log.error('Image not found: %s' % container['image'])

		return status

	def status(self, container):

		image_parts = container['image'].split(':')
		repository = image_parts[0]
		tag = 'latest' if len(image_parts) == 1 else image_parts[1]

		image = self.docker.image(repository, tag)
		container = self.docker.container(image['id']) if image else None

		return {
			'repository': repository,
			'tag': tag,
			'image': image['id'] if image else None,
			'container': container['id'] if container else None,
			'running': container['running'] if container else False
		}

	def updated(self, container):
		
		cachefile = '%s/%s.json' % (self.cache, self.__cache_name(container))

		if not os.path.exists(cachefile):
			return True

		serialized = json.dumps(container)

		with open(cachefile) as local:
			cached = local.read()

		if serialized != cached:
			return True

		return False

	def cache_config(self):
		
		if 'containers' in self.config:

			for container in self.config['containers']:

				cachefile = '%s/%s.json' % (self.cache, self.__cache_name(container))

				with open(cachefile, 'w') as local:
					json.dump(container, local)

	def __cache_name(self, container):
		return '%s-%s' % (container['image'].replace(':', '_').replace('/', '_'), container['name'])

	def run(self, config, status):

		if 'type' in config and config['type'] != 'docker':
			return False

		# Set up exported logging directory for apps
		args = ['-v', '/var/log/ext/%s:/var/log/ext' % status['image']]

		if 'volumes' in config:

			for vol in config['volumes']:

				if not 'containerPath' in vol:
					self.log.warn('No container mount point specified, skipping volume')
					continue

				volargs = []
				if 'hostPath' in vol:
					volargs.append(vol['hostPath'])
				volargs.append(vol['containerPath'])
				if 'mode' in vol:
					volargs.append(vol['mode'].lower())

				args.append('-v')
				args.append(':'.join(volargs))

		if 'name' in config:
			if config['name'].startswith('local-'):
				self.log.error('Invalid container name, local-* is reserved')
				return False
			args.append('--name=%s' % config['name'])

		if 'privileged' in config and config['privileged']:
			args.append('--privileged')

		if 'network' in config:
			args.append('--net=%s' % config['network'].lower())

		if 'portMappings' in config:
			for port in config['portMappings']:
				args.append('-p')
				if 'hostPort' in port:
					args.append('%s:%s' % (port['hostPort'], port['containerPort']))
				else:
					args.append(port['containerPort'])

		if 'env' in config:
			for key, value in config['env'].iteritems():
				args.append('-e')
				args.append('%s=%s' % (key, value))

		return self.docker.run(config['image'], args)

	def stop(self, status, remove=True):

		self.docker.stop(status['container'], remove)

		if remove:
			try:
				# Remove logs directory
				shutil.rmtree('/var/log/ext/%s' % status['image'])
			except Exception as e:
				self.log.warn('Could not remove logs: %s' % e)

	# Shutdown old containers
	def cleanup(self, running):

		for entry in os.listdir(self.cache):

			if not entry.endswith('.json'):
				continue

			cachefile = '%s/%s' % (self.cache, entry)

			with open(cachefile) as local:
				cached = json.load(local)

			status = self.status(cached)

			if status['container'] and not status['container'] in running:
				self.stop(status)

			os.unlink(cachefile)

	def start(self):

		# Process configuration and store running container IDs
		running = []
		if 'containers' in self.config:
			running = [self.update(container)['container'] for container in self.config['containers']]

		# Cleanup containers with no config
		self.cleanup(running)

		# Cache config for next run
		self.cache_config()

		# Remove unused containers/images from Docker
		self.docker.cleanup()
