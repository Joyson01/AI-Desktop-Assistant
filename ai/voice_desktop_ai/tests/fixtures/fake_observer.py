class FakeObserver:
    def __init__(self, screens):
        self.screens = list(screens)
        self.calls = []
        self.index = 0

    def __call__(self):
        self.calls.append(self.index)
        if self.index < len(self.screens):
            screen = self.screens[self.index]
            self.index += 1
            return screen
        return self.screens[-1]