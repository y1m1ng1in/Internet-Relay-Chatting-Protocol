# Copyright (c) 2020 Yiming Lin <yl6@pdx.edu>

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
  """ The central server for IRC protocol. 

      The server maintains a database that stores connected clients'
      connection, user identity, and room information (see class Table
      in serverlib.py). 

      The command factory produces different kinds of subclasses of Msg
      class. Every subclass object overrides Msg's execute() method.
      The command factory produces Msg objects and execute() them, which 
      will return Status objects, those Status object then enqueue to 
      clients' message queue. Finally all the Status objects are parsed 
      into byte-object and send to each client. 

      Attributes:
        database (Table)                : a Table object which stores all 
                                          the clients, rooms information.
                                          Database will be accessed by all 
                                          the child threads of the server.
        command_factory (CommandFactory): A CommandFactory object which 
                                          produces Msgs based on message
                                          sent by connected clients.
        s (socket)                      : server socket object
        host (str)                      : host name
        port (int)                      : port number
  """
  def __init__(self, port):
    self.database = Table(threading.Lock())
    self.command_factory = CommandFactory()
    self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    self.host = ''
    self.port = port
    self.s.bind((self.host, self.port))
    self.s.listen(1)

  def run(self):
    """ The main infinite loop of server. Once a client connects to the server,
        create a new thread for that client and start that thread immediately.
    """
    while (1):
      conn, addr = self.s.accept()
      t = threading.Thread(target=self.client_connection, args=(conn, addr))
      t.start()

  def client_connection(self, conn, addr):
    """ The main function for child thread of client connection
        Registration phrase goes first. If client does not close the connection
        from registration pharse, then enter into communication phrase.
    """
    communication_init_signal, remained_msgs = self.registration_phrase(conn, addr)
    if communication_init_signal:
      self.communication_phrase(
        conn, addr, RunningSignal(communication_init_signal), remained_msgs)

  def registration_phrase(self, conn, addr):
    """ The registration phrase for the client. 
    
        If the client closes the connection during this phrase, this function
        returns False to indicate communication phrase will not be entered.
        
        Otherwise, this function receives client's message. For each message
        the client sent, this function treats message as RegistrationCommand,
        and attempting to parse. Once a valid registration occurs, in other words,
        the client's entity has been recorded into server's database successfully,
        this function returns True with a list of unexecuted commands that are
        to executed in the communication phrase.
    """
    print('client is at', addr) 
    init_signal = True
    while(1):
      client_msg = conn.recv(10240)

      if client_msg == b'':
        init_signal = False   # client close the conn during registration
        conn.close()
        return init_signal, []

      # decode the message into string. Split the message into a list of 
      # un-parsed commands (in case of multiple commands are received together)
      client_msg = client_msg.decode(encoding="utf-8")
      msg_pattern = re.compile('\$[^\$]+\$')
      msg_list = msg_pattern.findall(client_msg)
      print("addr: ", addr, "client message:", msg_list)

      # for each un-parsed command in the list, treat it as a registration command
      # (since at this point, the user entity has not been in database)
      # once a RegistrationCommand is executed and a success code 200 is returned,
      # this function returns and the rest of the commands are to execute in the
      # next phrase.
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
    """ The communication phrase for the client.

        This function will produce two child threads which are to run concurrently.
        One thread receives messages that are sent from connected client. The other 
        thread get all the messages in the user's message queue and clear the message
        queue, then convert all the message into bytes and send them back to client.
    """
    # the producer thread that generate messages that are to send to clients.
    # and enqueue them to message queue
    producer_thread = threading.Thread(
      target=self.__receiving_thread, 
      args=(conn, addr, signal, remained_msgs))

    # the consumer thread that fetch messages from client's message queue then 
    # send them back to client
    consumer_thread = threading.Thread(
      target=self.__sending_thread, 
      args=(conn, addr, signal))
    
    producer_thread.start()   
    consumer_thread.start()

    producer_thread.join()
    consumer_thread.join()

    # once the user has disconnected, close the connection.
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