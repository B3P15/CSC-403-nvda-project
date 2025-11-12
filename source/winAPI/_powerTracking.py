# A part of NonVisual Desktop Access (NVDA)
# Copyright (C) 2022-2025 NV Access Limited, Rui Batista, Cyrille Bougot
# This file is covered by the GNU General Public License.
# See the file COPYING for more details.

"""
Tracking was introduced so that NVDA has a mechanism to announce changes to the power state.

When NVDA receives a power status change Window Message,
we notify the user of the power status.
The power status can also be reported using script_say_battery_status.
"""

from __future__ import annotations
import ctypes
from enum import (
	Enum,
	IntEnum,
	IntFlag,
	auto,
	unique,
)
from typing import (
	List,
	Optional,
)

from logHandler import log
import ui
import winBindings.kernel32
from winBindings.kernel32 import SYSTEM_POWER_STATUS as SystemPowerStatus
import winKernel
import comtypes


BATTERY_LIFE_TIME_UNKNOWN = 0xFFFFFFFF


class PowerBroadcast(IntEnum):
	# https://docs.microsoft.com/en-us/windows/win32/power/wm-powerbroadcast
	APM_POWER_STATUS_CHANGE = 0xA
	"""
	Notifies applications of a change in the power status of the computer,
	such as a switch from battery power to A/C.
	The system also broadcasts this event when remaining battery power
	slips below the threshold specified by the user
	or if the battery power changes by a specified percentage.
	A window receives this event through the WM_POWERBROADCAST message.
	https://docs.microsoft.com/en-us/windows/win32/power/pbt-apmpowerstatuschange
	"""
	APM_RESUME_AUTOMATIC = 0x12
	"""
	Operation is resuming automatically from a low-power state.
	This message is sent every time the system resumes.
	"""
	APM_RESUME_SUSPEND = 0x7
	"""
	Operation is resuming from a low-power state.
	This message is sent after APM_RESUME_AUTOMATIC if the resume is triggered by user input,
	such as pressing a key.
	"""
	APM_SUSPEND = 0x4
	"""
	System is suspending operation.
	"""
	POWER_SETTING_CHANGE = 0x8013
	"""
	A power setting change event has been received.
	"""


class BatteryFlag(IntFlag):
	# https://docs.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-system_power_status
	HIGH = 0x1
	"""More than 66%"""
	LOW = 0x2
	"""Less than 33%"""
	CRITICAL = 0x4
	"""Less than 5%"""
	NO_SYSTEM_BATTERY = 0x80
	UNKNOWN = 0xFF


class PowerState(IntFlag):
	# https://docs.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-system_power_status
	AC_OFFLINE = 0x0
	AC_ONLINE = 0x1
	UNKNOWN = 0xFF

	BatteryFlag: BatteryFlag
	ACLineStatus: PowerState
	BatteryLifePercent: int
	BatteryLifeTime: int


_powerState: PowerState = PowerState.UNKNOWN


def initialize():
	"""
	The NVDA message window only handles changes of state.
	As such, to correctly ignore an initial power change event,
	which does not change the power state (e.g. a battery level drop),
	we fetch the initial power state manually.
	"""
	global _powerState
	systemPowerStatus = winBindings.kernel32.SYSTEM_POWER_STATUS()
	if (
		not winKernel.GetSystemPowerStatus(systemPowerStatus)
		or systemPowerStatus.BatteryFlag == BatteryFlag.UNKNOWN
	):
		log.error("Error retrieving system power status")
		return

	if systemPowerStatus.BatteryFlag & BatteryFlag.NO_SYSTEM_BATTERY:
		return

	_powerState = systemPowerStatus.ACLineStatus
	return


@unique
class _ReportContext(Enum):
	"""
	Used to determine the order of information, based on relevance to the user,
	when announcing power status information
	"""

	AC_STATUS_CHANGE = auto()
	"""e.g. a charger is connected/disconnected"""
	FETCH_STATUS = auto()
	"""e.g. when a user presses nvda+shift+b to fetch the current battery status"""


def reportACStateChange() -> None:
	_reportPowerStatus(_ReportContext.AC_STATUS_CHANGE)


def reportCurrentBatteryStatus() -> None:
	_reportPowerStatus(_ReportContext.FETCH_STATUS)


