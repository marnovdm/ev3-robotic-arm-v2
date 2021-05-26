#!/usr/bin/env python3
__author__ = 'Nino Guba'

import logging
import os
import sys
import threading
import time

import evdev
import rpyc
# from signal import SIGINT, SIGTERM
from ev3dev2 import DeviceNotFound
from ev3dev2.led import Leds
from ev3dev2.sensor import INPUT_4
from ev3dev2.sensor.lego import ColorSensor
from ev3dev2.motor import (OUTPUT_A, OUTPUT_B, OUTPUT_C, OUTPUT_D, LargeMotor,
                           MoveTank)
# from ev3dev2.sound import Sound
from evdev import InputDevice, categorize, ecodes

from helper import LimitedRangeMotor, LimitedRangeMotorSet, ColorSensorMotor, StaticRangeMotor


# Config
REMOTE_HOST = '10.42.0.3'

# Define speeds
FULL_SPEED = 100
FAST_SPEED = 75
NORMAL_SPEED = 50
SLOW_SPEED = 25


# Setup logging
logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                    format='%(message)s')
# logging.getLogger().addHandler(logging.StreamHandler(sys.stderr))
logger = logging.getLogger(__name__)


## Some helpers ##
def scale(val, src, dst):
    return (float(val - src[0]) / (src[1] - src[0])) * (dst[1] - dst[0]) + dst[0]


def scale_stick(value, deadzone=10, scale_to=80, invert=False):
    result = scale(value, (0, 255), (-scale_to, scale_to))

    if deadzone and result < deadzone and result > -deadzone:
        result = 0
    
    if invert:
        result *= -1

    return result


def clean_shutdown():
    logger.info('Shutting down...')
    running = False
    logger.info('waist..')
    waist_motor.stop()
    logger.info('shoulder..')
    shoulder_motors.stop()
    logger.info('elbow..')
    elbow_motor.stop()
    logger.info('pitch..')
    pitch_motor.reset()
    pitch_motor.stop()
    logger.info('roll..')
    roll_motor.stop()
    logger.info('spin..')
    spin_motor.stop()

    if grabber_motor:
        logger.info('grabber..')
        grabber_motor.stop()

    logger.info('Shutdown completed.')

# Reset motor positions to default


def reset_motors():
    logger.info("Resetting motors...")
    waist_motor.reset()
    # shoulder_control1.reset()
    # shoulder_control2.reset()
    shoulder_motors.reset()
    elbow_motor.reset()
    roll_motor.reset()
    pitch_motor.reset()
    spin_motor.reset()
    if grabber_motor:
        grabber_motor.reset()


def back_to_start():
    roll_motor.on_to_position(NORMAL_SPEED, roll_motor.centerPos, True, True)
    pitch_motor.on_to_position(NORMAL_SPEED, 0, True, True)
    spin_motor.on_to_position(NORMAL_SPEED, 0, True, False)

    if grabber_motor:
        grabber_motor.on_to_position(NORMAL_SPEED, grabber_motor.centerPos, True, True)

    elbow_motor.on_to_position(SLOW_SPEED, elbow_motor.centerPos, True, True)
    shoulder_motors.on_to_position(SLOW_SPEED, shoulder_motors.centerPos, True, True)
    # shoulder_control1.on_to_position(SLOW_SPEED,0,True,True)
    # shoulder_control2.on_to_position(SLOW_SPEED,0,True,True)
    waist_motor.on_to_position(FAST_SPEED, waist_motor.centerPos, True, True)


## Initial setup ##

# RPyC
# Setup on slave EV3: https://ev3dev-lang.readthedocs.io/projects/python-ev3dev/en/stable/rpyc.html
# Create a RPyC connection to the remote ev3dev device.
# Use the hostname or IP address of the ev3dev device.
# If this fails, verify your IP connectivty via ``ping X.X.X.X``
logger.info("Connecting RPyC to {}...".format(REMOTE_HOST))
# change this IP address for your slave EV3 brick
conn = rpyc.classic.connect(REMOTE_HOST)
#remote_ev3 = conn.modules['ev3dev.ev3']
remote_motor = conn.modules['ev3dev2.motor']
remote_led = conn.modules['ev3dev2.led']
logger.info("RPyC started succesfully")

# Gamepad
# If bluetooth is not available, check https://github.com/ev3dev/ev3dev/issues/1314
logger.info("Connecting wireless controller...")
devices = [InputDevice(fn) for fn in evdev.list_devices()]
# for device in devices:
#     logger.info("{}".format(device.name))

