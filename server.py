import socket
import sys
import threading
from status import (
  CommandError, UserDisconnectedException, Status, RegistrationStatus, 
  JoinStatus, MessageStatus, DisconnectStatus, LeaveStatus)
from message import Msg, RegistrationCommand, JoinCommand, CommandFactory


if len(sys.argv) < 2:
  print("USAGE:   echo_server_sockets.py <PORT>") 
  sys.exit(0)


class User:

  def __init__(self, username, conn, addr):
    self.name      = username
    self.conn      = conn
    self.addr      = addr
    self.lock      = threading.Lock()  # lock for message queue
    self.has_msg   = threading.Condition(self.lock)
    self.msg_queue = []
    self.is_disconnected = False

  def get_messages(self):
    """ Block until message queue is not empty. Return all the messages
        and empty the message queue.
    """
    self.has_msg.acquire()
    try:
      while len(self.msg_queue) <= 0 and not self.is_disconnected:
        self.has_msg.wait()
      if not self.is_disconnected:
        messages = [msg for msg in self.msg_queue]
        self.msg_queue = []
        return messages
      else:
        return None
    finally:
      self.has_msg.release()
      
  def enqueue_message(self, msg: Status):
    """ Enqueue an Status object into msg_queue, also notify conditional
        variable. 
    """
    self.lock.acquire()
    self.msg_queue.append(msg)
    self.has_msg.notify()
    self.lock.release()

  def disconnection_release(self):
    self.lock.acquire()
    self.is_disconnected = True
    self.has_msg.notify()
    self.lock.release()
    

class Room:

  def __init__(self, roomName: str, creator: User):
    self.name    = roomName
    self.creator = creator
    self.users   = {}
    self.users[creator.name] = creator

  def join(self, user: User):
    self.users[user.name] = user

  def leave(self, username: str):
    """ Remove a user from user dict. If user doesn't exist in this room,
        remove nothing and return False. Otherwise, return True.
    """
    if username in self.users:
      del self.users[username]
      return True
    return False


class Table:
  """ The concurrent data structure for storeing user, room, connection
      data. 

      Attributes:
        rooms (dict)         : mapping room name to Room object
        users (dict)         : mapping user naem to User object
        conns (dict)         : mapping address to user name
        lock (threading.Lock): lock for concurrent data structure
  """
  def __init__(self, lock):
    self.rooms      = {}
    self.users      = {}
    self.conns      = {}
    self.lock       = lock
    
  def user_registration(self, username: str, conn, addr):
    self.lock.acquire()
    status = self.__valid_registration(username, addr)
    if status.code not in { 401, 402 }:
      self.users[username] = User(username, conn, addr)
      self.conns[hash(addr)] = username
      print("hash", addr, hash(addr))
      print(self)
    self.lock.release()
    return status

  def user_disconnection(self, username: str):
    """ This function remove user from all the rooms the user joined.
        This functio also remove user from user in user list in 
        server database. 
        This function does not remove conn list entry. 
    
        Returns:
          If username exist, return a set of room names to notify, and 
          a base Status object to indicate a success step.
          If username does not exist, return None and a DisconnectStatus
          object to indicate username does not exist.
    """
    self.lock.acquire()
    to_notify, status = self.__clear_disconnected_user(username)
    if status.code == 200:
      # flush_message_queue will be returned
      self.users[username].disconnection_release()  
      del self.users[username]
    self.lock.release()
    return to_notify, status

  def clear_user_conn(self, addr):
    """ Remove addr entry from conn dict. If the hash of addr does not
        exist, return a Status object with error code 462 to indicate
        failure; otherwise, remove it can return a Status object with 
        code 200. 
    """
    self.lock.acquire()
    if hash(addr) not in self.conns:
      status = Status(462, "Disconnect cannot find address")
    else:
      del self.conns[hash(addr)]
      status = Status(200, "success")
    self.lock.release()
    return status

  def join_room(self, roomName: str, username: str):
    """ Join a room or create a room based on whether room name exists.
        If username given does not have a corresponding entry in users,
        a 499 error code will be sent. 
        If user has already been in the given room, a 498 error code
        will be sent to indicated duplicated join.
        The room name length must be valided before passed in to this 
        function.
    """
    self.lock.acquire()
    status = self.__valid_username(username)
    if status.code == 499:
      status = JoinStatus(499, "User requested not found", roomName, username)
    if status.code == 200:
      if roomName not in self.rooms:
        status = self.__create_room(roomName, self.users[username])
      else:
        status = self.__valid_joining(roomName, username)
        if status.code == 200:
          self.rooms[roomName].join(self.users[username])
    print(self)
    self.lock.release()
    return status

  def leave_room(self, roomName: str, username: str):
    """ User leave a room. 

        Returns:
          If room name does not exist in server database, a 450 error code
          will be sent to indicate cannot find room to leave.
          If user does not exist in this room, a 451 error code will
          be sent to indicate user not found.
    """
    self.lock.acquire()
    status = self.__valid_username(username)
    if status.code == 200:
      if roomName not in self.rooms:
        status = LeaveStatus(450, "Room to leave not found", roomName, username)
      else:
        if self.rooms[roomName].leave(username):  # True if username exist in this room 
          status = LeaveStatus(200, "success", roomName, username)
        else:
          status = LeaveStatus(451, "User not found in room to leave", roomName, username)
    self.lock.release()
    return status

  def list_room_users(self, roomName: str):
    self.lock.acquire()
    if roomName in self.rooms:
      users = { username for username in self.rooms[roomName].users }
    self.lock.release()
    return users

  def enqueue_message(self, message: Status, receivers: list):
    for receiver in receivers:
      if receiver in self.users:
        self.users[receiver].enqueue_message(message)

  def flush_message_queue(self, addr):
    if hash(addr) not in self.conns:
      raise UserDisconnectedException
    username = self.conns[hash(addr)]
    message = self.users[username].get_messages() # return whem message available
    return message

  def has_room(self, roomName: str):
    """ Helper function for code outside of the Table object determine whether
        the room exist in current rooms dict. 
        The code outside of the Table object must use this function instead of
        access rooms dict directly without acquiring a lock.
    """
    self.lock.acquire()
    has = roomName in self.rooms
    self.lock.release()
    return has

  def has_username(self, username: str):
    """ Helper function for code outside of the Table object determine whether
        the username exist in current users dict.
        The code outside of the Table object must use this function instead of
        access users dict directly without acquiring a lock.
    """
    self.lock.acquire()
    has = username in self.users
    self.lock.release()
    return has

  def __create_room(self, roomName: str, creator: User):
    self.rooms[roomName] = Room(roomName, creator)
    return JoinStatus(200, "success", roomName, creator.name, True)

  def __valid_registration(self, username: str, addr):
    for id in self.users:
      if self.users[id].addr == addr:
        return RegistrationStatus(401, "Duplicated registration", username)
      elif self.users[id].name == username:
        return RegistrationStatus(402, "Username existed", username)
    return RegistrationStatus(200, "success", username)

  def __valid_username(self, username: str):
    if username not in self.users:
      return Status(499, "User not found")
    return Status(200, "success")

  def __valid_joining(self, roomName: str, username: str):
    if username in self.rooms[roomName].users:
      return JoinStatus(498, "Duplicated joining", roomName, username)
    return JoinStatus(200, "success", roomName, username)

  def __clear_disconnected_user(self, username):
    """ Remove all the username in all the rooms and notifiy all the rooms 

        Returns:
          If username exist, return a status code 200 to indicate user exist, 
          and a set of rooms to notify. 
          If username does not exist, return None to indicate no room to 
          notify and DisconnectStatus error code 461.
    """
    to_notify = set()
    if username not in self.users:
      return None, DisconnectStatus(461, "Disconnect user not found", username)
    for room in self.rooms:     # remove user from room
      if self.rooms[room].leave(username):
        to_notify.add(room)
    return to_notify, Status(200, "success")
    
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
  

