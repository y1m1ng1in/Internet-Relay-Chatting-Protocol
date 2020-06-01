import socket
import sys
import time
import argparse
from multiprocessing import Process
from status import (
  Status, RegistrationStatus, JoinStatus, MessageStatus, DisconnectStatus,
  LeaveStatus, RoomUserListStatus, ListRoomStatus)
from server import RunningSignal
from clientlib import (
  EmptyUsernameException, ClientApiArgumentError, Client)
from app import CmdExecution

def join_room(client, socket, room):
  client.join(room)
  socket.recv(1024)

def send_to_rooms(client, socket, rooms, room_message, msg_id):
  client.room_message(rooms, room_message + "    // room testing iteration " + str(msg_id))
  socket.recv(1024)

def send_to_users(client, socket, users, user_message, msg_id):
  client.private_message(users, user_message + "    // private testing iteration " + str(msg_id))
  socket.recv(1024)

def leave(client, socket, users, rooms):
  for room in rooms:
    client.leave(room)

def client(host, port: int, username: str, rooms: set, users: set, message: str, 
          time_interval: int, times: int):
  # setup connection
  s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
  s.connect((host, port))    
  
  # setup client and register username
  client = Client(s)
  username = CmdExecution.room_name_sanitize(username)
  client.register(username) # assume the username is unique
  client.set_username(username)
  s.recv(1024)

  rooms = set([CmdExecution.room_name_sanitize(r) for r in rooms])
  
  for r in rooms:
    join_room(client, s, r)
  
  time.sleep(time_interval)

  for i in range(times):
    send_to_rooms(client, s, rooms, message, i+1)
    time.sleep(1)
    send_to_users(client, s, users, message, i+1)
    time.sleep(time_interval)


  leave(client, s, users, rooms)

  time.sleep(10)
  client.disconnect()

def main():
  parser = argparse.ArgumentParser()

  parser.add_argument(
    '-n', '--num', type=int, help="number of clients", default=3)

  parser.add_argument(
    '-r','--room', type=str, action='append', help='<Required> send message to room', required=True)

  parser.add_argument(
    '-p', '--private', type=str, action='append', help='send message to user')

  parser.add_argument(
    '-i', '--interval', type=int, help="time interval to send message", default=5)

  parser.add_argument(
    '-t', '--time', type=int, help="how many times send message", default=5)

  parser.add_argument(
    '-m', '--message', type=str, help="<Required> message to send", required=True)

  parser.add_argument(
    '--host', type=str, help="host", default='localhost')

  parser.add_argument(
    '--port', type=int, help="port", default=8000)

  args = parser.parse_args()

  rooms    = set(args.room)
  users    = set(args.private)
  interval = args.interval
  time     = args.time
  message  = args.message
  host     = args.host
  port     = args.port
  num      = args.num

  clients = []
  for i in range(num):
    tester = 'tester-' + str(i+1)
    clients.append(Process(target=client, args=(host, port, tester, rooms, users, message, interval, time)))

  for i in range(len(clients)):
    clients[i].start()

  for i in range(len(clients)):
    clients[i].join()

if __name__ == '__main__':
  main()