from os import path, sync
from threading import Thread
from tempfile import NamedTemporaryFile
from pathlib import Path
from time import sleep, monotonic
from hashlib import sha256
from urllib3 import disable_warnings
import requests


class Downloader(Thread):
    def __init__(self, logger, shutdown, queue, profile, settings):
        Thread.__init__(self)
        disable_warnings()
        self.__logger = logger
        self.__queue = queue
        self.__shutdown = shutdown
        self.__profile = profile
        self.__settings = settings
        self.__check_intervall = 0
        self.__time_checked = 0
        self.__online = False

    def run(self):
        self.profile_update(self.__profile)
        while True:
            if self.__shutdown.wait(timeout=15):
                self.__logger.info('Shutting down downloader')
                break

            self.__check_internet(self.__profile['auto-update']['uri'])
            self.__search_new_firmware()

    def profile_update(self, profile):
        self.__check_intervall = int(self.__profile['auto-update']['check_interval']) * 3600
        self.__time_checked = 0 - self.__check_intervall
        self.__profile = profile
        self.__logger.info(f'Set checking for new firmware to "{self.__profile["auto-update"]["active"]}"')

    # get head of URI of Auto Update server to check for internet connection state
    def __check_internet(self, url):
        online = False
        try:
            r = requests.head(url, timeout=60)
            if r.status_code == 200:
                online = True
        except:
            pass

        if self.__online != online:
            self.__logger.info(f"Internet state changed to {online}")
            self.__online = online
            self.__queue.put({ "internet": online })

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
                    self.__queue.put({ "firmware": ret })
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
        r = None
        try:
            r = requests.get(uri, stream=True, verify=False, timeout=10)
        except:
            return False, None

        tmp = NamedTemporaryFile()
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
        firmware_path = Path(self.__settings['dirs']['files'])

        # download the file for arm32
        self.__download_file(dl_path, firmware_path, firmware_file_name, protocol, hostname)

        # download the file for arm64
        dl_path = f"{dl_path.split("tar")[0]}arm64.tar"
        firmware_file_name = f"{firmware_file_name.split("tar")[0]}arm64.tar"

        return self.__download_file(dl_path, firmware_path, firmware_file_name, protocol, hostname)

    def __download_file(self, dl_path, firmware_path, firmware_file_name, protocol, hostname):
        if path.isfile(firmware_path) is False:
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
        try:
            r = requests.get(protocol + '//' + hostname + '/' + dl_path, stream=True, verify=False, timeout=10)
        except:
            return False, None

        with open(firmware_path, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)

        # create hash file
        with open(firmware_path, 'rb') as f:
            hashes_path = Path(self.__settings['dirs']['hashes']).joinpath(firmware_file_name)
            data = f.read()
            try:
                h = open(hashes_path, "w", encoding="UTF-8")
                h.write(sha256(data).hexdigest())
                h.close()
            except Exception as e:
                self.__logger.info(f"Could not store sha256sum of file {firmware_path} : {str(e)}")

            sync()

        return False, firmware_file_name

