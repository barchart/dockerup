import subprocess
import logging
import threading
import re

def read_command(command, as_dict=False, nul_value=None, timeout=0):

	proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
	
	timer = None

	if timeout > 0:
		timer = threading.Timer(timeout, kill_process, (proc,))
		timer.daemon = True
		timer.start()

	try:

		contents = proc.stdout.read()

		if proc.wait() != 0:
			logging.getLogger(__name__).debug('Command failed: %s\nSTDOUT:\n%s\nSTDERR:\n%s' % (' '.join(command), contents.strip(), proc.stderr.read().strip()))
			raise Exception('Command failed: %s' % ' '.join(command))

	finally:
		if timer:
			timer.cancel()

	if as_dict:

		lines = re.split('\s*\n', contents)
		labels = split_fields(lines[0])

		rows = []

		for line in lines[1:]:
			if line:
				rows.append(dict(zip(labels, split_fields(line, nul_value))))

		return rows

	return contents

def kill_process(proc):

	if proc.poll() is None:
		logging.getLogger(__name__).error( 'Error: process taking too long to complete - terminating')
		proc.kill()

def split_fields(line, nul_value=None):

	fields = re.split('\s\s+', line)

	if nul_value:
		for i in range(0, len(fields)):
			if fields[i] == nul_value:
				fields[i] = None

	return fields