ps4gamepad = devices[0].fn      # PS4 gamepad
# ps4motion = devices[1].fn      # PS4 accelerometer
# ps4touchpad = devices[2].fn    # PS4 touchpad

gamepad = InputDevice(ps4gamepad)

# LEDs
leds = Leds()
remote_leds = remote_led.Leds()

# Sound
# sound = Sound()

# Sensors
color_sensor = ColorSensor(INPUT_4)
color_sensor.mode = ColorSensor.MODE_COL_COLOR

# Primary EV3
waist_motor = ColorSensorMotor(LargeMotor(
    OUTPUT_A), speed=40, name='waist', sensor=color_sensor)
# shoulder_control1 = LargeMotor(OUTPUT_B)
# shoulder_control2 = LargeMotor(OUTPUT_C)
shoulder_motors = LimitedRangeMotorSet(
    [LargeMotor(OUTPUT_B), LargeMotor(OUTPUT_C)], speed=30, name='shoulder')
elbow_motor = LimitedRangeMotor(LargeMotor(OUTPUT_D), speed=30, name='elbow')

# Secondary EV3
roll_motor = LimitedRangeMotor(remote_motor.MediumMotor(
    remote_motor.OUTPUT_A), speed=30, name='roll')
pitch_motor = LimitedRangeMotor(remote_motor.MediumMotor(
    remote_motor.OUTPUT_B), speed=10, name='pitch')
spin_motor = StaticRangeMotor(remote_motor.MediumMotor(
    remote_motor.OUTPUT_C), maxPos=14*360, speed=20, name='spin')

try:
    grabber_motor = LimitedRangeMotor(
        remote_motor.MediumMotor(remote_motor.OUTPUT_D))
    logger.info("Grabber motor detected!")
except DeviceNotFound:
    logger.info("Grabber motor not detected - running without it...")
    grabber_motor = False

reset_motors()

# Ratios
pitch_ratio = 5
spin_ratio = 7
grabber_ratio = 24

# Not calibrated yet, hardcoded for now:
pitch_max = 80
pitch_min = -90
spin_max = -360
spin_min = 360
grabber_max = -68
grabber_min = 0

# Variables for stick input
shoulder_speed = 0
elbow_speed = 0

# State variables
turning_left = False
turning_right = False
roll_left = False
roll_right = False
pitch_up = False
pitch_down = False
spin_left = False
spin_right = False
grabber_open = False
grabber_close = False

# We are running!
running = True


def calibrate_motors():
    logger.info('Calibrating motors...')
    shoulder_motors.calibrate()
    roll_motor.calibrate()
    elbow_motor.calibrate()
    waist_motor.calibrate()
    # pitch_motor.calibrate()  # needs to be more robust, gear slips now instead of stalling the motor
    if grabber_motor:
        grabber_motor.calibrate()

class MotorThread(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)

    def run(self):
        logger.info("Engine running!")
        os.system('setfont Lat7-Terminus12x6')
        leds.set_color("LEFT", "BLACK")
        leds.set_color("RIGHT", "BLACK")
        remote_leds.set_color("LEFT", "BLACK")
        remote_leds.set_color("RIGHT", "BLACK")
        # sound.play_song((('C4', 'e'), ('D4', 'e'), ('E5', 'q')))
        leds.set_color("LEFT", "GREEN")
        leds.set_color("RIGHT", "GREEN")
        remote_leds.set_color("LEFT", "GREEN")
        remote_leds.set_color("RIGHT", "GREEN")

        logger.info("Starting main loop...")
        while running:
            if shoulder_speed != 0:
                if shoulder_speed > 0:
                    shoulder_motors.on_to_position(shoulder_speed, shoulder_motors.minPos, True, False)
                else:
                    shoulder_motors.on_to_position(shoulder_speed, shoulder_motors.maxPos, True, False)
            elif shoulder_motors.is_running:
                shoulder_motors.stop()

            if elbow_speed != 0:
                if elbow_speed > 0:
                    elbow_motor.on_to_position(elbow_speed, elbow_motor.minPos, True, False)
                else:
                    elbow_motor.on_to_position(elbow_speed, elbow_motor.maxPos, True, False)
            elif elbow_motor.is_running:
                elbow_motor.stop()

            if not waist_motor.is_running and turning_left:
                # logger.info('moving left...')
                waist_motor.on(-FAST_SPEED, False)  # Left
            elif not waist_motor.is_running and turning_right:
                # logger.info('moving right...')
                waist_motor.on(FAST_SPEED, False)  # Right
            elif not turning_left and not turning_right and waist_motor.is_running:
                # logger.info('stopped moving left/right')
                waist_motor.stop()

            if not roll_motor.is_running and roll_left:
                roll_motor.on_to_position(
                    SLOW_SPEED, roll_motor.minPos, True, False)  # Left
            elif not roll_motor.is_running and roll_right:
                roll_motor.on_to_position(
                    SLOW_SPEED, roll_motor.maxPos, True, False)  # Right
            elif not roll_left and not roll_right and roll_motor.is_running:
                roll_motor.stop()

            if not pitch_motor.is_running and pitch_up:
                pitch_motor.on_to_position(
                    SLOW_SPEED, pitch_max*pitch_ratio, True, False)  # Up
            elif not pitch_motor.is_running and pitch_down:
                pitch_motor.on_to_position(
                    SLOW_SPEED, pitch_min*pitch_ratio, True, False)  # Down
            elif not pitch_up and not pitch_down and pitch_motor.is_running:
                pitch_motor.stop()

            if not spin_motor.is_running and spin_left:
                spin_motor.on_to_position(
                    SLOW_SPEED, spin_motor.minPos, True, False)  # Left
            elif not spin_motor.is_running and spin_right:
                spin_motor.on_to_position(
                    SLOW_SPEED, spin_motor.maxPos, True, False)  # Right
            elif not spin_left and not spin_right and spin_motor.is_running:
                spin_motor.stop()

            if grabber_motor:
                if grabber_open:
                    grabber_motor.on_to_position(
                        NORMAL_SPEED, grabber_motor.maxPos, True, True)  # Close
                    # grabber_motor.stop()
                elif grabber_close:
                    grabber_motor.on_to_position(
                        NORMAL_SPEED, grabber_motor.minPos, True, True)  # Open
                    # grabber_motor.stop()
                elif grabber_motor.is_running:
                    grabber_motor.stop()


