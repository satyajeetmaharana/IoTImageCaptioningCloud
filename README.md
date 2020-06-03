# Image-Captioning-IoT-Google-Cloud


## Design Details

We provide a decentralized solution that is migrated completely on the cloud for the purpose of this problem. Fig 1 diagrammatically displays the architecture that we have used in order to build our application. The model can be broadly divided into four major components namely, non- compute IoT devices, rekognition compute nodes, polly compute nodes and a single DApp node. Devices interact with one another in order to ask for services and provide results over a MQTT publish subscribe model. Each of these components and the communication between them has been described in greater detail below:


![Detailed Implementation architecture diagram](/Arch.png "Title")




**Non-Compute IoT Devices**: The devices shown on the left-hand side (in a vertical queue) are the non-compute IoT devices. As per our problem statement these devices should have picture capturing and audio playing capabilities. As the name suggests this device does not have compute capabilities and relies on the network of compute nodes in order to get the final audio file for the image it publishes on the network. The non-compute IoT devices have been simulated on the Google Cloud Platform.

**Rekognition Compute Nodes**: This node has also been simulated using the Google Cloud Platform IoT Core service. The blue nodes that have been placed vertically on the left-hand side represent the rekognition compute nodes in Fig 1. As the name suggests this node has compute capabilities. The non-compute node sends the images to this node and this node is tasked with running the image through the object detection model and returns the labels identified to the caller IoT device. This node receives the image over the MQTT queue and then stores it on the cloud. We have used AWS S3 to meet our storage needs. AWS also offers the Image Rekognition service which has a ML model pre-trained for object detection and this node uses this service on the image stored in the S3 bucket so as to get the labels in the image. The decision of which node serves which request has been made by a three-way handshake between the non-compute node and this node, such that the first node that provides an acknowledgement to the non-compute device is tasked with serving the request. Details of this communication have been presented later in the part where the MQTT communication is discussed.

**Polly Compute Nodes**: This node has also been simulated using the Google Cloud Platform IoT Core service. As the name suggests this node has compute capabilities. The blue nodes that have been placed horizontally at the bottom represent the polly compute nodes in Fig 1. The non-compute node sends the labels that it has received from the Rekognition Compute node to this node and this node is tasked with running the labels through the text-to-speech-model and an audio file that reads out the labels is sent to the caller IoT device. This node receives the image over the MQTT queue and then stores it on the cloud. We have used AWS S3 to meet our storage needs. AWS also offers the Image Rekognition service which has a ML model pre-trained for object detection and this node uses this service on the image stored in the S3 bucket so as to get the labels in the image. These labels are again returned using the MQTT queue. The decision of which node serves which request has been made by a three-way handshake between the non-compute node and this node, such that the first node that provides an acknowledgement to the non-compute device is tasked with serving the request. Details of this communication have been presented later in the part where the MQTT communication is discussed.

**DApp Node**: Our architecture currently supports a single DApp Node. The single IoT device present in the rightmost coroner of Fig 1 is the DApp node in the design diagram. This node is used for authentication before giving the device access to the MQTT central queue. For our project, we have used the Ropsten test network where each device has a wallet with address and private keys. The device gets access to the central queue as soon as a payment of 0.02 ether has been made via the “pay()” function in the smart contract pushed to the Ropsten test network. This is reflected in the Metamask wallet and can be seen on Etherscan as well. The user interface of the same can be seen in the figure below.

**MQTT Publish/Subscribe**: The devices interact between themselves using the MQTT Pub/Sub model. GCP provides a MQTT bridge for registries and we made use of that. Every device in the network (except DApp) is subscribed to the central topic (‘projects/project2-277316/topics/my-topic’ in our case). The compute nodes read messages from this queue and act on them only if it is a request that can be handled by it. The communication from the compute node to the non-compute device is more secure however, since the compute nodes publish the message directly to the device’s config which is private to the device. The direction of communications between devices and nodes has been shown in Fig1 through arrows. As can be seen only the non-compute nodes publish information to the central topic, while the compute nodes only read from this topic. The interaction from the compute node to the non-compute device is done to the device’s config directly.
An additional benefit of using a central queue across all services is that this makes the architecture very portable and easy to modify in case a new service has to be added at a later development stage.

## Components

**Decentralized (P2P) component**: In order to ensure that our design has decentralized peers and compute capabilities we have tweaked the way we publish and acknowledge requests from the MQTT queue. Fig2 explains how the P2P status has been ensured.

![Detailed Implementation P2P architecture diagram](/P2PArch.png "Title")

**IoT component**: As explained above, all the devices and nodes have been simulated as IoT devices on GCP, hence covering this requirement.

**Machine Learning component**: Both Rekognition and Polly use ML models in order to detect objects and convert text to speech, hence covering this requirement

**Multiple Clouds**: While all our devices and nodes are in GCP, the ML support for the architecture has been taken from AWS Polly and Rekognition services, hence covering this breadth

**DApp component**: The DApp server which is a part of the IoT core in GCP, utilizes the Web3 python library to interact with the smart contract pushed on the Ropsten Network with the help of its address and ABI.


## How to run

