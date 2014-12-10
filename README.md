## dockerup

dockerup is a Docker container bootstrapper for individual VM hosts. It
reads configuration from a file (or EC2 user-data to facilitate deploy-time
configuration) to build a list of containers that should be running on
the host. Using this configuration, it kills off containers that
shouldn't be running, upgrades containers that have updates available,
and launches all new containers listed in the config. After each run it
cleans up orphaned containers and images to save disk space.

To install dockerup on Ubuntu, install `docker` and run:

```
pip install dockerup
```

#### Running dockerup

dockerup is typically run from a cron job (once a minute) to check for
configuration and container updates. You should also run it immediately
on boot to ensure containers get started quickly after a reboot without
waiting on the next run.

```
dockerup --config /etc/dockerup/dockerup.conf --cache /var/cache/dockerup
```

By default the config file resides in `/etc/dockerup/dockerup.conf`. There
are currently only two valid config entries (defaults shown below):

```
confdir=/etc/dockerup/containers.d
aws=true
```

These config values can also be overridden on the command line with `--aws`
and `--confdir`.

`confdir` specifies a directory containing JSON files that define individual
containers that should be run, using the format below:

```
{
	"type": "docker",
	"name": "registry",
	"image": "registry",
	"portMappings": [
		{
			"containerPort": "5000",
			"hostPort": "5000"
		}
	],
	"env": {
		"STANDALONE": "false",
		"SETTINGS_FLAVOR": "s3",
		"AWS_BUCKET": "my-docker-registry",
		"STORAGE_PATH": "/registry",
		"MIRROR_SOURCE": "https://registry-1.docker.io",
		"MIRROR_SOURCE_INDEX": "https://index.docker.io registry"
	}
}
```

`aws` tells dockerup to also fetch EC2 user-data, and parse the results as
JSON to discover containers to run. The container configuration format is the
same as shown above, but is wrapped in a JSON `containers` array to allow defining
multiple containers per host:

```
{
	'containers': [
        {
            "type": "docker",
            "name": "my-app",
            "image": "example/my-app",
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
            "image": "example/logstash-forwarder",
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
```

Both of these configuration mechanisms can be used simultaneously; if both are
active, the resulting container list will be a combination of the two. This allows
you to deploy base VM images that run several utility containers by default,
while allowing dynamic definition of containers via user-data at deploy time,
making it ideal for orchestration with CloudFormation.
