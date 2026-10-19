from dataclasses import dataclass, field, replace

from computer.keyboard import parse_shortcut


@dataclass
class Intent:
	action: str
	target: str = ""
	role: str = ""
	value: object = None
	confidence: float = 1.0
	metadata: dict = field(default_factory=dict)

	def copy(self, **changes):
		return replace(self, **changes)


def parse_intent(transcript):
	raw_text = str(transcript).lower()
	if raw_text.lstrip().startswith("press "):
		text = " ".join(raw_text.replace(":", " ").split())
	else:
		text = " ".join(raw_text.replace(",", " ").replace(":", " ").split())
	text = text.removeprefix("maruti ").strip()
	text = text.replace("chorme", "chrome")
	if text in {"type mode", "typing mode", "type mode activate", "activate type mode", "start type mode", "typing mode on"}:
		return Intent("start_type_mode")
	if text == "type mode deactivate":
		return Intent("end_type_mode")
	if text in {"hello", "hi", "hey"}:
		return Intent("hello")
	if text == "how are you":
		return Intent("how_are_you")
	if text in {"exit", "stop", "quit", "goodbye", "close assistant"}:
		return Intent("exit")
	simple_actions = {
		"scroll down": "scroll_down", "scroll up": "scroll_up",
		"go back": "back", "back": "back", "go forward": "forward", "forward": "forward",
		"enter": "enter", "go top": "top", "go bottom": "bottom",
		"open new tab": "open_tab", "close tab": "close_tab",
		"close window": "close_window", "close the window": "close_window",
		"shut down": "shutdown", "shutdown": "shutdown",
	}
	if text in simple_actions:
		return Intent(simple_actions[text])
	if text.startswith("type "):
		return Intent("type", value=text[5:])
	if text.startswith("search for "):
		return Intent("search", value=text[11:])
	if text.startswith("search "):
		return Intent("search", value=text[7:])
	shortcut_keys = parse_shortcut(text)
	if shortcut_keys:
		if len(shortcut_keys) == 1:
			return Intent("press", value=shortcut_keys[0])
		return Intent("hotkey", metadata={"keys": shortcut_keys})
	for prefix, action in (("double click", "double_click"), ("right click", "right_click"), ("click", "click")):
		if text.startswith(prefix):
			target = text[len(prefix):].strip().removeprefix("on ").removeprefix("the ")
			return Intent(action, target=target)
	if text in {"open chrome", "open google chrome"}:
		return Intent("open", target="chrome")
	if text in {"close chrome", "close google chrome"}:
		return Intent("close", target="chrome")
	return None
