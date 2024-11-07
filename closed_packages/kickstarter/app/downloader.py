import os
from threading import Thread
import tempfile
from pathlib import Path
from time import sleep, monotonic
import urllib3
import requests
from hashlib import sha256

class Downloader(Thread):
    def __init__(self, logger, queue, config):
        Thread.__init__(self)
        urllib3.disable_warnings()
        self.__logger = logger
        self.__queue = queue
        self.__shutdown = False
        self.__config = config
        self.__profile = self.__config["profile"]

    def run(self):
        self.config_update(self.__config)
        while self.__shutdown is False:
            self.__search_new_firmware()
            sleep(10)

    def shutdown(self):
        self.__logger.info('Shutting down downloader')
        self.__shutdown = True

    def config_update(self, config):
        self.__check_intervall = int(self.__profile['auto-update']['check_interval']) * 3600
        self.__time_checked = 0 - self.__check_intervall
        self.__config = config
        self.__profile = self.__config["profile"]
        self.__logger.info(f'Set checking for new firmware to "{self.__profile["auto-update"]["active"]}"')

    # search for new firmware
    def __search_new_firmware(self):
        if self.__profile["auto-update"]["active"] is not True:
            return

        if self.__time_checked == 0 or monotonic() > (self.__time_checked + self.__check_intervall):
            self.__logger.info('Checking for new firmware update')
            while True:
                self.__time_checked = monotonic()

                err, ret = self.__start_autoupdate()
                if err: # check failed:
                    sleep(60)
                    continue

                if ret and '-' in ret: # new version downloaded
                    # extract x.y number from firmware file name
                    firmware_version = ret.split('-')[1]
                    self.__logger.info(f'Downloaded firmware version {firmware_version}')

                    # send firmware version to main
                    self.__queue.put(ret)
                else:
                    self.__logger.info('No new firmware version available')

                break

    # contact the Auto Update server for the firmware
    def __start_autoupdate(self):
        dl_path = None
        uri = self.__profile['auto-update']['uri']
        protocol = uri.split('/')[0]
        hostname = uri.split('/')[2]

        # download list file with downloading instructions
        with requests.get(uri, stream=True, verify=False, timeout=10) as r:
            r.raise_for_status()
            tmp = tempfile.NamedTemporaryFile()
            with open(tmp.name, "wb+") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)

            with open(tmp.name, "r+", encoding='UTF-8') as f:
                x = f.read()
                # extract path to file that should be downloaded
                dl_path = x.split(';')[1:][0].rstrip()

        if dl_path is None:
            return True, None

        # extract firmware file name from path, and remove trailing new line or carriage return
        firmware_file_name = dl_path.split('/')[1:][1:][0].rstrip()

        # create the target directory if it does not exist
        firmware_path = Path(self.__config['dirs']['files'])
        if os.path.isfile(firmware_path) is False:
            try:
                firmware_path.mkdir(exist_ok=True, parents=True)
            except Exception as e:
                self.__logger.info(f'Could not create directory {firmware_path}: {str(e)}')
                return False, None

        # check if file already exists locally
        firmware_path = firmware_path.joinpath(firmware_file_name)

        if firmware_path.is_file():
            self.__logger.info(f'Firmware already exists: {firmware_file_name}')
            return False, None

        # download file via http
        self.__logger.info(f'Downloading: {firmware_file_name}')
        with requests.get(protocol + '//' + hostname + '/' + dl_path, stream=True, verify=False, timeout=10) as r:
            r.raise_for_status()
            with open(firmware_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)

            # create hash file
            with open(firmware_path, 'rb') as f:
                hashes_path = Path(self.__config['dirs']['hashes']).joinpath(firmware_file_name)
                data = f.read()
                try:
                    h = open(hashes_path, "w", encoding="UTF-8")
                    h.write(sha256(data).hexdigest())
                    h.close()
                except Exception as e:
                    self.__logger.info(f"Could not store sha256sum of file {firmware_path} : {str(e)}")

            os.sync()
        return False, firmware_file_name
