class Error(Exception):
  """ Base class for client errors.
  """
  pass


class CommandError(Error):
  """ Handle errors that are related to commands
  """
  def __init__(self, err_code, msg="command error"):
    self.err_code = err_code
    self.err_msg = msg

class AddrError(Error):
  """ Error of server code itself in address of client.
      The address is valid and reigstered but not presented in
      the server db.
  """
  pass

class UserDisconnectedException(Exception):
  """ Handle user disconnections
  """
  pass


class Status:
  """ Class for status code and status message
      Produce a byte object as a server response to client
  """
  def __init__(self, code: int, message: str):
    self.code = code
    self.message = message

  def to_bytes(self):
    return ('$' + str(self.code) + self.message + '$').encode(encoding="utf-8")

  @staticmethod
  def parse(bytes):
    code = int(bytes[:3])
    message = bytes[3:]
    return Status(code, message)

  def print(self):
    print(str(self.code) + " " + self.message)


class RegistrationStatus(Status):
  """ Class for server to send back to client for user registration
  """
  def __init__(self, code: int, message: str, username: str):
    super().__init__(code, message)
    self.username     = username
    self.command_code = '00001'

  def to_bytes(self):
    return ('$'
      + str(self.code)
      + self.command_code
      + self.username + '#'
      + self.message
      + '$').encode(encoding="utf-8")
  
  @staticmethod
  def parse(bytes):
    if len(bytes) < 9:
      return None
    
    code = int(bytes[:3])
    command_code = bytes[3:8]

    if command_code != '00001':
      return None
    
    rest = bytes[8:]
    args = rest.split('#')
    
    if len(args) != 2:
      return None

    username = args[0]
    message = args[1]

    # print('parsed registration status: ', code, message, username)
    return RegistrationStatus(code, message, username)
    
  def print(self):
    if self.code == 200:
      print("[Registration] " + self.username + ": " + self.message)
    else:
      print("[Error code " + str(self.code) + "] " + self.message)


class JoinStatus(Status):
  """ Class for server to send back to client for room joining & creation
  """
  def __init__(self, code: int, message: str, roomName: str, username: str, is_creation: bool = False):
    super().__init__(code, message)
    self.roomName     = roomName
    self.username     = username
    self.is_creation  = is_creation
    self.command_code = '00002'

  def to_bytes(self):
    if self.is_creation == True:
      str_creation = '1'
    else:
      str_creation = '0'
    # print(self.code, self.command_code, str_creation, self.roomName, self.username, self.message)
    return ('$' 
      + str(self.code) 
      + self.command_code
      + str_creation 
      + self.roomName 
      + self.username + '#'
      + self.message 
      + '$').encode(encoding="utf-8")

  @staticmethod
  def parse(bytes):
    if len(bytes) < 29:
      return None

    code         = int(bytes[:3])
    command_code = bytes[3:8]
    is_creation  = bytes[8]
    room         = bytes[9:29]
    
    rest = bytes[29:]
    args = rest.split('#')

    if len(args) != 2:
      return None

    username     = args[0]
    message      = args[1]

    if command_code != '00002':
      return None

    if is_creation == '1':
      creation = True
    else:
      creation = False
    
    # print('parsed join status: ', code, message, room, username, creation)
    return JoinStatus(code, message, room, username, creation)

  def print(self):
    if self.code == 200:
      if self.is_creation:
        print("[Room] " + self.roomName + " " + self.username + " created")
      else:
        print("[Room] " + self.roomName + " " + self.username + " joined")
    else:
      print("[Error code " + str(self.code) + "] " + self.message)


class MessageStatus(Status):
  """ Class for server to send back to client for message forwarding
  """
  def __init__(self, code: int, message: str, to_room: bool, sender: str,
              room: str, username: str, data: str):
    super().__init__(code, message)
    self.code         = code
    self.message      = message
    self.to_room      = to_room
    self.sender       = sender
    self.room         = room
    self.username     = username
    self.data         = data
    if self.to_room:
      self.command_code = '00003'
    else:
      self.command_code = '00004'

  def to_bytes(self):
    if self.to_room == False:
      str_to_room = '0'
    else:
      str_to_room = '1'
    if self.to_room:
      return ('$'
        + str(self.code)
        + str(self.command_code)
        + str_to_room
        + self.sender + '#'
        + self.room + '#'
        + self.data + '#'
        + self.message
        + '$').encode(encoding="utf-8")
    else:
      return ('$'
        + str(self.code)
        + str(self.command_code)
        + str_to_room
        + self.sender + "#"
        + self.username + '#'
        + self.data + '#'
        + self.message
        + '$').encode(encoding="utf-8")

  @staticmethod
  def parse(bytes):
    if len(bytes) < 14:
      return None

    code = int(bytes[:3])
    command_code = bytes[3:8]
    to_room = bytes[8]

    if to_room == '1':
      send_to_room = True
      if command_code != '00003':
        return None
    else:
      send_to_room = False
      if command_code != '00004':
        return None
    
    rest = bytes[9:]
    args = rest.split('#')

    if len(args) != 4:
      return None
    
    sender  = args[0]
    name    = args[1]
    data    = args[2]
    message = args[3]

    # print('parsed message status: ', code, message, send_to_room, sender, name, data)
    if send_to_room:
      return MessageStatus(code, message, send_to_room, sender, name, '', data)
    else:
      return MessageStatus(code, message, send_to_room, sender, '', name, data)

  def print(self):
    if self.to_room:
      if self.code == 200:
        print("[Room] " + self.room + " " + self.sender + " sent: " + self.data)
      else:
        print("[Error code " + str(self.code) + "] " + self.room + " " + self.message)
    else:
      if self.code == 200:
        print("[Private] " + self.sender + " sent to " + self.username + ": " + self.data)
      else:
        print("[Error code " + str(self.code) + "] " + self.username + " " + self.message)


