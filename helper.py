#!/usr/bin/env python3

class SmartMotor:
    _motor = None
    _speed = None
    _name = None
    _minPos = 0
    _maxPos = None

    def __init__(self, motor, speed=10, name=None):
        self._motor = motor
        self._speed = speed
        self._name = name
        # self._motor.reset()

    def calibrate(self):
        self._motor.on(-self._speed, False)
        self._motor.wait_until('stalled')
        self._motor.reset()
        self._motor.on(self._speed, False)
        self._motor.wait_until('stalled')
        self._motor.stop()
        self._maxPos = self._motor.position
        self._motor.on_to_position(self._speed, self._maxPos / 2, True, False)
    
    @property
    def maxPos(self):
        return self._maxPos

    def __getattr__(self, name):
        return getattr(self._motor, name)
