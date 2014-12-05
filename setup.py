from distutils.core import setup

setup(name='dockerup',
	description='Docker container manager',
	long_description="""
	Docker container manager that synchronizes state from a configuration file.
	Can load configuration from EC2 user-data, and automatically handles container
	updates and redeployment.
	""",
	author='Jeremy Jongsma',
	author_email='jeremy@barchart.com',
	url='https://github.com/barchart/dockerup',
	version='1.0.0',
	packages=['dockerup'],
	scripts=['bin/dockerup'],
	data_files=[
		('/etc/dockerup', ['etc/dockerup.json.sample'])
	])
