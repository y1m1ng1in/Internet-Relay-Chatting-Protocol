import socket
import sys
import re
import threading
from status import (
  Status, RegistrationStatus, JoinStatus, MessageStatus, DisconnectStatus,
  LeaveStatus)

if len(sys.argv) < 3:
    print("USAGE: echo_client_sockets.py <HOST> <PORT>") 
    sys.exit(0)


class CmdError(Exception):

  def __init__(self, message="Command not found"):
    self.message = message


class ClientCmd:

  def __init__(self, socket):
    self.cmds = { "register", "join", "send to rooms", "quit" }
    self.socket = socket
    self.username = ''

  def set_username(self, username: str):
    self.username = username

  def parse(self, input: str):
    if input == "register":
      return Registration(self.socket)
    elif input == "join":
      return Joining(self.socket, self.username)
    elif input == "room message":
      return SendToRooms(self.socket, self.username)
    elif input == "private message":
      return SendToUsers(self.socket, self.username)
    elif input == "quit":
      return Disconnection(self.socket, self.username)
    elif input == "leave":
      return Leave(self.socket, self.username)
    else:
      raise CmdError()


class CmdExecution:
  def __init__(self, socket):
    self.socket = socket

  @staticmethod
  def room_name_sanitize(name: str):
    if len(name) > 20:
      print("Invalid room name.")
      return None
    padding = 20 - len(name)
    name += ' ' * padding
    return name

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
    print("room name (20 characters max, no newline):")
    sys.stdout.write('> ')
    sys.stdout.flush()
    name = sys.stdin.readline()[:-1]
    name = CmdExecution.room_name_sanitize(name)
    if name == None:
      return None
    self.socket.send(
      (self.command_code + name + self.username).encode(encoding="utf-8"))
    return name
    

class SendToRooms(CmdExecution):

  def __init__(self, socket, username):
    super().__init__(socket)
    self.command_code = '00003'
    self.username = username
    self.rooms = set()
    self.message = ""

  def execute(self):
    more_room = True
    while(more_room):
      print("room name (20 characters max, no newline):")
      sys.stdout.write('> ')
      sys.stdout.flush()
      name = sys.stdin.readline()[:-1]
      name = CmdExecution.room_name_sanitize(name)
      if name == None:
        return None
      self.rooms.add(name)
      print("send to more rooms? (y/n)")
      sys.stdout.write('> ')
      sys.stdout.flush()
      answer = sys.stdin.readline()[:-1]
      if answer != "y" and answer != "Y":
        more_room = False
    print("message (enter newline to end):")
    sys.stdout.write('> ')
    sys.stdout.flush()
    self.message = sys.stdin.readline()[:-1]
    if len(self.rooms) < 10:
      str_room_num = '0' + str(len(self.rooms))
    else:
      str_room_num = str(len(self.rooms))
    bytes = self.command_code + str_room_num + ''.join(self.rooms) + self.message
    self.socket.send(bytes.encode(encoding="utf-8"))
    return (self.rooms, self.message)


class SendToUsers(CmdExecution):

  def __init__(self, socket, username):
    super().__init__(socket)
    self.command_code = '00004'
    self.username = username
    self.users = set()
    self.message = ""

  def execute(self):
    more_users = True
    while(more_users):
      print("username (20 characters, no newline):")
      sys.stdout.write('> ')
      sys.stdout.flush()
      name = sys.stdin.readline()[:-1]
      if len(name) > 20:
        print("Invalid username.")
        return None
      self.users.add(name)
      print("send to more users? (y/n)")
      sys.stdout.write('> ')
      sys.stdout.flush()
      answer = sys.stdin.readline()[:-1]
      if answer != "y" and answer != "Y":
        more_users = False
    print("message (enter newline to end):")
    sys.stdout.write('> ')
    sys.stdout.flush()
    self.message = sys.stdin.readline()[:-1]
    if len(self.users) < 10:
      str_user_num = '0' + str(len(self.users))
    else:
      str_user_num = str(len(self.users))
    bytes = self.command_code + str_user_num + '&'.join(self.users) + '#' + self.message
    self.socket.send(bytes.encode(encoding="utf-8"))
    return (self.users, self.message)


