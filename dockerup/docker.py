import subprocess
import os
import sys
import re
import threading
import logging


class Docker(object):

	def __init__(self):

		self.image_cache = []
		self.container_cache = []

		self.log = logging.getLogger(__name__)

	def refresh(self):
		self.image_cache = self.__load_images()
		self.container_cache = self.__load_containers()

	def image(self, repository=None, tag=None, id=None):

		for image in self.images():

			if repository and repository != image['repository']:
				continue

			if tag and tag != image['tag']:
				continue

			if id and id != image['id']:
				continue

			return image

		return None

	def images(self):

		if not len(self.image_cache):
			self.image_cache = self.__load_images()

		return self.image_cache

	def container(self, image=None):

		for container in self.containers():
			if image is None or image == container['image']:
				return container

		return None

	def containers(self):

		if not len(self.container_cache):
			self.container_cache = self.__load_containers()

		return self.container_cache

	def pull(self, image):

		self.log.debug('Pulling image: %s', image)
		for line in self.__read_command(['docker', 'pull', image]):
			if line.startswith('Status: Downloaded newer image'):
				return True

		return False

	# Run a new container
	def run(self, image, options=None):

		args = ['docker', 'run', '-d', '--restart=always']

		if options is not None:
			args.extend(options)

		args.append(image)

		self.log.debug('Running container: %s' % image)

		container = self.__read_command(args).strip()

		self.log.info('Started container: %s' % container)

		return container

	# Start existing container
	def start(self, container):
		self.log.debug('Starting container: %s', container)
		out = self.__read_command(['docker', 'start', container])

	# Stop running container
	def stop(self, container, remove=True):

		self.log.debug('Stopping container: %s', container)
		out = self.__read_command(['docker', 'stop', container])

		if remove:
			self.rm(container)

	# Remove container
	def rm(self, container):

		self.log.debug('Removing stopped container: %s' % container)
		out = self.__read_command(['docker', 'rm', container])

	# Remove image
	def rmi(self, image):

		self.log.debug('Removing image: %s' % image)
		out = self.__read_command(['docker', 'rmi', image])

	# Cleanup stopped containers and unused images
	def cleanup(self, images=True):

		# Always refresh state before cleanup
		self.refresh()

		running = []

		for container in self.containers():
			if container['running']:
				running.append(container['image'])
			else:
				self.rm(container['id'])
		
		if images:
			for image in self.images():
				if not image['id'] in running:
					self.rmi(image['id'])

	"""
	Private methods
	"""

	def __load_images(self):

		out = self.__read_command(['docker', 'images', '--no-trunc'], True, '<none>')

		images = []

		return [{
				'id': line['IMAGE ID'],
				'repository': line['REPOSITORY'],
				'tag': line['TAG']
			} for line in out]

	def __load_containers(self):

		out = self.__read_command(['docker', 'ps', '-a', '--no-trunc'], True)

		containers = []
		images = self.images()

		for line in out:

			image_id = line['IMAGE']

			if ':' in line['IMAGE']:
				parts = line['IMAGE'].split(':')
				match = self.image(parts[0], parts[1])
				image_id = match['id'] if match else None

			containers.append({
				'id': line['CONTAINER ID'],
				'image': image_id,
				'running': line['STATUS'].startswith('Up ')
			})
		
		return containers

	def __read_command(self, command, as_dict=False, nul_value=None, timeout=0):

		proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
		
		if timeout > 0:
			threading.Timer(timeout, self.__kill_process, (proc,)).start()

		contents = proc.stdout.read()

		if proc.wait() != 0:
			self.log.debug('Command failed: %s\nSTDOUT:\n%s\nSTDERR:\n%s' % (' '.join(command), contents.strip(), proc.stderr.read().strip()))
			raise Exception('Command failed: %s' % ' '.join(command))

		if as_dict:

			lines = re.split('\s*\n', contents)
			labels = self.__split_fields(lines[0])

			rows = []

			for line in lines[1:]:
				if line:
					rows.append(dict(zip(labels, self.__split_fields(line, nul_value))))

			return rows

		return contents

	def __kill_process(self, proc):

		if proc.poll() is None:
			self.log.error( 'Error: process taking too long to complete - terminating')
			proc.kill()

	def __split_fields(self, line, nul_value=None):

		fields = re.split('\s\s+', line)

		if nul_value:
			for i in range(0, len(fields)):
				if fields[i] == nul_value:
					fields[i] = None

		return fields

