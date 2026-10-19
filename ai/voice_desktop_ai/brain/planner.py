class Plan:
    def __init__(self, steps): self.steps = steps

def make_plan(intent): return Plan([intent])
