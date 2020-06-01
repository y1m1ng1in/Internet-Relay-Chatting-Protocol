import socket
import sys
import threading
import re
from serverlib import User, Room, Table, RunningSignal
from message import (
  CommandFactory, CommandError, RegistrationCommand, UserDisconnect)
from status import(
  Status, DisconnectStatus, UserDisconnectedException, AddrError)


class Server:

  def __init__(self, port):
    self.database = Table(threading.Lock())
    self.command_factory = CommandFactory()
    self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    self.host = ''
    self.port = port
    self.s.bind((self.host, self.port))
    self.s.listen(1)

  def run(self):
    while (1):
      conn, addr = self.s.accept()
      t = threading.Thread(target=self.client_connection, args=(conn, addr))
      t.start()

  def client_connection(self, conn, addr):
    communication_init_signal, remained_msgs = self.registration_phrase(conn, addr)
    if communication_init_signal:
      self.communication_phrase(
        conn, addr, RunningSignal(communication_init_signal), remained_msgs)

  def registration_phrase(self, conn, addr):
    print('client is at', addr) 
    init_signal = True
    while(1):
      client_msg = conn.recv(1000000)

      if client_msg == b'':
        init_signal = False   # client close the conn during registration
        conn.close()
        return init_signal, []

      client_msg = client_msg.decode(encoding="utf-8")
      msg_pattern = re.compile('\$[^\$]+\$')
      msg_list = msg_pattern.findall(client_msg)
      print("addr: ", addr, "client message:", msg_list)

      for index, msg in enumerate(msg_list):
        msg = msg[1:-1]
        registration = RegistrationCommand(msg, self.database)
        status = registration.execute(conn, addr)
        conn.send(status.to_bytes())
        
        if status.code == 200:
          return init_signal, msg_list[index+1:]
          # now a user identity has been added into db
          # then go to concurrent receiving and sending stage...

  def communication_phrase(self, conn, addr, signal: RunningSignal, 
                           remained_msgs: list):
    producer_thread = threading.Thread(
      target=self.__receiving_thread, 
      args=(conn, addr, signal, remained_msgs))

    consumer_thread = threading.Thread(
      target=self.__sending_thread, 
      args=(conn, addr, signal))
    
    producer_thread.start()
    consumer_thread.start()

    producer_thread.join()
    consumer_thread.join()

    print(conn, addr, " joined")
    conn.close()

  def __receiving_thread(self, conn, addr, signal: RunningSignal, 
                         remained_msgs: list):
    while(signal.is_run()):
      try:
        client_msg = conn.recv(10240)

        if client_msg == b'':
          conn.close()
          break 

        client_msg = client_msg.decode(encoding="utf-8")
        msg_pattern = re.compile('\$[^\$]+\$')
        msg_list = msg_pattern.findall(client_msg)
        if len(remained_msgs) != 0:
          msg_list = remained_msgs + msg_list
          remained_msgs = []
        print("addr: ", addr, "client message:", msg_list)

        for msg in msg_list:
          msg = msg[1:-1]
          cmd = self.command_factory.produce(msg, self.database)
          status = cmd.execute(conn, addr)
          if isinstance(status, DisconnectStatus) and status.code == 200:
            # status.print()
            signal.set_stop()

      except CommandError as _:
        status = Status(400, "Bad command")
        self.database.enqueue_message(status, [self.database.conns[hash(addr)]])

      except ConnectionResetError as _:
        try:
          username_to_disconnect = self.database.get_username_by_addr(addr)
          diconnect_bytes = '00010' + username_to_disconnect
          disconn_cmd = UserDisconnect(diconnect_bytes, self.database)
          status = disconn_cmd.execute(conn, addr)
          signal.set_stop()
        except AddrError as _:  # another thread has already cleared the connection record
          signal.set_stop()
        

  def __sending_thread(self, conn, addr, signal: RunningSignal):
    run = True
    while(signal.is_run() and run):
      try:
        messages = self.database.flush_message_queue(addr)
        if messages == None:  # unblocked by disconnection_release
          run = False
        else:                 # unblocked by enqueu_message
          for msg in messages:  
            conn.send(msg.to_bytes())
      
      except UserDisconnectedException as _:
        run = False

      except ConnectionResetError as _:
        try:
          diconnect_bytes = '00010' + self.database.get_username_by_addr(addr)
          disconn_cmd = UserDisconnect(diconnect_bytes, self.database)
          status = disconn_cmd.execute(conn, addr)
          signal.set_stop()
          run = False
        except AddrError as _:  # another thread has already cleared the connection record
          signal.set_stop()
          run = False


def main():
  if len(sys.argv) < 2:
    print("USAGE:   echo_server_sockets.py <PORT>") 
    sys.exit(0)

  port = int(sys.argv[1])
  server = Server(port)
  server.run()


if __name__ == '__main__':
  main()