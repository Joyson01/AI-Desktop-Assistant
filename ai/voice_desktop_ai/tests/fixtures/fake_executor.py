class FakeExecutor:
    def __init__(self, results=None):
        self.calls = []
        self.results = list(results or [])

    def execute(self, payload):
        self.calls.append(dict(payload))
        if self.results:
            return self.results.pop(0)
        return {"success": True, "message": "simulated"}