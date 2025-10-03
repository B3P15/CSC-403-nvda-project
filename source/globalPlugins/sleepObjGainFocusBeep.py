# Beep indication when an object in sleep mode gains focus
# Author: Cooper Wooten

import globalPluginHandler
from tones import beep
import eventHandler
import api

# basic prototype code (subject to change)
class GlobalPlugin(globalPluginHandler.GlobalPlugin):
  # if the object is in sleep mode, check to see if it is the focus object
  # if not, keep checking to see when it gains focus again
  # when object regains focus, beep to indicate sleep mode object gained focus
  
  # version 1
  '''if obj.sleepMode == true:
    if api.getFocusObj() != obj.self:
      if obj.gainFocus:
        tones.beep(500, 500)  # beep at 500 hz for 500 ms
  '''

  # version 2
  if obj.sleepMode == true:
    if api.getFocusObj() != obj.self and eventHandler.lastQueuedFocusObject == obj.self:
      tones.beep(500, 500)
