#----------------------------------------------------------------------------
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
# E. A simple static website will monitor the FireBase realtime database for new entries.
#    If a new entry is found it will retrieve the corresponding video from the Storage
#    and display on the website.
#----------------------------------------------------------------------------

from bluepy.btle import Scanner, DefaultDelegate
import bluetooth
from gpiozero import Button
from gpiozero import LED
from picamera import PiCamera
from sense_hat import SenseHat
from datetime import datetime
import storeFileFB
import time
from subprocess import call
from urllib.request import urlopen
import  json
import threading
import blynklib   # pylint: disable=import-error

#----------------------------------------------------------------------------
# URL and API key for ThingSpeak
#----------------------------------------------------------------------------
WRITE_API_KEY='Z06OXSFDO9V5JU7V'
baseURL='https://api.thingspeak.com/update?api_key=%s' % WRITE_API_KEY

#----------------------------------------------------------------------------
# Blynk App authorisation key
#----------------------------------------------------------------------------
BLYNK_AUTH = 'xRgD5L7IUBd2IuDQvID2Dkd-1OS5GO8O'

#----------------------------------------------------------------------------
# initialize Blynk
#----------------------------------------------------------------------------
blynk = blynklib.Blynk(BLYNK_AUTH)

#----------------------------------------------------------------------------
# register handler for virtual pin V2(temperature) reading
#----------------------------------------------------------------------------
@blynk.handle_event('read V2')
def read_virtual_pin_handler(pin):
    temp=round(sense.get_temperature(),2)
    blynk.virtual_write(pin, temp)

#----------------------------------------------------------------------------
# register handler for virtual pin V1 write event
#----------------------------------------------------------------------------
@blynk.handle_event('write V1')
def write_virtual_pin_handler(pin, value):
    global blynkVideoTrigger
    if (value[0]) == '1':
        blynkVideoTrigger = True
        print ("blynkVideoTrigger is: ", blynkVideoTrigger)
    return(blynkVideoTrigger)

#----------------------------------------------------------------------------
# Scanning class for the bluetooth devices
#----------------------------------------------------------------------------
class ScanDelegate(DefaultDelegate):
    def __init__(self):
        DefaultDelegate.__init__(self)

    def handleDiscovery(self, dev, isNewDev, isNewData):
        if isNewDev:
            if "ef:e3:bb:09:63:cc" in dev.addr:
                print ("Found child Tile")
            elif "fc:d1:c3:68:b1:66" in dev.addr:
                print ("Found adult Tile")

#----------------------------------------------------------------------------
# Class defined for Child object  data
#----------------------------------------------------------------------------
class Child:
    childTileAddr = "ef:e3:bb:09:63:cc"
    childTileFound = False
    childInRoom = False
    lastChildInRoomTime = " "
    childTileInfo = " "
      
#----------------------------------------------------------------------------
# Class defined for Adult object  data
#----------------------------------------------------------------------------
class Adult:
    adultTileAddr = "fc:d1:c3:68:b1:66"
    adultTileFound = False
    adultInRoom = False
    lastAdultInRoomTime = " "
    adultTileInfo = " "

#----------------------------------------------------------------------------
# Method to write data to Thingspeak via API
#----------------------------------------------------------------------------
def writeData(temp, lightOn, lightOff, childPresent, adultPresent, fanOn, fanOff, videoURL):
    # Sending the data to thingspeak in the query string
    conn = urlopen(baseURL + '&field1=%s' % (temp) + '&field2=%s' % (lightOn) + '&field3=%s' % (lightOff) + 
                             '&field4=%s' % (childPresent) + '&field5=%s' % (adultPresent) +
                             '&field6=%s' % (fanOn) + '&field7=%s' % (fanOff) +
                             '&field8=%s' % (videoURL))
    print(conn.read())
    print("Data sent to ThingSpeak, temp =%d, lightOn = %s, lightOff= %s, fanOn= %s, fanOff= %s" 
          % (temp, lightOn, lightOff, fanOn, fanOff))
    
    # Closing the connectionx
    conn.close()

