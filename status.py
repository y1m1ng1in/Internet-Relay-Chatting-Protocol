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


class Status:
  """ Class for status code and status message
      Produce a byte object as a server response to client
  """
  def __init__(self, code: int, message: str):
    self.code = code
    self.message = message

  def to_bytes(self):
    return (str(self.code) + self.message).encode(encoding="utf-8")

  @staticmethod
  def parse(bytes):
    code = int(bytes[:3].decode(encoding="utf-8"))
    message = bytes[3:].decode(encoding="utf-8")
    return Status(code, message)