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
# from signal import SIGINT, SIGTERM
from ev3dev2 import DeviceNotFound
from ev3dev2.led import Leds
from ev3dev2.motor import (OUTPUT_A, OUTPUT_B, OUTPUT_C, OUTPUT_D, LargeMotor,
                           MoveTank)
from ev3dev2.sound import Sound
from evdev import InputDevice, categorize, ecodes


# Config
REMOTE_HOST = '10.42.0.3'
ASYNC_GAMEPAD = False

# Setup logging
logging.basicConfig(level=logging.INFO, stream=sys.stdout, format='%(message)s')
# logging.getLogger().addHandler(logging.StreamHandler(sys.stderr))
logger = logging.getLogger(__name__)

## Some helpers ##
def scale(val, src, dst):
    return (float(val - src[0]) / (src[1] - src[0])) * (dst[1] - dst[0]) + dst[0]

def scale_stick(value, deadzone=100):
    result = scale(value,(0,255),(-1000,1000))
    
    if deadzone and result < 100 and result > -100:
        result = 0
        
    return result


## Initial setup ##

# RPyC
# Setup on slave EV3: https://ev3dev-lang.readthedocs.io/projects/python-ev3dev/en/stable/rpyc.html
# Create a RPyC connection to the remote ev3dev device.
# Use the hostname or IP address of the ev3dev device.
# If this fails, verify your IP connectivty via ``ping X.X.X.X``
logger.info("Connecting RPyC to {}...".format(REMOTE_HOST))
conn = rpyc.classic.connect(REMOTE_HOST) # change this IP address for your slave EV3 brick
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
#ps4motion = devices[1].fn      # PS4 accelerometer
#ps4touchpad = devices[2].fn    # PS4 touchpad

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
shoulder_motor = MoveTank(OUTPUT_B,OUTPUT_C)
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

def calibrate_motors():
    logger.info('Calibrating motors...')
    
    # @TODO use color sensor or something
    # logger.info('waist motor...')
    # waist_motor.wait_until('stalled')
    # logger.info('OK')
    
    logger.info('shoulder motor, finding minimum...')
    shoulder_motor.on(-10, False)
    shoulder_motor.wait_until('stalled')
    shoulder_motor.reset()
    logger.info('shoulder motor, finding maximum...')
    shoulder_motor.on(100, False)
    # time.sleep(1)
    shoulder_motor.wait_until('stalled')
    shoulder_motor.stop()
    logger.info('OK, max at {}'.format(shoulder_motor.position))
    
    logger.info('elbow motor, finding minimum...')
    elbow_motor.on(-10, False)
    elbow_motor.wait_until('stalled')
    elbow_motor.reset()
    logger.info('elbow motor, finding maximum...')
    elbow_motor.on(10, False)
    elbow_motor.wait_until('stalled')
    elbow_motor.stop()
    logger.info('OK, max at {}'.format(elbow_motor.position))

    # @TODO check if these are wired correctly
    # roll_motor.wait_until('stalled')
    # pitch_motor.wait_until('stalled')
    # spin_motor.wait_until('stalled')

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
        
        logger.info("Stabilizing...")
        time.sleep(2)
        logger.info("Starting main loop...")
        while running:
            logger.debug('{},{},{},{},{},{},{},{}'.format(turning_left, turning_right, roll_left, roll_right, pitch_up, pitch_down, spin_left, spin_right))
            if forward_speed > 0 and shoulder_control1.position > ((shoulder_max*shoulder_ratio)+100):
                logger.debug('shoulder motor up')
                shoulder_motor.on( -normal_speed,-normal_speed)
            elif forward_speed < 0 and shoulder_control1.position < ((shoulder_min*shoulder_ratio)-100):
                logger.debug('shoulder motor down')
                shoulder_motor.on( normal_speed,normal_speed)
            elif shoulder_motor.is_running:
                logger.debug('shoulder motor stop')
                shoulder_motor.stop()

            if not elbow_motor.is_running and upward_speed > 0:
                elbow_motor.on_to_position(normal_speed,elbow_max*elbow_ratio,True,False) #Up
            elif not elbow_motor.is_running and upward_speed < 0:
                elbow_motor.on_to_position(normal_speed,elbow_min*elbow_ratio,True,False) #Down
            elif upward_speed == 0 and elbow_motor.is_running:
                elbow_motor.stop()

            if not waist_motor.is_running and turning_left:
                logger.info('moving left...')
                waist_motor.on_to_position(fast_speed,waist_min*waist_ratio,True,False) #Left
                # waist_motor.on(fast_speed,True,False) #Left
            elif not waist_motor.is_running and turning_right:
                logger.info('moving right...')
                waist_motor.on_to_position(fast_speed,waist_max*waist_ratio,True,False) #Right
            elif not turning_left and not turning_right and waist_motor.is_running:
                logger.info('stopped moving left/right')
                waist_motor.stop()

            if not roll_motor.is_running and roll_left:
                roll_motor.on_to_position(normal_speed,roll_min*roll_ratio,True,False) #Left
            elif not roll_motor.is_running and roll_right:
                roll_motor.on_to_position(normal_speed,roll_max*roll_ratio,True,False) #Right
            elif not roll_left and not roll_right and roll_motor.is_running:
                roll_motor.stop()

            if not pitch_motor.is_running and pitch_up:
                pitch_motor.on_to_position(normal_speed,pitch_max*pitch_ratio,True,False) #Up
            elif not pitch_motor.is_running and pitch_down:
                pitch_motor.on_to_position(normal_speed,pitch_min*pitch_ratio,True,False) #Down
            elif not pitch_up and not pitch_down and pitch_motor.is_running:
                pitch_motor.stop()

            if not spin_motor.is_running and spin_left:
                spin_motor.on_to_position(normal_speed,spin_min*spin_ratio,True,False) #Left
            elif not spin_motor.is_running and spin_right:
                spin_motor.on_to_position(normal_speed,spin_max*spin_ratio,True,False) #Right
            elif not spin_left and not spin_right and spin_motor.is_running:
                spin_motor.stop()

            if grabber_motor:
                if grabber_open:
                    grabber_motor.on_to_position(normal_speed,grabber_max*grabber_ratio,True,True) #Close
                    grabber_motor.stop()
                elif grabber_close:
                    grabber_motor.on_to_position(normal_speed,grabber_min*grabber_ratio,True,True) #Open
                    grabber_motor.stop()
                elif grabber_motor.is_running:
                    grabber_motor.stop()
        
        logging.info('No longer running... shutting down')
        waist_motor.stop()
        shoulder_motor.stop()
        elbow_motor.stop()
        roll_motor.stop()
        pitch_motor.stop()
        spin_motor.stop()
        if grabber_motor:
            grabber_motor.stop()


