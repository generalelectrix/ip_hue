import qhue
from hue_lamp import HueLamp
import os

BRIDGE_IP = '192.168.2.3'
UNAME_FILE = 'bridge_username.txt'

def start():

    if not os.path.exists(UNAME_FILE):

        username = qhue.create_new_username(BRIDGE_IP)

        with open(UNAME_FILE, 'w') as f:
            f.write(username)

    else:

        with open(UNAME_FILE, 'r') as f:
            username = f.read()

    b = qhue.Bridge(BRIDGE_IP, username)

    lights = b.lights

    return b, lights