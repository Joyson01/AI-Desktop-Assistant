from uia_engine import get_active_ui_elements, find_element, invoke

def observe(target=None): return get_active_ui_elements(target=target)
def find_target(target, role="", elements=None, screenshot=None, visual_candidates=None, context=None):
	return find_element(target, elements, role, screenshot=screenshot, visual_candidates=visual_candidates, context=context)
def perform(element, action):
	return invoke(element, action)