### 1. Google Cloud Setup
1. In the Cloud Console, on the project selector page, select or create a Cloud project.
2. Make sure that billing is enabled for your Google Cloud project.
3. Enable the Cloud IoT Core and Cloud Pub/Sub APIs. [Enable APIs](https://console.cloud.google.com/flows/enableapi?apiid=cloudiot.googleapis.com,pubsub&_ga=2.87379615.606901808.1589575300-1724261215.1588892683 "Title")

### 2. Setup your local environment

1. [Install and initialize the Cloud SDK](https://cloud.google.com/sdk/docs/ "Title")
2. Clone this repo : https://github.com/satyajeetmaharana/Image-Captioning-IoT-Google-Cloud.git. 
3. Change current directory to this repo folder
4. Download [Google's CA root certificate](https://pki.goog/roots.pem "Title") into the same directory. You can optionally set the location of the certificate with the --ca_certs flag.

### 3. Create a new Registry
1. Go to Google Cloud Console. If a project is not already created, create a new project.

2. Go to the [Google Core IoT module](https://console.cloud.google.com/iot?_ga=2.52683439.606901808.1589575300-1724261215.1588892683 "Title") in your project. 

3. Click Create registry.
* Name: my-registry
* Region: us-central1
4.  In the Default telemetry topic dropdown list, select Create a topic.
* In the Create a topic dialog, enter my-device-events in the Name field.
* Click Create in the Create a topic dialog
* The Device state topic and Certificate value fields are optional, so leave them blank.
5. Click Create on the Cloud IoT Core page.

### 4. Create a device private key pair
1. On your local machine, open up a terminal window and run the following command : 
```shell
openssl req -x509 -newkey rsa:2048 -keyout rsa_private.pem -nodes \
    -out rsa_cert.pem -subj "/CN=unused"
```

2. This will generate two files "rsa_private.pem" and "rsa_cert.pem"

### 5. Create a new device
1. On the Registries page, select my-registry.

2. Select the Devices tab and click Create a device.

3. Enter my-device for the Device ID.

4. Select Allow for Device communication.

5. Add the public key information to the Authentication fields.

* Copy the contents of rsa_cert.pem from the step above to the clipboard. Make sure to include the lines that say -----BEGIN CERTIFICATE----- and -----END CERTIFICATE-----.
* Select RS256_X509 for the Public key format.
* Paste the public key in the Public key value box.
* Click Add to associate the RS256_X509 key with the device.
6. The Device metadata field is optional; leave it blank.

7. Click Create.


### 6. Run the following command to create subscription
```shell
gcloud pubsub subscriptions create \
    projects/PROJECT_ID/subscriptions/my-subscription \
    --topic=projects/PROJECT_ID/topics/my-device-events
```

### 7. Create an IAM User. 
1. Use Cloud Console to create a [service account](https://console.cloud.google.com/iam-admin/serviceaccounts/?_ga=2.153330239.606901808.1589575300-1724261215.1588892683 "Title"):
2. Click Select, then select a project to use for the service account.
3. Click Create service account.
- Name the account e2e-example and click Create.
- Select the role Project > Editor and click Continue.
- Click Create key.
- Under Key type, select JSON and click Create.
- Save this key to the same directory as the example Python files, and rename it service_account.json.


### 8. Start the dapp server using the below command. Double check the parameters
```shell
python3 dappserver.py
    `--project_id=<id of the google cloud project you made above>`
    `--registry_id=<registry id>`
    `--device_id=<The dapp server is also running on an iot device, so create a device on GCP and mention the  device id here>`
    `--private_key_file=<path to the private key for the iot device mentioned above>`
    `--algorithm=RS256`
    `--ca_cert=<path to the ca_certificate>`
    `--service_account_json=<path to the json file for the IAM User>`
```

### 9. Start the rekognition nodes using the following command. Multiple nodes can be added to the network, just ensure that each node is linked to a different device id and a different pubsub subscription. Make sure that AWS credentials have been configured. Add aws_access_key_id and aws_secret_access_key into aws/credentials file.

```shell
python reknode.py
    `--project_id=<id of the google cloud project you made above>`
    `--registry_id=<registry id>`
    `--device_id=<The rekognition server is also running on an iot device, so create a device on GCP and mention the device id here>`
    `--private_key_file=<path to the private key for the iot device mentioned above>`
    `--algorithm=RS256` 
    `--ca_cert=<path to the ca_certificate>`
    `--pubsub_subscription=<id of the subscription that was created for this device>`
    `--service_account_json=<path to the json file for the IAM User>`
```
### 10. Start the polly nodes using the following command. Multiple nodes can be added to the network, just ensure that each node is linked to a different device id and a different pubsub subscription. Add the AWS credentials in the code to be able to use polly.

```shell
python pollyNode.py
    `--project_id=<id of the google cloud project you made above>`
    `--registry_id=<registry id>`
    `--device_id=<The rekognition server is also running on an iot device, so create a device on GCP and mention the device id here>`
    `--private_key_file=<path to the private key for the iot device mentioned above>`
    `--algorithm=RS256`
    `--ca_cert=<path to the ca_certificate>`
    `--pubsub_subscription=<id of the subscription that was created for this device>`
    `--service_account_json=<path to the json file for the IAM User>`
```

### 11. Use the below code to send some example images via MQTT to the server. You should see the output objects detected printed out on the console. Multiple nodes can be added to the network, just ensure that each node is linked to a different device id and a different pubsub subscription

```shell
python iotdevice.py
    `--project_id=<id of the google cloud project you made above>`
    `--registry_id=<registry id>`
    `--device_id=<The rekognition server is also running on an iot device, so create a device on GCP and mention  the device id here>`
    `--private_key_file=<path to the private key for the iot device mentioned above>`
    `--algorithm=RS256`
    `--ca_cert=<path to the ca_certificate>`
    `--pubsub_subscription=<id of the subscription that was created for this device>`
    `--images_path=<path to the folder where the images are stored>`
    `--dapp_key=<the metamask key that is required for etherium payment>`
    `--dapp_addr=<the metamask address that is required for etherium payment>`
    `--dapp_id=<id of the dapp core machine that was started in step 8>`
    `--service_account_json=<path to the json file for the IAM User>`
```