# calibrate_motors()

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
    global roll_left
    global roll_right
    global pitch_up
    global pitch_down
    global spin_left
    global spin_right

    async for event in gamepad.async_read_loop():
        if event.type == 3:
            # logger.info(event)
            if event.code == 0:  # Left stick X-axis
                forward_speed = scale_stick(event.value)
            #if event.code == 1:  # Left stick Y-axis
            #    forward_side_speed = scale_stick(event.value)
            elif event.code == 3:  # Right stick X-axis
                upward_speed = -scale_stick(event.value)
            #if event.code == 4:  # Right stick Y-axis
            #    upward_side_speed = scale_stick(event.value)
            # else:
            #     logger.info('no action')
            
            # if forward_speed != 0 and forward_speed < 100 and forward_speed > -100:
            #     # logger.info('resetting forward_speed from {} to 0'.format(forward_speed))
            #     forward_speed = 0
            
            # if upward_speed != 0 and upward_speed < 100 and upward_speed > -100:
            #     # logger.info('resetting upward_speed from {} to 0'.format(upward_speed))
            #     upward_speed = 0
            
            # if forward_side_speed != 0 and forward_side_speed < 100 and forward_side_speed > -100:
            #     logger.info('resetting forward_side_speed from {} to 0'.format(forward_side_speed))
            #     forward_side_speed = 0
            
            # if upward_side_speed != 0 and upward_side_speed < 100 and upward_side_speed > -100:
            #     logger.info('resetting upward_side_speed from {} to 0'.format(upward_side_speed))
            #     upward_side_speed = 0

        elif event.type == 1:
            # logger.info(event)
            # print('event type: {}, code: {}, value: {}'.format(event.type, event.code, event.value))

            if event.code == 310:  # L1
                # logger.info('L1')
                if event.value == 1 and not turning_left:
                    turning_right = False
                    turning_left = True
                    logger.info('LEFT')
                    # waist_motor.on(fast_speed,True,False) #Left
                elif event.value == 0 and turning_left:
                    turning_left = False
                    # waist_motor.stop()
                    logger.info('STOP MOVING LEFT')

            elif event.code == 311:  # R1
                if event.value == 1 and not turning_right:
                    turning_left = False
                    turning_right = True
                    logger.info('RIGHT')
                    # waist_motor.on(-fast_speed,True,False) #Right
                elif event.value == 0 and turning_right:
                    # waist_motor.stop()
                    turning_right = False
                    logger.info('STOP MOVING RIGHT')

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

            elif event.code == 315 and event.value == 1:  # Options
                # Reset
                roll_motor.on_to_position(normal_speed,0,True,False)
                pitch_motor.on_to_position(normal_speed,0,True,False)
                spin_motor.on_to_position(normal_speed,0,True,False)
                if grabber_motor:
                    grabber_motor.on_to_position(normal_speed,0,True,True)
                elbow_motor.on_to_position(slow_speed,0,True,False)
                shoulder_control1.on_to_position(slow_speed,0,True,False)
                shoulder_control2.on_to_position(slow_speed,0,True,False)
                waist_motor.on_to_position(fast_speed,0,True,True)

            elif event.code == 316 and event.value == 1:  # PS
                logger.info("Engine stopping!")
                running = False

                # Reset
                roll_motor.on_to_position(normal_speed,0,True,False)
                pitch_motor.on_to_position(normal_speed,0,True,False)
                spin_motor.on_to_position(normal_speed,0,True,False)
                if grabber_motor:
                    grabber_motor.on_to_position(normal_speed,0,True,True)
                elbow_motor.on_to_position(slow_speed,0,True,False)
                shoulder_control1.on_to_position(slow_speed,0,True,False)
                shoulder_control2.on_to_position(slow_speed,0,True,False)
                waist_motor.on_to_position(fast_speed,0,True,True)

                sound.play_song((('E5', 'e'), ('C4', 'e')))
                leds.set_color("LEFT", "BLACK")
                leds.set_color("RIGHT", "BLACK")
                remote_leds.set_color("LEFT", "BLACK")
                remote_leds.set_color("RIGHT", "BLACK")

                time.sleep(1)  # Wait for the motor thread to finish
                break


