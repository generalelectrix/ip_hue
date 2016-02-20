from collections import namedtuple
import numpy as np
from qhue import QhueException

def cp(x, y):
    return np.array((x, y))

Gamut = namedtuple('Gamut', ('red', 'green', 'blue', 'constants'))

# include constants for checking if colors are in gamut
def _make_gamut(red, green, blue):
    v0 = green - red
    v1 = blue - red
    dot00 = np.dot(v0, v0)
    dot01 = np.dot(v0, v1)
    dot11 = np.dot(v1, v1)
    inv_denom = 1. / (dot00 * dot11 - dot01 * dot01)
    return Gamut(
        red=red,
        green=green,
        blue=blue,
        constants=(v0, v1, dot00, dot01, dot11, inv_denom))

# living colors, etc
GAMUT_A = _make_gamut(
    red=cp(0.704, 0.296),
    green=cp(0.2151, 0.7106),
    blue=cp(0.138, 0.08))

# hue
GAMUT_B = _make_gamut(
    red=cp(0.675, 0.322),
    green=cp(0.409, 0.518),
    blue=cp(0.167, 0.04))

def xy_color_in_gamut(color, gamut):
    """Return True if the color with coordinates x,y is in gamut.

    From the linear algebraic basis method at
    http://www.blackpawn.com/texts/pointinpoly/
    """
    v0, v1, d00, d01, d11, inv_denom = gamut.constants
    v2 = color - gamut.red
    d02 = np.dot(v0, v2)
    d12 = np.dot(v1, v2)

    u = (d11 * d02 - d01 + d12) * inv_denom
    v = (d00 * d12 - d01 * d02) * inv_denom

    return u >= 0. and v >= 0. and u + v < 1.

def distance(A, B):
    D = A - B
    return np.sqrt(np.dot(D, D))

def closest_point_on_line(line, P):
    """Get the point on the line closest to P.

    Direct port from hue color conversion docs.
    """
    A, B = line
    AB = B - A
    ab2 = np.dot(AB, AB)
    ap_ab = np.dot(P - A, AB)

    t = ap_ab / ab2

    t = max(min(t, 1.0), 0.0)

    return (A + AB) * t

def get_closest_color_in_gamut(color, gamut):

    def get_best_point_for_line(line):
        pAB = closest_point_on_line(line, color)
        return pAB, distance(color, pAB)

    lines = (
        (gamut.red, gamut.green),
        (gamut.blue, gamut.red),
        (gamut.green, gamut.blue))

    bests = (get_best_point_for_line(line) for line in lines)
    best_color, _ = min(bests, key=lambda best: best[1])
    return best_color

def coerce_into_gamut(color, gamut):
    """Coerce an XY color into gamut, if necessary."""
    if not xy_color_in_gamut(color, gamut):
        return get_closest_color_in_gamut(color, gamut)
    else:
        return color

def gamma_correction(value):
    """Perform hue-recommended gamma correction on a unipolar float."""
    if value > 0.04045:
        return ((value + 0.055) / 1.055)**2.4
    else:
        return value / 12.92

def rgb_to_xy(color_rgb, gamut, gamma_correct=True):
    """Convert an RGB color to an in-gamut XY color and brightness.

    Direct port from hue color conversion docs.
    """
    if gamma_correct:
        red, green, blue = (gamma_correction(c) for c in color_rgb)
    else:
        red, green, blue = color_rgb

    # convert to XYZ using Wide RGB D65
    X = red * 0.664511 + green * 0.154324 + blue * 0.162028
    Y = red * 0.283881 + green * 0.668433 + blue * 0.047685
    Z = red * 0.000088 + green * 0.072310 + blue * 0.986039

    div = X + Y + Z
    if div == 0.:
        color_xy = cp(0., 0.)
    else:
        color_xy = cp(X / div, Y / div)

    color_xy = coerce_into_gamut(color_xy, gamut)

    return color_xy, Y


# deciseconds, matches the hue default
_DEFAULT_TRANSITION_TIME = 4

_MIN_CT = 153
_MAX_CT = 500

