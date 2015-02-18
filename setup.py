from distutils.core import setup

setup(name='dockerup',
	description='Docker container bootstrapper',
	long_description="""
	Docker container bootstrapper that synchronizes state from a configuration file.
	It can load configuration from EC2 user-data, and automatically handles container
	updates and cleanup.
	""",
	author='Jeremy Jongsma',
	author_email='jeremy@barchart.com',
	url='https://github.com/barchart/dockerup',
	version='1.0.20',
	packages=['dockerup'],
	scripts=['bin/dockerup'],
	data_files=[
		('/etc/dockerup', ['etc/dockerup.conf']),
		('/etc/dockerup/containers.d', ['etc/dockerup.json.sample']),
	],
	install_requires=['docker-py>=0.7.0'])
