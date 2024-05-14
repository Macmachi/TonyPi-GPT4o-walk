# Version: 1.0.0
# Author: Arnaud Ricci
# Project TonyPi GPTo Walk: A humanoid robot that understands its environment through GPT vision and makes decisions for its movement.

#!/usr/bin/python3
# coding=utf8
import sys
import cv2
import time
import numpy as np
import hiwonder.PID as PID
import hiwonder.Misc as Misc
import hiwonder.Board as Board
import hiwonder.Camera as Camera
import hiwonder.ActionGroupControl as AGC
import hiwonder.yaml_handle as yaml_handle
import openai
import pygame
import io
import base64
import requests
import configparser
import os
import datetime

script_dir = os.path.dirname(os.path.realpath(__file__))
os.chdir(script_dir)
config_path = os.path.join(script_dir, 'config.ini')

config = configparser.ConfigParser()
# Please edit the INI file with personal information (check comments in INI file)
config.read(config_path)

# KEYs from the INI file
API_KEY = config['KEYS']['OPENAI_API_KEY']
openai.api_key = API_KEY
client = openai.Client(api_key=openai.api_key)

if sys.version_info.major == 2:
    print('Veuillez exécuter ce programme avec python3 !')
    sys.exit(0)

# Delete the image folder at script launch
if os.path.exists("images_gptvision"):
    for file in os.listdir("images_gptvision"):
        os.remove(os.path.join("images_gptvision", file))
    os.rmdir("images_gptvision")

# A boolean variable indicating whether the program is running.
__isRunning = False

capture_analysing = False
last_instruction = ""

size = (320, 240)

def text_to_speech(text, voice='alloy', model='tts-1', output_format='mp3'):
    """
    This function uses the OpenAI API to convert text to speech and play the result directly.
    """
    # Generate audio file
    response = client.audio.speech.create(
        model=model,
        voice=voice,
        input=text,
        response_format=output_format
    )

    # Initialize Pygame
    pygame.mixer.init()

    # Load the audio file into Pygame
    if output_format == 'mp3':
        audio_file = pygame.mixer.music.load(io.BytesIO(response.read()))
    else:
        raise ValueError("Unsupported output format")

    # Play the audio file
    pygame.mixer.music.play()

    while pygame.mixer.music.get_busy():
        pygame.time.Clock().tick(10)

servo_data = None

def load_config():
    """
    Load servo configuration data from YAML file.
    """    
    global servo_data
    servo_data = yaml_handle.get_yaml_data(yaml_handle.servo_file_path)

load_config()

x_dis = servo_data['servo2']
y_dis = 1500

# Initial position
def initMove():
    Board.setPWMServoPulse(1, y_dis, 500)
    Board.setPWMServoPulse(2, x_dis, 500)

#pid initialisation
x_pid = PID.PID(P=0.45, I=0.02, D=0.02)
y_pid = PID.PID(P=0.45, I=0.02, D=0.02)

# Reset variables
def reset():
    global x_dis, y_dis
    x_dis = servo_data['servo2']
    y_dis = 1500
    x_pid.clear()
    y_pid.clear()
    initMove()

# Initializes the gpt vision walking application.
def init():
    print("Initializing gpt vision walking")
    load_config()
    reset()

# Starts the gpt vision walking application.
def start():
    global __isRunning
    __isRunning = True
    print("Starts gpt vision walking")

# Stops the gpt vision walking application.
def stop():
    global __isRunning
    __isRunning = False
    reset()
    print("Stops gpt vision walking")
      
