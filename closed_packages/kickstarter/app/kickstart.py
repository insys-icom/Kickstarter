#!/usr/bin/env python3

import signal
import sys
import os
import json
import csv
import subprocess
import argparse
from pathlib import Path
from queue import Empty, Queue
import logging.handlers
from time import sleep
from downloader import Downloader
from mqtt import Mqtt, Topics
from updater import Updater
from file import File
from cli import Cli
from searcher import Searcher

class Kickstart():
    def __init__(self):
        self.__logger = None
        self.__queue_mqtt = Queue()
        self.__queue_searcher = Queue()
        self.__queue_downloader = Queue()
        self.__queue_devices = {}          # key: IP address, value: Queue object of thread
        self.__thread_list = {}            # key: IP address, value: thread object
        self.__existing_list = {}          # key: IP address, value: message struct
        self.__config_file = "config.json" # path to the config file
        self.__path_firmware = ''          # path to currently used firmware file
        self.__path_aftercare = None       # path to data with aftercare data
        self.__path_csv = None             # path to data containing the aftercare data as CSV
        self.__config = {}                 # contains config for this backend
        self.__profile = {}                # contains profile, what user wants to put onto devices
        self.__fw_version = "---"          # the firmware we are currently flashing onto devices
        self.__aftercare_data = {}         # all known data from aftercare phases
        self.__device_info = '/devices/device_info.json'  # path to detect, if this is an INSYS device
        self.__uds = '/devices/cli_no_auth/cli.socket'    # path to the UDS that gives unauthorized access to the CLI

        # create Logger
        self.__create_logger("kickstarter")

        # get given arguments
        parser = argparse.ArgumentParser(description='Search for Link-Local IPv6 addresses and try to configure them')
        parser.add_argument('-c', '--config', dest='config_path', nargs=1, help='path to config file')
        args = parser.parse_args()

        # read the config and its stored profile
        if args.config_path:
            self.__config_file = ''.join(args.config_path)
        self.__read_configfile()
        if self.__config is False:
            sys.exit(-1)

        # start device searcher
        self.__searcher = Searcher(self.__logger, self.__queue_searcher, self.__config['net']['interface'], self.__config['net']['prefix'])
        self.__searcher.start()

        # start MQTT client
        self.__mqtt = Mqtt(self.__logger, self.__queue_mqtt, self.__config)

        # use MQTT client as an additional logger
        self.__logger.addHandler(self.__mqtt)

        # get a File instance
        self.__file = File(self.__logger, self.__mqtt, self.__config["dirs"])

        # start Downloader to get most recent firmware update
        self.__downloader = Downloader(self.__logger, self.__queue_downloader, self.__config)
        self.__downloader.start()

        # read all locally stored files
        self.__file.read_local_files()

        # load firmware to update devices to
        self.__get_firmwarefile_name()

        # install signal handler to exit
        signal.signal(signal.SIGINT, self.__shutdown)

        # clear alarm topic
        self.__mqtt.msg_alert('')

        # set a few path variables
        if 'aftercare' in self.__profile:
            if 'logfile' in self.__profile['aftercare']:
                self.__path_aftercare = Path(self.__config['dirs']['files']).joinpath(self.__profile['aftercare']['logfile'])

            if 'csvfile' in self.__profile['aftercare']:
                self.__path_csv = Path(self.__config['dirs']['files']).joinpath(self.__profile['aftercare']['csvfile'])

        # read all aftercare data from file
        self.__read_aftercare_file()

        # start never ending main loop
        self.__mainloop()

    def __shutdown(self, frame, x):
        self.__downloader.shutdown()
        self.__mqtt.shutdown()
        self.__logger.info("Shutting down")
        sys.exit(0)

    def __read_configfile(self):
        try:
            with open(self.__config_file, "r", encoding='UTF-8') as f:
                self.__config = json.load(f)
        except Exception as err:
            print("Could not read config file: %s", {err})
            sys.exit(-1)

        self.__profile = self.__config["profile"]

    # get history of all finished devices from file
    def __read_aftercare_file(self):
        if self.__path_aftercare is None:
            return False

        if not "aftercare" in self.__profile:
            return True
        if not "active" in self.__profile["aftercare"]:
            return True
        if not "logfile" in self.__profile["aftercare"]:
            return True

        try:
            file = open(self.__path_aftercare, "r", encoding='UTF-8')
            self.__aftercare_data = json.load(file)
            file.close()
        except Exception as e:
            return False

        self.__mqtt.msg_aftercare_devices(len(self.__aftercare_data))

    # append info of aftercare phase to log file
    def __append_aftercare_data(self, message):
        if self.__path_aftercare is None:
            return False

        if not 'aftercare' in message:
            return False

        self.__aftercare_data[message['ip']] = message['aftercare']

        try:
            json.dump(self.__aftercare_data, open(self.__path_aftercare, 'w', encoding='UTF-8'), indent=4)
        except Exception as e:
            self.__logger.info("Could not store JSON file: " + str(e))
            return False

        self.__mqtt.msg_aftercare_devices(len(self.__aftercare_data))

        return True

    # export the aftercare data into a CSV file
    def __create_csv_file(self):
        if self.__path_csv is None:
            return False

        delimiter = ";"
        if 'csv_delimiter' in self.__profile['aftercare']:
            delimiter = self.__profile['aftercare']['csv_delimiter']
        csv.register_dialect('insys', delimiter=delimiter)

        fieldnames = []
        for i in self.__aftercare_data:
            fieldnames = self.__aftercare_data[i].keys()
            break

        with open(self.__path_csv, 'w', newline='', encoding='utf-8') as outfile:
            writer = csv.DictWriter(outfile, fieldnames=fieldnames, dialect='insys')
            writer.writeheader()

            # apppend lines
            for i in self.__aftercare_data:
                writer.writerow(self.__aftercare_data[i])

        return True

    # find the firmware file name, that should be flashed
    def __get_firmwarefile_name(self):
        name = self.__profile["firmware"]["filename"]

        if name == "latest":
            self.__path_firmware = self.__file.get_latest_firmware()
        elif name == "---":
            self.__path_firmware = None
        else:
            self.__path_firmware = name

        if self.__path_firmware and len(self.__path_firmware) > 1:
            self.__fw_version = self.__path_firmware.split('-')[1]

    # default syslogger writing to syslog
    def __create_logger(self, name):
        self.__logger = logging.getLogger(name)
        self.__logger.setLevel(logging.INFO)
        handler = logging.handlers.SysLogHandler(address='/dev/log')
        handler.formatter = logging.Formatter(": %(name)s: %(message)s")
        self.__logger.addHandler(handler)
        self.__logger.info("Started")

    # find out or own link lokal IP address on the configured eth interface
    def __find_own_ip(self):
        ips = []
        if not os.path.exists(self.__device_info):
            # own IP address only relevant when kickstarter runs on an INSYS device
            return None

        if not os.path.exists(self.__uds):
            self.__logger.info("Unable to get own IP addresses - is unauthorized access to CLI active?")
            self.__mqtt.msg_alert('This container needs access to the router CLI without authentication, at least the user group "Status"')
            return ips

        cli = Cli(self.__uds)
        if cli is False:
            self.__logger.info("Unable to get own IP addresses")
            sys.exit(-1)

        text = cli.get("status.sysdetail.ip_addresses")
        for line in str(text).split("\n"):
            if "].ip_address=" in line and "fe80::" in line:
                ips.append(f'{self.__config['net']['prefix']}{line.split("fe80::")[1].split("/")[0]}')

        cli.disconnect()
        return ips

    # ping a specific IP address
    def __ping_device(self, ip):
        """ ping a specific device """
        ping = subprocess.Popen(["ping", "-c", "1", "-W", "1", "-I",
                                 self.__config['net']['interface'], ip],
                                 stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE)
        out = ping.communicate()

        for line in str(out).split("\\n"):
            if "1 packets transmitted, 1 " in line:
                return True

        return False

    # send list of all found devices
    def __send_existing(self):
        j = []
        for value in self.__existing_list.values():
            entry = {}
            if 'serial' in value:
                entry['Serial'] = value['serial']
            if 'board' in value:
                entry['Model'] = value['board']
            if 'version' in value:
                entry['Firmware'] = value['version']
            if 'ip' in value:
                entry['IPv6 address'] = value['ip']
            if 'action' in value:
                entry['Action'] = value['action']
            if 'in_progress' in value:
                entry['in_progress'] = value['in_progress']
            j.append(entry)

        self.__mqtt.msg_existing_devices(json.dumps(j))

    # collect all messages from threads
    def __get_queue_messages(self, queue):
        try:
            return queue.get(block=True, timeout=0)
        except Empty:
            pass
        return None

    # send info about all detected devices
    def __mqtt_hello(self):
        # set status to online
        self.__mqtt.msg_status_online()

        # send list of detected devices
        self.__send_existing()

        # send the current firmware version
        self.__mqtt.msg_latest_firmware(self.__fw_version)

        # send current profile
        self.__mqtt.msg_profile(self.__profile)

        # send latest log entries
        self.__mqtt.msg_last_log_entries()

        # update list of locally stored files
        self.__file.read_local_files()

        # send number of finished devices in aftercare file
        self.__mqtt.msg_aftercare_devices(len(self.__aftercare_data))

    # interprete an incoming MQTT message
    def __do_mqtt_message(self, msg):
        # a new client connected and needs info
        if "connect" in msg:
            # we, the backend, connected to mqtt, so broadcast all info
            self.__mqtt_hello()

        # another mqtt client sent something
        if "message" in msg:
            m = msg["message"]

            if m.topic == Topics.UPLOAD.fullpath():
                # store the file locally
                self.__file.store_uploaded_file(json.loads(m.payload))

            elif m.topic == Topics.PROFILE_UP.fullpath():
                # store the received profile in file
                self.__profile = json.loads(m.payload)
                self.__file.store_profile(self.__config_file, self.__config, self.__profile)

                # broadcast new profile to everyone
                self.__mqtt.msg_profile(self.__profile)

                # load firmware to update devices to
                self.__get_firmwarefile_name()

                # send the current firmware version
                self.__mqtt.msg_latest_firmware(self.__fw_version)

                # reconfigure downloader thread
                self.__downloader.config_update(self.__config)

            elif m.topic == Topics.DELETE_FILE.fullpath():
                self.__file.delete_file(json.loads(m.payload))

            elif m.topic == Topics.AFTERCARE_RESET.fullpath():
                self.__logger.info("Starting new aftercare files due to restart signal")
                self.__file.rollate_aftercare_files(self.__path_csv, self.__path_aftercare)
                self.__file.read_local_files()

                # send number of finished devices in aftercare file, should be 0 now
                self.__aftercare_data = {}
                self.__mqtt.msg_aftercare_devices(len(self.__aftercare_data))


    # never ending main loop
    def __mainloop(self):
        """ endlessly search for new devices and start a configure thread for every found one """
        mqtt_update = False
        # ignore IPs from config
        ignore_ips = self.__config['net']['ignore-ips'].split(',')

        # ignore own IPs from this devices
        own_ips = []
        while True:
            ret = self.__find_own_ip()
            if ret is None:
                break;

            own_ips = ret
            if len(own_ips) < 1:
                sleep(10)
            else:
                break

        for i in own_ips:
            ignore_ips.append(i)

        ips = [] # list of found devices
        while True:
            remove_ips = []

            for ip in ips:
                mqtt_update = False

                # ignore these IPs
                if ip in ignore_ips:
                    continue

                # ignore already updated devices:
                if ip in self.__existing_list:
                    continue

                # this is an unknown IP address
                if ip not in self.__thread_list:
                    # start configuring the device if it is still pingable
                    if self.__ping_device(ip) is True:
                        self.__logger.info('Device found: %s', ip)
                        self.__queue_devices[ip] = Queue()
                        self.__thread_list[ip] = Updater(self.__logger,
                                                         self.__queue_devices[ip],
                                                         "[" + ip + "]",
                                                         self.__path_firmware,
                                                         self.__config['dirs'],
                                                         self.__profile)

                        # start the thread
                        self.__thread_list[ip].start()
                    else:
                        # remove none reachable devices from list
                        remove_ips.append(ip)

            # wait for messages from the updating threads
            for ip in ips:
                try:
                    message = self.__queue_devices[ip].get(block=False)
                    self.__queue_devices[ip].task_done()
                    if message is not None:
                        mqtt_update = True
                        self.__existing_list[ip] = message
                        if message["aftercare"] is not None:
                            self.__append_aftercare_data(message)
                            self.__create_csv_file()
                            self.__file.read_local_files()

                except:
                    pass

                if ip in self.__thread_list:
                    if self.__thread_list[ip].is_alive() is False:
                        remove_ips.append(ip)

            # get rid of old threads
            for i in remove_ips:
                if i in self.__thread_list:
                    del self.__thread_list[i]
                if i in self.__queue_devices:
                    del self.__queue_devices[i]

            # get rid of unpingable devices, unless they perform a reset
            repeat = True
            while repeat:
                repeat = False
                for i in self.__existing_list:
                    if i not in ips:
                        if self.__existing_list[i]['in_progress'] is not True:
                            del self.__existing_list[i]
                            mqtt_update = True
                            repeat = True
                            break

            # publish complete list after any change
            if mqtt_update:
                self.__send_existing()

            # read incoming message from MQTT broker
            msg = self.__get_queue_messages(self.__queue_mqtt)
            if msg:
                self.__do_mqtt_message(msg)

            # read incoming message from device searcher
            msg = self.__get_queue_messages(self.__queue_searcher)
            if msg is not None:
                ips = msg

            # read incoming message from downloader
            ret = self.__get_queue_messages(self.__queue_downloader)
            if ret and '-' in ret:
                self.__logger.info(ret)
                self.__fw_version = ret.split('-')[1]
                self.__mqtt.msg_latest_firmware(self.__fw_version)

                if self.__profile["firmware"]["filename"] == "latest":
                    self.__path_firmware = ret
                    self.__profile["firmware"]["filename"] = ret

            sleep(1)

def main():
    Kickstart()

if __name__ == '__main__':
    main()
