# ## dockerup

dockerup is a Docker container bootstrapper for individual VM hosts. It
reads configuration from a file (or EC2 user-data to facilitate deploy-time
configuration) to build a list of containers that should be running on
the host. Using this configuration, it kills off containers that
shouldn't be running, upgrades containers that have updates available,
and launches all new containers listed in the config. After each run it
cleans up orphaned containers and images to save disk space.

Install dockerup with `pip`:

```
pip install dockerup
```

## Running dockerup

dockerup should be run in its own Docker container. You should ensure that
it is set to automatically run on Docker startup. An example of running it
this way can be found here:

https://github.com/barchart/docker-dockerup

If you are running it outside of a container, it can also be executed manually:

```
dockerup --config /etc/dockerup/dockerup.conf --cache /var/cache/dockerup
```

By default the config file resides in `/etc/dockerup/dockerup.conf`. Valid
configuration options are (defaults shown):

```ini
; Container configuration files
confdir=/etc/dockerup/containers.d

; Docker remote socket
remote=unix://var/run/docker.sock

; Polling interval for image changes
interval=60

; Check EC2 user-data for container configuration
aws=false

; Also pull images from the registry when checking for container
; configuration updates
pull=true
```

These config values can also be overridden on the command line. Run `dockerup --help`
for details.

## Container Configuration

`confdir` specifies a directory containing JSON files that define individual
containers that should be run. All files ending with a `.json` extension will
be parsed for container definitions.

Example:

```
etc/
  dockerup/
    containers.d/
      registry.json
      dockerup.json
      myapp.json
```

### Container Configuration Format

The container configuration defines which image to run and how to configure it.

Simple example of running a private registry mirror:

```json
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

The full set of configuration options are shown below.

#### type

The container type. Only `docker` is supported.

```json
"type": "docker"
```

#### image

The docker image to run. You should always fully qualify your image with a version tag.

```json
"image": "barchart/java:latest"
```

#### name

The container name. This must be unique per-host, and can be used for configuring
data volume containers and network linking.

```json
"name": "mysql"
```

#### cpu

The host CPU shares to allocate to this container.

```json
"cpu": 10
```

#### memory

The host memory to allocate to this container.

```json
"memory": "2048m"
```

#### entrypoint

Override the entrypoint for the container.

```json
"entrypoint": "/bin/bash"
```

#### command

Override the command executed by this container.

```json
"command": "/usr/bin/nginx"
```

#### privileged

Run the container in privileged mode (required for some kernel operations.)

```json
"privileged": true
```

#### network

The Docker networking mode to use. Valid values are `bridge`, `none`, `container`, `host`.

```json
"network": "host"
```

#### volumes

Volume mappings for the container. This can be used for host-mapped volumes, or data
volumes shared with other containers.

Examples:

```js
"volumes": [

  // Host-mapped volume
  {
    "containerPath": "/data",
    "hostPath": "/mnt/data"
  },

  // Container volume for exporting to other containers
  {
    "containerPath": "/storage"
  },

  // Read-only host volume
  {
    "containerPath": "/etc/passwd",
    "hostPath": "/etc/passwd",
    "mode": "ro"
  },

  // Import all volumes from a data volume container
  {
    "from": "backup"
  }

]
```

#### portMappings

Network ports to map to the host system.

```js
"portMappings": [
  
  // Automatically assigned random host port
  {
    "containerPort": 8080
  },

  // Manually mapped port
  {
    "containerPort": 8080,
    "hostPort": 8080
  }

]
```

#### env

A hash of environment variables to pass to the container.

```json
"env": {
  "API_KEY": "XXX123",
  "HOME": "/data"
}
```

#### restart

Container restart behavior. Valid values are `always`, `on-failure`, `never`.

```json
"restart": "on-failure"
```

#### update

Update behavior configuration. There are three options in side the update block:

- `pull` (true): If false, do not pull images when checking for updates. If an image does not
  exist locally, it will still make a pull attempt.
- `eager` (false): It true, when container changes are detected, launch the replacement container
   before stopping the existing one. This is primarily in order to allow the dockerup
   container to update itself, but is useful in other situations.
- `rolling` (false): *Not yet implemented*

```json
"update": {
  "pull": true,
  "eager": true
}
```

## EC2 User-Data

The `aws=true` setting tells dockerup to also fetch EC2 user-data, and parse the
results as JSON to discover containers to run. The container configuration format is
the same as shown above, but is wrapped in a `containers` array to allow defining
multiple containers per host:

```json
{
	"containers": [
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

Both the local and EC2 configuration mechanisms can be used at the same time; if
both are active, the resulting container list will be a combination of the two.
This allows you to deploy base VM images that run several utility containers by
default, while allowing dynamic definition of containers via user-data at deploy
time, making it ideal for orchestration with CloudFormation.
