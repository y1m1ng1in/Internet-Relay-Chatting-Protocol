import socket
import sys
import re
import threading
from status import (
  Status, RegistrationStatus, JoinStatus, MessageStatus, DisconnectStatus,
  LeaveStatus, RoomUserListStatus, ListRoomStatus)
from server import RunningSignal
from clientlib import (
  EmptyUsernameException, ClientApiArgumentError, Client)


class CmdError(Exception):

  def __init__(self, message="Command not found"):
    self.message = message


class ClientCmd:

  def __init__(self, socket):
    self.cmds = { "register", "join", "send to rooms", "quit" }
    self.socket = socket
    self.client = Client(socket)

  def set_username(self, username: str):
    self.client.set_username(username)

  def parse(self, input: str):
    if input == "register":
      return Registration(self.client)
    elif input == "join":
      return Joining(self.client)
    elif input == "room message":
      return SendToRooms(self.client)
    elif input == "private message":
      return SendToUsers(self.client)
    elif input == "quit":
      return Disconnection(self.client)
    elif input == "leave":
      return Leave(self.client)
    elif input == "room users":
      return ListUsers(self.client)
    elif input == "rooms":
      return ListRooms(self.client)
    else:
      raise CmdError()


class CmdExecution:
  def __init__(self, client):
    self.client = client

  @staticmethod
  def room_name_sanitize(name: str):
    if len(name) > 20:
      print("Invalid input: length is greater then 20.")
      return None
    padding = 20 - len(name)
    name += ' ' * padding
    return name

  @staticmethod
  def input_room():
    print("room name (20 characters max, no newline):")
    sys.stdout.write('> ')
    sys.stdout.flush()
    name = sys.stdin.readline()[:-1]
    name = CmdExecution.room_name_sanitize(name)
    return name

  @staticmethod
  def input_username():
    print("username (20 characters, no newline):")
    sys.stdout.write('> ')
    sys.stdout.flush()
    name = sys.stdin.readline()[:-1]
    name = CmdExecution.room_name_sanitize(name)
    return name

  @staticmethod
  def input_message():
    print("message (enter newline to end):")
    sys.stdout.write('> ')
    sys.stdout.flush()
    message = sys.stdin.readline()[:-1]
    return message

  @staticmethod
  def input_iteration(prompt: str, input_func: callable) -> set:
    more = True
    result = set()
    while(more):
      item = input_func()
      if item == None:
        return None
      result.add(item)
      print(prompt)
      sys.stdout.write('> ')
      sys.stdout.flush()
      answer = sys.stdin.readline()[:-1]
      if answer != "y" and answer != "Y":
        more = False 
    return result

  def execute(self):
    """ The method for child classes to override
        and to be called in the main loop 
    """
    pass


class Registration(CmdExecution):

  def __init__(self, client):
    super().__init__(client)

  def execute(self):
    name = CmdExecution.input_username()
    if name != None:
      self.client.register(name)
    return name


class Joining(CmdExecution):

  def __init__(self, client):
    super().__init__(client)

  def execute(self):
    name = CmdExecution.input_room()
    if name == None:
      return None
    # if not self.client.disconnected:
    self.client.join(name)
    return name
    

class SendToRooms(CmdExecution):

  def __init__(self, client):
    super().__init__(client)
    self.rooms = set()
    self.message = ""

  def execute(self):
    self.rooms = CmdExecution.input_iteration(
      "send to more rooms? (y/n)", 
      CmdExecution.input_room)
    self.message = CmdExecution.input_message()
    self.client.room_message(self.rooms, self.message)
    return (self.rooms, self.message)


class SendToUsers(CmdExecution):

  def __init__(self, client):
    super().__init__(client)
    self.users = set()
    self.message = ""

  def execute(self):
    self.users = CmdExecution.input_iteration(
      "send to more users? (y/n)", 
      CmdExecution.input_username)
    self.message = CmdExecution.input_message()
    self.client.private_message(self.users, self.message)
    return (self.users, self.message)


class Disconnection(CmdExecution):

  def __init__(self, client):
    super().__init__(client)

  def execute(self):
    self.client.disconnect()


class Leave(CmdExecution):

  def __init__(self, client):
    super().__init__(client)

  def execute(self):
    name = CmdExecution.input_room()
    if name == None:
      return None
    self.client.leave(name)
    return name


class ListUsers(CmdExecution):

  def __init__(self, client):
    super().__init__(client)

  def execute(self):
    room = CmdExecution.input_room()
    if room == None:
      return None
    self.client.list_room_users(room)
    return room


class ListRooms(CmdExecution):
  def __init__(self, client):
    super().__init__(client)

  def execute(self):
    self.client.list_rooms()
    return bytes


