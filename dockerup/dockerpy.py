import json

from dockerup.client import DockerClient
from docker.client import Client

class DockerPyClient(DockerClient):

    def __init__(self, remote, username=None, password=None, email=None):
        super(DockerPyClient,self).__init__()
        self.client = Client(base_url=remote, version='1.15')
        if username:
            self.client.login(username=username, password=password, email=email)

    def docker_images(self, filters=None):
        return self.client.images(filters=filters)

    def __id(self, ioc):
        if ioc and 'Id' in ioc:
            return ioc['Id']
        return None
        
    def docker_containers(self):
        return [{
            'Id': cont['Id'],
            'Tag': cont['Image'],
            'Image': self.__id(self.image(cont['Image'])),
            'Names': cont['Names'],
            'Ports': cont['Ports'],
            'Created': cont['Created'],
            'Command': cont['Command'],
            'Status': cont['Status'],
            'Running': cont['Status'].startswith('Up ')
        } for cont in self.client.containers()]

    def docker_pull(self, image):
        (repository, tag) = self.tag(image)
        updated = False
        for line in self.client.pull(repository=repository, stream=True, insecure_registry=True):
            parsed = json.loads(line)
            if 'error' in parsed:
                raise Exception(parsed['error'])
            elif 'status' in parsed and parsed['status'].startswith('Status: Downloaded newer image'):
                updated = True
        return updated

    def docker_run(self, entry):

        volumes = ['/var/log/ext']

        kwargs = {
            'image': entry['image'],
            'volumes': volumes,
            'detach': True
        }

        if 'name' in entry:
            if entry['name'].startswith('local-'):
                self.log.error('Invalid container name, local-* is reserved')
                return False
            kwargs['name'] = entry['name']

        if 'env' in entry:
            kwargs['environment'] = entry['env']

        if 'cpu' in entry:
            kwargs['cpu_shares'] = entry['cpu']

        if 'memory' in entry:
            kwargs['mem_limit'] = entry['memory']

        if 'entrypoint' in entry:
            kwargs['entrypoint'] = entry['entrypoint']

        if 'command' in entry:
            kwargs['command'] = entry['command']

        if 'volumes' in entry:
            volumes.extend([vol['containerPath'] for vol in entry['volumes'] if 'containerPath' in vol])
            volsFrom = [vol['from'] for vol in entry['volumes'] if 'from' in vol]
            if len(volsFrom):
                kwargs['volumes_from'] = volsFrom

        if 'portMappings' in entry:
            kwargs['ports'] = [p['containerPort'] for p in entry['portMappings']]

        container = self.client.create_container(**kwargs)

        self.docker_start(container['Id'], entry)

        return container['Id']

    def docker_start(self, container, entry=None):

        binds = {
            '/var/log/ext/%s' % container: {
                'bind': '/var/log/ext',
                'ro': False
            }
        }

        kwargs = {
            'container': container,
            'restart_policy': { 'MaximumRetryCount': 0, 'Name': 'on-failure' },
            'binds':  binds
        }
        
        if entry is not None:

            if 'network' in entry:
                kwargs['network_mode'] = entry['network']

            if 'privileged' in entry:
                kwargs['privileged'] = entry['privileged']

            if 'volumes' in entry:
                
                volsFrom = []

                for vol in entry['volumes']:

                    if 'from' in vol:
                        volsFrom.append(vol['from'])
                        continue

                    if not 'containerPath' in vol:
                        self.log.warn('No container mount point specified, skipping volume')
                        continue

                    if not 'hostPath' in vol:
                        # Just a local volume, no bindings
                        continue

                    binds[vol['hostPath']] = {
                        'bind': vol['containerPath'],
                        'ro': 'mode' in vol and vol['mode'].lower() == 'ro'
                    }

                if len(volsFrom):
                    kwargs['volumes_from'] = volsFrom

            if 'portMappings' in entry:
                portBinds = {}
                for pm in entry['portMappings']:
                    portBinds[pm['containerPort']] = pm['hostPort'] if 'hostPort' in pm else None
                kwargs['port_bindings'] = portBinds

        self.client.start(**kwargs);

    def docker_restart(self, container):
        self.client.restart(container)

    def docker_stop(self, container):
        self.client.stop(container)

    def docker_rm(self, container):
        self.client.remove_container(container)

    def docker_rmi(self, image):
        self.client.remove_image(image)