if ASYNC_GAMEPAD:
    logger.info('Running ASYNC gamepad loop...')
    # Start async input handling loop
    loop = asyncio.get_event_loop()
    # for signal in [SIGINT, SIGTERM]:
    #     loop.add_signal_handler(signal, main_task.cancel)

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
else:
    logger.info('Running SYNC gamepad loop...')
    for event in gamepad.read_loop():   # this loops infinitely
        if event.type == 3:
            # logger.info(event)
            if event.code == 0:  # Left stick X-axis
                forward_speed = scale_stick(event.value)
            #if event.code == 1:  # Left stick Y-axis
            #    forward_side_speed = scale_stick(event.value)
            elif event.code == 3:  # Right stick X-axis
                upward_speed = -scale_stick(event.value)
            #if event.code == 4:  # Right stick Y-axis
            #    upward_side_speed = scale_stick(event.value)
            # else:
            #     logger.info('no action')
            
            # if forward_speed != 0 and forward_speed < 100 and forward_speed > -100:
            #     # logger.info('resetting forward_speed from {} to 0'.format(forward_speed))
            #     forward_speed = 0
            
            # if upward_speed != 0 and upward_speed < 100 and upward_speed > -100:
            #     # logger.info('resetting upward_speed from {} to 0'.format(upward_speed))
            #     upward_speed = 0
            
            # if forward_side_speed != 0 and forward_side_speed < 100 and forward_side_speed > -100:
            #     logger.info('resetting forward_side_speed from {} to 0'.format(forward_side_speed))
            #     forward_side_speed = 0
            
            # if upward_side_speed != 0 and upward_side_speed < 100 and upward_side_speed > -100:
            #     logger.info('resetting upward_side_speed from {} to 0'.format(upward_side_speed))
            #     upward_side_speed = 0

        elif event.type == 1:
            # logger.info(event)
            # print('event type: {}, code: {}, value: {}'.format(event.type, event.code, event.value))

            if event.code == 310:  # L1
                # logger.info('L1')
                if event.value == 1 and not turning_left:
                    turning_right = False
                    turning_left = True
                    logger.info('LEFT')
                    # waist_motor.on(fast_speed,True,False) #Left
                elif event.value == 0 and turning_left:
                    turning_left = False
                    # waist_motor.stop()
                    logger.info('STOP MOVING LEFT')

            elif event.code == 311:  # R1
                if event.value == 1 and not turning_right:
                    turning_left = False
                    turning_right = True
                    logger.info('RIGHT')
                    # waist_motor.on(-fast_speed,True,False) #Right
                elif event.value == 0 and turning_right:
                    # waist_motor.stop()
                    turning_right = False
                    logger.info('STOP MOVING RIGHT')

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

            elif event.code == 315 and event.value == 1:  # Options
                # Reset
                roll_motor.on_to_position(normal_speed,0,True,False)
                pitch_motor.on_to_position(normal_speed,0,True,False)
                spin_motor.on_to_position(normal_speed,0,True,False)
                if grabber_motor:
                    grabber_motor.on_to_position(normal_speed,0,True,True)
                elbow_motor.on_to_position(slow_speed,0,True,False)
                shoulder_control1.on_to_position(slow_speed,0,True,False)
                shoulder_control2.on_to_position(slow_speed,0,True,False)
                waist_motor.on_to_position(fast_speed,0,True,True)

            elif event.code == 316 and event.value == 1:  # PS
                logger.info("Engine stopping!")
                running = False

                # Reset
                roll_motor.on_to_position(normal_speed,0,True,False)
                pitch_motor.on_to_position(normal_speed,0,True,False)
                spin_motor.on_to_position(normal_speed,0,True,False)
                if grabber_motor:
                    grabber_motor.on_to_position(normal_speed,0,True,True)
                elbow_motor.on_to_position(slow_speed,0,True,False)
                shoulder_control1.on_to_position(slow_speed,0,True,False)
                shoulder_control2.on_to_position(slow_speed,0,True,False)
                waist_motor.on_to_position(fast_speed,0,True,True)

                sound.play_song((('E5', 'e'), ('C4', 'e')))
                leds.set_color("LEFT", "BLACK")
                leds.set_color("RIGHT", "BLACK")
                remote_leds.set_color("LEFT", "BLACK")
                remote_leds.set_color("RIGHT", "BLACK")

                time.sleep(1)  # Wait for the motor thread to finish
                break


