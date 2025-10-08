# Beep indication when an object in sleep mode gains focus
# Author: Cooper Wooten

import globalPluginHandler
import tones
from scriptHandler import script
import api
import ui

class GlobalPlugin(globalPluginHandler.GlobalPlugin):

	@script(gesture="kb:NVDA+alt+a", allowInSleepMode=True)
	def script_sleepModeBeepAnnounce(self, gesture):
		focus = api.getFocusObject()
		curFocus = focus.appModule
		if curFocus.sleepMode:
			tones.beep(440, 500)

	@script(gesture="kb:NVDA+alt+b", allowInSleepMode=True)
	def script_sleepModeSpeechAnnounce(self, gesture):
		focus = api.getFocusObject()
		currFocus = focus.appModule
		if currFocus.sleepMode:
			ui.message(f"{focus.name} is currently in sleep mode")