def _reportPowerStatus(context: _ReportContext) -> None:
	"""
	@param context: the context is used to order the announcement.
	When the context is AC_STATUS_CHANGE, this reports the current AC status first.
	When the context is FETCH_STATUS, this reports the remaining battery life first.
	"""
	global _powerState
	systemPowerStatus = _getPowerStatus()
	speechSequence = _getSpeechForBatteryStatus(systemPowerStatus, context, _powerState)
	if speechSequence:
		ui.message(" ".join(speechSequence))
	if systemPowerStatus is not None:
		_powerState = systemPowerStatus.ACLineStatus


def _getPowerStatus() -> Optional[SystemPowerStatus]:
	sps = SystemPowerStatus()
	systemPowerStatusUpdateResult = winKernel.GetSystemPowerStatus(sps)
	if not systemPowerStatusUpdateResult:
		log.error(f"Error retrieving power status: {ctypes.GetLastError()}")
		return None
	return sps


def _getSpeechForBatteryStatus(
	systemPowerStatus: Optional[SystemPowerStatus],
	context: _ReportContext,
	oldPowerState: PowerState,
) -> List[str]:
	if not systemPowerStatus or systemPowerStatus.BatteryFlag == BatteryFlag.UNKNOWN:
		# Translators: This is presented when there is an error retrieving the battery status.
		return [_("Unknown power status")]

	if systemPowerStatus.BatteryFlag & BatteryFlag.NO_SYSTEM_BATTERY:
		# Translators: This is presented when there is no battery such as desktop computers
		# and laptops with battery pack removed.
		return [_("No system battery")]

	if context == _ReportContext.AC_STATUS_CHANGE and systemPowerStatus.ACLineStatus == oldPowerState:
		# Sometimes, the power change event double fires.
		# The power change event also fires when the battery level decreases by 3%.
		return []

	text: List[str] = []
	
	remainingChargeTime = _getTimeToFullCharge()
	if context == _ReportContext.AC_STATUS_CHANGE:
		# When the AC status changes, users want to be alerted to the new AC status first.
		text.append(_getACStatusText(systemPowerStatus))
		text.extend(_getBatteryInformation(systemPowerStatus))
	elif context == _ReportContext.FETCH_STATUS:
		# When fetching the current battery status,
		# users want to know the current battery status first,
		# rather than the AC status which should be unchanged.
		text.extend(_getBatteryInformation(systemPowerStatus))
		text.append(_getACStatusText(systemPowerStatus))
		if remainingChargeTime is not None:
			text.append(
				# Translators: Reported when the battery is charging.
				# E.g. "30 minutes remaining until full charge"
				_("{minute} minutes remaining until fully charged").format(minute=_getTimeToFullCharge())
		)
	else:
		raise NotImplementedError(f"Unexpected _ReportContext: {context}")

	return text


def _getACStatusText(systemPowerStatus: SystemPowerStatus) -> str:
	# Translators: This is presented to inform the user of the current battery percentage.
	if systemPowerStatus.ACLineStatus & PowerState.AC_ONLINE:
		# Translators: Reported when the battery is plugged in, and now is charging.
		return _("Plugged in")
	else:
		# Translators: Reported when the battery is no longer plugged in, and now is not charging.
		return _("Unplugged")


def _getBatteryInformation(systemPowerStatus: SystemPowerStatus) -> List[str]:
	text: List[str] = []
	# Translators: This is presented to inform the user of the current battery percentage.
	text.append(_("%d percent") % systemPowerStatus.BatteryLifePercent)
	SECONDS_PER_HOUR = 3600
	SECONDS_PER_MIN = 60
	if systemPowerStatus.BatteryLifeTime != BATTERY_LIFE_TIME_UNKNOWN:
		nHours = systemPowerStatus.BatteryLifeTime // SECONDS_PER_HOUR
		nMinutes = (systemPowerStatus.BatteryLifeTime % SECONDS_PER_HOUR) // SECONDS_PER_MIN

		# Skip if no time, as it likely means the status check is inaccurate
		if systemPowerStatus.BatteryLifeTime == 0:
			return text
		if nHours == 0 and nMinutes == 0:
			# Translators: Reported when battery time is less than 1 minute.
			text.append(_("Less than 1 minute remaining"))
			return text

		hourText: str | None = None
		minuteText: str | None = None

		# Handle hours - only if greater than 0
		if nHours > 0:
			hourText = ngettext(
				# Translators: This is the hour string part of the estimated remaining runtime of the laptop battery.
				# E.g. if the full string is "1 hour and 34 minutes remaining", this string is "1 hour".
				"{hours:d} hour",
				"{hours:d} hours",
				nHours,
			).format(hours=nHours)

		# Handle minutes - only if greater than 0
		if nMinutes > 0:
			minuteText = ngettext(
				# Translators: This is the minute string part of the estimated remaining runtime of the laptop battery.
				# E.g. if the full string is "1 hour and 34 minutes remaining", this string is "34 minutes".
				"{minutes:d} minute",
				"{minutes:d} minutes",
				nMinutes,
			).format(minutes=nMinutes)

		# Combine hours and minutes appropriately
		if hourText is not None and minuteText is not None:
			text.append(
				# Translators: This is the main string for the estimated remaining runtime of the laptop battery.
				# E.g. hourText is replaced by "1 hour" and minuteText by "34 minutes".
				_("{hourText} and {minuteText} remaining").format(hourText=hourText, minuteText=minuteText),
			)
		elif hourText is not None:
			text.append(
				# Translators: Reported when only hours remaining for battery life.
				# E.g. "2 hours remaining"
				_("{hourText} remaining").format(hourText=hourText),
			)
		elif minuteText is not None:
			text.append(
				# Translators: Reported when only minutes remaining for battery life.
				# E.g. "30 minutes remaining"
				_("{minuteText} remaining").format(minuteText=minuteText),
			)
	return text

