from status import Status, CommandError

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


class UserMessage(Msg):
  """ Parse the message sent from client by getting the message to 
      send, the user to receive, and send message to receiver user.
  """
  def __init__(self, bytes, table):
    super().__init__(bytes, table)

