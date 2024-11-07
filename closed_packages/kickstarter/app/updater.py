from threading import Thread
from time import monotonic, sleep
import datetime
from pathlib import Path
import requests
import urllib3
import csv
import tempfile
import os
from irm import Irm

class Updater(Thread):
    def __init__(self, logger, queue, ip, firmware, dirs, profile):
        urllib3.disable_warnings()
        self.__logger = logger
        self.__profile = profile
        Thread.__init__(self)
        self.__queue = queue
        self.__ip = ip
        self.__dir_files = Path(dirs['files'])
        self.__dir_irm = Path(dirs['irm'])
        self.__firmware = firmware
        self.__firmware_version = "-.-"
        self.__firmwares_available = {}
        self.__session = requests.Session()
        self.__session.verify = False # disable HTTPS certificate check
        self.__serialnumber = ""
        self.__message = {
            'in_progress': True,
            'serial':   "---",
            'board':    "---",
            'version':  "---",
            'ip':       self.__ip,
            'action':   "---"
        }

        if firmware and int(len(firmware.split('-')) > 1):
            self.__firmware_version = firmware.split('-')[1]

    def run(self):
        # log in
        if self.__login_rest() is False:
            self.__queue.put(self.__message)
            return

        # get serialnumber of this device
        for _ in range(3):
            self.__message['serial'], self.__message['version'], self.__message['board'] = self.__get_serial()
            if self.__message['serial'] is None:
                sleep(1)
                continue
        if self.__message['serial'] is None:
            self.__logger.error("No serial number found")
            self.__queue.put(self.__message)
            return
        self.__logger.info(f"Device serial number: {self.__message['serial']}")

        # let INFO LED flash
        self.__queue.put(self.__message)
        self.__set_info_led("flash")

        # set time
        self.__message['action'] = "Setting time"
        self.__queue.put(self.__message)
        if self.__set_time() is False:
            self.__end_updating("off")
            return

        # update the firmware
        self.__message['action'] = "Updating firmware"
        self.__queue.put(self.__message)
        if self.__firmware_update() is False:
            self.__end_updating("off")
            return

        # upload various files
        self.__message['action'] = "Uploading additional files"
        self.__queue.put(self.__message)
        if self.__upload_files() is False:
            self.__end_updating("off")
            return

        # Apply config according to stored CSV file
        self.__message['action'] = "Uploading config from CSV"
        self.__queue.put(self.__message)
        if self.__upload_config() is False:
            self.__end_updating("off")
            return

        # TODO iCS

        # Register device at iRM
        self.__message['action'] = "Registering device at iRM"
        self.__queue.put(self.__message)
        if self.__register_irm() is False:
            self.__end_updating("off")
            return

        # no more action to be started
        self.__message['action'] = "---"
        self.__end_updating("on")
        return

    def shutdown(self):
        self.__logger.info('Shutting down updater')

    def __end_updating(self, onoff):
        # turn on INFO LED to signal that everything if done
        self.__message['in_progress'] = False
        if onoff == "off":
            self.__message['action'] = f'Error at "{self.__message['action']}"'
        self.__queue.put(self.__message)
        self.__set_info_led(onoff)
        return True

    def __firmware_update(self):
        # no firmware available, nothing to do
        if self.__firmware_version == "-.-":
            return True

        if self.__message['version']:
            if self.__message['version'] == self.__firmware_version:
                self.__logger.info(f"{self.__serialnumber}: Update not necessary, firmware is already at ({self.__message['version']})")
                self.__queue.put(self.__message)
                return True

        self.__logger.info(f"{self.__serialnumber}: Firmware active on device: {self.__message['version']}, starting update")
        self.__queue.put(self.__message)

        # get all firmware versions, that are already stored on the device
        self.__message['action'] = 'Get list of stored firmware versions'
        response = self.__get_firmware_list()
        if response is False:
            self.__message['action'] = 'Failed to get list with stored firmware versions'
            self.__queue.put(self.__message)
            return False

        # upload firmware
        self.__message['action'] = 'Uploading firmware'
        response = self.__upload_file(self.__firmware, self.__dir_files, filetype="firmware")
        if response is False:
            self.__message['action'] = 'Failed to upload firmware'
            self.__queue.put(self.__message)
            return False
        elif response is not True:
            # store firmware permanently, if not already existent
            self.__message['action'] = 'Storing firmware'
            self.__queue.put(self.__message)
            response = self.__perform_autoupdate(response)
            if response is False:
                self.__message['action'] = 'Failed to store firmware'
                self.__queue.put(self.__message)
                return False

        # activate new firmware
        if self.__message['board'] == "RMINI":
            self.__logger.info(f"{self.__serialnumber}: Waiting for at least 6.5 minutes ....")
        else:
            self.__logger.info(f"{self.__serialnumber}: Waiting for at least 1.5 minutes ....")
        self.__message['action'] = 'Activating firmware'
        self.__queue.put(self.__message)
        response = self.__activate_firmware()
        if response is False:
            self.__message['action'] = 'Failed to activate firmware'
            self.__queue.put(self.__message)
            return False

        # device will reboot now
        start = monotonic()
        while (monotonic() - start) < 60:
            sleep(1)

            # log in again
            try:
                logged_in = self.__login_rest(silent=True, timeout=5)
            except:
                continue

            if not logged_in:
                continue

            # get serialnumber of this device
            self.__message['serial'], self.__message['version'], self.__message['board'] = self.__get_serial()
            if self.__message['serial'] is None or self.__message['version'] is None or self.__message['board'] is None:
                continue

            if self.__message['version'] == self.__firmware_version:
                self.__logger.info(f"{self.__serialnumber}: Update finished, firmware on device is: {self.__message['version']}")
                return True

        # we could not contact device any more
        return False

    def __login_rest(self, username='insys', password='icom', silent=False, timeout=10):
        url = f'https://{self.__ip}/api/v2_0/auth/login'

        auth = { 'username': username, 'password': password }
        try:
            response = self.__session.post(url=url, json=auth, timeout=timeout)
        except:
            if not silent:
                self.__logger.error(f"{self.__serialnumber}: Unable to do HTTP login")
            return False

        self.__session.headers["Authorization"] = "Bearer " + response.json()['access']
        return True

    def __get_serial(self):
        url = f'https://{self.__ip}/api/v2_0/status/device_info'
        try:
            response = self.__session.get(url, verify=False, timeout=10)
        except Exception as e:
            self.__logger.info(f"{self.__serialnumber}: Could not contact device to get serial number: {str(e)}")
            return None, None, None

        if response.status_code != 200:
            self.__logger.info(f"{self.__serialnumber}: Could not get serial number of device: {response.status_code}")
            return None, None, None

        try:
            serialnumber = response.json()["status"]["list"][0]["serial_number"]
            if len(serialnumber) < 8:
                return None, None, None
        except:
            return None, None, None
        self.__serialnumber = serialnumber

        try:
            version = response.json()["status"]["list"][0]["firmware_version"]
            if len(version) < 3:
                return None, None, None
        except:
            self.__logger.info(f"{self.__serialnumber}: JSON does not contain valid firmware version")
            return None, None, None

        try:
            board_type = response.json()["status"]["list"][0]["board_type"]
            if len(board_type) < 3:
                return None, None, None
        except:
            self.__logger.info(f"{self.__serialnumber}: JSON does not contain valid board type")
            return None, None, None

        return serialnumber, version, board_type

    def __get_firmware_list(self):
        url = f'https://{self.__ip}/api/v2_0/firmware'
        try:
            response = self.__session.get(url, verify=False, timeout=10)
        except:
            self.__logger.info(f"{self.__serialnumber}: Could not get list of already stored firmware versions")

        if response.status_code != 200:
            self.__logger.info(f"{self.__serialnumber}: Getting firmware list failed")
            return False

        firmwares = response.json()
        if "firmware" in firmwares:
            self.__firmwares_available = firmwares["firmware"]
            return True

        return False

    def __set_time(self):
        url = f'https://{self.__ip}/api/v2_0/operation'
        now = datetime.datetime.now()
        payload = {}
        payload['method'] = 'manual_action'
        payload['params'] = {   'type': 'set_time',
                                'options': {
                                    'hour':   f"{now.hour}",
                                    'minute': f"{now.minute}",
                                    'second': f"{now.second}",
                                    'year':   f"{now.year}",
                                    'month':  f"{now.month}",
                                    'day':    f"{now.day}"
                                }
                            }
        try:
            response = self.__session.post(url, json=payload, verify=False, timeout=10)
        except Exception as e:
            self.__logger.info(f"{self.__serialnumber}: Setting time failed: {str(e)}")
            return False

        if response.status_code != 201:
            self.__logger.info(f"{self.__serialnumber}: Setting time failed")
            return False

        self.__logger.info(f"{self.__serialnumber}: Set time to {now.strftime('%F %T')}")
        return True

    def __set_info_led(self, onoff):
        url = f'https://{self.__ip}/api/v2_0/operation'
        payload = {}
        payload['method'] = 'manual_action'
        payload['params'] = { 'type': 'info_led', 'options': {'info_led': onoff}}

        try:
            response = self.__session.post(url, json=payload, verify=False, timeout=10)
        except Exception as e:
            self.__logger.info(f'{self.__serialnumber}: Switching INFO LED to "{onoff}" failed: {str(e)}')
            return False

        if response.status_code != 201:
            self.__logger.info(f'{self.__serialnumber}: Switching INFO LED to "{onoff}" failed')
            return False

        self.__logger.info(f'{self.__serialnumber}: Switch INFO LED to "{onoff}"')
        return True

    def __register_irm(self):
        if not "irm" in self.__profile:
            return True
        if not "active" in self.__profile["irm"]:
            return True
        if not "uri" in self.__profile["irm"]:
            return True
        if not "token" in self.__profile["irm"]:
            return True
        if not "group" in self.__profile["irm"]:
            return True
        active = self.__profile["irm"]["active"]
        uri    = self.__profile["irm"]["uri"]
        token  = self.__profile["irm"]["token"]
        group  = self.__profile["irm"]["group"]

        if active is False:
            self.__logger.info(f"{self.__serialnumber}: Skipping iRM registration")
            return True

        i = Irm(self.__logger, self.__dir_irm, uri, token)
        group_id = i.get_group_ID(group)

        # create device
        device_id = i.create_device(group_id, self.__serialnumber)
        if device_id is None:
            return False
        if i.get_connection_profile(device_id, self.__serialnumber) is False:
            return False

        response = self.__upload_file(f'{self.__serialnumber}.tar', self.__dir_irm)
        if response is False:
            return False

        response = self.__perform_upload(response.json(), True)
        if response is False:
            return False
        return True

    def __upload_config(self):
        filename = None
        config_table = self.__profile["config_table"]
        if "filename" in config_table:
            if config_table["filename"] == "---":
                return True

            filename = config_table["filename"]

        try:
            infile = open(self.__dir_files.joinpath(filename), 'r', encoding='UTF-8')
            table = csv.DictReader(infile, delimiter=';')
        except Exception as e:
            self.__logger.info(f'{self.__serialnumber}: Opening {filename} failed: {str(e)}')
            return False

        header =  table.fieldnames

        # search column with our serial number
        if self.__serialnumber in header:
            device_column = header.index(self.__serialnumber)
        else:
            self.__logger.info(f'{self.__serialnumber}: Serial number of device not found in CSV file')
            return False

        cli_list = []
        for row in table:
            cmd = row[header[0]]
            default_value = row[header[1]]
            value = row[header[device_column]]

            if "{VALUE_FROM_SN}" in cmd:
                cmd = cmd.format(VALUE_FROM_SN=value)

            if "{VALUE_FROM_ALL}" in cmd:
                cmd = cmd.format(VALUE_FROM_ALL=default_value)

            cli_list.append(cmd)

        _, tmp_file = tempfile.mkstemp(dir="/tmp")
        with open(tmp_file, 'w', newline='', encoding='utf-8') as outfile:
            for line in cli_list:
                outfile.write(line + '\n')

        response = self.__upload_file(tmp_file, self.__dir_files)
        os.remove(tmp_file)
        if response is False:
            return False

        response = self.__perform_upload(response.json(), True)
        if response is False:
            return False

        return True

    def __upload_files(self):
        for i in self.__profile["uploads"]:
            self.__message['action'] = f'Uploading: {i["filename"]}'
            self.__queue.put(self.__message)
            self.__logger.info(f'{self.__serialnumber}: Uploading {i["filename"]}')
            activate = False

            if "activate" in i:
                activate = i["activate"]

            response = self.__upload_file(i["filename"], self.__dir_files)
            if response is False:
                return False

            response = self.__perform_upload(response.json(), activate)
            if response is False:
                return False

        return

    def __upload_file(self, filename, filedir, filetype=None):
        if filetype and filetype == "firmware":
            # avoid uploading firmware, if it is already there
            fw = filename.split('-')[1]
            for i in self.__firmwares_available:
                if i["type"] == "icom_os":
                    if i["name"] == fw:
                        self.__logger.info(f'{self.__serialnumber}: Uploading {filename} not necessary, it is already available on device')
                        return True

        try:
            f = open(filedir.joinpath(filename), 'rb')
        except Exception as e:
            self.__logger.info(f'{self.__serialnumber}: Failed to open file {filedir.joinpath(filename)}')
            return False
        filedata = f.read()
        f.close()

        url = f'https://{self.__ip}/api/v2_0/upload/analyze'
        data = { 'fileinfo': '{"filename":"' + filename + '","profile":"Profile","password":""}' }
        try:
            files = { 'filedata': filedata }
        except Exception as e:
            self.__logger.info(f"{self.__serialnumber}: File {filename} could not be openend: {str(e)}")
            return False

        for i in range(3):
            try:
                response = self.__session.post(url, data=data, files=files, verify=False, timeout=120)
            except:
                sleep(3)
                continue

            if response.status_code != 201:
                self.__logger.info(f'{self.__serialnumber}: Uploading file "{filename}" failed, {response.status_code}: {response.reason}, {response.json()}')
                return False
            return response

        return False

    def __perform_upload(self, response, activate=False):
        url = f'https://{self.__ip}/api/v2_0/upload/perform'

        payload = {
            "identifier": response["identifier"],
            "profile": "Profile", # we assume, that we are in default settings"
            "entries": []
        }

        # walk over all entries of the analysed upload
        for c in response['content']:
            # ignore invalid entries
            if c['valid'] is False:
                continue

            e = {
                "entry": c['entry'],
                "action": "store"
            }

            # in case of an Update Packet with an ASCII file, store or apply it according to the result of the analysis
            if c['type'] == 'ASCII Configuration':
                if activate:
                    e['action'] = "apply"

            payload['entries'].append(e)

        self.__logger.info(f'{self.__serialnumber}: Storing uploaded file')
        for _ in range(3):
            try:
                response = self.__session.post(url, json=payload, verify=False, timeout=300)
            except:
                sleep(3)
                continue

            if response.status_code != 201:
                self.__logger.info(f'{self.__serialnumber}: Storing uploaded file failed: {response.status_code}: {response.reason}, {response.json()}')
                return False
            break;

        # walk over entries of response
        for x in response.json()['content']:
            if x["result"] != "done":
                self.__logger.info(f'{self.__serialnumber}: Storing uploaded file failed: {x["error"]}')
                #return False

        return True

    def __perform_autoupdate(self, response):
        url = f'https://{self.__ip}/api/v2_0/upload/perform'
        payload = {
            "identifier": response.json()["identifier"],
            "entries": [
                {
                    "entry": 0,
                    "action": "store"
                },
                {
                    "entry": 1,
                    "action": "store"
                }
            ]
        }
        self.__logger.info(f'{self.__serialnumber}: Storing uploaded file')
        try:
            response = self.__session.post(url, json=payload, verify=False, timeout=300)
        except Exception as e:
            self.__logger.info(f'{self.__serialnumber}: Storing firmware failed: {str(e)}')
            return False

        if response.status_code != 201:
            self.__logger.info(f'{self.__serialnumber}: Storing firmware failed: {response.status_code}: {response.reason}, {response.json()}')
            return False

        return True

    def __activate_firmware(self):
        url = f'https://{self.__ip}/api/v2_0/firmware'
        payload = {
            "type": "icom_os",
            "name": f'{self.__firmware_version}',
            "issue_reset": True
        }

        self.__logger.info(f"{self.__serialnumber}: Activating firmware {self.__firmware_version}")
        try:
            response = self.__session.put(url, json=payload, verify=False, timeout=300)
        except Exception as e:
            self.__logger.info(f'{self.__serialnumber}: Activating firmware {self.__firmware_version} failed: {str(e)}')
            return False

        if response.status_code != 200:
            self.__logger.info(f'{self.__serialnumber}: Activating firmware {self.__firmware_version} failed')
            return False

        return True