class HueLamp (object):
    """Useful interface to a Hue lamp.

    At the moment, gamut B is hardcoded as I don't own any other lamps :)

    Transition time is am attribute of this class, and will be sent with every
    command.
    """

    # use gamma correction?
    gamma_correct = True
    gamut = GAMUT_B

    def __init__(self, qhue_light):
        self.light = qhue_light
        info = qhue_light()
        self.name = info['name']
        self.ttime = _DEFAULT_TRANSITION_TIME
        self.state = {}
        self.refresh_state(info['state'])

    @property
    def xy(self):
        return self.state['xy']

    @property
    def ct(self):
        return self.state['ct']

    @property
    def bri(self):
        return self.state['bri']

    @property
    def on(self):
        return self.state['on']

    @property
    def last_colormode(self):
        return self.state['colormode']

    def refresh_state(self, state=None):
        # query the light if we didn't pass in a state
        if state is None:
            self.state = self.light()['state']
        else:
            self.state.update(state)

    def _filter_command(self, **commands):
        """Given a full command, minimize the number of args.

        Uses the last known state of the lamp to do this.  Using this helper
        should minimize traffic on the puny zigbee network.
        """
        try:
            bri = commands.pop('bri')
        except KeyError:
            pass
        else:
            if bri == 0:
                # if the light is already off do nothing
                if not self.on:
                    return None
                # otherwise, just turn it off
                return {'on': False}

            # if we're changing the brightness, put the command back
            if bri != self.bri:
                commands['bri'] = bri

        # if the lamp is off, turn it on
        if not self.on:
            commands['on'] = True

        # deal with transition times
        ttime = commands.pop('transitiontime', None)
        ttime = self.ttime if ttime is None else ttime
        # only send ttime if it isn't the hue default
        if ttime != _DEFAULT_TRANSITION_TIME:
            commands['transitiontime'] = ttime

        # xy overrides ct, so never send ct if xy
        if 'xy' in commands:
            commands.pop('ct', None)

        # if we are setting xy color, the color is unchanged, and the last
        # command was xy, don't send it
        if ('xy' in commands and
            self.last_colormode == 'xy' and
            (commands['xy'] == self.xy).all()):
            del commands['xy']

        # if we are setting color temperature, it is unchanged, and the last
        # command was color temperature, don't send it
        if ('ct' in commands and
            self.last_colormode == 'ct' and
            commands['ct'] == self.ct):
            del commands['ct']

        print commands
        return commands

    def send_command(self, **commands):
        """Send a command to the lamp and update the local state upon success."""
        commands = self._filter_command(**commands)

        if commands is None:
            return

        # handle the case if the lamp was off when not expected to be
        try:
            self.light.state(**commands)
        except QhueException as err:
            if 'Device is set to off.' in err.args[0]:
                # this can only occur if the lamp should have been on, so force
                print "Forcing on."
                commands['on'] = True
                print commands
                self.light.state(**commands)

        # update our local state based on the commands we just sent, if success
        colormode = self.last_colormode
        if 'ct' in commands:
            colormode = 'ct'
        if 'xy' in commands:
            colormode = 'xy'
        self.refresh_state(dict(commands, colormode=colormode))

    def send_color(self, color_rgb, ttime=None):
        """Send a color transition to the lamp."""
        xy, bri_float = rgb_to_xy(color_rgb, self.gamut, self.gamma_correct)

        # this only works because 254 is the max but the bridge coerces 255
        # to 254.  Otherwise, to get full range we'd need to do 256 and coerce
        # down to 255 ourselves.
        bri = int(bri_float*255)

        self.send_command(bri=bri, xy=xy, transitiontime=ttime)

    def send_ct(self, ct, ttime=None):
        """Send a color temp transition to the lamp.

        ct: a float on the range [0, 1]. Higher values -> higher color temp.
        """
        ct = int((1.0 - ct) * (_MAX_CT - _MIN_CT) + _MIN_CT)

        self.send_command(ct=ct, transitiontime=ttime)

    def send_bri(self, bri_float, ttime=None):
        """Send brightness to the lamp.

        bri_float: a float on the range [0, 1].
        """
        bri = int(bri_float*255)
        self.send_command(bri=bri, transitiontime=ttime)
