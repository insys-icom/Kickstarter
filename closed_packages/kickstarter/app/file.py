from threading import Thread, Event
from os import path, makedirs, sync, remove, scandir, rename, listdir
from base64 import b64decode
from datetime import datetime
from pathlib import Path
import asyncio
from hashlib import sha256
from subprocess import Popen, PIPE, check_output
from string import Template

from asyncinotify import Inotify, Mask

from mqtt import Topics

class File():
    def __init__(self, logger, mqtt, dirs):
        self.__logger = logger
        self.__mqtt = mqtt
        self.__local_files = []          # contains all locally stored files like Update Packets or ASCII files
        self.__filepath = Path(dirs['files'])
        self.__hashpath = Path(dirs['hashes'])

        # create path in case this is the first run
        if not path.exists(self.__filepath):
            makedirs(self.__filepath)

        # start observing the locally stored files in a thread
        self._shutdown = Event()
        self._thread = Thread(target=self.__wrap_async_func, args=[self.__filepath, self._shutdown])
        self._thread.start()

    def shutdown(self):
        self.__logger.info("Shutting down file monitor")

    def __wrap_async_func(self, watch_path, shutdown):
        asyncio.run(self.__observe_dir(watch_path, shutdown))

    # store a file uploaded via MQTT
    def store_uploaded_file(self, j):
        self.__logger.info(f"File received: {j["name"]}, {j["type"]}, {j["size"]} bytes")

        try:
            data = b64decode(str(j["content"]).split(",")[1])
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

        sync()
        return True

    def delete_file(self, msg):
        if "filename" in msg:
            try:
                remove(self.__filepath.joinpath(msg["filename"]))
            except Exception as e:
                self.__logger.info(f"Could not delete file {msg["filename"]} : {str(e)}")

            # ignore errors when deleting the HASH file; there is none when it's an self generated one
            try:
                remove(self.__hashpath.joinpath(msg["filename"]))
            except:
                pass

            return True
        return False

    def store_config(self, filepath, content):
        try:
            with open(filepath, "w+", encoding='UTF-8') as f:
                f.write(content)
        except Exception as err:
            self.__logger.info(f"Could not write config file: {err}")
            return False

        return True

    def get_sha256(self, file):
        h = "---"
        try:
            f = open(self.__hashpath.joinpath(file), "r", encoding="UTF-8")
        except:
            return h

        h = f.read()
        f.close()
        return h

    def read_local_files(self):
        with scandir(self.__filepath) as dir_entries:
            files = []
            for f in dir_entries:
                if f.is_file:
                    fstat = f.stat()
                    fsize = fstat.st_size
                    entry = {}
                    entry['name'] = f.name
                    entry['size'] = f'{fsize}'
                    entry['mtime'] = datetime.fromtimestamp(fstat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
                    entry['sha256'] = self.get_sha256(f.name)
                    files.append(entry)
            self.__local_files = sorted(files, key=lambda d: d['name'])

            # send existing locally stored files
            self.__mqtt.publish(Topics.LOCALFILES, self.__local_files, retain=True)

        return True

    def get_latest_firmware(self):
        file_list = listdir(self.__filepath)
        version = 0
        for f in file_list:
            if "autoupdate-" in f[:-11] and ("-full.tar" in f[-9:] or
                                       "-full.arm32.tar" in f[-15:] or
                                       "-full.arm64.tar" in f[-15:]):
                try:
                    version_in_filename = float(f.split('-')[1])
                    version = max(version, version_in_filename)
                except:
                    pass

        if version != 0:
            return f"{version}"
        return "---"

    def rollate_aftercare_files(self, csv_path, log_path):
        now = datetime.now().strftime('%Y-%m-%d_%H%M%S')

        if (path.isfile(csv_path)):
            directory = path.dirname(csv_path)
            base = path.basename(csv_path)
            result = Path(directory).joinpath(now + "_" + base)
            rename(csv_path, result)

        if (path.isfile(log_path)):
            directory = path.dirname(log_path)
            base = path.basename(log_path)
            result = Path(directory).joinpath(now + "_" + base)
            rename(log_path, result)

    async def __observe_dir(self, watch_path, shutdown):
        mask = Mask.DELETE | Mask.DELETE_SELF | Mask.CLOSE_WRITE
        with Inotify() as inotify:
            inotify.add_watch(Path(watch_path), mask)
            async for event in inotify:
                # update list of locally stored files
                self.read_local_files()
                if event.mask == Mask.IGNORED:
                    inotify.add_watch(Path(watch_path), mask)

    # flush all IPv6 addresses from an interface and set new link local one and add the first address of the given prefix
    def reconfigure_net(self, interface, prefix):
        with Popen(["/bin/ip", "-6", "address", "flush", "dev", interface ]) as cmd:
            cmd.communicate()

        with Popen(["/bin/ip", "-6", "address", "add", "fe80::1/64", "dev", interface ]) as cmd:
            cmd.communicate()

        with Popen(["/bin/ip", "-6", "address", "add", f"{prefix}1/64", "dev", interface ]) as cmd:
            cmd.communicate()

    # write a new radvd config file and restart radvd
    def radvd_config(self, interface, prefix):
        template = ""

        # read template
        try:
            with open("/etc/radvd_template.conf", "r", encoding='UTF-8') as f:
                template = f.read()
        except Exception as e:
            self.__logger.info(f"Error: Could not read radvd config: {str(e)}")
            return False

        # create new config
        s = Template(template)
        try:
            s = s.safe_substitute(INTERFACE=interface, PREFIX=prefix)
        except Exception as e:
            self.__logger.info(f"Error: Could not substitute values in radvd config template: {str(e)}")
            return False

        # write new config to file
        try:
            with open("/etc/radvd.conf", "wb") as f:
                f.write(bytes(s, 'UTF-8'))
        except Exception as e:
            self.__logger.info(f"Error: Could not write radvd config: {str(e)}")
            return False

        # get radvd PID and kill it
        pid = ""
        try:
            with open("/tmp/radvd.pid", "r", encoding='UTF-8') as f:
                pid = f.read().strip("\n")
        except Exception as e:
            self.__logger.info(f"Error: Could not read radvd PID file: {str(e)}")
            return False

        with Popen(["kill", pid], stdout=PIPE, stderr=PIPE) as kill:
            kill.communicate()

        return True

    # set login for http and ssh
    def set_login(self, login):
        active = login["active"]
        username = login["username"]
        password = login["password"]

        if username == "" or password == "":
            active = False

        # create a new config file for httpd
        with open("/data/etc/httpd.conf", "w+", encoding='UTF-8') as f:
            line = ""
            if active:
                line = f"/:{username}:{password}\n"
            f.write(line)

        # let httpd restart by init
        with Popen(["killall", "httpd"], stdout=PIPE, stderr=PIPE) as kill:
            kill.communicate()

        # set password of root to the same
        if active is False:
            password = "root"

        with Popen([ "/bin/echo", f"root:{password}" ], stdout=PIPE) as ps:
            check_output(('chpasswd'), stdin=ps.stdout)
            ps.wait()
