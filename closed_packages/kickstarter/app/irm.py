""" Create devices in iRM and download the Connection Profile """

import os
import json
import requests
from pathlib import Path

class Irm():
    def __init__(self, logger, dir_irm, uri, token):
        self.__logger = logger
        self.__dir_irm = Path(dir_irm)
        self.__bearer = 'Bearer ' + token
        self.__header = { 'Authorization': self.__bearer,
                          'Content-Type': 'application/json' }
        self.__uri = uri + '/'

    # get UUID of given group or the very first group, when no groupname is given
    def get_group_ID(self, group_name=None):
        payload = {}
        try:
            response = requests.request("GET", self.__uri + 'inventory/device-groups',
                                        data=json.dumps(payload), headers=self.__header, timeout=21)
        except Exception as e:
            self.__logger.info(f"iRM: Could not connect to iRM at: {self.__uri}; could not get group ID: {e}")
            return None

        if response.status_code != 200:
            self.__logger.info(f'iRM: Could not get group ID, status code {response.status_code}')
            return None

        # if no group_name has been given, use the first group
        result = response.json()
        group_id = result['members'][0]['uuid']
        if group_name:
            group_found = False
            for g in result['members']:
                if g['name'] == group_name:
                    group_id = g['uuid']
                    group_found = True
                    break

            # if given group has not been found, create a group
            if group_found is False:
                self.__logger.info(f'iRM: group "{group_name}" not found, creating group')
                return self.__create_group(group_name)

        return group_id

    # create a new group
    def __create_group(self, group_name):
        payload = { 'name': group_name }
        try:
            response = requests.request("POST", self.__uri + 'inventory/device-groups',
                                        data=json.dumps(payload),
                                        headers=self.__header, timeout=22)
        except Exception as e:
            self.__logger.info(f'iRM: Could not create "{group_name}": {e}')
            return None

        if response.status_code != 201:
            self.__logger.info(f'iRM: Could not create "{group_name}": {response.status_code}')
            return None

        self.__logger.info(f'iRM: Created group "{group_name}"')
        return response.json()['uuid']

    # create a new device
    def create_device(self, group_id, serial):
        payload = { 'connectionPingInterval': 120,
                    'connectionPongTimeout': 104,
                    'connectionSessionTimeout': 16,
                    'groupUuid': group_id,
                    'location': '',
                    'name': serial,
                    'serialNumber': serial }
        try:
            response = requests.request("POST", self.__uri + 'inventory/managed-devices', data=json.dumps(payload),
                                        headers=self.__header, timeout=23)
        except Exception as e:
            self.__logger.info(f"iRM: Could not create device with serial number: {serial}: {e}")
            return None

        if response.status_code == 201:
            self.__logger.info(f'iRM: Created device with serial number {serial}')
        else:
            # eventually a device with this serial number already exists, send a request about it
            payload = {}
            url = f'{self.__uri}inventory/managed-devices?serialNumber={serial}'
            try:
                response = requests.request("GET", url, data=json.dumps(payload), headers=self.__header, timeout=24)
            except Exception as e:
                self.__logger.info(f'iRM: Could not connect to iRM at: {self.__uri}; could check device with serial number: {e}')
                return None

            if response.status_code != 200:
                self.__logger.info(f'iRM: Could not create device with serial number {serial}: {response.status_code}')
                return None
            self.__logger.info(f'iRM: Device with serial number {serial}: already exists, it will not get modified')

        return response.json()['uuid']

    # get Connection Profile
    def get_connection_profile(self, device_id, serial):
        payload = {}
        url = f'{self.__uri}inventory/managed-devices/{device_id}/connection-profile?format=update-packet'
        try:
            response = requests.request("GET", url, data=json.dumps(payload), headers=self.__header, timeout=120)
        except Exception as e:
            self.__logger.info(f"iRM: Could not connect to iRM at: {self.__uri}; could not get Connection Profile: {e}")
            return False

        if response.status_code != 200:
            self.__logger.info(f"iRM: Could not download Connection Profile of device with serial number {serial}: {response.status_code}")
            return False

        # store a given content in a file
        with open(self.__dir_irm.joinpath(serial + '.tar'), "wb") as file:
            file.write(response.content)

        return True

    # delete device
    def delete_device(self, device_id):
        payload = {}
        url = f'{self.__uri}inventory/managed-devices/{device_id}'
        try:
            response = requests.request("DELETE", url, data=json.dumps(payload), headers=self.__header, timeout=26)
        except Exception as e:
            self.__logger.info(f"iRM: Could not connect to iRM at: {self.__uri}; could not delete device: {e}")
            return False

        if response.status_code != 201:
            self.__logger.info(f"iRM: Could not delete device with device_id {device_id}: {response.status_code}")
            return False
        return True
