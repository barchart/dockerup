import os
import json
import logging
from dockerup.proc import read_command

def settings(args):

	settings = properties(args.config) if os.path.exists(args.config) else {}

	if args.confdir:
		settings['confdir'] = args.confdir

	if args.aws:
		settings['aws'] = True

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


class Config(object):

	def __init__(self):
		self.config = {}
		self.log = logging.getLogger(__name__)

	def merge(self, other):

		if isinstance(other, Config):
			other = other.config

		for key in other:
			if key in self.config:
				self.config[key].extend(other[key])
			else:
				self.config[key] = other[key]
		
		return self
	

class FilesConfig(Config):

	def __init__(self, directory):

		super(FilesConfig, self).__init__()

		if not os.path.exists(directory):
			raise Exception('Configuration directory not found: %s' % directory)

		self.log.debug('Loading configuration from %s' % directory)

		containers = []
		for entry in os.listdir(directory):
			if entry.endswith('.json'):
				with open('%s/%s' % (directory, entry)) as local:
					containers.append(json.load(local))

		if len(containers):
			self.merge({ 'containers': containers })

class AWSConfig(Config):

	def __init__(self):

		super(AWSConfig, self).__init__()

		try:
			self.log.debug('Loading configuration from EC2 user-data')
			self.merge(json.loads(read_command(['ec2metadata', '--user-data'], timeout=5.0)))
		except Exception as e:
			pass