# Main Face Tracking Function
def run(img):
    global capture_analysing
    global last_instruction

    if not __isRunning:
        return img

    if capture_analysing == False:
        capture_analysing = True
        print("Capturing image...")
        # Capture an image using the camera
        ret, img = my_camera.read()
        if ret:
            # Créer le dossier "images_gptvision" s'il n'existe pas
            if not os.path.exists("images_gptvision"):
                os.makedirs("images_gptvision")

            # Générer le nom de fichier avec la date, le numéro et l'instruction
            now = datetime.datetime.now()
            image_number = len(os.listdir("images_gptvision")) + 1
            image_filename = f"images_gptvision/{now.strftime('%Y%m%d_%H%M%S')}_{image_number}.jpg"

            # Sauvegarder l'image capturée
            cv2.imwrite(image_filename, img)

            face_img = img.copy()
            face_img_encoded = cv2.imencode('.jpg', face_img)[1]
            face_img_base64 = base64.b64encode(face_img_encoded).decode('utf-8')

            # Send the request to the OpenAI API
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {openai.api_key}"
            }

            # Create a payload for the OpenAI API request
            payload = {
                "model": "gpt-4o",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": f"Based on the center of the image, which direction should you move? Please provide only one direction in your response as the prompt is seeking the decision you will make. If possible, prioritize moving 'forward' if the path is clear, otherwise, based on the side that appears to have the fewest obstacles, consider 'turn right' or 'turn left' given that the last instruction was '{last_instruction}'"
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{face_img_base64}"
                                }
                            }
                        ]
                    }
                ],
                "max_tokens": 300
            }

            try:
                response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
                # Raises an exception for HTTP responses with an error code (4xx or 5xx)
                response.raise_for_status()  
            # Handle the HTTP error here (e.g., log the error, retry, etc.)
            except requests.exceptions.HTTPError as http_err:
                print(f"HTTP error occurred: {http_err}")  # Python 3.6+
                capture_analysing = False
            # Handle the connection error here (e.g., log the error, retry, etc.)
            except requests.exceptions.ConnectionError as conn_err:
                print(f"Connection error occurred: {conn_err}")
                capture_analysing = False                
            # Handle the timeout here (e.g., log the error, retry, etc.)
            except requests.exceptions.Timeout as timeout_err:
                print(f"Timeout error occurred: {timeout_err}")
                capture_analysing = False                
            # Handle any other exceptions that might occur
            except Exception as e:
                print(f"An error occurred: {e}")
                capture_analysing = False                
            # Parse the response and extract the generated text description
            else:
                response_json = response.json()
                print(response_json)
                text_response = response_json["choices"][0]["message"]["content"]

                text_to_speech(text_response)

                # Extract the instruction from the response
                instruction = None
                if "forward" in text_response.lower():
                    instruction = "forward"
                elif "turn right" in text_response.lower():
                    instruction = "right"
                elif "turn left" in text_response.lower():
                    instruction = "left"
                else:
                    print("Unknown instruction")
                    instruction = None
                
                last_instruction = instruction

                # Perform the action based on the instruction
                if instruction == "forward":
                    AGC.runActionGroup('go_forward')
                    AGC.runActionGroup('go_forward')
                    AGC.runActionGroup('go_forward')
                    AGC.runActionGroup('go_forward')
                elif instruction == "right":
                    AGC.runActionGroup('turn_right')
                    AGC.runActionGroup('turn_right')
                    AGC.runActionGroup('turn_right')
                    AGC.runActionGroup('turn_right')
                elif instruction == "left":
                    AGC.runActionGroup('turn_left')
                    AGC.runActionGroup('turn_left')
                    AGC.runActionGroup('turn_left')
                    AGC.runActionGroup('turn_left')
                else:
                    print("No action taken")

                # Add instruction to image file name
                if instruction:
                    new_image_filename = f"images_gptvision/{now.strftime('%Y%m%d_%H%M%S')}_{image_number}_{instruction}.jpg"
                    os.rename(image_filename, new_image_filename)
                
                # Wait for stabilization to avoid potential camera shake 
                time.sleep(0.3)
                capture_analysing = False

    return img

# Main function
if __name__ == '__main__':
    from CameraCalibration.CalibrationConfig import *

    # Loading parameters
    param_data = np.load(calibration_param_path + '.npz')

    # Retrieving parameters
    mtx = param_data['mtx_array']
    dist = param_data['dist_array']
    newcameramtx, roi = cv2.getOptimalNewCameraMatrix(mtx, dist, (640, 480), 0, (640, 480))
    mapx, mapy = cv2.initUndistortRectifyMap(mtx, dist, None, newcameramtx, (640, 480), 5)
    
    init()
    start()

    open_once = yaml_handle.get_yaml_data('/boot/camera_setting.yaml')['open_once']
    if open_once:
        my_camera = cv2.VideoCapture('http://127.0.0.1:8080/?action=stream?dummy=param.mjpg')
    else:
        my_camera = Camera.Camera()
        my_camera.camera_open()

    text_to_speech("Script launched")
    AGC.runActionGroup('stand')
    while True:
        ret, img = my_camera.read()
        if ret:
            frame = img.copy()
            # Distortion correction
            frame = cv2.remap(frame, mapx, mapy, cv2.INTER_LINEAR)  
            Frame = run(frame)
            cv2.imshow('Frame', Frame)
            key = cv2.waitKey(1)
            if key == 27:
                break
        else:
            time.sleep(0.01)

    my_camera.camera_close()
    cv2.destroyAllWindows()