def _propertyDictionary(com_obj):
    """Return a dict of property name -> value for a SWbemObject (comtypes)."""
    props = {}
    try:
        for p in com_obj.Properties_:
            # Some properties may be None; that's fine
            props.get  # ensure 'p' is a COM prop object
            name = getattr(p, "Name", None)
            val = getattr(p, "Value", None)
            if name is not None:
                props[name] = val
    except Exception:
        # If iteration fails, try attribute-based access as a last resort
        try:
            for name in dir(com_obj):
                if not name.startswith("_"):
                    try:
                        props[name] = getattr(com_obj, name)
                    except Exception:
                        pass
        except Exception:
            pass
    return props

def _getTimeToFullCharge():
    """
    Return calculated minutes until full charge when charging.
	Returns None if unavailable.
    Uses root\\wmi BatteryStatus and BatteryStaticData for battery information.
    """
    try:
        # Connect to WMI root\wmi
        locator = comtypes.client.CreateObject("WbemScripting.SWbemLocator")
        svc = locator.ConnectServer(".", "root\\wmi")

        status_q = svc.ExecQuery("SELECT * FROM BatteryStatus")
        static_q = svc.ExecQuery("SELECT * FROM BatteryStaticData")

        # No data present
        if not status_q:
            log.debug("BatteryStatus WMI query returned no instances.")
            return None

        # Use first battery entry (extend if multi-battery present)
        status_obj = list(status_q)[0]
        status_properties = _propertyDictionary(status_obj)

        # static data may be missing; try to use DesignCapacity if FullChargedCapacity missing
        full_capacity = None
        if static_q:
            static_obj = list(static_q)[0]
            static_properties = _propertyDictionary(static_obj)
            # prefer FullChargedCapacity, fall back to DesignCapacity
            full_capacity = static_properties.get("FullChargedCapacity") or static_properties.get("DesignedCapacity")

        # Values from BatteryStatus
        remaining = status_properties.get("RemainingCapacity")  # mWh
        charge_rate = status_properties.get("ChargeRate")       # often mWh/hour
        charging = bool(status_properties.get("Charging"))

        # Validate numeric values
        def is_valid_num(x):
            return x is not None and isinstance(x, (int, float)) and not (isinstance(x, float))

        if not is_valid_num(remaining):
            log.debug("RemainingCapacity unavailable; cannot compute ETA.")
            return None

        # Prefer full_capacity; if still None we cannot compute ETA
        if not is_valid_num(full_capacity):
            log.debug("FullChargedCapacity/DesignCapacity unavailable; cannot compute ETA.")
            return None

        # Charging case: use charge_rate
        if charging and is_valid_num(charge_rate) and charge_rate != 0:
            # charge_rate is assumed mWh per hour (i.e. energy/hour),
            # so (full - remaining) [mWh] / rate [mWh/hour] = hours
            delta_mwh = float(full_capacity) - float(remaining)
            if delta_mwh <= 0:
                return 0.0
            hours = delta_mwh / float(charge_rate)
            minutes = hours * 60.0
            if minutes > 0:
                return round(minutes)
            return None

        # If rates are zero or missing, we can't compute via BatteryStatus rates
        log.debug("Charge rate missing or zero; cannot compute ETA from BatteryStatus.")
        return None

    except Exception as e:
        log.debug(f"Exception computing battery ETA from root\\wmi BatteryStatus: {e}")
        return None
