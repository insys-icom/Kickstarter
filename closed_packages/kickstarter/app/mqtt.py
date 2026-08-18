from enum import StrEnum

import logging
import json
import paho.mqtt.client as mqtt

class Topics(StrEnum):
    TOP             = 'kickstarter'
    STATUS          = f'{TOP}/status'
    LOG             = f'{TOP}/log'
    DEVICES         = f'{TOP}/devices'
    FW_LATEST       = f'{TOP}/fw_latest'
    PROFILE         = f'{TOP}/profile'
    PROFILE_UP      = f'{TOP}/profile_up'
    SETTINGS        = f'{TOP}/settings'
    SETTINGS_UP     = f'{TOP}/settings_up'
    UPLOAD          = f'{TOP}/upload'
    LOCALFILES      = f'{TOP}/localfiles'
    DELETE_FILE     = f'{TOP}/delete_file'
    ALERT           = f'{TOP}/alert'
    AFTERCARE       = f'{TOP}/aftercare'
    AFTERCARE_RESET = f'{TOP}/aftercare_reset'
    INTERNET        = f'{TOP}/internet'

class Mqtt(logging.Handler):
    def __init__(self, logger, queue, settings):
        self.__logger = logger
        self.__init_logger()
        self.__logger.info('Starting MQTT client')

        self.__queue = queue
        self.__logfile = settings["dirs"]["log"]

        self.__client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
        self.__client.on_connect = self.on_connect
        self.__client.on_message = self.on_message
        #self.__client.tls_set(profile["mqtt"]["ca"], profile["mqtt"]["cert"], profile["mqtt"]["key"])
        #self.__client.user_data_set(profile)
        self.__client.will_set(Topics.STATUS, "offline", retain=True)
        self.__client.connect_async(host=settings["mqtt"]["url"],
                                    port=int(settings["mqtt"]["port"]),
                                    keepalive=60,
                                    bind_address="")
        self.__client.loop_start()
        return

    def __init_logger(self):
        logging.Handler.__init__(self)
        self.formatter = logging.Formatter("%(asctime)s %(message)s", datefmt='%F %T')

    # The callback for when the client receives a CONNACK response from the server.
    def on_connect(self, client, userdata, flags, rc, properties):
        self.close()
        self.__init_logger()
        self.__logger.info("Started MQTT connection")

        self.__queue.put({ "connect": "" })
        client.subscribe(Topics.UPLOAD)
        client.subscribe(Topics.PROFILE_UP)
        client.subscribe(Topics.SETTINGS_UP)
        client.subscribe(Topics.DELETE_FILE)
        client.subscribe(Topics.AFTERCARE_RESET)

    # The callback for when a PUBLISH message is received from the server.
    def on_message(self, client, userdata, msg):
        self.__queue.put({ "message": msg })

    def shutdown(self):
        self.__logger.info('Shutting down MQTT client')
        self.__client.loop_stop()

    def msg_last_log_entries(self):
        try:
            with open(self.__logfile, "r", encoding='utf-8') as file:
                text = ""
                logs = file.readlines()
                for line in logs[-25:]:
                    if '[' not in line:
                        continue
                    # cut out the program name from log, as this is nothing new
                    l = line.rstrip()
                    a = l.split(' [', 1)
                    b = l.split(']', 1)
                    text = text + f'{a[0]}{b[1]}' + '\n'
                self.__client.publish(Topics.LOG, text, retain=True)
        except:
            pass

    def publish(self, topic, payload, plain=False, retain=False):
        """ send message via MQTT """
        if plain is False:
            payload = json.dumps(payload)
        self.__client.publish(topic, payload=payload, retain=retain)

    def emit(self, record):
        self.__client.publish(Topics.LOG, self.format(record), retain=True)
        return None