#----------------------------------------------------------------------------
# Method to determine the data to write to the Thingspeak channel
# 1. Gets the current temp
# 2. Calls the handleLight() method to determine light settings required
# 3. Calls the handleFan() method to determine the fan dettings requried
# 4. Checks the presence in the room to set the childPresent and AdultPresent variables
# 5. Makes a call to method to write data to Thingspeak channel.
#----------------------------------------------------------------------------
def determineThingSpeakData(childInRoom, adultInRoom, videoURL):
    currentTime = time.localtime()
    timeString = time.strftime("%H:%M:%S", currentTime)
    print(timeString)
    temp=round(sense.get_temperature(),2)

    lightSetting = handleLight(childInRoom, adultInRoom)
    lightOn = lightSetting[0]
    lightOff = lightSetting[1]

    fanSetting = handleFan(temp, childInRoom, adultInRoom)
    fanOn = fanSetting[0]
    fanOff = fanSetting[1]

    if childInRoom:
        childPresent = "Y"
    else:
        childPresent = "N"
    
    if adultInRoom:
        adultPresent = "Y"
    else:
        adultPresent = "N"

    writeData(temp, lightOn, lightOff, childPresent, adultPresent, fanOn, fanOff, videoURL)

#----------------------------------------------------------------------------
# Determines what light setting are required, i.e. turn on or off!
#----------------------------------------------------------------------------
def handleLight(childInRoom, adultInRoom):
    # This will decide if the light should be switched on or off based on the time
    # and if anyone is present in the room
    # Light on before 8am or after 5pm if there is someone present
    # Light off between 8am and 5pm or if no one present
    timeNow = datetime.now()

    if (timeNow <= todayAt(8) or timeNow >= todayAt(17)) and (childInRoom or adultInRoom):
        lightOn = 'Y'
        lightOff = 'N'
    elif (timeNow > todayAt(8) and timeNow < todayAt(17) or (not childInRoom and not adultInRoom)):
        lightOn = 'N'
        lightOff = 'Y'
    else:
        lightOn = 'N'
        lightOff = 'N'
    
    return (lightOn, lightOff)

#----------------------------------------------------------------------------
# Determines what light setting are required, i.e. turn on or off!
# This is based on the current temperture and if anyone is present in the room.
#----------------------------------------------------------------------------
def handleFan(temp, childInRoom, adultInRoom):
    # This will decide if the fan should be switched on or off based on the temp
    # and if anyone is present in the room
    if temp >= 23 and (childInRoom or adultInRoom):
        fanOn = 'Y'
        fanOff = 'N'
    elif temp < 22:
        fanOn = 'N'
        fanOff = 'Y'
    else:
        fanOn = 'N'
        fanOff = 'N'
    
    return (fanOn, fanOff)

def todayAt(hr, min=0, sec=0, micro=0):
    now = datetime.now()
    return now.replace(hour=hr, minute=min, second=sec, microsecond=micro)

#----------------------------------------------------------------------------
# This is a method which gets the current temperture fromt the SenseHat
# It also displays this on the LED output on the sensehat in green or red
#----------------------------------------------------------------------------
def getCurrentTemp(child, adult):
    temp = sense.get_temperature() 
    tempStr = str(round(temp,2))
    if temp >=23:
        sense.show_message(tempStr, text_colour = red)
        if child.childInRoom or adult.adultInRoom:
            sense.show_message("Fan On", text_colour = red)
    else:
        sense.show_message(tempStr, text_colour = green)
        sense.show_message("Feels nice", text_colour = green)

    print("Current Temp is %s" %(tempStr))

    return (temp, tempStr)

#----------------------------------------------------------------------------
# This is a method which takes in a list of bluetooth devices and the adult and
# child objects (BLE tiles) and determines who is present in the room.
# It first checks which of our BLE tiles have been found in the list of devices
# in range, it then checks the rssi signal strength to determine the approx
# distance the BLE device is from the Raspberry Pi. For my purposes I have 
# calibrated that any rssi signal > -65 is in range of being in the room.
# Each BLE device is identified using it's unique address so I can distinguish
# between the child tile and the adult tile.
#----------------------------------------------------------------------------
def checkWhoIsInRoom(child, adult, devices):
    for dev in devices:
        if child.childTileAddr in dev.addr:
            child.childTileFound = True
            child.childTileInfo = dev
            if child.childTileInfo.rssi > -65:
                child.childInRoom = True
                child.lastChildInRoomTime = datetime.today()
                print ("Child is in the room")
            else:
                print ("Child is not in the room")

        elif adult.adultTileAddr in dev.addr:
            adult.adultTileFound = True
            adult.adultTileInfo = dev
            if adult.adultTileInfo.rssi > -65:
                adult.adultInRoom = True
                adult.lastAdultInRoomTime = datetime.today()
                print ("Adult is in the room")
            else:
                print ("Adult is not in the room")
            
    return (child, adult)

