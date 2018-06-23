#! /usr/bin/env python
# -*- coding: utf-8 -*-
####################
# Copyright (c) 2016, Perceptive Automation, LLC. All rights reserved.
# http://www.indigodomo.com

import indigo
import time
from ghpu import GitHubPluginUpdater
import math
import random
import numpy as stats

# Note the "indigo" module is automatically imported and made available inside
# our global name space by the host process.

################################################################################
# Globals

k_updateCheckHours = 24

################################################################################
class Plugin(indigo.PluginBase):

    #-------------------------------------------------------------------------------
    def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
        super(Plugin, self).__init__(pluginId, pluginDisplayName, pluginVersion, pluginPrefs)

        self.updater = GitHubPluginUpdater(self)

    #-------------------------------------------------------------------------------
    # Start, Stop and Config changes
    #-------------------------------------------------------------------------------
    def startup(self):
        self.nextCheck = self.pluginPrefs.get('nextUpdateCheck',0)
        self.debug = self.pluginPrefs.get("showDebugInfo",False)
        self.logger.debug(u"startup")
        if self.debug:
            self.logger.debug(u"Debug logging enabled")
        self.deviceDict = dict()

        indigo.devices.subscribeToChanges()

    #-------------------------------------------------------------------------------
    def shutdown(self):
        self.logger.debug(u"shutdown")
        self.pluginPrefs['nextUpdateCheck'] = self.nextCheck
        self.pluginPrefs['showDebugInfo'] = self.debug

    #-------------------------------------------------------------------------------
    def closedPrefsConfigUi(self, valuesDict, userCancelled):
        self.logger.debug(u"closedPrefsConfigUi")
        if not userCancelled:
            self.debug = valuesDict.get('showDebugInfo',False)
            if self.debug:
                self.logger.debug(u"Debug logging enabled")

    #-------------------------------------------------------------------------------
    def runConcurrentThread(self):
        try:
            while True:
                for instance in self.deviceDict.values():
                    instance.tick()
                if time.time() > self.nextCheck:
                    self.checkForUpdates()
                self.sleep(1)
        except self.StopThread:
            pass

    #-------------------------------------------------------------------------------
    # Device Methods
    #-------------------------------------------------------------------------------
    def deviceStartComm(self, dev):
        self.logger.debug(u"deviceStartComm: {}".format(dev.name))
        if dev.configured:
            if dev.deviceTypeId == 'SensorStats':
                self.deviceDict[dev.id] = SensorStats(dev, self.logger)
            elif dev.deviceTypeId == 'SinewaveDummySensor':
                self.deviceDict[dev.id] = SinewaveDummySensor(dev, self.logger)
            elif dev.deviceTypeId == 'RandomDummySensor':
                self.deviceDict[dev.id] = RandomDummySensor(dev, self.logger)

    #-------------------------------------------------------------------------------
    def deviceStopComm(self, dev):
        self.logger.debug(u"deviceStopComm: {}".format(dev.name))
        if dev.id in self.deviceDict:
            del self.deviceDict[dev.id]

    #-------------------------------------------------------------------------------
    def validateDeviceConfigUi(self, valuesDict, typeId, devId):
        errorsDict = indigo.Dict()

        # FIXME

        if len(errorsDict) > 0:
            self.logger.debug(u"validate device config error: \n{}".format(errorsDict))
            return (False, valuesDict, errorsDict)
        return (True, valuesDict)

    #-------------------------------------------------------------------------------
    # General Action callback
    #-------------------------------------------------------------------------------
    def actionControlUniversal(self, action, dev):
        instance = self.deviceDict[dev.id]

        # FIXME
        pass

        ###### OTHER ACTIONS ######
        # else:
        #     self.logger.debug(u'"{}" {} action not available'.format(dev.name, unicode(action.deviceAction)))


    #-------------------------------------------------------------------------------
    # Menu Methods
    #-------------------------------------------------------------------------------
    def checkForUpdates(self):
        try:
            self.updater.checkForUpdate()
        except Exception as e:
            msg = u"Check for update error.  Next attempt in {} hours.".format(k_updateCheckHours)
            if self.debug:
                self.logger.exception(msg)
            else:
                self.logger.error(msg)
                self.logger.debug(e)
        self.nextCheck = time.time() + k_updateCheckHours*60*60

    #-------------------------------------------------------------------------------
    def updatePlugin(self):
        self.updater.update()

    #-------------------------------------------------------------------------------
    def forceUpdate(self):
        self.updater.update(currentVersion='0.0.0')

    #-------------------------------------------------------------------------------
    def toggleDebug(self):
        if self.debug:
            self.logger.debug(u"Debug logging disabled")
            self.debug = False
        else:
            self.debug = True
            self.logger.debug(u"Debug logging enabled")

    #-------------------------------------------------------------------------------
    # subscribed changes
    #-------------------------------------------------------------------------------
    def deviceUpdated(self, old_dev, new_dev):
        if new_dev.pluginId == self.pluginId:
            # device belongs to plugin
            indigo.PluginBase.deviceUpdated(self, old_dev, new_dev)

        for instance in self.deviceDict.values():
            instance.deviceUpdated(old_dev, new_dev)

