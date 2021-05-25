#!/usr/bin/env python3
__author__ = 'Nino Guba'

import asyncio
import logging
import os
import sys
import threading
import time

import evdev
import rpyc
from ev3dev2 import DeviceNotFound
from ev3dev2.led import Leds
from ev3dev2.motor import (OUTPUT_A, OUTPUT_B, OUTPUT_C, OUTPUT_D, LargeMotor,
                           MoveTank)
from ev3dev2.sound import Sound
from evdev import InputDevice, categorize, ecodes


# Config
REMOTE_HOST = '10.42.0.3'

# Setup logging
logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                    format='%(message)s')
logging.getLogger().addHandler(logging.StreamHandler(sys.stderr))
logger = logging.getLogger(__name__)

## Some helpers ##


def scale(val, src, dst):
    return (float(val - src[0]) / (src[1] - src[0])) * (dst[1] - dst[0]) + dst[0]


def scale_stick(value):
    return scale(value, (0, 255), (-1000, 1000))


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
logger.info("Finding wireless controller...")
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
sound = Sound()

# Setup motors
waist_motor = LargeMotor(OUTPUT_A)
shoulder_control1 = LargeMotor(OUTPUT_B)
shoulder_control2 = LargeMotor(OUTPUT_C)
shoulder_motor = MoveTank(OUTPUT_B, OUTPUT_C)
elbow_motor = LargeMotor(OUTPUT_D)
roll_motor = remote_motor.MediumMotor(remote_motor.OUTPUT_A)
pitch_motor = remote_motor.MediumMotor(remote_motor.OUTPUT_B)
spin_motor = remote_motor.MediumMotor(remote_motor.OUTPUT_C)

try:
    grabber_motor = remote_motor.MediumMotor(remote_motor.OUTPUT_D)
    logger.info("Grabber motor detected!")
except DeviceNotFound:
    logger.info("Grabber motor not detected - running without it...")
    grabber_motor = False

# Reset motor positions to default
waist_motor.position = 0
shoulder_control1.position = 0
shoulder_control2.position = 0
shoulder_motor.position = 0
elbow_motor.position = 0
roll_motor.position = 0
pitch_motor.position = 0
spin_motor.position = 0
if grabber_motor:
    grabber_motor.position = 0

# Ratios
waist_ratio = 7.5
shoulder_ratio = 7.5
elbow_ratio = 5
roll_ratio = 7
pitch_ratio = 5
spin_ratio = 7
grabber_ratio = 24

# Define valid range of motion
waist_max = 360
waist_min = -360
if grabber_motor:
    shoulder_max = -60
    shoulder_min = 50
else:
    shoulder_max = -75
    shoulder_min = 65
elbow_max = -175
elbow_min = 0
roll_max = 180
roll_min = -180
pitch_max = 80
pitch_min = -90
spin_max = -360
spin_min = 360
grabber_max = -68
grabber_min = 0

# Define speeds
full_speed = 100
fast_speed = 75
normal_speed = 50
slow_speed = 25

forward_speed = 0
forward_side_speed = 0

upward_speed = 0
upward_side_speed = 0

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

        while running:
            logger.debug('LEFT: {}, RIGHT: {}'.format(
                turning_left, turning_right))
            print('#')
            if turning_left:
                # logger.info('moving left...')
                waist_motor.on_to_position(
                    fast_speed, waist_min*waist_ratio, True, False)  # Left
            elif turning_right:
                # logger.info('moving right...')
                waist_motor.on_to_position(
                    fast_speed, waist_max*waist_ratio, True, False)  # Right
            elif waist_motor.is_running:
                # logger.info('stop moving left/right')
                waist_motor.stop()

        logging.info('No longer running... shutting down')
        waist_motor.stop()
        shoulder_motor.stop()
        elbow_motor.stop()
        roll_motor.stop()
        pitch_motor.stop()
        spin_motor.stop()
        if grabber_motor:
            grabber_motor.stop()


motor_thread = MotorThread()
motor_thread.setDaemon(True)
motor_thread.start()

# this requires evdev >= 1.0.0 which is not available by default on ev3dev. Install it using python3-pip
# https://python-evdev.readthedocs.io/en/latest/changelog.html


async def process_input(gamepad):

    global forward_speed
    global forward_side_speed
    global upward_speed
    global upward_side_speed
    global turning_left
    global turning_right

    async for event in gamepad.async_read_loop():
        if event.type == 1:
            # logger.info(event)
            # print('event type: {}, code: {}, value: {}'.format(event.type, event.code, event.value))
            print('.')
            if event.code == 310:  # L1
                logger.info('L1')
                if event.value == 1:
                    turning_left = True
                    turning_right = False
                    logger.info('LEFT')
                    # waist_motor.on(fast_speed,True,False) #Left
                elif event.value == 0:
                    turning_left = False
                    # waist_motor.stop()
                    logger.info('STOP MOVING LEFT')

            elif event.code == 311:  # R1
                logger.info('R1')
                if event.value == 1:
                    turning_right = True
                    turning_left = False
                    logger.info('RIGHT')
                    # waist_motor.on(-fast_speed,True,False) #Right
                elif event.value == 0:
                    # waist_motor.stop()
                    turning_right = False
                    logger.info('STOP MOVING RIGHT')

# Start async input handling loop
loop = asyncio.get_event_loop()

try:
    loop.run_until_complete(process_input(gamepad))
except KeyboardInterrupt:
    logger.info('Got CTRL+C, shutting down...')
    waist_motor.stop()
    shoulder_motor.stop()
    elbow_motor.stop()
    roll_motor.stop()
    pitch_motor.stop()
    spin_motor.stop()
    if grabber_motor:
        grabber_motor.stop()
