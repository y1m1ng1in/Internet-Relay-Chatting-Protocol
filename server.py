import socket
import sys
import threading
from status import CommandError, Status
from message import Msg, RegistrationCommand, JoinCommand, CommandFactory


if len(sys.argv) < 2:
  print("USAGE:   echo_server_sockets.py <PORT>") 
  sys.exit(0)


class User:

  def __init__(self, username, conn, addr):
    self.name      = username
    self.conn      = conn
    self.addr      = addr
    self.lock      = threading.lock()  # lock for command queue
    self.cmd_queue = []


class Room:

  def __init__(self, roomName: str, creator: User):
    self.name    = roomName
    self.creator = creator
    self.users   = {}
    self.users[creator.name] = creator

  def join(self, user: User):
    self.users[user.name] = user

  def leave(self, user: User):
    del self.users[user.name]


class Table:

  def __init__(self, lock):
    self.rooms      = {}
    self.users      = {}
    self.lock       = lock
    
  def user_registration(self, username: str, conn, addr):
    self.lock.acquire()
    status = self.__valid_registration(username, addr)
    if status.code not in { 401, 402 }:
      self.users[username] = User(username, conn, addr)
      print(self)
    self.lock.release()
    return status

  def user_disconnection(self, username: str):
    self.lock.acquire()
    self.__clear_disconnected_user(username)
    del self.users[userid]
    self.lock.release()

  def join_room(self, roomName: str, username: str):
    """ Join a room or create a room based on whether room name exists.
        If username given does not have a corresponding entry in users,
        a 499 error code will be sent. 
        If user has already been in the given room, a 412 error code
        will be sent to indicated duplicated join.
        The room name length must be valided before passed in to this 
        function.
    """
    self.lock.acquire()
    status = self.__valid_username(username)
    if status.code == 200:
      if roomName not in self.rooms:
        self.__create_room(roomName, self.users[username])
      else:
        status = self.__valid_joining(roomName, username)
        if status.code == 200:
          self.rooms[roomName].join(self.users[username])
    print(self)
    self.lock.release()
    return status

  def leave_room(self, roomName: str, user: User):
    self.lock.acquire()
    self.rooms[roomName].leave(user)
    self.lock.release()

  def __create_room(self, roomName: str, creator: User):
    self.rooms[roomName] = Room(roomName, creator)

  def __valid_registration(self, username: str, addr):
    for id in self.users:
      if self.users[id].addr == addr:
        return Status(401, "Duplicated registration")
      elif self.users[id].name == username:
        return Status(402, "Username existed")
    return Status(200, "success")

  def __valid_username(self, username: str):
    if username not in self.users:
      return Status(499, "User not found")
    return Status(200, "success")

  def __valid_joining(self, roomName: str, username: str):
    if username in self.rooms[roomName].users:
      return Status(498, "Duplicated joining")
    return Status(200, "success")

  def __clear_disconnected_user(self, userid):
    """ Remove all the userid entry in all the rooms and notifiy all the rooms 
    """
    pass

  def __str__(self):
    string = "users:\n"
    for name in self.users:
      string += self.users[name].name + "  " + str(self.users[name].addr) + '\n'
    string += "\n"
    for room in self.rooms:
      string += self.rooms[room].name + ":\n"
      for name in self.rooms[room].users:
        string += self.rooms[room].users[name].name + "  " + str(self.rooms[room].users[name].addr) + '\n'
      string += "\n"
    return string
  

database        = Table(threading.Lock())
command_factory = CommandFactory()

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
host = ''
port = int(sys.argv[1])
s.bind((host, port))
s.listen(1)

def process_connection(conn, addr):
  """ 1. produce cmd
      2. push cmd to user queue
      3. pop first cmd from user queue
      4. execute popped cmd
      5. send to user
  """
  print('client is at', addr) 
  while(1):  
    client_msg = conn.recv(1000000)

    if client_msg == b'':  # client close the connection
      conn.close()
      break
    
    client_msg = client_msg.decode(encoding="utf-8")
    print("addr: ", addr, "client message:", client_msg)

    try:
      cmd = command_factory.produce(client_msg, database)
      status = cmd.execute(conn, addr)
      conn.send(status.to_bytes())

    except CommandError as e:
      status = Status(400, "Bad command").to_bytes()
      conn.send(status)


while (1):
  conn, addr = s.accept()
  t = threading.Thread(target=process_connection, args=(conn, addr))
  t.start()