try:
    calibrate_motors()

    motor_thread = MotorThread()
    motor_thread.setDaemon(True)
    motor_thread.start()

    for event in gamepad.read_loop():  # this loops infinitely
        if event.type == 3:
            # logger.info(event)
            if event.code == 0:  # Left stick X-axis
                shoulder_speed = scale_stick(event.value, invert=True)
            elif event.code == 3:  # Right stick X-axis
                elbow_speed = -scale_stick(event.value, invert=True)

        elif event.type == 1:

            if event.code == 310:  # L1
                if event.value == 1 and not turning_left:
                    turning_right = False
                    turning_left = True
                elif event.value == 0 and turning_left:
                    turning_left = False

            elif event.code == 311:  # R1
                if event.value == 1 and not turning_right:
                    turning_left = False
                    turning_right = True
                elif event.value == 0 and turning_right:
                    turning_right = False

            elif event.code == 308:  # Square
                if event.value == 1:
                    roll_right = False
                    roll_left = True
                elif event.value == 0:
                    roll_left = False

            elif event.code == 305:  # Circle
                if event.value == 1:
                    roll_left = False
                    roll_right = True
                elif event.value == 0:
                    roll_right = False

            elif event.code == 307:  # Triangle
                if event.value == 1:
                    pitch_down = False
                    pitch_up = True
                elif event.value == 0:
                    pitch_up = False

            elif event.code == 304:  # X
                if event.value == 1:
                    pitch_up = False
                    pitch_down = True
                elif event.value == 0:
                    pitch_down = False

            elif event.code == 312:  # L2
                if event.value == 1:
                    spin_right = False
                    spin_left = True
                elif event.value == 0:
                    spin_left = False

            elif event.code == 313:  # R2
                if event.value == 1:
                    spin_left = False
                    spin_right = True
                elif event.value == 0:
                    spin_right = False

            elif event.code == 318:  # R3
                if event.value == 1:
                    if grabber_open:
                        grabber_open = False
                        grabber_close = True
                    else:
                        grabber_open = True
                        grabber_close = False
            elif event.code == 314 and event.value == 1:  # Share
                reset_motors()

            elif event.code == 315 and event.value == 1:  # Options
                # Reset
                back_to_start()

            elif event.code == 316 and event.value == 1:  # PS
                logger.info("Engine stopping!")
                running = False

                # Reset
                back_to_start()

                # sound.play_song((('E5', 'e'), ('C4', 'e')))
                leds.set_color("LEFT", "BLACK")
                leds.set_color("RIGHT", "BLACK")
                remote_leds.set_color("LEFT", "BLACK")
                remote_leds.set_color("RIGHT", "BLACK")

                time.sleep(1)  # Wait for the motor thread to finish
                break


except KeyboardInterrupt:
    clean_shutdown()
