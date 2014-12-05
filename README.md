## crypter

Crypter is an encryption daemon designed to be run on a container host (i.e. Docker).
It listens to unix domain sockets for client connections, and encrypts or decrypts
values on request. This allows sensitive configuration values (i.e. credentials)
to be encrypted in a docker container and decrypted at runtime by the container
host.

To install crypter on Ubuntu:

```
apt-get install openssl
pip install crypter
```

Due to the current messy state of Python encryption libraries, crypter depends
on a local OpenSSL binary for data encryption.

An RSA private key and certificate for encryption can be generated with the
following OpenSSL command:

```
openssl req -x509 -newkey rsa:2048 -keyout key.pem -out cert.pem -days XXX -nodes
```

Keep your private key in a safe place, and distribute it to your container hosts
when they are built. We use puppetmaster to store the key locally and copy it to
Docker host nodes during image building.

#### Running the daemon

To run the daemon, provide the location of your key files and the directory to
create unix sockets in:

```
crypter -d /var/run/crypter --key /path/to/key.pem --cert /path/to/cert.pem
```

You can also specify default configuration values in `/etc/crypter/crypter.cfg`:

```
directory=/var/run/crypter
key=/path/to/key.pem
cert=/path/to/cert.pem
```

The daemon creates two unix domain sockets: `/var/run/crypter/encrypt` and
`/var/run/crypter/decrypt` that clients can connect to and request encryption
or decryption of values. Once connected, to encrypt a value the client can
connect to the `encrypt` socket and send the value to encrypt followed by two
newlines:

```
value-to-encrypt\n
\n
```

Note that the value to encrypt cannot contain two consecutive newlines.
If you need to encrypt larger chunks of data that may contain this sequence
(such as a file) you should Base64-encode the data first.

The daemon will respond with the encrypted value as a PEM-encoded PKCS#7
message, followed by two newlines:

```
-----BEGIN PKCS7-----
MIIBeQYJKoZIhvcNAQcDoIIBajCCAWYCAQAxggEhMIIBHQIBADAFMAACAQEwDQYJ
KoZIhvcNAQEBBQAEggEAKvgvyDUB1tDvU55foX2e5zK7cMBsxFXc1Mvle+3cmz+m
Eysq1TljQ5Zg1iuJFzprP3WtEcTgywCn1DRgyasu2XAD0h9EZrcm99uU4djBUGMI
hhPW+EAOdU9rdono/7q+Jqp0mpBXUc2nVjS9njjnXpHNRmHPHuX/yx3OMKhjFtDm
2PQofTZfRtFS/Q6cE/d930rRhV31GeN1S8my8CFgAO1EEPetVCr2hm1natGK3LYd
af+xhzLc+QrsT13Hx0pr5j7qYlfPlFR5HlDSyOs/oxvQ58WJAG1jKlGsjAAD24V0
Q7bfC60Ns7EYqGOAbL50/3XGcbBjj+AUtz5sYUwQHzA8BgkqhkiG9w0BBwEwHQYJ
YIZIAWUDBAEqBBAVCm6GhgsWvSPIKub28YdwgBDo0j7xAbBXCdsiEA7iq9wP
-----END PKCS7-----

```

To decrypt, simply reverse the process - connect to the `decrypt` socket and
send the encrypted value returned above (boundary lines optional) followed
by two newlines. Decrypting will not be supported if the private key is not
available.

Due to the basic nature of the protocol, subsequent encrypt/decrypt requests
over a single connection should only be sent after the previous response is
received, or results will be undefined.

##### Technical Note

Behind the scenes, data is encrypted by OpenSSL via the following commands
(data is piped via STDIN):

```
openssl smime -encrypt -outform pem -aes256 &gt;PUBKEY&lt;
```

```
openssl smime -decrypt -inform pem -inkey &gt;PRIVKEY&lt;
```

#### Using the CLI client

A command line client is provided for use within the container that
provides a simple way to handle configuration decryption in shell scripts.
It also reads `/etc/crypter/crypter.cfg` to find the default unix socket
directory, or it can be specified on the command line with `-d`.

```
echo "MIIBeQYJKoZIhvcNAQcDoIIBajCCAWYCAQAxggEhMIIBHQIBADAFMAACAQEwDQYJ
	KoZIhvcNAQEBBQAEggEAKvgvyDUB1tDvU55foX2e5zK7cMBsxFXc1Mvle+3cmz+m
	Eysq1TljQ5Zg1iuJFzprP3WtEcTgywCn1DRgyasu2XAD0h9EZrcm99uU4djBUGMI
	hhPW+EAOdU9rdono/7q+Jqp0mpBXUc2nVjS9njjnXpHNRmHPHuX/yx3OMKhjFtDm
	2PQofTZfRtFS/Q6cE/d930rRhV31GeN1S8my8CFgAO1EEPetVCr2hm1natGK3LYd
	af+xhzLc+QrsT13Hx0pr5j7qYlfPlFR5HlDSyOs/oxvQ58WJAG1jKlGsjAAD24V0
	Q7bfC60Ns7EYqGOAbL50/3XGcbBjj+AUtz5sYUwQHzA8BgkqhkiG9w0BBwEwHQYJ
	YIZIAWUDBAEqBBAVCm6GhgsWvSPIKub28YdwgBDo0j7xAbBXCdsiEA7iq9wP" \
	| crypter-client decrypt
```

### Docker integration

To use crypter inside Docker, deploy your keys to the Docker host, start
crypter, and map the host's socket directory to a volume inside the Docker
container.

```
$ docker run -d -v /var/run/crypter:/var/run/crypter ubuntu
```

Once running, you will see the `encrypt` and `decrypt` sockets exposed inside
the container at `/var/run/crypter`. You can now decrypt values (i.e.
credentials in app configuration) without exposing your private key to the
container.
