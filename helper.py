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


class LimitedRangeMotor(SmartMotorBase):
    """ handle motors with a limited range of valid movements """
    _minPos = 0
    _maxPos = None
    
    def calibrate(self):
        super().calibrate()
        self._motor.on(-self._speed, False)

        def checkMotorState(state):
            print(state)
            if 'overloaded' in state or 'stalled' in state:
                return True

            return False

        self._motor.wait(checkMotorState, 10000)
        self._motor.reset()  # sets 0 point

        self._motor.on(self._speed, False)
        # self._motor.wait_until('stalled')

        self._motor.wait(checkMotorState, 10000)
        self._motor.stop()

        self._maxPos = self._motor.position
        self._motor.on_to_position(self._speed, self._maxPos / 2, True, True)
    
    @property
    def maxPos(self):
        return self._maxPos


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
            motor.on_to_position(self._speed, self._maxPos / 2, True, False)

    @property
    def maxPos(self):
        return self._maxPos

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
            self._motor.run_forever(-self._speed, False)  # TODO: non hardcoded negative speed here to reverse direction
            while self._sensor.color != 5:
                time.sleep(0.1)
            
        self._motor.reset()


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
            self._motor.run_forever(-self._speed, False)
            self._sensor.wait_for_pressed()
            
        self._motor.reset()
