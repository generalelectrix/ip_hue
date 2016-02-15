import qhue

class HueLamp (object):
    """Useful interface to a Hue lamp.

    Eventually there should be a factory class that sets up the fixture
    with the correct gamut and using the correct conversion functions.
    """

    def __init__(self, qhue_light):
        self.qlight = qhue_light
        state = qhue_light()
        self.name = state['name']

    def set_transition_time