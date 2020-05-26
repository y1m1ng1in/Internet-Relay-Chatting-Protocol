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
  """
  def __init__(self, bytes, table):
    self.args  = bytes[5:]
    self.table = table

  def execute(self, conn, addr):
    pass


class RegistrationCommand(Msg):
  """ Parse the message sent from client by getting the username 
      Execute to register user into the server database.
  """
  def __init__(self, bytes, table):
    super().__init__(bytes, table)
    self.username = self.args

  def execute(self, conn, addr):
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
    self.roomName = self.args[:5] # length is 20
    self.username = self.args[5:]

  def execute(self, conn, addr):
    status = self.table.join_room(self.roomName, self.username)
    return status


class UserMessage(Msg):
  """ Parse the message sent from client by getting the message to 
      send, the user to receive, and send message to receiver user.
  """
  def __init__(self, bytes, table):
    super().__init__(bytes, table)