###############################################################################
# Classes
###############################################################################
class SensorStats(object):
    #-------------------------------------------------------------------------------
    def __init__(self, device, logger):
        self.logger = logger
        self.dev = device
        self.props = device.pluginProps

        self.decimals = int(self.props.get('decimals',1))
        self.units = self.props.get('units','')
        self.display = self.props.get('display','all_mean')
        self.therm_type = self.props.get('therm_state',None)

        self.sensorValues = dict()
        self.sensorNames = dict()
        for sid in self.props.get('sensors',[]):
            sensor = indigo.devices[int(sid)]
            self.sensorValues[int(sid)] = sensor.sensorValue
            self.sensorNames[int(sid)] = sensor.name
        for sid in self.props.get('thermostats',[]):
            sensor = indigo.devices[int(sid)]
            if self.therm_type == 'temperature':
                try:
                    self.sensorValues[int(sid)] = sensor.temperatures[0]
                    self.sensorNames[int(sid)] = sensor.name
                except IndexError:
                    pass
            elif self.therm_type == 'humidity':
                try:
                    self.sensorValues[int(sid)] = sensor.humidities[0]
                    self.sensorNames[int(sid)] = sensor.name
                except IndexError:
                    pass

    #-------------------------------------------------------------------------------
    def deviceUpdated(self, old_dev, new_dev):
        if new_dev.id in self.sensorValues.keys():
            self.sensorNames[new_dev.id] = new_dev.name
            if isinstance(new_dev, indigo.SensorDevice):
                self.sensorValues[new_dev.id] = new_dev.sensorValue
            elif isinstance(new_dev, indigo.ThermostatDevice):
                if self.therm_type == 'temperature':
                    self.sensorValues[new_dev.id] = new_dev.temperatures[0]
                elif self.therm_type == 'humidity':
                    self.sensorValues[new_dev.id] = new_dev.humidities[0]

            values = self.sensorValues.values()
            all_mean = stats.mean(values)
            all_median = stats.median(values)
            all_deviation = stats.std(values)
            max_value = max(values)
            max_delta = max_value - all_mean
            max_deviation = max_delta / all_deviation
            min_value = min(values)
            min_delta = min_value - all_mean
            min_deviation = min_delta / all_deviation
            all_range = max_value - min_value

            for sid in self.sensorValues.keys():
                if self.sensorValues[sid] == max_value:
                    max_id = sid
                    max_name = self.sensorNames[sid]
                    break
            for sid in self.sensorValues.keys():
                if self.sensorValues[sid] == min_value:
                    min_id = sid
                    min_name = self.sensorNames[sid]
                    break

            state_list = StateList(self.decimals, self.units)
            state_list.appendState('all_mean', all_mean)
            state_list.appendState('all_median', all_median)
            state_list.appendState('all_deviation', all_deviation, unit=False)
            state_list.appendState('all_range', all_range)
            state_list.appendState('max_value', max_value)
            state_list.appendState('max_delta', max_delta)
            state_list.appendState('max_deviation', max_deviation, unit=False)
            state_list.appendState('max_id', max_id, num=False)
            state_list.appendState('max_name', max_name, num=False)
            state_list.appendState('min_value', min_value)
            state_list.appendState('min_delta', min_delta)
            state_list.appendState('min_deviation', min_deviation, unit=False)
            state_list.appendState('min_id', min_id, num=False)
            state_list.appendState('min_name', min_name, num=False)

            for d in state_list:
                if d['key'] == self.display:
                    state_list.append({'key':'sensorValue', 'value':d['value'], 'uiValue':d.get('uiValue',None), 'decimals':d.get('decimals',None)})
                    break

            self.dev.updateStatesOnServer(state_list)

    #-------------------------------------------------------------------------------
    def selfUpdated(self, new_dev):
        self.dev = new_dev

    #-------------------------------------------------------------------------------
    def tick(self):
        pass