class DisconnectStatus(Status):
  """ Class for server to send back to client for user disconnection 
  """
  def __init__(self, code:int, message: str, username: str, room: str = '', addr=None):
    super().__init__(code, message)
    self.username = username  # error code 461 used
    self.command_code = '00010'
    self.addr = addr  # error code 462 used 
    self.room = room  # used to notify a room that someone disconnected

  def to_bytes(self):
    if self.addr == None:
      return ('$' 
        + str(self.code) 
        + self.command_code 
        + self.username 
        + '#'
        + '#' + self.room
        + '#'+ self.message 
        + '$').encode(encoding="utf-8")
    else:
      return ('$' 
        + str(self.code) 
        + self.command_code 
        + self.username + '#'
        + self.addr + '#'
        + self.room + '#'
        + self.message 
        + '$').encode(encoding="utf-8")

  @staticmethod
  def parse(bytes):
    if len(bytes) < 11:
      return None

    code = int(bytes[:3])
    command_code = bytes[3:8]
    if command_code != '00010':
      return None
    rest = bytes[8:]
    args = rest.split('#')
    if len(args) != 4:
      return None
    name = args[0]
    addr = args[1]
    room = args[2]
    message = args[3]
    if addr == '':
      addr = None
    return DisconnectStatus(code, message, name, room, addr)

  def print(self):
    if self.code == 200:
      if self.room == '':
        print("[Disconnection] " + self.username + " disconnected.")
      else:
        print("[Room] " + self.room + " " + self.username + " disconnected.")
    else:
      print("[Error code " + str(self.code) + "] " + self.message)


class LeaveStatus(Status):

  def __init__(self, code: int, message: str, roomName: str, username: str):
    super().__init__(code, message)
    self.room = roomName
    self.username = username    
    self.command_code = '00005'

  def to_bytes(self):
    return ('$'
      + str(self.code)
      + self.command_code
      + self.room
      + self.username + '#'
      + self.message
      + '$').encode(encoding="utf-8")
  
  @staticmethod
  def parse(bytes):
    if len(bytes) < 11:
      return None

    code = int(bytes[:3])
    command_code = bytes[3:8]
    if command_code != '00005':
      return None
    room = bytes[8:28]
    rest = bytes[28:].split('#')
    if len(rest) != 2:
      return None
    username = rest[0]
    message = rest[1]

    return LeaveStatus(code, message, room, username)

  def print(self):
    if self.code == 200:
      print("[Room] " + self.room + " " + self.username + " leaved")
    else:
      print("[Error code " + str(self.code) + "] " + self.message)


class RoomUserListStatus(Status):

  def __init__(self, code: int, message: str, room: str, userlist: set):
    super().__init__(code, message)
    self.room = room
    self.userlist = userlist
    self.command_code = '00006'

  def to_bytes(self):
    str_userlist = '&'.join(self.userlist)
    return ('$'
      + str(self.code)
      + self.command_code
      + self.room
      + str_userlist
      + '#' + self.message
      + '$').encode(encoding="utf-8")

  @staticmethod
  def parse(bytes):
    if len(bytes) < 11:
      return None 
    
    code = int(bytes[:3])
    command_code = bytes[3:8]
    if command_code != '00006':
      return None 
    room = bytes[8:28]
    rest = bytes[28:]
    args = rest.split('#')
    if len(args) != 2:
      return None 
    message = args[1]
    userlist = set(args[0].split('&'))
    return RoomUserListStatus(code, message, room, userlist)

  def print(self):
    if self.code == 200:
      print("[Room] " + self.room + " " + "\nCurrent joined users:")
      for user in self.userlist:
        print(user)
    else:
      print("[Error code " + str(self.code) + "] " + self.message )


class ListRoomStatus(Status):

  def __init__(self, code: int, message: str, rooms: set):
    super().__init__(code, message)
    self.rooms = rooms
    self.command_code = '00007'

  def to_bytes(self):
    str_roomlist = '&'.join(self.rooms)
    return ('$'
      + str(self.code)
      + self.command_code
      + str_roomlist
      + '#' + self.message
      + '$').encode(encoding="utf-8")

  @staticmethod
  def parse(bytes):
    if len(bytes) < 11:
      return None 

    code = int(bytes[:3])
    command_code = bytes[3:8]
    if command_code != '00007':
      return None 
    rest = bytes[8:].split("#")
    if len(rest) != 2:
      return None 
    message = rest[1]
    rooms = set(rest[0].split('&'))
    return ListRoomStatus(code, message, rooms)

  def print(self):
    if self.code == 200:
      print("[Room] Current room list:")
      for room in self.rooms:
        print(room)
    else:
      print("[Error code " + str(self.code) + "] " + self.message)
