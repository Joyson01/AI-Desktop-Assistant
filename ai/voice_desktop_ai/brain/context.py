class Context:
    def __init__(self):
        self.last_target = None
        self.application = ""
        self.window_title = ""

    def remember_target(self, target):
        self.last_target = target