#----------------------------------------------------------------------------
# Calculate the distance of the BLE tile from the Pi using RSSI
#----------------------------------------------------------------------------
def calculateDistance(measuredPower, RSSI, environmentalFactor):
    calcVal1 = (measuredPower - RSSI) / (10 * environmentalFactor)
    distance = 10 ** calcVal1
    return(distance)

#----------------------------------------------------------------------------
# This is a method to run the main Blynk routine which is responsible for keeping
# connection alive and sending and receiving data. This will be run in a separate 
# thread to stop the sleep function in the main program from breaking the 
# connection.
#----------------------------------------------------------------------------
def processBlynkRun():
    while True:
        blynk.run()

#----------------------------------------------------------------------------
# Start of processing
#----------------------------------------------------------------------------
if __name__ == "__main__":


    #----------------------------------------------------------------------------
    # This is setting up some variables for the Camera, SenHat and the LEDs on the Pi
    #----------------------------------------------------------------------------
    camera = PiCamera()
    sense = SenseHat()
    sense.clear()
    green = (0, 255, 0)
    red = (255,0,0)
    redLED = LED(18)

    #----------------------------------------------------------------------------
    # Starts camera preview on the Pi's primary display
    #----------------------------------------------------------------------------
    camera.start_preview()

    #----------------------------------------------------------------------------
    # Instanciates the Child and Adult classes. These will hold info about 
    # the 2 BLE tiles which will represent the child and adult in the system
    #----------------------------------------------------------------------------
    adult = Adult()
    child = Child()

    #----------------------------------------------------------------------------
    # Sets some default values for the child and adult objects
    #----------------------------------------------------------------------------
    adult.lastAdultInRoomTime = datetime.today()
    adult.lastChildInRoomTime = datetime.today()
    lastVideoTaken = datetime.today()
    child.childTileInfo = " " 
    adult.adultTileInfo = " "
    secondsSinceAdultInRoom = 0
    secondsSinceVideoTaken = 0
    blynkVideoTrigger = False
    videoURL = " "

    #----------------------------------------------------------------------------
    # This create a separate thread for the Blynk program and starts the it.
    # This will allow the connection to Blynk to stay connection when the main
    # program uses the sleep() method in it's processing
    #----------------------------------------------------------------------------
    thread = threading.Thread(target=processBlynkRun)  
    thread.start()


    #----------------------------------------------------------------------------
    # This is the main processing in the program which will be continually executed.
    #----------------------------------------------------------------------------

    while True:
        child.childTileFound = False
        adult.adultTileFound = False
        child.childInRoom = False
        adult.adultInRoom = False
        
        #----------------------------------------------------------------------------
        # Scans for any Bluetooth devices in range
        #----------------------------------------------------------------------------
        scanner = Scanner().withDelegate(ScanDelegate())
        devices = scanner.scan(10.0)
        
        #----------------------------------------------------------------------------
        # This method checks who is currenly in the room by searching for the child and
        # adult bluetooth tiles and examining the RSSI signal strength to determine distance 
        # from the Pi and hence if the tile is in the room.
        #----------------------------------------------------------------------------
        checkWhoIsInRoom(child, adult, devices)

        #----------------------------------------------------------------------------
        # Gets the current temp and displays on SenseHat LED screen. Also indicates
        # if the fan will be turned on depending on presence in the room.
        #----------------------------------------------------------------------------
        getCurrentTemp(child, adult)

        #----------------------------------------------------------------------------   
        # Works out how long since the last vidio was taken in seconds
        #----------------------------------------------------------------------------
        secondsSinceVideoTaken = (datetime.today() - lastVideoTaken).total_seconds()

        #----------------------------------------------------------------------------
        # If there is no adult in the room then it checks how long since there was an adult in the room
        # and stores this value in seconds.
        #----------------------------------------------------------------------------
        if not adult.adultInRoom:
            if child.childInRoom:
                timeSinceAdultInRoom = datetime.today() - adult.lastAdultInRoomTime
                secondsSinceAdultInRoom = timeSinceAdultInRoom.total_seconds()
                print ("No adult present in room for: ", secondsSinceAdultInRoom)
                print ("Time Since Last Video: ", secondsSinceVideoTaken)
            else:
                secondsSinceAdultInRoom = 0
                adult.lastAdultInRoomTime = datetime.today()
                print ("Resetting timeSinceAdultInRoom, because no Child Present either")

        #----------------------------------------------------------------------------
        # This calls a method to determine the data to pass to ThingSpeak and then
        # calls the API to send this to the appropriate channel.
        #----------------------------------------------------------------------------
        determineThingSpeakData(child.childInRoom, adult.adultInRoom, videoURL)
        
        print ("Blynk Video Trigger: ", blynkVideoTrigger)
        #----------------------------------------------------------------------------
        # This section of the program is responsible for determining if a video should be
        # taken. There are a number of criteria which must be met for this to happen.
        # Approach A (Automated):
        #   - Conditions which ALL must to be Met for video to be taken:
        #   1. the child BLE tile is in the room
        #   2. the adult BLE tile is NOT in the room
        #   3. the adult BLE tile has not been in the room for 3 minutes (180 seconds)
        #   4. the last video taken must have been at least 3 minutes ago (180 seconds)
        #
        # Approach B (Blynk Trigered):
        #   - Condition to be met:
        #   1. The blynkVideoTrigger booleen must be true. This is set from a button press on the
        #      Blynk app. This will trigger a video regardless of any other conditions.
        #
        #----------------------------------------------------------------------------
        if (child.childInRoom and not adult.adultInRoom and secondsSinceAdultInRoom > 180.0 and 
            secondsSinceVideoTaken > 180.0) or (blynkVideoTrigger):

            blynkVideoTrigger = False

            #----------------------------------------------------------------------------
            # Calculate the distance from both the BLE tiles to the Pi.
            # Print the rssi and approximate distance for each tile.
            #----------------------------------------------------------------------------
            childDistance = calculateDistance(-52, child.childTileInfo.rssi, 2)
            adultDistance = calculateDistance(-52, adult.adultTileInfo.rssi, 2)
            print ("Device: %s, RSSI=%d dB, Distance=%d meters" % ("Child BLE Tile", child.childTileInfo.rssi, childDistance))
            print ("Device: %s, RSSI=%d dB, Distance=%d meters" % ("Adult BLE Tile", adult.adultTileInfo.rssi, adultDistance))
            
            #----------------------------------------------------------------------------
            # Set location and name of .h264 and .mp4 files
            #----------------------------------------------------------------------------
            videoLoc = f'/home/pi/week10/img/latestToday.h264'
            videoLocMp4 = f'/home/pi/week10/img/latestToday.mp4'
            currentTime = datetime.today().strftime("%d/%m/%Y %H:%M:%S")

            #----------------------------------------------------------------------------
            # Flash the red LED to indicate a video is about to be taken
            #----------------------------------------------------------------------------
            redLED.on()
            time.sleep(2)
            redLED.off()

            #----------------------------------------------------------------------------
            # Store the date/time of the video being taken
            #----------------------------------------------------------------------------
            lastVideoTaken = datetime.today()

            #----------------------------------------------------------------------------
            # Start the Video, wait 5 seconds and then stop the video
            #----------------------------------------------------------------------------
            camera.start_recording(videoLoc)  
            time.sleep(5)
            camera.stop_recording()
            print(f'latestToday taken at {currentTime}') # print frame number to console

            #----------------------------------------------------------------------------
            # Convert the video from .h264 to MP4 format with a shell command
            #----------------------------------------------------------------------------
            command = "MP4Box -add " + videoLoc + " " + videoLocMp4
            call([command], shell=True)
            print("Video converted")
            
            #----------------------------------------------------------------------------
            # Store the MP4 video on firebase storage, and the 
            # name and time of the file the firebase realtime DB
            #----------------------------------------------------------------------------
            videoURL = storeFileFB.store_file(videoLocMp4)
            storeFileFB.push_db(videoLocMp4, currentTime, child.childInRoom, adult.adultInRoom)
            print("files saved on firebase")

            #----------------------------------------------------------------------------
            # Remove both video formats from the local Pi storage
            #----------------------------------------------------------------------------
            commandDel = "rm" + " " + videoLocMp4 + " " + videoLoc
            call([commandDel], shell=True)
            print ("Files deleted from local img folder")
        
            time.sleep(30)

        time.sleep(10)
