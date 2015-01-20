import os
import sys
import logging
from dockerup.proc import read_command

class Docker(object):

	def __init__(self):

		self.image_cache = []
		self.container_cache = []

		self.log = logging.getLogger(__name__)

	def flush_images(self):
		self.image_cache = []

	def flush_containers(self):
		self.container_cache = []

	def flush(self):
		self.flush_images()
		self.flush_containers()

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

		try:
			self.log.debug('Pulling image: %s', image)
			for line in read_command(['docker', 'pull', image]).split('\n'):
				if line.startswith('Status: Downloaded newer image'):
					self.log.debug('Updated image found')
					self.flush_images()
					return True
			self.log.debug('Image is up to date')
		except:
			self.log.debug('Pull failed')
			# Missing image probably, just return false
			pass

		return False

	# Run a new container
	def run(self, image, options=None):

		args = ['docker', 'run', '-d', '--restart=always']

		if options is not None:
			args.extend(options)

		args.append(image)

		self.log.debug('Running container: %s' % image)

		container = read_command(args).strip()

		self.log.info('Started container: %s' % container)

		self.flush_containers()

		return container

	# Start existing container
	def start(self, container):

		self.log.debug('Starting container: %s', container)
		out = read_command(['docker', 'start', container])

		self.flush_containers()

	# Stop running container
	def stop(self, container, remove=True):

		self.log.debug('Stopping container: %s', container)
		out = read_command(['docker', 'stop', container])

		if remove:
			self.rm(container)

		self.flush_containers()

	# Remove container
	def rm(self, container):

		self.log.debug('Removing stopped container: %s' % container)
		out = read_command(['docker', 'rm', container])

		self.flush_containers()

	# Remove image
	def rmi(self, image):

		self.log.debug('Removing image: %s' % image)
		out = read_command(['docker', 'rmi', image])

		self.flush_images()

	# Cleanup stopped containers and unused images
	def cleanup(self, images=True):

		# Always refresh state before cleanup
		self.flush()

		for container in self.containers():
			if not container['running']:
				self.rm(container['id'])
		
		out = read_command(['docker', 'images', '-f', 'dangling=true', '-q', '--no-trunc']).strip()
		if len(out):
			dangling = out.split('\n')
			self.log.debug('Dangling images: %s' % dangling)
			if len(dangling):
				for dangling in out.split('\n'):
					self.rmi(dangling)

	"""
	Private methods
	"""

	def __load_images(self):

		out = read_command(['docker', 'images', '--no-trunc'], True, '<none>')

		images = []

		return [{
				'id': line['IMAGE ID'],
				'repository': line['REPOSITORY'],
				'tag': line['TAG']
			} for line in out]

	def __load_containers(self):

		out = read_command(['docker', 'ps', '-a', '--no-trunc'], True)

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
