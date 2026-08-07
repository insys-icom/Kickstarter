from threading import Thread
from subprocess import Popen, PIPE
from time import sleep

class Searcher(Thread):
    def __init__(self, logger, queue, interface, prefix):
        self.__logger = logger
        self.__interface = interface
        self.__prefix = prefix
        self.__queue = queue
        self.__shutdown = False
        Thread.__init__(self)

    def run(self):
        while self.__shutdown is False:
            ips = self.__get_neighbours()
            self.__queue.put(ips)
            sleep(1)
        return

    def shutdown(self):
        self.__logger.info('Shutting down searcher')
        self.__shutdown = True

    # ping a specific IP address
    def ping_device(self, ip, interface):
        """ ping a specific device """
        ping = Popen(["ping", "-c", "1", "-W", "1", "-I", interface, ip], stdout=PIPE, stderr=PIPE)
        out = ping.communicate()

        for line in str(out).split("\\n"):
            if "1 packets transmitted, 1 " in line:
                return True

        return False

    def __get_neighbours(self):
        ping = Popen(["ping", "-c", "1", "-W", "1", "-w", "1", "-I", self.__interface, "ff02::1"],
                       stdout=PIPE, stderr=PIPE)
        ping.communicate()

        neigh = Popen(["ip", "-6", "neigh", "show", "dev", self.__interface], stdout=PIPE, stderr=PIPE, text=True)
        out = neigh.communicate()
        ips = []
        for line in str(out).split("\\n"):
            if "FAILED" in line:
                continue
            if "fe80::205:b6ff:fe" in line or "fe80::728b:97ff:fe" in line:
                if not line.startswith("fe80::"):
                    line = f'fe80::{line.split("fe80::")[1]}'
                ip = line.split(" ")[0]
                # ping to verify that it is still there
                ping = Popen(["ping", "-c", "1", "-W", "1", "-w", "1", "-I", self.__interface, ip], stdout=PIPE, stderr=PIPE)
                out = ping.communicate()

                for pingline in str(out).split("\\n"):
                    if "1 packets received" in pingline:
                        # link local address is the first bytes
                        ip = line.split(" ")[0]

                        # replace link local prefix with radvd prefix
                        p = ip.split("fe80::")[-1:]
                        ip = self.__prefix + p[0]
                        ips.append(ip)
                        break
        return ips
