from status import (
  Status, CommandError, JoinStatus, MessageStatus, DisconnectStatus,
  LeaveStatus)

class CommandFactory:
  """ Given a byte object, parse command and argument and produce 
      relevant command object. 
  """
  def __init__(self):
    pass
  
  def produce(self, bytes, table):
    cmd  = bytes[:5]
    args = bytes[5:]
    if cmd == '00001':
      return RegistrationCommand(bytes, table)

    elif cmd == '00002':
      return JoinCommand(bytes, table)

    elif cmd == '00003':
      return UserMessageToRooms(bytes, table)

    elif cmd == '00004':
      return UserMessageToUsers(bytes, table)

    elif cmd == '00010':
      return UserDisconnect(bytes, table)

    elif cmd == '00005':
      return LeaveRoom(bytes, table)

    else:
      raise CommandError(400, msg="cannot find appropriate command")


class Msg:
  """ The abstract base class for different commands, other meaningful
      command classes will derive this class.

      Attributes:
        args (str)     : The arguments for this command message
        table (Table)  : The concurrent data structure of server
        receiver (list): The list of username that should receive message 
                         sent from server.
  """
  def __init__(self, bytes, table):
    self.args      = bytes[5:]
    self.table     = table
    self.receivers = None

  def execute(self, conn, addr):
    pass
    


class RegistrationCommand(Msg):
  """ Parse the message sent from client by getting the username 
      Execute to register user into the server database.

      Attributes:
        receiver (list): The register's username
        username (str) : The username parsed from args
  """
  def __init__(self, bytes, table):
    super().__init__(bytes, table)
    self.receivers = [ self.args ]
    self.username  = self.args

  def execute(self, conn, addr):
    if hash(addr) in self.table.conns:
      status = self.table.user_registration(self.username, conn, addr)
      self.table.enqueue_message(status, [self.table.conns[hash(addr)]])
    else:
      status = self.table.user_registration(self.username, conn, addr)
    return status


class JoinCommand(Msg):
  """ Parse the message sent from client by getting the room name. 
      If room name is found, this message is treated as a 
      join command.
      If user already in this room, a 498 error code will sent. 
      If room name is not found, this command is treated as a 
      creation commend. 
      Otherwise, error is raised. 
      The length of the room name is fixed 20 bytes in message
  """
  def __init__(self, bytes, table):
    super().__init__(bytes, table)
    self.roomName = self.args[:20]
    self.username = self.args[20:]

  def execute(self, conn, addr):
    status = self.table.join_room(self.roomName, self.username)
    self.__get_receivers(status)
    if self.receivers != {}:  
      # can find receiver, enqueue status object to all receivers;
      # otherwise, simply send back status object to connection 
      # in current thread
      self.table.enqueue_message(status, self.receivers)
    else:
      self.table.enqueue_message(status, [self.table.conns[hash(addr)]])
    return status

  def __get_receivers(self, status: Status):
    if status.code == 200:
      self.receivers = self.table.list_room_users(self.roomName)
    elif status.code == 499:
      self.receivers = {}
    else:
      self.receivers = { self.username } 


class UserMessageToRooms(Msg):
  """ Parse the message sent from client by getting the message to 
      send, the user to receive, and send message to receiver user.
      args: 
        number of rooms to send (99 max, 2 digit)
        room name (20 bytes each)
        message
  """
  def __init__(self, bytes, table):
    super().__init__(bytes, table)
    self.room_num = int(self.args[:2])
    self.rooms = self.args[2:]
    self.rooms = [self.args[2 + i*20 : 2 + (i+1)*20] for i in range(self.room_num)]
    self.message = self.args[2 + self.room_num*20:]

  def execute(self, conn, addr):
    sender_name = self.table.conns[hash(addr)]
    status = self.__valid_room_names(sender_name)
    if status.code == 200:
      receivers = self.__get_receivers()
      for room in receivers:
        status = MessageStatus(200, 'success', True, sender_name, room, '', self.message)
        self.table.enqueue_message(status, receivers[room])
    else:
      receivers = [sender_name]
      self.table.enqueue_message(status, receivers)

  def __valid_room_names(self, sender):
    for roomName in self.rooms:
      if roomName not in self.table.rooms:
        return MessageStatus(497, "Room not found", True, sender, roomName, '', self.message)
      else:
        return Status(200, "success")

  def __get_receivers(self):
    receivers = {}
    for roomName in self.rooms:
      receivers[roomName] = self.table.list_room_users(roomName)
    return receivers


class UserMessageToUsers(Msg):
  """ Parse the message sent from client by getting the message to 
      send, the user to receive, and send message to receiver user.
      The sender will also receive a copy of what it sent.
      args: 
        number of users to send (99 max, 2 digit)
        message
        00004__weirj&siofjwie&wioerj&ewroj#_____________
  """
  def __init__(self, bytes, table):
    super().__init__(bytes, table)
    self.user_num     = int(self.args[:2])
    self.message_args = self.args[2:].split('#')
    self.users         = self.message_args[0].split('&')
    self.message       = self.message_args[1]

  def execute(self, conn, addr):
    sender_name = self.table.conns[hash(addr)]
    status = self.__valid_usernames(sender_name)
    if status.code == 200:
      for user in self.users:
        status = MessageStatus(200, 'success', False, sender_name, '', user, self.message)
        self.table.enqueue_message(status, [user])
      if sender_name not in self.users:
        self.table.enqueue_message(status, [sender_name])
    else:
      receivers = [sender_name]
      self.table.enqueue_message(status, receivers)

  def __valid_usernames(self, sender):
    for username in self.users:
      if username not in self.table.users:
        return MessageStatus(496, "Message receiver not found", False, sender, '', username, self.message)
      else:
        return Status(200, "success")


class UserDisconnect(Msg):
  """ Client subjectively close the connection (close not caused by crash)
  """
  def __init__(self, bytes, table):
    super().__init__(bytes, table)
    self.username = self.args

  def execute(self, conn, addr):
    to_notify, status = self.table.user_disconnection(self.username)
    if status.code == 200:
      status = self.table.clear_user_conn(addr)
      if status.code != 200:  # internal error of this protocol
        status = DisconnectStatus(status.code, status.message, self.username, addr)
      else:                   # clear user from server db successfully
        receivers = {}        # now notify rooms that user joined before disconnected
        for room in to_notify:
          receivers[room] = self.table.list_room_users(room)
        for room in receivers:  # enqueue a message to each users in rooms
          status = DisconnectStatus(200, "success", self.username, room=room)
          self.table.enqueue_message(status, receivers[room])
    if status.code == 200:  # the returned object indicate success of curr user disconnection
      return DisconnectStatus(200, "success", self.username)
    else:
      return status


class LeaveRoom(Msg):
  """ Client leave a room. When client leave a room, the room will be notified.
      The argument format is room name followed by username 
  """
  def __init__(self, bytes, table):
    super().__init__(bytes, table)
    self.room = self.args[:20]
    self.username = self.args[20:]

  def execute(self, conn, addr):
    status = self.table.leave_room(self.room, self.username) 
    if status.code == 200:
      to_notify = self.table.list_room_users(self.room)
      to_notify.add(self.username)  # also notify leaver itself success of leaving
      self.table.enqueue_message(status, to_notify)
    else:
      self.table.enqueue_message(status, [self.table.conns[hash(addr)]])
    return status