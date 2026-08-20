#!/usr/bin/env python

from signal import signal, SIGINT
from sys import exit
import json
from  csv import register_dialect, DictWriter
import argparse
from threading import Event

from pathlib import Path
from queue import Empty, Queue
import logging.handlers
from time import sleep

from downloader import Downloader
from mqtt import Mqtt, Topics
from updater import Updater
from file import File
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
        self.__config_file = "/data/etc/kickstarter.json" # path to the config file
        self.__path_aftercare = None       # path to data with aftercare data
        self.__path_csv = None             # path to data containing the aftercare data as CSV
        self.__config = {}                 # contains config for this backend
        self.__profile = {}                # contains profile, what user wants to put onto devices
        self.__settings = {}               # contains settings concerning kickstarter itself
        self.__fw_version = "---"          # the firmware we are currently flashing onto devices
        self.__aftercare_data = {}         # all known data from aftercare phases
        self.__event_shutdown = Event()    # signal to all threads to shut down
        self.__ips = []                    # list of found devices

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
            exit(-1)

        # start device searcher
        self.__searcher = Searcher(self.__logger, self.__event_shutdown, self.__queue_searcher, self.__settings)
        self.__searcher.start()

        # start MQTT client
        self.__mqtt = Mqtt(self.__logger, self.__queue_mqtt, self.__settings)

        # use MQTT client as an additional logger
        self.__logger.addHandler(self.__mqtt)

        # get a File instance
        self.__file = File(self.__logger, self.__mqtt, self.__settings["dirs"])

        # set local IPv6 addresses
        self.__file.reconfigure_net(self.__settings['net']['interface'], self.__settings['net']['prefix'])

        # reconfigure radvd and restart it
        self.__file.radvd_config(self.__settings['net']['interface'], self.__settings['net']['prefix'])

        # start Downloader to get most recent firmware update
        self.__downloader = Downloader(self.__logger, self.__event_shutdown, self.__queue_downloader, self.__settings)
        self.__downloader.start()

        # read all locally stored files
        self.__file.read_local_files()

        # load firmware to update devices to
        self.__get_firmware_version()

        # install signal handler to exit
        signal(SIGINT, self.__shutdown)

        # clear alarm topic
        self.__mqtt.publish(Topics.ALERT, '', plain=True, retain=False)

        # set a few path variables
        if 'aftercare' in self.__profile:
            if 'logfile' in self.__profile['aftercare']:
                self.__path_aftercare = Path(self.__settings['dirs']['files']).joinpath(self.__profile['aftercare']['logfile'])

            if 'csvfile' in self.__profile['aftercare']:
                self.__path_csv = Path(self.__settings['dirs']['files']).joinpath(self.__profile['aftercare']['csvfile'])

        # read all aftercare data from file
        self.__read_aftercare_file()

        # start never ending main loop
        self.__mainloop()

    def __shutdown(self, frame, x):
        self.__event_shutdown.set()
        self.__file.shutdown()
        self.__mqtt.shutdown()
        self.__logger.info("Shutting down")
        exit(0)

    def __read_configfile(self):
        try:
            with open(self.__config_file, "r", encoding='UTF-8') as f:
                self.__config = json.load(f)
        except Exception as err:
            print("Could not read config file: %s", {err})
            exit(-1)

        self.__profile = self.__config['profile']
        self.__settings = self.__config['settings']

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

        self.__mqtt.publish(Topics.AFTERCARE, len(self.__aftercare_data), plain=True, retain=True)

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

        self.__mqtt.publish(Topics.AFTERCARE, len(self.__aftercare_data), plain=True, retain=True)

        return True

    # export the aftercare data into a CSV file
    def __create_csv_file(self):
        if self.__path_csv is None:
            return False

        delimiter = ";"
        if 'csv_delimiter' in self.__profile['aftercare']:
            delimiter = self.__profile['aftercare']['csv_delimiter']
        register_dialect('insys', delimiter=delimiter)

        fieldnames = []
        for i in self.__aftercare_data:
            fieldnames = self.__aftercare_data[i].keys()
            break

        with open(self.__path_csv, 'w', newline='', encoding='utf-8') as outfile:
            writer = DictWriter(outfile, fieldnames=fieldnames, dialect='insys')
            writer.writeheader()

            # apppend lines
            for i in self.__aftercare_data:
                writer.writerow(self.__aftercare_data[i])

        return True

    # find the firmware version, that should be flashed
    def __get_firmware_version(self):
        name = self.__profile["firmware"]["version"]

        if name == "latest":
            self.__fw_version = self.__file.get_latest_firmware()
        else:
            self.__fw_version = name

    # default syslogger writing to syslog
    def __create_logger(self, name):
        self.__logger = logging.getLogger(name)
        self.__logger.setLevel(logging.INFO)
        handler = logging.handlers.SysLogHandler(address='/dev/log')
        handler.formatter = logging.Formatter(": %(name)s: %(message)s")
        self.__logger.addHandler(handler)
        self.__logger.info("Started")

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
        self.__mqtt.publish(Topics.DEVICES, j, retain=True)

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
        self.__mqtt.publish(Topics.STATUS, payload="online", plain=True, retain=True)

        # send list of detected devices
        self.__send_existing()

        # send the current firmware version
        self.__mqtt.publish(Topics.FW_LATEST, self.__fw_version, plain=True, retain=True)

        # send current profile
        self.__mqtt.publish(Topics.PROFILE, self.__profile, retain=True)

        # send the current settings
        self.__mqtt.publish(Topics.SETTINGS, self.__settings, retain=True)

        # send latest log entries
        self.__mqtt.msg_last_log_entries()

        # update list of locally stored files
        self.__file.read_local_files()

        # send number of finished devices in aftercare file
        self.__mqtt.publish(Topics.AFTERCARE, len(self.__aftercare_data), plain=True, retain=True)

    # interprete an incoming MQTT message
    def __do_mqtt_message(self, msg):
        # a new client connected and needs info
        if "connect" in msg:
            # we, the backend, connected to mqtt, so broadcast all info
            self.__mqtt_hello()

        # another mqtt client sent something
        if "message" in msg:
            m = msg["message"]

            if m.topic == Topics.UPLOAD:
                # store the file locally
                self.__file.store_uploaded_file(json.loads(m.payload))

            elif m.topic == Topics.PROFILE_UP:
                # store the received profile in file
                self.__profile = json.loads(m.payload)
                self.__config["profile"] = self.__profile
                self.__file.store_config(self.__config_file, json.dumps(self.__config, indent=4))

                # broadcast new profile to everyone
                self.__mqtt.publish(Topics.PROFILE, self.__profile, retain=True)

                # load firmware to update devices to
                self.__get_firmware_version()

                # send the current firmware version
                self.__mqtt.publish(Topics.FW_LATEST, self.__fw_version, plain=True, retain=True)

            elif m.topic == Topics.SETTINGS_UP:
                settings_new = json.loads(m.payload)

                # compare net settings with current ones and update searcher and restart router advertiser
                if self.__settings["net"] != settings_new["net"]:
                    self.__searcher.update_network(settings_new["net"])
                    self.__file.reconfigure_net(settings_new['net']['interface'], settings_new['net']['prefix'])
                    self.__file.radvd_config(settings_new['net']['interface'], settings_new['net']['prefix'])

                # compare login settings with current ones
                if self.__settings["login"] != settings_new["login"]:
                    self.__file.set_login(settings_new["login"])

                # store the received settings in file
                self.__settings = settings_new
                self.__config["settings"] = self.__settings
                self.__file.store_config(self.__config_file, json.dumps(self.__config, indent=4))

                # reconfigure downloader thread
                self.__downloader.profile_update(self.__settings)

                # broadcast new settings to everyone
                self.__mqtt.publish(Topics.SETTINGS, self.__settings, retain=True)

            elif m.topic == Topics.DELETE_FILE:
                self.__file.delete_file(json.loads(m.payload))

            elif m.topic == Topics.AFTERCARE_RESET:
                self.__logger.info("Starting new aftercare files due to restart signal")
                self.__file.rollate_aftercare_files(self.__path_csv, self.__path_aftercare)
                self.__file.read_local_files()

                # send number of finished devices in aftercare file, should be 0 now
                self.__aftercare_data = {}
                self.__mqtt.publish(Topics.AFTERCARE, len(self.__aftercare_data), plain=True, retain=True)

    # interprete a message from the searcher
    def __do_searcher_message(self, msg):
        if "ips" in msg:
            self.__ips = msg["ips"]

        if "alarm" in msg:
            self.__mqtt.publish(Topics.ALERT, msg["alarm"], plain=True, retain=False)

    # interprete a message from the downloader
    def __do_downloader_message(self, msg):
        if "firmware" in msg:
            if '-' in msg["firmware"]:
                fw = msg["firmware"]

                self.__fw_version = fw.split('-')[1]
                self.__mqtt.publish(Topics.FW_LATEST, self.__fw_version, plain=True, retain=True)

                if self.__profile["firmware"]["version"] == "latest":
                    self.__profile["firmware"]["version"] = fw

        if "internet" in msg:
            # broadcast new intenet state to everyone
            text = "offline"
            if msg["internet"]:
                text = "online"
            self.__mqtt.publish(Topics.INTERNET, text, plain=True, retain=True)

    # never ending main loop
    def __mainloop(self):
        """ endlessly search for new devices and start a configure thread for every found one """
        mqtt_update = False

        while True:
            remove_ips = []

            # start processing new devices
            for ip in self.__ips:
                mqtt_update = False

                # ignore already updated devices:
                if ip in self.__existing_list:
                    continue

                # this is an unknown IP address
                if ip not in self.__thread_list:

                    # start configuring the device if it is still pingable
                    if self.__searcher.ping_device(ip, self.__settings['net']['interface']) is True:
                        self.__logger.info('Device found: %s', ip)
                        self.__queue_devices[ip] = Queue()
                        self.__thread_list[ip] = Updater(self.__logger,
                                                         self.__queue_devices[ip],
                                                         "[" + ip + "]",
                                                         self.__fw_version,
                                                         self.__settings['dirs'],
                                                         self.__profile,
                                                         self.__settings)

                        # start the thread
                        self.__thread_list[ip].start()
                    else:
                        # remove none reachable devices from list
                        remove_ips.append(ip)

            # wait for messages from the updating threads
            for ip in self.__ips:
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
                for i, _ in self.__existing_list.items():
                    if i not in self.__ips:
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
            if msg:
                self.__do_searcher_message(msg)

            # read incoming message from downloader
            msg = self.__get_queue_messages(self.__queue_downloader)
            if msg:
                self.__do_downloader_message(msg)

            sleep(1)

def main():
    Kickstart()

if __name__ == '__main__':
    main()
