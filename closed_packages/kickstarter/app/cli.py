import socket

class Cli():
    def __init__(self, uds):
        self._cli = None
        self._prompt = None
        self.connect(uds)

    def connect(self, uds):
        self._cli = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            self._cli.connect(uds)
        except:
            return False

        # remember prompt configuration
        self._prompt = self._cli.recv(1024).decode('utf-8')
        return True

    def disconnect(self):
        self._cli.close()
        return True

    def get(self, command):
        # append eventually missing new line character
        if command.endswith('\n') is False:
            command = command + '\n'

        self._cli.send(bytes(command, 'utf-8'))
        response = ""
        while True:
            response = response + (self._cli.recv(1024).decode('utf-8'))
            if len(response) >= len(self._prompt):
                if response.endswith(self._prompt):
                    break
        return response[:len(response) - len(self._prompt)]