###############################################################################
class SinewaveDummySensor(object):
    #-------------------------------------------------------------------------------
    def __init__(self, instance, logger):
        self.logger = logger
        self.dev = instance
        self.props = instance.pluginProps

        self.min = float(self.props.get('minValue',-1.0))
        self.max = float(self.props.get('maxValue',1.0))
        self.period = float(self.props.get('period',60.0))
        self.frequency = int(self.props.get('frequency',10))

        self.amplitude = (self.max-self.min)/2.0
        self.mid = self.min + self.amplitude
        self.start_time = time.time()
        self.last_time = 0.0

    #-------------------------------------------------------------------------------
    def deviceUpdated(self, old_dev, new_dev):
        pass

    #-------------------------------------------------------------------------------
    def selfUpdated(self, new_dev):
        self.dev = new_dev

    #-------------------------------------------------------------------------------
    def tick(self):
        now = time.time()
        if now >= self.last_time + self.frequency:
            whole, part = divmod(now-self.start_time, self.period)
            radians = part/self.period * math.pi * 2.0
            value = self.amplitude * math.sin(radians) + self.mid
            self.dev.updateStateOnServer(key='sensorValue', value=value, uiValue=str(round(value,2)))
            self.last_time = now

###############################################################################
class RandomDummySensor(object):
    #-------------------------------------------------------------------------------
    def __init__(self, instance, logger):
        self.logger = logger
        self.dev = instance
        self.props = instance.pluginProps

        self.min = float(self.props.get('minValue',0.0))
        self.max = float(self.props.get('maxValue',1.0))
        self.frequency = int(self.props.get('frequency',10))

        self.last_time = 0

    #-------------------------------------------------------------------------------
    def deviceUpdated(self, old_dev, new_dev):
        pass

    #-------------------------------------------------------------------------------
    def selfUpdated(self, new_dev):
        self.dev = new_dev

    #-------------------------------------------------------------------------------
    def tick(self):
        now = time.time()
        if now >= self.last_time + self.frequency:
            value = random.uniform(self.min, self.max)
            self.dev.updateStateOnServer(key='sensorValue', value=value, uiValue=str(round(value,2)))
            self.last_time = now

################################################################################
# Utilities
################################################################################
class StateList(list):
    def __init__(self, decimals=None, units=None):
        super(StateList, self).__init__()
        self.decimals = decimals
        self.units = units
    def appendState(self, key, value, num=True, unit=True):
        d = dict()
        d['key'] = key
        d['value'] = value
        if num and self.decimals:
            d['decimals'] = self.decimals
            if unit and self.units:
                d['uiValue'] = '{}{}'.format(round(value,self.decimals), self.units)
            else:
                d['uiValue'] = '{}'.format(round(value,self.decimals))
        return self.append(d)

#-------------------------------------------------------------------------------
def zint(value):
    try: return int(value)
    except: return 0

#-------------------------------------------------------------------------------
def validateTextFieldNumber(rawInput, numType=float, zero=True, negative=True):
    try:
        num = numType(rawInput)
        if not zero:
            if num == 0: raise
        if not negative:
            if num < 0: raise
        return True
    except:
        return False