class Disconnection(CmdExecution):

  def __init__(self, socket, username):
    super().__init__(socket)
    self.username = username
    self.command_code = '00010'

  def execute(self):
    bytes = (self.command_code + self.username).encode(encoding="utf-8")
    self.socket.send(bytes)
    return self.username


class Leave(CmdExecution):

  def __init__(self, socket, username):
    super().__init__(socket)
    self.username = username
    self.command_code = '00005'

  def execute(self):
    print("room name (20 characters max, no newline):")
    sys.stdout.write('> ')
    sys.stdout.flush()
    name = sys.stdin.readline()[:-1]
    name = CmdExecution.room_name_sanitize(name)
    if name == None:
      return None
    bytes = (self.command_code + name + self.username).encode(encoding="utf-8")
    self.socket.send(bytes)
    return name



s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
host = sys.argv[1]
port = int(sys.argv[2])
s.connect((host,port))

cmd = ClientCmd(s)

lock = threading.Lock()
has_execution = threading.Condition()
to_execute = []

status_pattern = re.compile('\$[\w#\s]+\$')
user_unset = True

manually_disconnected = False

while(user_unset):
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
    data = data.decode(encoding="utf-8")
    status = status_pattern.findall(data)
    parsed = []
    for msg in status:
      # print(msg[1:-1])
      msg = msg[1:-1]
      if len(msg) >= 8:
        command_code = msg[3:8]
        if command_code == '00001':
          parsed.append(RegistrationStatus.parse(msg))
        else:
          parsed.append(Status.parse(msg))
      else:
        parsed.append(Status.parse(msg))
      
    # status = Status.parse(data)

    if isinstance(to_execute, Registration):
      for msg in parsed:
        if msg.code == 200 and msg.command_code == '00001':
          cmd.set_username(msg.username)
          user_unset = False

        if msg.code in { 400, 401, 402, 411, 450, 451, 496, 497, 498, 499 }:  # errors...
          msg.print()
        elif msg.code in { 200 }:  # success
          msg.print()
        else:
          print("unknown status code...")
  
  except CmdError as e:
    print(e.message)


def sending_thread():
  while(1):
    # if manually_disconnected == True:
    #   break
    msg = sys.stdin.readline()[:-1]
    if len(msg) == 0:
      lock.acquire()
      sys.stdout.write('>>> ')
      sys.stdout.flush()
      msg = sys.stdin.readline()[:-1]
  
      try:
        to_execute = cmd.parse(msg)
        to_execute.execute()   
      except CmdError as e:
        print(e.message)
      finally:
        lock.release()

      if msg == 'quit': 
        break
    
    else:
      print("Enter a single newline character to enter command.")


def receive_thread():
  run = True
  while(run):
    data = s.recv(10000000)
    if data == b'':
      break
    # print(data)
    data = data.decode(encoding="utf-8")
    status = status_pattern.findall(data)
    parsed = []
    for msg in status:
      # print(msg[1:-1])
      msg = msg[1:-1]
      if len(msg) >= 8:
        command_code = msg[3:8]
        if command_code == '00001':
          parsed.append(RegistrationStatus.parse(msg))
        elif command_code == '00002':
          parsed.append(JoinStatus.parse(msg))
        elif command_code == '00003' or command_code == '00004':
          parsed.append(MessageStatus.parse(msg))
        elif command_code == '00010':
          parsed_msg = DisconnectStatus.parse(msg)
          parsed.append(parsed_msg)
          # print(parsed_msg.username, cmd.username)
          if parsed_msg.username == cmd.username:
            run = False
        elif command_code == '00005':
          parsed.append(LeaveStatus.parse(msg))
        else:
          parsed.append(Status.parse(msg))
      else:
        parsed.append(Status.parse(msg))
      
    lock.acquire()
    for item in parsed:
      if item.code in { 400, 401, 402, 411, 496, 497, 498, 499 }:  # errors...
        item.print()
      elif item.code in { 200 }:  # success
        item.print()
      else:
        print("unknown status code...")
    lock.release()


sending = threading.Thread(target=sending_thread)
receiving = threading.Thread(target=receive_thread)

sending.start()
receiving.start()

sending.join()
receiving.join()
  
print(".............")