class RunningSignal:

  def __init__(self, initial_state: bool =True):
    self.run = initial_state
    self.lock = threading.Lock()

  def set_run(self):
    self.lock.acquire()
    self.run = True
    self.lock.release()

  def set_stop(self):
    self.lock.acquire()
    self.run = False
    self.lock.release()

  def is_run(self):
    self.lock.acquire()
    result = self.run
    self.lock.release()
    return result


database        = Table(threading.Lock())
command_factory = CommandFactory()

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
host = ''
port = int(sys.argv[1])
s.bind((host, port))
s.listen(1)



def process_connection(conn, addr):
  print('client is at', addr) 
  while(1):
    client_msg = conn.recv(1000000)

    if client_msg == b'':
      conn.close()
      break

    client_msg = client_msg.decode(encoding="utf-8")
    print("addr: ", addr, "client message:", client_msg)

    registration = command_factory.produce(client_msg, database)
    status = registration.execute(conn, addr)
    conn.send(status.to_bytes())
    
    if status.code == 200:
      break 
      # now a user identity has been added into db
      # then go to concurrent receiving and sending stage...
  
  def receive_client(signal: RunningSignal):  
    while(signal.is_run()):
      client_msg = conn.recv(1000000)

      if client_msg == b'':
        conn.close()
        break 

      client_msg = client_msg.decode(encoding="utf-8")
      print("addr: ", addr, "client message:", client_msg)

      try:
        cmd = command_factory.produce(client_msg, database)
        status = cmd.execute(conn, addr)
        if isinstance(status, DisconnectStatus) and status.code == 200:
          # status.print()
          signal.set_stop()

      except CommandError as _:
        status = Status(400, "Bad command")
        database.enqueue_message(status, [database.conns[hash(addr)]])
  
  def send_to_client(signal: RunningSignal):
    run = True
    while(signal.is_run() and run):
      try:
        messages = database.flush_message_queue(addr)
        if messages == None:  # unblocked by disconnection_release
          run = False
        else:                 # unblocked by enqueu_message
          for msg in messages:  
            conn.send(msg.to_bytes())
      except UserDisconnectedException as _:
        run = False

  signal = RunningSignal(True)
  producer_thread = threading.Thread(target=receive_client, args=[signal])
  consumer_thread = threading.Thread(target=send_to_client, args=[signal])
  
  producer_thread.start()
  consumer_thread.start()

  producer_thread.join()
  consumer_thread.join()

  print(conn, addr, " joined")
  conn.close()




while (1):
  conn, addr = s.accept()
  t = threading.Thread(target=process_connection, args=(conn, addr))
  t.start()

