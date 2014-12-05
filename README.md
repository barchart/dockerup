## dockerup

dockerup is a Docker container manager for individual hosts. It reads
configuration from a file (or EC2 user-data to facilitate deploy-time
configuration) to build a list of containers that should be running on
the host. Using this configuration, it kills off containers that
shouldn't be running, upgrades containers that have updates available,
and launches all containers listed in the config. After each run it
cleans up any leftover containers and images that are not in use, to
save disk space.

To install dockerup on Ubuntu, install `docker` and run:

```
pip install dockerup
```

#### Running dockerup

dockerup is typically run from a cron job (once a minute) to check for
configuration and container updates.

```
dockerup --config /my/config.json --cache /var/cache/dockerup
```

If you omit `--config`, dockerup will look in `/etc/dockerup/dockerup.json`.
You can also use EC2 user-data by specifying `--config aws`. A sample JSON
configuration file is shown below:

```
{
	"containers": [
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
		},
        {
            "type": "docker",
            "name": "historical-app",
            "image": "barchart/historical",
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
```
