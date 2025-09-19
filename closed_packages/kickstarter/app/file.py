import threading
import os
import json
import base64
import datetime
from pathlib import Path
import asyncio
from hashlib import sha256
from asyncinotify import Inotify, Mask

class File():
    def __init__(self, logger, mqtt, dirs):
        self.__logger = logger
        self.__mqtt = mqtt
        self.__local_files = []          # contains all locally stored files like Update Packets or ASCII files
        self.__filepath = Path(dirs['files'])
        self.__hashpath = Path(dirs['hashes'])

        # create path in case this is the first run
        if not os.path.exists(self.__filepath):
            os.makedirs(self.__filepath)

        # start observing the locally stored files in a thread
        _thread = threading.Thread(target=self.__wrap_async_func, args=[self.__filepath])
        _thread.start()

    def __wrap_async_func(self, args):
        asyncio.run(self.__observe_dir(args))

    # store a file uploaded via MQTT
    def store_uploaded_file(self, j):
        self.__logger.info(f"File received: {j["name"]}, {j["type"]}, {j["size"]} bytes")

        try:
            data = base64.b64decode(str(j["content"]).split(",")[1])
        except:
            return False

        # store file
        try:
            f = open(self.__filepath.joinpath(j["name"]), "wb")
            f.write(data)
            f.close()
        except Exception as e:
            self.__logger.info(f"Could not store {j['name']} : {str(e)}")

        # store hash value
        try:
            f = open(self.__hashpath.joinpath(j['name']), "w", encoding="UTF-8")
            f.write(sha256(data).hexdigest())
            f.close()
        except Exception as e:
            self.__logger.info(f"Could not store sha256sum of file {j['name']} : {str(e)}")

        os.sync()
        return True

    def delete_file(self, msg):
        if "filename" in msg:
            try:
                os.remove(self.__filepath.joinpath(msg["filename"]))
            except Exception as e:
                self.__logger.info(f"Could not delete file {msg["filename"]} : {str(e)}")

            # ignore errors when deleting the HASH file; there is none when it's an self generated one
            try:
                os.remove(self.__hashpath.joinpath(msg["filename"]))
            except Exception as e:
                pass

            return True
        return False

    def store_profile(self, filepath, config, profile):
        try:
            with open(filepath, "w+", encoding='UTF-8') as f:
                config["profile"] = profile
                f.write(json.dumps(config, indent=4))
        except Exception as err:
            self.__logger.info(f"Could not write config file: {err}")
            return False

        return True

    def get_sha256(self, file):
        h = "---"
        try:
            f = open(self.__hashpath.joinpath(file), "r", encoding="UTF-8")
        except Exception as e:
            #self.__logger.info(f"Could not read sha256sum of file {file} : {str(e)}")
            return h

        h = f.read()
        f.close()
        return h

    def read_local_files(self):
        with os.scandir(self.__filepath) as dir_entries:
            files = []
            for f in dir_entries:
                if f.is_file:
                    fstat = f.stat()
                    fsize = fstat.st_size
                    entry = {}
                    entry['name'] = f.name
                    entry['size'] = f'{fsize}'
                    entry['mtime'] = datetime.datetime.fromtimestamp(fstat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
                    entry['sha256'] = self.get_sha256(f.name)
                    files.append(entry)
            self.__local_files = sorted(files, key=lambda d: d['name'])

            # send existing locally stored files
            self.__mqtt.msg_local_files(self.__local_files)

        return True

    def get_latest_firmware(self):
        file_list = os.listdir(self.__filepath)
        s = []
        for f in file_list:
            if "autoupdate-" in f and "-full.tar" in f[-9:]:
                s.append(f)
        s = sorted(s)[-1:]
        if len(s) > 0:
            return s[0]
        else:
            return []

    def rollate_aftercare_files(self, csv_path, log_path):
        now = datetime.datetime.now().strftime('%Y-%m-%d_%H%M%S')

        if (os.path.isfile(csv_path)):
            directory = os.path.dirname(csv_path)
            base = os.path.basename(csv_path)
            result = Path(directory).joinpath(now + "_" + base)
            os.rename(csv_path, result)

        if (os.path.isfile(log_path)):
            directory = os.path.dirname(log_path)
            base = os.path.basename(log_path)
            result = Path(directory).joinpath(now + "_" + base)
            os.rename(log_path, result)

    async def __observe_dir(self, path):
        mask = Mask.DELETE | Mask.DELETE_SELF | Mask.CLOSE_WRITE
        with Inotify() as inotify:
            inotify.add_watch(Path(path), mask)
            async for event in inotify:
                # update list of locally stored files
                self.read_local_files()
                if event.mask == Mask.IGNORED:
                    inotify.add_watch(Path(path), mask)
