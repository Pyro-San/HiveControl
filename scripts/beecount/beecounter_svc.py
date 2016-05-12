#!/usr/bin/env python
"""
Counts Bees in and bees out of a beehive. 
Take as input a top-down view of the behive entrance and assume a fairly static
background.

algo goes as follow :
- build and keep up to date a statistical model of the background
- image substraction + morphological operator to henance the contrast
- blob detection
- blob tracking using basic munkres assignment, should use prediction based on
previous motion
- count IN +1 for each bees from which track is lost close to the entrance
- count OUT +1 for each bees from which track appears close to the entrance

# Copyright (c) 2015 Antoine Letouzey antoine.letouzey@gmail.com
# Author: Antoine Letouzey
# Modified for Hivetool.org usage by: Ryan Crum
# LICENSE: LGPL

"""

import picamera
import numpy as np
import math
import cv2
import sys
import traceback

import io
from collections import deque
from munkresPi import linear_assignment # local import



#------------   

# statistical background model, build a model from previous frames
class BGmodel(object):
    def __init__(self, size, shape=(640, 480)):
        self.size = size #number of frame used to compute a model
        self.hist = np.zeros((self.size, shape[1], shape[0]))
        self.model = None
        self.cpt = 0
        self.ready = False

    # add a frame and update the model
    def add(self, frame, updateModel = True):
        self.hist[self.cpt,:,:] = np.copy(frame)
        self.cpt += 1
        if self.cpt == (self.size - 1) :
            self.ready = True
        self.cpt %= self.size
        if updateModel:
            self.updateModel()
    
    # update the model from the current frame history
    def updateModel(self):
        # np.mean is faster but median yields better results
        #self.model = np.median(self.hist, axis=0).astype(np.int32)
        self.model = np.mean(self.hist, axis=0).astype(np.int32)
    
    def getModel(self):
        return np.copy(self.model)
       
    # substract the background to the current frame
    def apply(self, frame):
        self.add(frame)
        # *2 to enhance the contrast
        res = 2*(np.abs(frame-self.model).astype(np.int32))
        res = np.clip(res, 0, 255)
        return res.astype(np.uint8)



# -----------------

# convininent Bee object to hold a bee's position, motion history and provides
# drawing functions
class Bee(object):
    staticID = 0
    def __init__(self, pos):
        self.pos = [list(pos)]
        self.lastSeen = 0
        self.ID = Bee.staticID
        Bee.staticID += 1
        self.age = 0
        self.color =  tuple(255*(0.2+4*np.random.random((3))/5))
    
    # move the bee to it's new position
    def move(self, pos):
        self.age += 1
        self.pos.append(list(pos))
    
    # remove last position
    def pop(self):
        self.age -= 1
        self.pos.pop()
    
    # compute distance to a point from given previous position
    def dist(self, pt, offset = 0):
        return math.sqrt((pt[0]-self.pos[-(1+offset)][0])**2 + (pt[1]-self.pos[-(1+offset)][1])**2)
    
    # draw the bee's path as a line onto an image
    def draw(self, img):
        #print "drawing bee#%d"%self.ID
        cv2.polylines(img, [np.int32(self.pos)], False, self.color)



# -----------------


class Hive(object):
    def __init__(self, x, y, w, h):
        self.IN = 0 # number of bees that went in
        self.OUT = 0 # number of bees that went out
        self.x = 0 # X coordinate of top left corner of the entrance
        self.y = 280 # Y coordinate of top left corner of the entrance
        self.w = 640 # width of the entrance
        self.h = 65 # height of the entrance
    
    # new bee, check if it came from the entrance
    def append(self, pt):
        # if a bee pops out from the hive entrance, then count it
        if pt[0] > self.x and pt[0] < self.x+self.w and pt[1] > self.y and pt[1] < self.y+self.h:
            self.OUT += 1
    
    # lost bee, check if it went into the entrance
    def remove(self, pt):
        # if a bee desapears closer to the hive entrance, then count it
        if pt[0] > self.x and pt[0] < self.x+self.w and pt[1] > self.y and pt[1] < self.y+self.h:
            self.IN += 1
    
    # draw counters on the image
    def draw(self, img):
        cv2.putText(img,"IN  : %d OUT : %d"%(self.IN, self.OUT), (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,0,255),2)
        cv2.rectangle(img,(self.x,self.y),(self.x+self.w,self.y+self.h),(255,0,0),5)





#-------------------------------------------------------------------------------
#
# INPUT and parameters
#
#-------------------------------------------------------------------------------

#------------   DATASET dependent
# scale of the inpute image, must be a divisor of 640 and 480 (see bellow)
SCALE = 1 # 1 => (640,480), 2 => (320, 240), 4 => (160, 120)

# number of frames used to compute a statistical model of the background, 
# more is better but slower
HISTSIZE = 30

# position of the hive entrance rectangle with top left corner (X,Y) and 
# size (width, height)
hive = Hive(225./SCALE,640./SCALE,325./SCALE,640./SCALE)

#----------  CAMERA 
camera = picamera.PiCamera()
camera.resolution = (640/SCALE, 480/SCALE)
camera.framerate = 30


#------------   GENERIC parameters
# morphological structuring element to clean the image
kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(5,5))
# background model with history size
bgm = BGmodel(HISTSIZE, camera.resolution)
# maximum "jump" a bee can make between two consecutive detections in pixels
THRESHBEE = 60/SCALE


