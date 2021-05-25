#!/usr/bin/env python3
import time

class SmartMotorBase:
    """ base class for handling motors """
    _motor = None
    _speed = None
    _name = None

    def __init__(self, motor, speed=10, name=None):
        self._motor = motor
        self._speed = speed
        self._name = name

    def calibrate(self):
        print('Calibrating {}...'.format(self._name))

    def __getattr__(self, name):
        return getattr(self._motor, name)


class StaticRangeMotor(SmartMotorBase):
    _minPos = 5
    _maxPos = None
    
    def __init__(self, motor, maxPos, speed=10, name=None):
        self._maxPos = maxPos
        super().__init__(motor, speed, name)
    
    def calibrate(self):
        raise NotImplemented
    
    @property
    def maxPos(self):
        return self._maxPos

    @property
    def minPos(self):
        return self._minPos
    
    @property
    def centerPos(self):
        return (self._maxPos - self._minPos) / 2

class LimitedRangeMotor(SmartMotorBase):
    """ handle motors with a limited range of valid movements """
    _minPos = 5
    _maxPos = None

    def calibrate(self):
        super().calibrate()
        self._motor.on(-self._speed, False)

        def checkMotorState(state):
            # print(state)
            if 'overloaded' in state or 'stalled' in state:
                return True

            return False

        self._motor.wait(checkMotorState, 10000)
        self._motor.reset()  # sets 0 point

        self._motor.on(self._speed, False)
        # self._motor.wait_until('stalled')

        self._motor.wait(checkMotorState, 10000)
        self._motor.stop()

        self._maxPos = self._motor.position - 5
        self._motor.on_to_position(self._speed, self.centerPos, True, True)
        print('Motor {} found max {}'.format(self._name, self._maxPos))

    @property
    def maxPos(self):
        return self._maxPos

    @property
    def minPos(self):
        return self._minPos

    @property
    def centerPos(self):
        return (self._maxPos - self._minPos) / 2


class LimitedRangeMotorSet(LimitedRangeMotor):

    def calibrate(self):
        # super().calibrate()
        for motor in self._motor:
            motor.on(-self._speed, False)

        def checkMotorState(state):
            # print(state)
            if 'overloaded' in state or 'stalled' in state:
                return True

            return False

        self._motor[1].wait(checkMotorState, 10000)
        for motor in self._motor:
            motor.reset()  # sets 0 point

        for motor in self._motor:
            motor.on(self._speed, False)

        self._motor[1].wait(checkMotorState, 10000)
        for motor in self._motor:
            motor.stop()

        self._maxPos = self._motor[1].position
        for motor in self._motor:
            motor.on_to_position(self._speed, self.centerPos, True, False)
        
        # cant wait here because of motor set, so let's at least give it 1 second
        time.sleep(1)
        print('Motor {} found max {}'.format(self._name, self._maxPos))

    def on_to_position(self, speed, position, brake, wait):
        for motor in self._motor:
            motor.on_to_position(speed, position, brake, False)  # @TODO hardcoded no-waiting because of dual motor setup

    def reset(self):
        for motor in self._motor:
            motor.reset()

    def stop(self):
        for motor in self._motor:
            motor.stop()

    def on(self, speed):
        for motor in self._motor:
            motor.on(speed)

    @property
    def is_running(self):
        return self._motor[0].is_running


class ColorSensorMotor(SmartMotorBase):
    _sensor = None

    def __init__(self, motor, speed=10, name=None, sensor=None):
        self._sensor = sensor
        super().__init__(motor, speed, name)

    def calibrate(self):
        super().calibrate()
        if self._sensor.color != 5:
            # TODO: non hardcoded negative speed here to reverse direction
            self._motor.on(-self._speed, False)
            while self._sensor.color != 5:
                time.sleep(0.1)

        self._motor.reset()
    
    @property
    def centerPos(self):
        return 0

class TouchSensorMotor(SmartMotorBase):
    _sensor = None
    _max = None

    def __init__(self, motor, speed=10, name=None, sensor=None, max=None):
        self._sensor = sensor
        self._max = max
        super().__init__(motor, speed, name)

    def calibrate(self):
        super().calibrate()
        if not self._sensor.is_pressed:
            self._motor.on(-self._speed, False)
            self._sensor.wait_for_pressed()

        self._motor.reset()
