from os import path
from threading import Thread
from subprocess import Popen, PIPE
from time import sleep

from cli import Cli

class Searcher(Thread):
    def __init__(self, logger, shutdown, queue, settings):
        self.__logger = logger
        self.__interface = settings["net"]["interface"]
        self.__prefix = settings["net"]["prefix"]
        self.__ignore_ips = settings['net']['ignore_ips'].split(',')
        self.__device_info = '/devices/device_info.json'  # path to detect, if this is an INSYS device
        self.__uds = '/devices/cli_no_auth/cli.socket'    # path to the UDS that gives unauthorized access to the CLI
        self.__queue = queue
        self.__shutdown = shutdown
        Thread.__init__(self)

    def run(self):
        self.__find_ignore_ips()

        while True:
            if self.__shutdown.wait(timeout=1):
                self.__logger.info('Shutting down searcher')
                break

            msg = { "ips": self.__get_neighbours() }
            self.__queue.put(msg)

    # use new settings
    def update_network(self, net):
        self.__interface = net["interface"]
        self.__prefix = net["prefix"]
        self.__ignore_ips = net["ignore_ips"].split(',')
        self.__find_ignore_ips()

    # ping a specific IP address
    def ping_device(self, ip, interface):
        """ ping a specific device """
        ping = Popen(["ping", "-c", "1", "-W", "1", "-I", interface, ip], stdout=PIPE, stderr=PIPE)
        out = ping.communicate()

        for line in str(out).split("\\n"):
            if "1 packets transmitted, 1 " in line:
                return True

        return False

    # find all IP adresses we should ignore
    def __find_ignore_ips(self):
        own_ips = []
        while True:
            ret = self.__find_own_ip()
            if ret is None:
                break

            own_ips = ret
            if len(own_ips) < 1:
                sleep(10)
            else:
                break

        for i in own_ips:
            self.__logger.info(f"Searcher: ignoring own IP: {i}")
            self.__ignore_ips.append(i)

    # find out or own link lokal IP address on the configured eth interface
    def __find_own_ip(self):
        ips = []
        if not path.exists(self.__device_info):
            # own IP address only relevant when kickstarter runs on an INSYS device
            return None

        if not path.exists(self.__uds):
            self.__logger.info("Unable to get own IP addresses - is unauthorized access to CLI active?")
            msg = { "alarm": 'This container needs access to the router CLI without authentication, at least the user group "Status"' }
            self.__queue.put(msg)

            return ips

        cli = Cli(self.__uds)
        if cli is False:
            self.__logger.info("Unable to get own IP addresses")
            exit(-1)

        text = cli.get("status.sysdetail.ip_addresses")
        for line in str(text).split("\n"):
            if "].ip_address=" in line and "fe80::" in line:
                ips.append(f'{self.__prefix}{line.split("fe80::")[1].split("/")[0]}')

        cli.disconnect()
        return ips

    # get all IPv6 neighbours, that are INSYS routers
    def __get_neighbours(self):
        # ping all routers to trigger responses, this filles up the neighour table
        with Popen(["ping", "-c", "1", "-W", "1", "-w", "1", "-I", self.__interface, "ff02::1"], stdout=PIPE, stderr=PIPE) as ping:
            ping.communicate()

        # interprete neighbour table
        with Popen(["ip", "-6", "neigh", "show", "dev", self.__interface], stdout=PIPE, stderr=PIPE, text=True) as neigh:
            out = neigh.communicate()
            ips = []
            for line in str(out).split("\\n"):
                if "FAILED" in line:
                    continue

                # only look for INSYS devices
                if "fe80::205:b6ff:fe" not in line and "fe80::728b:97ff:fe" not in line:
                    continue

                if not line.startswith("fe80::"):
                    line = f'fe80::{line.split("fe80::")[1]}'
                ip = line.split(" ")[0]

                # ping to verify that it is still there
                with Popen(["ping", "-c", "1", "-W", "1", "-w", "1", "-I", self.__interface, ip], stdout=PIPE, stderr=PIPE) as ping:
                    # walk over every line of the response
                    for pingline in str(ping.communicate()).split("\\n"):
                        if "1 packets received" in pingline:
                            # link local address is the first bytes
                            ip = line.split(" ")[0]

                            # replace link local prefix with radvd prefix
                            p = ip.split("fe80::")[-1:]
                            ip = self.__prefix + p[0]

                            # ignore these IP from ignore list
                            if ip not in self.__ignore_ips:
                                ips.append(ip)

                            break
        return ips
