import socket
import sys
import re
from status import Status

if len(sys.argv) < 3:
    print("USAGE: echo_client_sockets.py <HOST> <PORT>") 
    sys.exit(0)

class ClientCmd:

  def __init__(self):
    self.cmds = { "register", "join" }

  def parse(self, input: str):
    args = re.split('(\W+)', input, maxsplit=1)
    if len(self.args) == 0:
      print("Invalid command.")
    elif len(self.args) >= 1:
      cmd = self.args[0]
      if cmd not in self.cmds:
        print("Invalid command.")
      else:
        if cmd == "register":
          return Registration(args[1:])
        elif cmd == "join":
          return Joining(args[1:])
        else:
          return None
    return None


class CmdExecution:

  def __init__(self, args):
    self.args = args

  def execute(self):
    """ The method for child classes to override
        and to be called in the main loop 
    """
    pass


class Registration(CmdExecution):

  def __init__(self, args):
    super().__init__(args)

  def execute(self):
    pass


class Joining(CmdExecution):

  def __init__(self, args):
    super().__init__(args)

  def execute(self):
    pass



s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
host = sys.argv[1]
port = int(sys.argv[2])
s.connect((host,port))

while (1):
  sys.stdout.write('>> ')
  msg = sys.stdin.readline()

  if msg == 'quit\n': 
    s.close()
    break

  s.send(msg.encode('utf-8'))

  data = s.recv(10000000)
  status = Status.parse(data)

  if status.code in { 400, 401, 402, 411, 498, 499 }:  # errors...
    print(status.message)
  elif status.code in { 200 }:  # success
    print(status.message)
  else:
    print("unknown status code...")

  