#------------   BLOB detector parametrization

# Setup SimpleBlobDetector parameters.
params = cv2.SimpleBlobDetector_Params()
 
# Change thresholds
params.filterByColor = False;
#params.minThreshold = 10;
#params.maxThreshold = 255;
 
# Filter by Area.
params.filterByArea = True
params.minArea = 10/(SCALE*SCALE)
params.maxArea = 400/(SCALE*SCALE)
 
# Filter by Circularity
params.filterByCircularity = False
params.minCircularity = 0.70
 
# Filter by Convexity
params.filterByConvexity = True
params.minConvexity = 0.70
 
# Filter by Inertia
params.filterByInertia = True
params.minInertiaRatio = 0.1
params.maxInertiaRatio = 0.5
 
# Create a detector with the parameters
ver = (cv2.__version__).split('.')
if int(ver[0]) < 3 :
    detector = cv2.SimpleBlobDetector(params)
else : 
    detector = cv2.SimpleBlobDetector_create(params)



#-------------------------------------------------------------------------------
#
# MAIN LOOP
#
#-------------------------------------------------------------------------------
frameid = -1
bees = []


try :
    while True:
        # get a new frame from the video file
        frameid += 1
        stream = io.BytesIO()
        camera.capture(stream, format='jpeg', use_video_port=True)
        # Construct a numpy array from the stream
        data = np.fromstring(stream.getvalue(), dtype=np.uint8)
        # "Decode" the image from the array, preserving colour as BGR
        frame = cv2.imdecode(data, 1)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray,(5,5),0).astype(np.int32)
        
        # update the model and apply it to the current frame
        fgmask = bgm.apply(gray)
        
        # Mathematical morphology to enhance the mask and remove outliers
        #fgmask = cv2.erode(fgmask,kernel,iterations = 1)
        fgmask = cv2.morphologyEx(fgmask, cv2.MORPH_OPEN, kernel)
        fgmask = cv2.morphologyEx(fgmask, cv2.MORPH_CLOSE, kernel)
        
        
        im_with_keypoints = None
        
        # blob detection only if we gathered enough images for the background model
        if bgm.ready :
            keypoints = detector.detect(fgmask)
            # Draw detected blobs as red circles.
            im_with_keypoints = np.zeros((480/SCALE,640/SCALE,3))#cv2.drawKeypoints(fgmask, keypoints, np.array([]), (0,0,255))
            if len(bees) == 0: # no bees yet, no matching to do, just add them
                for kp in keypoints:
                    bees.append(Bee(kp.pt))
                    hive.append(kp.pt)
            else :
                # MUNKRES assignment, slightly better
                freeBees = [True for i in xrange(len(bees))]
                freeKP = [True for i in xrange(len(keypoints))]
                # build cost matrix 
                cost = np.zeros((len(keypoints), len(bees)))
                for i,kp in enumerate(keypoints):
                    for j,b in enumerate(bees):
                        cost[i,j] = b.dist(kp.pt)
                # proper assignment
                assignment = linear_assignment(cost)
                for ass in assignment :
                    if cost[ass[0], ass[1]] < THRESHBEE:
                        bees[ass[1]].move(keypoints[ass[0]].pt)
                        freeBees[ass[1]] = False
                        freeKP[ass[0]] = False
                for i in xrange(len(freeBees)): # lost bees
                    if freeBees[i]:
                        bees[i].lastSeen += 1
                for i in xrange(len(freeKP)): # new keypoints
                    if freeKP[i]:
                        bees.append(Bee(keypoints[i].pt))
                        hive.append(kp.pt)                    
            # remove lost bees (not seen for at least 15 frames)
            tmp = []
            for b in bees:
                if b.lastSeen < 15: # bee still "alive"
                    tmp.append(b)
                    b.draw(im_with_keypoints)
                    b.draw(frame)
                else :
                    hive.remove(b.pos[-1])            
            bees = tmp
            hive.draw(im_with_keypoints)
            hive.draw(frame)
            #print "frame : %d /  IN : %d /  OUT : %d"%(frameid, hive.IN, hive.OUT)
            cv2.imwrite("/home/HiveControl/www/public_html/video/out/frame.jpg", frame)
            fout = open('myfile','w')
            fout.write("%d,%d"%(hive.IN, hive.OUT)) # python will convert \n to os.linesep
            fout.close() # you can omit in most cases as the destructor will call it
                    
        #debug output, uncomment to see each step
        #cv2.imshow('frame',np.concatenate((fgmask, gray2), axis=1))
        #cv2.imshow('model',bgm.model.astype(np.uint8))
        #cv2.imshow('frame',gray.astype(np.uint8))
        #cv2.imshow('mask',fgmask)
        #if im_with_keypoints is not None : 
        #    cv2.imshow("Keypoints", im_with_keypoints)
        #cv2.imshow('color',frame)

        # needs to be uncommented for the images to show properly
        #if cv2.waitKey(1) & 0xFF == ord('q'):
        #    break
except Exception as e:
    print e
    traceback.print_exc(file=sys.stdout)
    # always end with an error, but sequences are too long for me to bother debuging :(
    pass
finally :
    camera.close()
    cv2.destroyAllWindows()

print "IN : ", hive.IN
print "OUT: ", hive.OUT
