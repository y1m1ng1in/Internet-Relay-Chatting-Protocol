import socket
import sys
import re

class EmptyUsernameException(Exception):
  pass

class ClientApiArgumentError(Exception):
  """ Handle argument error when application calling 
      client api
  """
  def __init__(self, msg):
    self.msg = msg


class Client:

  def __init__(self, socket):
    self.socket = socket
    self.command_code = {
      'register'  : '00001',
      'join'      : '00002',
      'room msg'  : '00003',
      'user msg'  : '00004',
      'disconn'   : '00010',
      'leave'     : '00005',
      'room users': '00006',
      'rooms'     : '00007'
    }
    self.username = None
    self.disconnected = False

  def set_username(self, username: str):
    self.username = username

  def set_disconnected(self):
    self.disconnected = True

  def register(self, username: str):
    if not self.disconnected:
      self.socket.send(
        ('$' + self.command_code['register'] + username + '$').encode(encoding="utf-8"))

  def join(self, room: str):
    if not self.username:
      raise EmptyUsernameException
    if not self.disconnected:
      self.socket.send(
        ('$' + self.command_code['join'] + room + self.username + '$').encode(encoding="utf-8"))
    
  def room_message(self, rooms: set, msg: str):
    if not self.username:
      raise EmptyUsernameException
    if len(rooms) >= 100:
      raise ClientApiArgumentError("Must provide less than 100 room names")
    if len(rooms) < 10:
      str_room_num = '0' + str(len(rooms))
    else:
      str_room_num = str(len(rooms))
    if not self.disconnected:
      bytes = '$' + self.command_code['room msg'] + str_room_num + ''.join(rooms) + msg + '$'
      self.socket.send(bytes.encode(encoding="utf-8"))

  def private_message(self, users: set, msg: str):
    if not self.username:
      raise EmptyUsernameException
    if len(users) >= 100:
      raise ClientApiArgumentError("Must provide less than 100 user names")
    if len(users) < 10:
      str_user_num = '0' + str(len(users))
    else:
      str_user_num = str(len(users))
    if not self.disconnected:
      bytes = '$' + self.command_code['user msg'] + str_user_num + '&'.join(users) + '#' + msg + '$'
      self.socket.send(bytes.encode(encoding="utf-8"))

  def disconnect(self):
    if not self.username:
      raise EmptyUsernameException
    if not self.disconnected:
      bytes = ('$' + self.command_code['disconn'] + self.username + '$').encode(encoding="utf-8")
      self.socket.send(bytes)  

  def leave(self, room: str):
    if not self.username:
      raise EmptyUsernameException
    if not self.disconnected:
      bytes = ('$' + self.command_code['leave'] + room + self.username + '$').encode(encoding="utf-8")
      self.socket.send(bytes)

  def list_room_users(self, room: str):
    if not self.username:
      raise EmptyUsernameException
    if not self.disconnected:
      bytes = ('$' + self.command_code['room users'] + room + '$').encode(encoding="utf-8")
      self.socket.send(bytes)

  def list_rooms(self):
    if not self.username:
      raise EmptyUsernameException
    if not self.disconnected:
      bytes = ('$' + self.command_code['rooms'] + '$').encode(encoding="utf-8")
      self.socket.send(bytes)