"""
#Calibrations
waist_motor.on_to_position(fast_speed,(waist_max/2)*waist_ratio,True,True) #Right
waist_motor.on_to_position(fast_speed,(waist_min/2)*waist_ratio,True,True) #Left
waist_motor.on_to_position(fast_speed,0,True,True)

shoulder_motor.on_for_degrees(normal_speed,normal_speed,shoulder_max*shoulder_ratio,True,True) #Forward
shoulder_motor.on_for_degrees(normal_speed,normal_speed,-shoulder_max*shoulder_ratio,True,True) 
shoulder_motor.on_for_degrees(normal_speed,normal_speed,shoulder_min*shoulder_ratio,True,True) #Backward
shoulder_motor.on_for_degrees(normal_speed,normal_speed,-shoulder_min*shoulder_ratio,True,True)

elbow_motor.on_to_position(normal_speed,elbow_max*elbow_ratio,True,True) #Up
elbow_motor.on_to_position(normal_speed,elbow_min*elbow_ratio,True,True) #Down

roll_motor.on_to_position(normal_speed,(roll_max/2)*roll_ratio,True,True) #Right
roll_motor.on_to_position(normal_speed,(roll_min/2)*roll_ratio,True,True) #Left
roll_motor.on_to_position(normal_speed,0,True,True)

pitch_motor.on_to_position(normal_speed,pitch_max*pitch_ratio,True,True) #Up
pitch_motor.on_to_position(normal_speed,pitch_min*pitch_ratio,True,True) #Down
pitch_motor.on_to_position(normal_speed,0,True,True)

spin_motor.on_to_position(normal_speed,(spin_max/2)*spin_ratio,True,True) #Right
spin_motor.on_to_position(normal_speed,(spin_min/2)*spin_ratio,True,True) #Left
spin_motor.on_to_position(normal_speed,0,True,True)

if grabber_motor:
    grabber_motor.on_to_position(normal_speed,grabber_max*grabber_ratio,True,True) #Close
    grabber_motor.on_to_position(normal_speed,grabber_min*grabber_ratio,True,True) #Open

#Reach
elbow_motor.on_to_position(normal_speed,-90*elbow_ratio,True,False) #Up
shoulder_motor.on_for_degrees(normal_speed,normal_speed,shoulder_max*shoulder_ratio,True,True) #Forward
waist_motor.on_to_position(fast_speed,waist_max*waist_ratio,True,True) #Right
elbow_motor.on_to_position(normal_speed,elbow_max*elbow_ratio,True,False) #Up
shoulder_motor.on_for_degrees(normal_speed,normal_speed,75*shoulder_ratio,True,True) #Reset
elbow_motor.on_to_position(normal_speed,-90*elbow_ratio,True,False) #Down
shoulder_motor.on_for_degrees(normal_speed,normal_speed,65*shoulder_ratio,True,True) #Backward
waist_motor.on_to_position(fast_speed,0,True,True) #Center
elbow_motor.on_to_position(slow_speed,elbow_min*elbow_ratio,True,True) #Reset
shoulder_motor.on_for_degrees(slow_speed,slow_speed,-65*shoulder_ratio,True,True) #Reset
"""