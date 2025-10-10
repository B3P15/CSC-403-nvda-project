# Indication upon NVDA+alt+a when an object in sleep mode gains focus
# NVDA+alt+b toggles the aforementioned gesture between a beep and a speech
# The speech option mentions the name of the focus object and the keybind to turn sleep mode off again
# Author: Cooper Wooten

import globalPluginHandler
import tones
from scriptHandler import script
import api
import ui

class GlobalPlugin(globalPluginHandler.GlobalPlugin):

	togSleepType = "beep"

	@script(gesture="kb:NVDA+alt+b", allowInSleepMode=True)
	def script_sleepModeTypeToggle(self, gesture):
		if GlobalPlugin.togSleepType == "beep":
			GlobalPlugin.togSleepType = "speak"
		else:
			GlobalPlugin.togSleepType = "beep"

	@script(gesture="kb:NVDA+alt+a", allowInSleepMode=True)
	def script_sleepModeIndicate(self, gesture):
		focus = api.getFocusObject()
		curFocus = focus.appModule
		if curFocus.sleepMode:
			if GlobalPlugin.togSleepType == "beep":
				tones.beep(440, 500)
			else: 
				ui.message(f"{focus.name} is currently in sleep mode, Use NVDA plus shift plus z to turn sleep mode off.")
