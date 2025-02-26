import logging
import json
import paho.mqtt.client as mqtt
from enum import StrEnum

class TopicType(StrEnum):
    def fullpath(self):
        return 'kickstarter/' + self.value

class Topics(TopicType):
    STATUS      = 'status'
    LOG         = 'log'
    DEVICES     = 'devices'
    FW_LATEST   = 'fw_latest'
    PROFILE     = 'profile'
    PROFILE_UP  = 'profile_up'
    UPLOAD      = 'upload'
    LOCALFILES  = 'localfiles'
    DELETE_FILE = 'delete_file'
    ALERT       = 'alert'

class Mqtt(logging.Handler):
    def __init__(self, logger, queue, profile):
        self.__logger = logger
        self.__init_logger()
        self.__logger.info('Starting MQTT client')

        self.__queue = queue
        self.__logfile = profile["dirs"]["log"]

        self.__client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
        self.__client.on_connect = self.on_connect
        self.__client.on_message = self.on_message
        #self.__client.tls_set(profile["mqtt"]["ca"], profile["mqtt"]["cert"], profile["mqtt"]["key"])
        #self.__client.user_data_set(profile)
        self.__client.will_set(Topics.STATUS.fullpath(), "offline", retain=True)
        self.__client.connect_async(host=profile["mqtt"]["url"],
                                    port=int(profile["mqtt"]["port"]),
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
        client.subscribe(Topics.UPLOAD.fullpath())
        client.subscribe(Topics.PROFILE_UP.fullpath())
        client.subscribe(Topics.DELETE_FILE.fullpath())

    # The callback for when a PUBLISH message is received from the server.
    def on_message(self, client, userdata, msg):
        self.__queue.put({ "message": msg })

    def shutdown(self):
        self.__logger.info('Shutting down MQTT client')
        self.__client.loop_stop()

    def msg_last_log_entries(self):
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
            self.__client.publish(Topics.LOG.fullpath(), text, retain=True)

    def msg_status_online(self):
        return self.__client.publish(Topics.STATUS.fullpath(), payload="online", retain=True)

    def msg_latest_firmware(self, firmware_version):
        return self.__client.publish(Topics.FW_LATEST.fullpath(), payload=firmware_version, retain=True)

    def msg_existing_devices(self, existing_devices):
        return self.__client.publish(Topics.DEVICES.fullpath(), payload=existing_devices, retain=True)

    def msg_profile(self, userdata):
        return self.__client.publish(Topics.PROFILE.fullpath(), payload=json.dumps(userdata), retain=True)

    def msg_local_files(self, local_files):
        return self.__client.publish(Topics.LOCALFILES.fullpath(), payload=json.dumps(local_files), retain=True)

    def msg_alert(self, text):
        return self.__client.publish(Topics.ALERT.fullpath(), payload=text, retain=False)

    def emit(self, record):
        self.__client.publish(Topics.LOG.fullpath(), self.format(record), retain=True)
        return None
