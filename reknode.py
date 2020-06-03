# Copyright 2017 Google Inc. All rights reserved.
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Sample device that consumes configuration from Google Cloud IoT.
This example represents a simple device with a temperature sensor and a fan
(simulated with software). When the device's fan is turned on, its temperature
decreases by one degree per second, and when the device's fan is turned off,
its temperature increases by one degree per second.

Every second, the device publishes its temperature reading to Google Cloud IoT
Core. The server meanwhile receives these temperature readings, and decides
whether to re-configure the device to turn its fan on or off. The server will
instruct the device to turn the fan on when the device's temperature exceeds 10
degrees, and to turn it off when the device's temperature is less than 0
degrees. In a real system, one could use the cloud to compute the optimal
thresholds for turning on and off the fan, but for illustrative purposes we use
a simple threshold model.

To connect the device you must have downloaded Google's CA root certificates,
and a copy of your private key file. See cloud.google.com/iot for instructions
on how to do this. Run this script with the corresponding algorithm flag.

  $ python cloudiot_pubsub_example_mqtt_device.py \
      --project_id=my-project-id \
      --registry_id=example-my-registry-id \
      --device_id=my-device-id \
      --private_key_file=rsa_private.pem \
      --algorithm=RS256

With a single server, you can run multiple instances of the device with
different device ids, and the server will distinguish them. Try creating a few
devices and running them all at the same time.
"""

import argparse
import datetime
import json
import os
import ssl
import time
from threading import Lock

import jwt
import paho.mqtt.client as mqtt
import glob
import random
import base64
import io
import boto3
from google.cloud import pubsub
from google.cloud import pubsub_v1
from google.oauth2 import service_account
from googleapiclient import discovery


v_count = 0
image_dict = dict()
send_rek_ack = list()
send_rek = list()

API_SCOPES = ['https://www.googleapis.com/auth/cloud-platform']
API_VERSION = 'v1'
DISCOVERY_API = 'https://cloudiot.googleapis.com/$discovery/rest'
SERVICE_NAME = 'cloudiot'

def create_jwt(project_id, private_key_file, algorithm):
    """Create a JWT (https://jwt.io) to establish an MQTT connection."""
    token = {
        'iat': datetime.datetime.utcnow(),
        'exp': datetime.datetime.utcnow() + datetime.timedelta(minutes=60),
        'aud': project_id
    }
    with open(private_key_file, 'r') as f:
        private_key = f.read()
    print('Creating JWT using {} from private key file {}'.format(
        algorithm, private_key_file))
    return jwt.encode(token, private_key, algorithm=algorithm)


def error_str(rc):
    """Convert a Paho error to a human readable string."""
    return '{}: {}'.format(rc, mqtt.error_string(rc))


class Device(object):
    """Represents the state of a single device."""

    def __init__(self, dev_id, service_account_json):
        self.temperature = 0
        self.fan_on = False
        self.connected = False
        self.id = dev_id
        credentials = service_account.Credentials.from_service_account_file(
            service_account_json).with_scopes(API_SCOPES)
        if not credentials:
            sys.exit('Could not load service account credential '
                     'from {}'.format(service_account_json))

        discovery_url = '{}?version={}'.format(DISCOVERY_API, API_VERSION)

        self._service = discovery.build(
            SERVICE_NAME,
            API_VERSION,
            discoveryServiceUrl=discovery_url,
            credentials=credentials,
            cache_discovery=False)

        # Used to serialize the calls to the
        # modifyCloudToDeviceConfig REST method. This is needed
        # because the google-api-python-client library is built on top
        # of the httplib2 library, which is not thread-safe. For more
        # details, see: https://developers.google.com/
        #     api-client-library/python/guide/thread_safety
        self._update_config_mutex = Lock()

    def _update_device_config(self, project_id, region, registry_id, device_id, data):
        """Push the data to the given device as configuration."""
        body = {
            'version_to_update': 0,
            'binary_data': base64.b64encode(
                    data.encode('utf-8')).decode('ascii')
        }
        device_name = ('projects/{}/locations/{}/registries/{}/'
                       'devices/{}'.format(
                           project_id,
                           region,
                           registry_id,
                           device_id))
        request = self._service.projects().locations().registries().devices(
        ).modifyCloudToDeviceConfig(name=device_name, body=body)
        time.sleep(20)
        # The http call for the device config change is thread-locked so
        # that there aren't competing threads simultaneously using the
        # httplib2 library, which is not thread-safe.
        self._update_config_mutex.acquire()
        try:
            request.execute()
            time.sleep(5)
        except HttpError as e:
            # If the server responds with a HtppError, log it here, but
            # continue so that the message does not stay NACK'ed on the
            # pubsub channel.
            print('Error executing ModifyCloudToDeviceConfig: {}'.format(e))
        finally:
            self._update_config_mutex.release()

    def get_id(self):
        return self.id

    def update_sensor_data(self):
        """Pretend to read the device's sensor data.
        If the fan is on, assume the temperature decreased one degree,
        otherwise assume that it increased one degree.
        """
        if self.fan_on:
            self.temperature -= 1
        else:
            self.temperature += 1

    def wait_for_connection(self, timeout):
        """Wait for the device to become connected."""
        total_time = 0
        while not self.connected and total_time < timeout:
            time.sleep(1)
            total_time += 1

        if not self.connected:
            raise RuntimeError('Could not connect to MQTT bridge.')

    def on_connect(self, unused_client, unused_userdata, unused_flags, rc):
        """Callback for when a device connects."""
        print('Connection Result:', error_str(rc))
        self.connected = True

    def on_disconnect(self, unused_client, unused_userdata, rc):
        """Callback for when a device disconnects."""
        print('Disconnected:', error_str(rc))
        self.connected = False

    def on_publish(self, unused_client, unused_userdata, unused_mid):
        """Callback when the device receives a PUBACK from the MQTT bridge."""
        print('Published message acked.')

    def on_subscribe(self, unused_client, unused_userdata, unused_mid, granted_qos):
        """Callback when the device receives a SUBACK from the MQTT bridge."""
        print('Subscribed: ', granted_qos)
        if granted_qos[0] == 128:
            print('Subscription failed.')

    def on_message(self, unused_client, unused_userdata, message):
        """Callback when the device receives a message on a subscription."""
        payload = message.payload.decode('utf-8')
        print('Received message \'{}\' on topic \'{}\' with Qos {}'.format(
            payload, message.topic, str(message.qos)))

        # The device will receive its latest config when it subscribes to the
        # config topic. If there is no configuration for the device, the device
        # will receive a config with an empty payload.
        if not payload:
            return

        # The config is passed in the payload of the message. In this example,
        # the server sends a serialized JSON string.
        data = json.loads(payload)


def parse_command_line_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Example Google Cloud IoT MQTT device connection code.')
    parser.add_argument(
        '--project_id',
        default=os.environ.get("GOOGLE_CLOUD_PROJECT"),
        required=True,
        help='GCP cloud project name.')
    parser.add_argument(
        '--registry_id', required=True, help='Cloud IoT registry id')
    parser.add_argument(
        '--device_id',
        required=True,
        help='Cloud IoT device id')
    parser.add_argument(
        '--private_key_file', required=True, help='Path to private key file.')
    parser.add_argument(
        '--algorithm',
        choices=('RS256', 'ES256'),
        required=True,
        help='Which encryption algorithm to use to generate the JWT.')
    parser.add_argument(
        '--cloud_region', default='us-central1', help='GCP cloud region')
    parser.add_argument(
        '--ca_certs',
        default='roots.pem',
        help='CA root certificate. Get from https://pki.google.com/roots.pem')
    parser.add_argument(
        '--num_messages',
        type=int,
        default=100,
        help='Number of messages to publish.')
    parser.add_argument(
        '--mqtt_bridge_hostname',
        default='mqtt.googleapis.com',
        help='MQTT bridge hostname.')
    parser.add_argument(
        '--mqtt_bridge_port', type=int, default=8883, help='MQTT bridge port.')
    parser.add_argument(
        '--message_type', choices=('event', 'state'),
        default='event',
        help=('Indicates whether the message to be published is a '
              'telemetry event or a device state message.'))
    parser.add_argument(
        '--images_path', 
        default='./images',
        help=('The path to the folder containing test images to send'))
    parser.add_argument(
        '--pubsub_subscription',
        required=True,
        help='Google Cloud Pub/Sub subscription name.')

    parser.add_argument(
        '--service_account_json',
        required=True,
        help='Path to service account json file.')

    return parser.parse_args()
#Added code to encode image

def convertImageToByteArray(image_path):
    with io.open(image_path, 'rb') as image_file:
        image_data = base64.b64encode(image_file.read()).decode('utf-8')
    return image_data

def getJSONForEncodedImage(image_path):
    imgStr = convertImageToByteArray(image_path)
    payload_json = {'temperature': 0,'image_data' : imgStr}
    #payload_json = {'temperature': 0}
    return imgStr

def upload_to_aws(local_file, bucket, s3_file):
    s3 = boto3.client('s3',region_name='us-east-1')
    try:
        s3.upload_file(local_file, bucket, s3_file)
        print("Upload Successful")
        return True
    except FileNotFoundError:
        print("The file was not found")
        return False
    except NoCredentialsError:
        print("Credentials not available")
        return False

def detect_labels(photo, bucket):

    client=boto3.client('rekognition', region_name='us-east-1')

    response = client.detect_labels(Image={'S3Object':{'Bucket':bucket,'Name':photo}},
        MaxLabels=10)
    labels = list()
    for label in response['Labels']:
        labels.append(label['Name'])
    return labels


def main():
    args = parse_command_line_args()

    subscriber = pubsub.SubscriberClient()
    subscription_path = subscriber.subscription_path(
                              args.project_id,
                              args.pubsub_subscription)

    publisher = pubsub_v1.PublisherClient()
    global count
    count = 0
    # Create the MQTT client and connect to Cloud IoT.
    client = mqtt.Client(
        client_id='projects/{}/locations/{}/registries/{}/devices/{}'.format(
            args.project_id,
            args.cloud_region,
            args.registry_id,
            args.device_id))
    client.username_pw_set(
        username='unused',
        password=create_jwt(
            args.project_id,
            args.private_key_file,
            args.algorithm))
    client.tls_set(ca_certs=args.ca_certs, tls_version=ssl.PROTOCOL_TLSv1_2)

    device = Device(args.device_id, args.service_account_json)
    os.system("rm -rf receieved_images" + device.get_id())
    os.system("mkdir receieved_images" + device.get_id())

    client.on_connect = device.on_connect
    client.on_publish = device.on_publish
    client.on_disconnect = device.on_disconnect
    client.on_subscribe = device.on_subscribe
    client.on_message = device.on_message

    client.connect(args.mqtt_bridge_hostname, args.mqtt_bridge_port)

    client.loop_start()

    mqtt_service_topic = 'projects/project2-277316/topics/my-topic'  #central
    mqtt_config_topic = '/devices/{}/config'.format(args.device_id)

    # Wait up to 5 seconds for the device to connect.
    device.wait_for_connection(5)
    
    def callback(message):
        """Logic executed when a message is received from
        subscribed topic.
        """
        '''
        try:
            data = json.loads(message.data.decode('utf-8'))
        except ValueError as e:
            print('Loading Payload ({}) threw an Exception: {}.'.format(
                message.data, e))
            message.ack()
            return
        '''
        global count
        try:
            try:
                data = json.loads(message.data.decode('utf-8'))
            except ValueError as e:
                print('Loading Payload ({}) threw an Exception: {}.'.format(
                    message.data, e))
                message.ack()
                return
            if data['type'] == 'REK':
                dev_id = data['dev_id']
                img = data['img_name']
                print("Recieved initial request from device " + dev_id + "for image " + img + "\n\n\n")
                message.ack()
                mqtt_config_topic = '/devices/{}/config/'.format(dev_id)
                payload_json = {'type' : 'REKSYM', 'img_name':img, 'node_id': device.get_id()}
                payload = json.dumps(payload_json)
                device_project_id = args.project_id
                device_registry_id = args.registry_id
                device_id = dev_id
                device_region = args.cloud_region
                print("Sending acknowledgement to device " + dev_id + "for image " + img + "\n\n\n")
                # Send the config to the device.
                device._update_device_config(
                  device_project_id,
                  device_region,
                  device_registry_id,
                  device_id,
                  payload)
                # print("10.....................")
                time.sleep(1)
                
            elif data['type'] == 'REKACK':
                if(data['node_id'] == device.get_id()):
                    image_data = base64.b64decode(data['img_data'])
                    print("Recieved acknowledgement from device " + data['dev_id'] + "for image " + data['img_name'] + "\n\n\n")
                    message.ack()
                    count = count + 1
                    # dateTimeObj = datetime.now()
                    # dateStr = dateTimeObj.strftime("%b%d%Y%H:%M:%S.%f")
                    with io.open("receieved_images" + device.get_id() + "/receieved_image" + str(count) + ".jpeg", 'wb') as f:
                        f.write(image_data)
                        bucket_name = 'project2-buck'
                        image_name = device.get_id() + 'image' + str(count) + '.jpg'
                        is_uploaded = upload_to_aws("receieved_images" + device.get_id() + "/receieved_image" + str(count) + ".jpeg",bucket_name, image_name)
                        num_labels = 0
                        labels = list()
                        if is_uploaded == True:
                            #Call rekognition
                            labels = detect_labels(image_name,bucket_name)
                        payload_json = {'type': 'REKRES', 'img_name':data['img_name'], 'is_success':is_uploaded, 'labels': labels, 'node_id': device.get_id()}
                        payload = json.dumps(payload_json)
                        device_project_id = args.project_id
                        device_registry_id = args.registry_id
                        device_id = data['dev_id']
                        device_region = args.cloud_region
                        print("Publishing rekognition results to device " + data['dev_id'] + " for image " + data['img_name'])
                        print("The labels in image are : ")
                        for l in labels:
                            print(l)
                        print("\n\n\n\n")
                        # Send the config to the device.
                        device._update_device_config(
                          device_project_id,
                          device_region,
                          device_registry_id,
                          device_id,
                          payload)
                        time.sleep(1)
                        # Signal to the main thread that we can exit.
                        #job_done.set()
                else:
                    message.ack()
        
        except binascii.Error:
            message.ack()  # To move forward if a message can't be processed

    print('Listening for messages on {}'.format(subscription_path))  
    subscriber.subscribe(subscription_path, callback=callback)      
    time.sleep(3000)
    client.disconnect()
    client.loop_stop()
    print('Finished loop successfully. Goodbye!')


if __name__ == '__main__':
    main()
