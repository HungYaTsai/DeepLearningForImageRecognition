#!/usr/bin/env python2
#
# Example to classify faces.
# Brandon Amos
# 2015/10/11
#
# Copyright 2015-2016 Carnegie Mellon University
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import time

start = time.time()

import sys

sys.path.append('/usr/local/lib/python2.7/site-packages')

import dlib
from skimage import io
import argparse
import cv2
import os
import pickle
import sys

from operator import itemgetter

import numpy as np
np.set_printoptions(precision=2)
import pandas as pd

import openface

from sklearn.pipeline import Pipeline
from sklearn.lda import LDA
from sklearn.preprocessing import LabelEncoder
from sklearn.svm import SVC
from sklearn.grid_search import GridSearchCV
from sklearn.mixture import GMM
from sklearn.tree import DecisionTreeClassifier
from sklearn.naive_bayes import GaussianNB

fileDir = os.path.dirname(os.path.realpath(__file__))
modelDir = os.path.join(fileDir, '..', 'models')
dlibModelDir = os.path.join(modelDir, 'dlib')
openfaceModelDir = os.path.join(modelDir, 'openface')


def getRep(imgPath, multiple=True):
    start = time.time()
    bgrImg = cv2.imread(imgPath)
    if bgrImg is None:
        raise Exception("Unable to load image: {}".format(imgPath))

    rgbImg = cv2.cvtColor(bgrImg, cv2.COLOR_BGR2RGB)

    if args.verbose:
        print("  + Original size: {}".format(rgbImg.shape))
        if args.verbose:
            print("Loading the image took {} seconds.".format(time.time() - start))

    start = time.time()
    
    if multiple:
        bbs = align.getAllFaceBoundingBoxes(rgbImg)
        print("1")
    else:
        bb1 = align.getLargestFaceBoundingBox(rgbImg)
        bbs = [bb1]
        print("2")
    if len(bbs) == 0 or (not multiple and bb1 is None):
        raise Exception("Unable to find a face: {}".format(imgPath))
    if args.verbose:
        print("Face detection took {} seconds.".format(time.time() - start))

    reps = []
    for bb in bbs:
        start = time.time()
        alignedFace = align.align(
            args.imgDim,
            rgbImg,
            bb,
            landmarkIndices=openface.AlignDlib.OUTER_EYES_AND_NOSE)
        if alignedFace is None:
            raise Exception("Unable to align image: {}".format(imgPath))
        if args.verbose:
            print("Alignment took {} seconds.".format(time.time() - start))
        print("This bbox is centered at {}, {}".format(bb.center().x, bb.center().y))
        cv2.rectangle(rgbImg, (bb.left(), bb.top()), (bb.right(), bb.bottom()), (0,0,255), 3)
                                              
        start = time.time()
        rep = net.forward(alignedFace)
        if args.verbose:
            print("Neural network forward pass took {} seconds.".format(time.time() - start))
        reps.append((bb.center().x, rep))

    sreps = sorted(reps, key=lambda x: x[0])
    return sreps


def infer(args, multiple=True):
    with open(args.classifierModel, 'rb') as f:
        if sys.version_info[0] < 3:
            (le, clf) = pickle.load(f)
        else:
            (le, clf) = pickle.load(f, encoding='latin1')


    for img in args.imgs:
        print("\n=== {} ===".format(img))
        reps = getRep(img, multiple)
        if len(reps) > 1:
            print("List of faces in image from left to right")
        for r in reps:
            rep = r[1].reshape(1, -1)
            bbx = r[0]
            start = time.time()
            predictions = clf.predict_proba(rep).ravel()
            maxI = np.argmax(predictions)
            person = le.inverse_transform(maxI)
            confidence = predictions[maxI]
            if args.verbose:
                print("Prediction took {} seconds.".format(time.time() - start))
            if multiple:
                print("Predict {} @ x={} with {:.2f} confidence.".format(person.decode('utf-8'), bbx,
                                                                         confidence))
            else:
                print("Predict {} with {:.2f} confidence.".format(person.decode('utf-8'),
                                                                  confidence))
            if isinstance(clf, GMM):
                dist = np.linalg.norm(rep - clf.means_[maxI])
                print("  + Distance from the mean: {}".format(dist))


if __name__ == '__main__':
    
    parser = argparse.ArgumentParser()
    
    parser.add_argument(
        '--dlibFacePredictor',
        type=str,
        help="Path to dlib's face predictor.",
        default=os.path.join(
            dlibModelDir,
            "shape_predictor_68_face_landmarks.dat"))
    parser.add_argument(
        '--networkModel',
        type=str,
        help="Path to Torch network model.",
        default=os.path.join(
            openfaceModelDir,
            'nn4.small2.v1.t7'))
    parser.add_argument('--imgDim', type=int,
                        help="Default image dimension.", default=96)
    parser.add_argument('--cuda', action='store_true')
    parser.add_argument('--verbose', action='store_true')
                                             
    subparsers = parser.add_subparsers(dest='mode', help="Mode")
    trainParser = subparsers.add_parser('train',
                                        help="Train a new classifier.")
    trainParser.add_argument('--ldaDim', type=int, default=-1)
    trainParser.add_argument(
        '--classifier',
        type=str,
        choices=[
            'LinearSvm',
            'GridSearchSvm',
            'GMM',
            'RadialSvm',
            'DecisionTree',
            'GaussianNB',
            'DBN'],
        help='The type of classifier to use.',
        default='LinearSvm')
    trainParser.add_argument(
        'workDir',
        type=str,
        help="The input work directory containing 'reps.csv' and 'labels.csv'. Obtained from aligning a directory with 'align-dlib' and getting the representations with 'batch-represent'.")
                                             
    inferParser = subparsers.add_parser(
        'infer', help='Predict who an image contains from a trained classifier.')
    inferParser.add_argument(
        'classifierModel',
        type=str,
        help='The Python pickle representing the classifier. This is NOT the Torch network model, which can be set with --networkModel.')
    inferParser.add_argument('imgs', type=str, nargs='+',
                               help="Input image.")
    inferParser.add_argument('--multi', help="Infer multiple faces in image",
                               action="store_true")
                                             
    args = parser.parse_args()
    if args.verbose:
        print("Argument parsing and import libraries took {} seconds.".format(
            time.time() - start))
                                             
    if args.mode == 'infer' and args.classifierModel.endswith(".t7"):
        raise Exception("""
        Torch network model passed as the classification model,
        which should be a Python pickle (.pkl)
        
        See the documentation for the distinction between the Torch
        network and classification models:
        
        http://cmusatyalab.github.io/openface/demo-3-classifier/
        http://cmusatyalab.github.io/openface/training-new-models/
        
        Use `--networkModel` to set a non-standard Torch network model.""")
    start = time.time()
    
    align = openface.AlignDlib(args.dlibFacePredictor)
    net = openface.TorchNeuralNet(args.networkModel, imgDim=args.imgDim,
                                  cuda=args.cuda)
                                  
    if args.verbose:
        print("Loading the dlib and OpenFace models took {} seconds.".format(
            time.time() - start))
    start = time.time()

    if args.mode == 'infer':
        infer(args, False)
        dlib.hit_enter_to_continue()