class App:

  def __init__(self, host, port):
    self.s    = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    self.host = host
    self.port = port
    self.s.connect((self.host, self.port))
    self.cmd  = ClientCmd(self.s)

    self.status_pattern = re.compile('\$[^\$]+\$')
    self.user_unset     = True
    
    self.lock = threading.Lock()

  def parse_cmd(self, msg: str, cmd_limits: iter):
    if len(msg) >= 8:
      command_code = msg[3:8]
      if command_code not in cmd_limits:
        return Status.parse(msg)
        
      if command_code == '00001':
        return RegistrationStatus.parse(msg)
      elif command_code == '00002':
        return JoinStatus.parse(msg)
      elif command_code == '00003' or command_code == '00004':
        return MessageStatus.parse(msg)
      elif command_code == '00010':
        return DisconnectStatus.parse(msg)
      elif command_code == '00005':
        return LeaveStatus.parse(msg)
      elif command_code == '00006':
        return RoomUserListStatus.parse(msg)
      elif command_code == '00007':
        return ListRoomStatus.parse(msg)
      else:
        return Status.parse(msg)

    else:
      return Status.parse(msg)

  def print_status(self, status):
    if status.code in { 
      400, 401, 402, 403, 411, 420, 450, 451, 462, 496, 497, 498, 499 
    }:  # errors...
      status.print()
    elif status.code in { 200 }:  # success
      status.print()
    else:
      print("unknown status code...")

  def get_input_command(self):
    sys.stdout.write('>>> ')
    sys.stdout.flush()
    msg = sys.stdin.readline()[:-1]
    return msg

  def receive_server_status(self):
    data = self.s.recv(10240)
    data = data.decode(encoding="utf-8")
    status = self.status_pattern.findall(data)
    return status

  def print_prompt(self):
    print('Internet Relay Chatting Client')
    print('Copyright (c) 2020 Yiming Lin')
    print("\n\ntype in 'register' first to register a username")
    print("\nAfter registration success, the following commands are available:")
    print("join\nroom message\nprivate message\nquit\nleave\nroom users\nrooms\n\n")

  def run(self):
    disconn = self.registeration_phrase()
    if not disconn:
      self.communication_phrase()

  def registeration_phrase(self):
    manually_disconnected = False

    self.print_prompt()

    while(self.user_unset and not manually_disconnected):
      msg = self.get_input_command()
      if msg == 'quit': 
        self.s.close()
        return True

      try:
        to_execute = self.cmd.parse(msg)
        if not isinstance(to_execute, Registration):
          print("type 'register' to register a username first.")
          continue
        to_execute.execute()

        status = self.receive_server_status()
        parsed = []
        for msg in status:
          msg = msg[1:-1]
          status = self.parse_cmd(msg, { '00001' })
          parsed.append(status)
        for msg in parsed:
          if msg.code == 200 and msg.command_code == '00001':
            if isinstance(to_execute, Registration):
              self.cmd.set_username(msg.username)
              self.user_unset = False
          self.print_status(msg)
        
        if not self.user_unset:
          return False
      
      except CmdError as e:
        print(e.message)

      except ConnectionResetError as _:
        print("server disconnected.")
        manually_disconnected = True
        self.cmd.client.set_disconnected()
        self.s.close()
        return True

  def communication_phrase(self):
    signal = RunningSignal(True)
    sending = threading.Thread(target=self.__sending_thread, args=(signal,))
    receiving = threading.Thread(target=self.__receiving_thread, args=(signal,))

    sending.start()
    receiving.start()

    sending.join()
    receiving.join()
      
    print("Disconnected from server successfully.")

  def __sending_thread(self, signal: RunningSignal):
    print("\nEnter a single newline character to enter command.\n")
    while(signal.is_run()):
      msg = sys.stdin.readline()[:-1]
      if not signal.is_run(): # receiving thread terminated
        return None

      if len(msg) == 0:
        self.lock.acquire()
        msg = self.get_input_command()
        try:
          to_execute = self.cmd.parse(msg)
          to_execute.execute()   
        except CmdError as e:
          if signal.is_run():
            print(e.message)
        finally:
          self.lock.release()
        if msg == 'quit': 
          break

      else:
        print("Enter a single newline character to enter command.")

  def __receiving_thread(self, signal: RunningSignal):
    while(signal.is_run()):
      try:
        data = self.s.recv(10240) # ConnectionResetError
        if data == b'':
          break

        data = data.decode(encoding="utf-8")
        status = self.status_pattern.findall(data)
        parsed = []

        for msg in status:
          msg = msg[1:-1]
          msg = self.parse_cmd(
            msg, 
            {'00001', '00002', '00003', '00004', '00005', '00006', '00007', '00010'})
          parsed.append(msg)
          if isinstance(msg, DisconnectStatus):
            if msg.username == self.cmd.client.username:
              signal.set_stop()

        self.lock.acquire()
        for status in parsed:
          self.print_status(status)
        self.lock.release()
      
      except ConnectionResetError as _: # server crash
        print("server disconnected. Enter a new line to quit")
        self.s.close()
        self.cmd.client.set_disconnected()
        signal.set_stop()


def main():
  if len(sys.argv) < 3:
    print("USAGE: echo_client_sockets.py <HOST> <PORT>") 
    sys.exit(0)

  host = sys.argv[1]
  port = int(sys.argv[2])
  app = App(host, port)
  app.run()


if __name__ == '__main__':
  main()
