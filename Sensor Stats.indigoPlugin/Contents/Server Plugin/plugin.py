#! /usr/bin/env python
# -*- coding: utf-8 -*-
####################
# Copyright (c) 2016, Perceptive Automation, LLC. All rights reserved.
# http://www.indigodomo.com

import indigo
import time
import math
import random
import numpy as stats

# Note the "indigo" module is automatically imported and made available inside
# our global name space by the host process.

################################################################################
# Globals

################################################################################
class Plugin(indigo.PluginBase):

    #-------------------------------------------------------------------------------
    def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
        super(Plugin, self).__init__(pluginId, pluginDisplayName, pluginVersion, pluginPrefs)

    #-------------------------------------------------------------------------------
    # Start, Stop and Config changes
    #-------------------------------------------------------------------------------
    def startup(self):
        self.debug = self.pluginPrefs.get("showDebugInfo",False)
        self.logger.debug(u"startup")
        if self.debug:
            self.logger.debug(u"Debug logging enabled")
        self.deviceDict = dict()

        indigo.devices.subscribeToChanges()

    #-------------------------------------------------------------------------------
    def shutdown(self):
        self.logger.debug(u"shutdown")
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
                self.sleep(1)
        except self.StopThread:
            pass

    #-------------------------------------------------------------------------------
    # Device Methods
    #-------------------------------------------------------------------------------
    def deviceStartComm(self, dev):
        self.logger.debug(f"deviceStartComm: {dev.name}")
        if dev.configured:
            if dev.deviceTypeId == 'SensorStats':
                self.deviceDict[dev.id] = SensorStats(dev, self.logger)
            elif dev.deviceTypeId == 'SinewaveDummySensor':
                self.deviceDict[dev.id] = SinewaveDummySensor(dev, self.logger)
            elif dev.deviceTypeId == 'RandomDummySensor':
                self.deviceDict[dev.id] = RandomDummySensor(dev, self.logger)

    #-------------------------------------------------------------------------------
    def deviceStopComm(self, dev):
        self.logger.debug(f"deviceStopComm: {dev.name}")
        if dev.id in self.deviceDict:
            del self.deviceDict[dev.id]

    #-------------------------------------------------------------------------------
    def validateDeviceConfigUi(self, valuesDict, typeId, devId):
        errorsDict = indigo.Dict()

        if typeId == 'SensorStats':
            if len(valuesDict.get('sensors',[])) == 0:
                errorsDict['sensors'] = errorsDict['thermostats'] = "At least one sensor required."
            else:
                for sensor_id in valuesDict['sensors']:
                    try:
                        sensor = indigo.devices[int(sensor_id)]
                        if isinstance(sensor, indigo.ThermostatDevice):
                            try:
                                if valuesDict['therm_type'] == 'temperature':
                                    value = sensor.temperatures[0]
                                elif valuesDict['therm_type'] == 'humidity':
                                    value = sensor.humidities[0]
                            except IndexError:
                                errorsDict['sensors'] = f"Selected thermostat doesn't support {valuesDict['therm_type']} value."
                    except:
                        sensors = valuesDict['sensors']
                        sensors.remove(sensor_id)
                        valuesDict['sensors'] = sensors

        elif typeId in ['SinewaveDummySensor','RandomDummySensor']:
            for key in (set(valuesDict.keys()) & set('minValue','maxValue','period')):
                if not validateTextFieldNumber(valuesDict.get(key)):
                    errorsDict[key] = 'Must be a number'
            if valuesDict['minValue'] > valuesDict['maxValue']:
                errorsDict['minValue'] = 'Must be less than Maximum Value'
                errorsDict['maxValue'] = 'Must be greater than Minimum Value'

        if len(errorsDict) > 0:
            self.logger.debug(f"validate device config error: \n{errorsDict}")
            return (False, valuesDict, errorsDict)
        return (True, valuesDict)

    #-------------------------------------------------------------------------------
    # Action Methods
    #-------------------------------------------------------------------------------
    def actionControlSensor(self, action, device):
        if action.sensorAction == indigo.kUniversalAction.RequestStatus:
            self.logger.info(f'"{device.name}" status update')
            instance = self.deviceDict[device.id]
            instance.statusRequest()
        else:
            self.logger.debug(f'"{dev.name}" {str(action.speedControlAction)} request ignored')

    #-------------------------------------------------------------------------------
    # Menu Methods
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

    #-------------------------------------------------------------------------------
    # callbacks
    #-------------------------------------------------------------------------------
    def getSensorDeviceList(self, filter="", valuesDict=None, typeId="", targetId=0):
        selfList = []
        for dev in indigo.devices.iter(filter='self'):
            if dev.deviceTypeId == 'SensorStats':
                selfList.append(dev.id)

        sensorList = []
        for dev in indigo.devices.iter(filter='indigo.sensor, props.SupportsSensorValue'):
            if dev.id not in selfList:
                sensorList.append((dev.id,dev.name))

        thermList = [(dev.id,dev.name) for dev in indigo.devices.iter(filter='indigo.thermostat')]

        returnList = sensorList + [(0,'---')] + thermList
        if filter == 'menu':
            returnList = [(0,'')] + returnList
        return returnList

