# -*- mode: ruby -*-
# vi: set ft=ruby :

# "local" will be mapped to /etc/dockerup in the VM

Vagrant.configure(2) do |config|
  config.vm.box = "ubuntu/trusty64"
  config.vm.provision "shell", inline: <<-SHELL
	# First time setup
	if ! dpkg -s lxc-docker; then
		sudo apt-get -y update
		sudo apt-get -y install python-pip curl
		sudo pip install docker-py
		curl -sSL https://get.docker.com/ | sudo sh
		sudo rm -rf /etc/dockerup
		sudo ln -s /vagrant/local /etc/dockerup
		sudo cp /vagrant/local/.dockercfg /root/.dockercfg
	fi
	# Every time refresh
	cd /vagrant
	sudo python setup.py install
	sudo dockerup -v
  SHELL
end
