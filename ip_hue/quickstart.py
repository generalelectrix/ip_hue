import qhue
import os
from pkg_resources import resource_filename

_bridge_ip = '192.168.2.3'
_uname_file = 'bridge_username.txt'
_uname_file_location = resource_filename(__name__, _uname_file)

def quickstart():

    if not os.path.exists(_uname_file_location):

        username = qhue.create_new_username(_bridge_ip)

        with open(_uname_file_location, 'w') as f:
            f.write(username)

    else:

        with open(_uname_file_location, 'r') as f:
            username = f.read()

    b = qhue.Bridge(_bridge_ip, username)

    lights = b.lights

    return b, lights