###############################################################################
# Classes
###############################################################################
class SensorStats(object):
    #-------------------------------------------------------------------------------
    def __init__(self, device, logger):
        self.logger = logger
        self.dev = device
        self.props = device.pluginProps

        self.sensor_ids = [int(sid) for sid in self.props.get('sensors',[])]
        self.special_id = zint(self.props.get('special',0))

        self.decimals = int(self.props.get('decimals',1))
        self.units = self.props.get('units','')
        self.display = self.props.get('display','all_avg')
        self.therm_type = self.props.get('therm_type','temperature')

        self.statusRequest()

    #-------------------------------------------------------------------------------
    def deviceUpdated(self, old_dev, new_dev):
        update = False
        if new_dev.id in self.sensor_values.keys():
            self.sensor_names[new_dev.id] = new_dev.name
            self.sensor_values[new_dev.id] = self._getSensorValue(new_dev)
            update = True
        if new_dev.id == self.special_id:
            self.special_value = self._getSensorValue(new_dev)
            update = True
        if update:
            self.updateInstance()

    #-------------------------------------------------------------------------------
    def statusRequest(self):
        self.sensor_values = dict()
        self.sensor_names = dict()

        for sid in self.sensor_ids:
            sensor = indigo.devices[sid]
            self.sensor_names[sid] = sensor.name
            self.sensor_values[sid] = self._getSensorValue(sensor)

        if self.special_id:
            self.special_value = self._getSensorValue(indigo.devices[self.special_id])

        self.updateInstance()

    #-------------------------------------------------------------------------------
    def updateInstance(self):
        values = list(self.sensor_values.values())
        all_avg = float(stats.mean(values))
        all_med = float(stats.median(values))
        all_dev = float(stats.std(values))
        max_val = max(values)
        max_var = max_val - all_avg
        max_dev = max_var / all_dev if all_dev else 0
        min_val = min(values)
        min_var = min_val - all_avg
        min_dev = min_var / all_dev if all_dev else 0
        all_rng = max_val - min_val

        for sid in self.sensor_values.keys():
            if self.sensor_values[sid] == max_val:
                max_id = sid
                max_name = self.sensor_names[sid]
                break
        for sid in self.sensor_values.keys():
            if self.sensor_values[sid] == min_val:
                min_id = sid
                min_name = self.sensor_names[sid]
                break

        if self.special_id:
            spc_val = self.special_value
        else:
            spc_val = all_avg
        spc_var = spc_val - all_avg
        spc_dev = spc_var / all_dev if all_dev else 0
        spc_max = spc_val >= max_val
        spc_min = spc_val <= min_val

        state_list = StateList(self.decimals, self.units)
        state_list.appendState('all_avg', all_avg)
        state_list.appendState('all_med', all_med)
        state_list.appendState('all_dev', all_dev, unit=False)
        state_list.appendState('all_rng', all_rng)
        state_list.appendState('max_val', max_val)
        state_list.appendState('max_var', max_var)
        state_list.appendState('max_dev', max_dev, unit=False)
        state_list.appendState('max_id',  max_id,  num=False)
        state_list.appendState('max_name',max_name,num=False)
        state_list.appendState('min_val', min_val)
        state_list.appendState('min_var', min_var)
        state_list.appendState('min_dev', min_dev, unit=False)
        state_list.appendState('min_id',  min_id,  num=False)
        state_list.appendState('min_name',min_name,num=False)
        state_list.appendState('spc_val', spc_val)
        state_list.appendState('spc_var', spc_var)
        state_list.appendState('spc_dev', spc_dev, unit=False)
        state_list.appendState('spc_max', spc_max, num=False)
        state_list.appendState('spc_min', spc_min, num=False)

        for d in state_list:
            if d['key'] == self.display:
                state_list.append({'key':'sensorValue', 'value':d['value'], 'uiValue':d.get('uiValue',None), 'decimals':d.get('decimals',None)})
                break

        self.dev.updateStatesOnServer(state_list)

    #-------------------------------------------------------------------------------
    def tick(self):
        pass

    #-------------------------------------------------------------------------------
    # helpers
    #-------------------------------------------------------------------------------
    def _getSensorValue(self, sensor):
        if isinstance(sensor, indigo.SensorDevice):
            value = sensor.sensorValue
        elif isinstance(sensor, indigo.ThermostatDevice):
            if self.therm_type == 'temperature':
                value = sensor.temperatures[0]
            elif self.therm_type == 'humidity':
                value = sensor.humidities[0]
        return value

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
        if num and (self.decimals is not None):
            d['decimals'] = self.decimals
            if unit and self.units:
                d['uiValue'] = f'{round(value,self.decimals)}{self.units}'
            else:
                d['uiValue'] = f'{round(value,self.decimals)}'
        return self.append(d)

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
    def statusRequest(self):
        pass

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

        self.last_time = 0.0

    #-------------------------------------------------------------------------------
    def deviceUpdated(self, old_dev, new_dev):
        pass

    #-------------------------------------------------------------------------------
    def statusRequest(self):
        pass

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
