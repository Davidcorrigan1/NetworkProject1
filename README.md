# Author: David Corrigan
# Date: 28.12.2020
# 
# Description:
# ------------
# This module runs the SmartHomeHub which has the following funcionality
#
# A. It monitors the presence of a child or adult in a specific room using the
#    presence of BLE tiles and a Raspberry Pi. The Pi is the Central device which 
#    will scan for the presence of the BLE tiles and determine if they are in the room
#    using the rssi signal strength. 
#    If the child is in the room and the adult has not been present for a period of time (3 mins)
#    then a 5 second video will be taken. This video will be stored on Firebase Storage to 
#    make it available to other applications. Videos will be taken at most every 3 minutes unless 
#    triggered manually from the Blynk app.
#    A Red LED connected to the Raspberry Pi will flash for 2 seconds prior to the video being 
#    taken to be transparent about when videos are being taken.
#
# B. It continually checks the room temperture and the presence in the room. Based on 
#    the temperture and the presence of child or adult in the room will trigger a fan
#    to turn on. Once the temperture drops below a certain value it will trigger the 
#    fan to turn off. This is achieved by sending Fan on and off indicators to a Thingspeak
#    channel. The channel is being monitored by a number 'Reacts' which check the 'Fan_on'
#    and 'fan_off' fields which if set to Y trigger a certain 'ThingHTTP'. This will either
#    trigger a IFTTT api to to turn on the fan or turn off the fan. 
#    The LED screen on the SenseHat will how the current temperture each time it's taken and 
#    will show a message when the fan is being triggered.
#
# C. It continually checks the current time and the presence in the room. Based on 
#    the time and the presence of child or adult in the room will trigger a light
#    to turn on/off. This is achieved by sending light on and off indicators to a Thingspeak
#    channel. The channel is being monitored by a number 'Reacts' which check the 'light_on'
#    and 'light_off' fields which if set to Y trigger a certain 'ThingHTTP'. This will either
#    trigger a IFTTT api to to turn on the light or turn off the light. 
#
# D. It will interface with the Blynk app to send temperture data to it on 5 second intervals.
#    It also takes input from a 'Start Video' button on the Blynk app which will trigger a 5 second
#    video to be taken regardless of any other conditions.
#    The Blynk will show the latest video taken once it's uploaded to Firebase. 
#
# E. A node.js website dashboard will make an API call to thingspeak to retrieve the latest data.
#    This will include the current temperature, the indicator to say an adult is present and also
#    one to indicate if a child is present. It will also have the URL of the latest video taken.
