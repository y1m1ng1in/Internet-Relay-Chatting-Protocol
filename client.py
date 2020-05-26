import socket
import sys
import re
import threading
from status import Status

if len(sys.argv) < 3:
    print("USAGE: echo_client_sockets.py <HOST> <PORT>") 
    sys.exit(0)


class CmdError(Exception):

  def __init__(self, message="Command not found"):
    self.message = message


class ClientCmd:

  def __init__(self, socket):
    self.cmds = { "register", "join" }
    self.socket = socket
    self.username = ''

  def set_username(self, username: str):
    self.username = username

  def parse(self, input: str):
    if input == "register":
      return Registration(self.socket)
    elif input == "join":
      return Joining(self.socket, self.username)
    else:
      raise CmdError()


class CmdExecution:
  def __init__(self, socket):
    self.socket = socket

  def execute(self):
    """ The method for child classes to override
        and to be called in the main loop 
    """
    pass


class Registration(CmdExecution):

  def __init__(self, socket):
    super().__init__(socket)
    self.command_code = '00001'

  def execute(self):
    print("username (20 characters, no newline):")
    sys.stdout.write('> ')
    sys.stdout.flush()
    name = sys.stdin.readline()[:-1]
    if len(name) > 20:
      print("Invalid username.")
      return None
    self.socket.send((self.command_code + name).encode(encoding="utf-8"))
    return name


class Joining(CmdExecution):

  def __init__(self, socket, username):
    super().__init__(socket)
    self.command_code = '00002'
    self.username = username

  def execute(self):
    print("room name (20 characters, no newline):")
    sys.stdout.write('> ')
    sys.stdout.flush()
    name = sys.stdin.readline()[:-1]
    if len(name) > 20:
      print("Invalid room name.")
      return None
    padding = 20 - len(name)
    name += ' ' * padding
    self.socket.send(
      (self.command_code + name + self.username).encode(encoding="utf-8"))
    return name
    


s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
host = sys.argv[1]
port = int(sys.argv[2])
s.connect((host,port))

cmd = ClientCmd(s)

lock = threading.Lock()
has_execution = threading.Condition()
to_execute = []

while(1):
  sys.stdout.write('>>> ')
  sys.stdout.flush()
  msg = sys.stdin.readline()[:-1]
  if msg == 'quit': 
    s.close()
    break
  try:
    to_execute = cmd.parse(msg)
    value = to_execute.execute()

    data = s.recv(10000000)
    status = Status.parse(data)

    if isinstance(to_execute, Registration):
      if status.code == 200:
        print(status.message)
        cmd.set_username(value)
        break

    if status.code in { 400, 401, 402, 411, 498, 499 }:  # errors...
      print(status.message)
    elif status.code in { 200 }:  # success
      print(status.message)
    else:
      print("unknown status code...")
  
  except CmdError as e:
    print(e.message)


def sending_thread():
  while(1):
    sys.stdout.write('>>> ')
    sys.stdout.flush()
    msg = sys.stdin.readline()[:-1]

    if msg == 'quit': 
      s.close()
      break
    
    try:
      to_execute = cmd.parse(msg)
      to_execute.execute()
      
    except CmdError as e:
      print(e.message)


def receive_thread():
  while(1):
    data = s.recv(10000000)
    if data == b'':
      break
    status = Status.parse(data)
      
    if status.code in { 400, 401, 402, 411, 498, 499 }:  # errors...
      print(status.message)
    elif status.code in { 200 }:  # success
      print(status.message)
    else:
      print("unknown status code...")


sending = threading.Thread(target=sending_thread)
receiving = threading.Thread(target=receive_thread)

sending.start()
receiving.start()
  