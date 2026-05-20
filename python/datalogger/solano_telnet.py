import telnetlib
import time

class Command:
    def __init__(self, command_id, command_name, command_type, parameters=""):
        self.command_id = command_id
        self.command_name = command_name
        self.command_type = command_type
        self.parameters = parameters

# Define command types
class CommandType:
    ACTION = "Action"
    STATUS_COMMAND = "StatusCommand"
    STATUS_VARIABLE = "StatusVariable"
    INITIALIZATION = "Initialization"
    CONFIGURATION = "Configuration"

# Define commands
COMMANDS_INFO = [
    # Action commands
    Command("ControlOn", "c_cmd=C_CONTROLON", CommandType.ACTION),
    Command("ControlOff", "c_cmd=C_CONTROLOFF", CommandType.ACTION),
    Command("MovePTP", "c_cmd=C_MOVE_PTP", CommandType.ACTION, "c_par"),
    Command("ValidPtpMove", "c_cmd=C_VALID_PTP", CommandType.ACTION, "c_par(0)"),
    Command("Home", "c_cmd=C_HOME", CommandType.ACTION),
    Command("VirtualHome", "c_cmd=C_HOMEVIRTUAL", CommandType.ACTION),
    Command("Stop", "c_cmd=C_STOP", CommandType.ACTION),

    # Status commands
    Command("Version", "c_cmd=C_VERSION", CommandType.STATUS_COMMAND, "c_par(0),11,1"),

    # Status variables
    Command("CmdStatus", "c_cmd", CommandType.STATUS_VARIABLE),
    Command("HexStatus", "s_hexa", CommandType.STATUS_VARIABLE),
    Command("AllStatus", "s_hexa,50,1", CommandType.STATUS_VARIABLE),
    Command("AxisStatus", "s_ax_1,6,1", CommandType.STATUS_VARIABLE),
    Command("AxisPosition", "s_pos_ax_1,6,1", CommandType.STATUS_VARIABLE),
    Command("ErrorNumber", "s_err_nr", CommandType.STATUS_VARIABLE),
    Command("UtoPosition", "s_uto_tx,6,1", CommandType.STATUS_VARIABLE),
    Command("MtpPosition", "s_mtp_tx,6,1", CommandType.STATUS_VARIABLE),

    # Initialization commands
    Command("Gpascii", "gpascii -2", CommandType.INITIALIZATION),
    Command("Echo7", "echo7", CommandType.INITIALIZATION),

    # Configuration commands
    Command("SaveConfiguration", "c_cmd=C_CFG_SAVE", CommandType.CONFIGURATION, "c_par(0)"),
    Command("Speed", "c_cmd=C_CFG_SPEED", CommandType.CONFIGURATION, "c_par(0),6,1"),
    Command("WorkspaceLimits", "c_cmd=C_CFG_LIMIT", CommandType.CONFIGURATION, "c_par(0),13,1"),
    Command("AccelerationTime", "c_cmd=C_CFG_TA", CommandType.CONFIGURATION, "c_par(0),3,1"),
    Command("KinematicList", "c_cmd=C_CFG_KINLIST", CommandType.CONFIGURATION, "c_par(0),20,1"),
    Command("AxisLimit", "c_cmd=C_CFG_AXIS_LIMIT", CommandType.CONFIGURATION, "c_par(0),4,1"),
    Command("AxisParam", "c_cmd=C_CFG_AXIS_PARAM", CommandType.CONFIGURATION, "c_par(0),4,1")
]

class Solano:
    def __init__(self, host: str, port: int = 23, timeout: int = 10):
        """
        Initializes the Solano class with the host, port, and timeout.

        :param host: The IP address or hostname of the Solano hexapod.
        :param port: The port number for the Telnet connection (default is 23).
        :param timeout: The timeout for the Telnet connection in seconds (default is 10).
        """
        self.host = host
        self.port = port
        self.timeout = timeout
        self.connection = None

    def connect(self):
        """
        Establishes a Telnet connection to the Solano hexapod.
        """
        try:
            self.connection = telnetlib.Telnet(self.host, self.port, self.timeout)
            print(f"Connected to Solano at {self.host}:{self.port}")
        except Exception as e:
            print(f"Failed to connect to Solano: {e}")
            self.connection = None

    def authenticate(self, username: str = "root", password: str = "deltatau"):
        """
        Authenticates the Telnet connection with a username and password.

        :param username: The username for authentication (default is "root").
        :param password: The password for authentication (default is "deltatao").
        """
        if not self.connection:
            raise ConnectionError("Not connected to Solano. Call connect() first.")
        
        try:
            self.connection.read_until(b"login: ")
            self.connection.write(username.encode('ascii') + b'\n')
            self.connection.read_until(b"Password: ")
            self.connection.write(password.encode('ascii') + b'\n')
            shell_prompt = self.connection.read_until(b":/opt/ppmac#")  # Wait for the shell prompt
            print(shell_prompt.decode('ascii'))
            print("Authentication successful.")
        except Exception as e:
            print(f"Authentication failed: {e}")

    def send_command(self, command: str) -> str:
        """
        Sends a command to the Solano hexapod and returns the response.

        :param command: The command string to send.
        :return: The response from the hexapod.
        """
        if not self.connection:
            raise ConnectionError("Not connected to Solano. Call connect() first.")

        try:
            # Flush any unwanted content in the channel
            self.connection.read_very_eager()

            # Send the command
            self.connection.write(command.encode('ascii') + b'\r\n')
            # print(f"Command sent: {command}")

            #read and discard the echo
            # discarded = self.connection.read_until(command.encode('ascii'))
            # discarded = self.connection.read_very_eager()
            # print(f"Discarded echo: {discarded.hex()}")

            # Read the response
            response = self.connection.read_until(b'\x06', timeout=self.timeout).decode('ascii')
            #strip the command from the response
            if response.startswith(command):
                response = response[len(command):].strip()
            # print(f"Response received: {response}")


            return response
        except Exception as e:
            print(f"Failed to send command: {e}")
      
            return ""

    def handle_command_response(self, command_id: str, parameters: str = "") -> str:
        """
        Handles the command response by sending the command and processing the response.

        :param command_id: The ID of the command to execute.
        :param parameters: Optional parameters for the command.
        :return: The processed response.
        """
        command = self.find_command(command_id)
        if not self.is_command_valid(command):
            raise ValueError(f"Invalid command: {command_id}")

        full_command = command.command_name
        if command.parameters:
            full_command += f" {command.parameters}"
        if parameters:
            full_command += f" {parameters}"

        response = self.send_command(full_command)

        # Process the response if needed (e.g., check for errors or extract data)
        if "error" in response.lower():
            print(f"Error in response: {response}")
        else:
            # print(f"Command executed successfully: {response}")
            pass

        return response

    def disconnect(self):
        """
        Closes the Telnet connection to the Solano hexapod.
        """
        if self.connection:
            self.connection.close()
            print("Disconnected from Solano.")
            self.connection = None
        else:
            print("No active connection to disconnect.")

    def find_command(self, command_id):
        """
        Finds a command by its name.

        :param command_name: The name of the command to find.
        :return: The Command object if found, else None.
        """
        for command in COMMANDS_INFO:
            if command.command_id in command_id:
                return command
        return None

    def is_command_valid(self, command):
        """
        Validates a command object.

        :param command: The Command object to validate.
        :return: True if valid, False otherwise.
        """
        return command is not None and command.command_id and command.command_name and command.command_type

    def execute_command(self, command_id, parameters=None):
        """
        Executes a command by its name and returns the response.

        :param command_name: The name of the command to execute.
        :return: The response from the hexapod.
        """
        command = self.find_command(command_id)
        if not self.is_command_valid(command):
            raise ValueError(f"Invalid command: {command_id}")

        if command_id == "MovePTP":
            if parameters and len(parameters) == 6:
                # Construct the MovePTP command with the given parameters
                tx, ty, tz, rx, ry, rz = parameters
                absolute_move_command = f"c_par(0)=0"  # 0 for absolute move
                move_data_command = f"c_par(1)={tx} c_par(2)={ty} c_par(3)={tz} c_par(4)={rx} c_par(5)={ry} c_par(6)={rz}"
                move_ptp_command = f"c_cmd=C_MOVE_PTP " 
                full_command = f"{absolute_move_command} \r\n {move_data_command} \r\n {move_ptp_command}"

        
                response = self.send_command(f"c_par(0)=1 c_par(1)=0 c_par(2)={tx} c_par(3)={ty} c_par(4)={tz} c_par(5)={rx} c_par(6)={ry} c_par(7)={rz} c_cmd=C_VALID_PTP")
                time.sleep(0.05)
                response = self.send_command("c_par(0)")
                print(f"Executing command: {full_command}, move valid: {response}")
                response = self.send_command(absolute_move_command)
                response = self.send_command(move_data_command)
                response = self.send_command(move_ptp_command)
                _ = self.send_command(move_ptp_command)
            else:
                raise ValueError("Invalid parameters for MovePTP. Expected a tuple of 6 values.")
        else:
            full_command = command.command_name
            if command.parameters:
                full_command += f" {command.parameters}"
            if parameters:
                full_command += f" {parameters}"

            response = self.send_command(full_command)
        # print(f"Executing command: {full_command}")
        # response = self.send_command(absolute_move_command)
        # response = self.send_command(move_data_command)
        # response = self.send_command(move_ptp_command)

        # response = self.send_command(full_command)
        response = response.rstrip("\r\n\x06")
        
        # Split the string to make sure additional responses (split by \r\n) are removed, remaining only the last response
        response = response.split("\r\n")[-1]
        return response.rstrip()
    
    def init(self):
        """
        Initializes the Solano hexapod by sending a series of initialization commands.
        """
        self.connection.write(b"gpascii -2\n")
        time.sleep(0.25)  # Wait for the command to take effect
        ascii_response = self.connection.read_until(b"ASCII Input")  # Wait for the shell prompt
        print(ascii_response.decode('ascii'))
        self.connection.write(b"Echo7\n")
        time.sleep(0.25)  # Wait for the command to take effect

    def disconnect(self):
        """
        Closes the Telnet connection to the Solano hexapod.
        """
        if self.connection:
            self.connection.close()
            print("Disconnected from Solano.")
            self.connection = None
        else:
            print("No active connection to disconnect.")


        # Optionally, you can send other initialization commands here
        # e.g., self.execute_command("ControlOn")
        # self.execute_command("ValidPtpMove")

    def move_P2P(self, tx, ty, tz, rx, ry, rz):
        """
        Moves the hexapod to a point-to-point position.

        :param tx: Target x-coordinate.
        :param ty: Target y-coordinate.
        :param tz: Target z-coordinate.
        :param rx: Target roll angle.
        :param ry: Target pitch angle.
        :param rz: Target yaw angle.
        """
        parameters = (tx, ty, tz, rx, ry, rz)
        response = self.execute_command("MovePTP", parameters)
        # print(f"Moved to {parameters}: {response}")
        time.sleep(0.075)

        while int(self.execute_command("HexStatus")) & (1 << 4):
            # print("Waiting for move to complete...")
            time.sleep(0.075)


# Example usage:
# solano = Solano(host="192.168.1.100")
# solano.connect()
# response = solano.send_command("STATUS")
# print(response)
# solano.disconnect()

# Example usage to move the hexapod point-to-point over a list of 6-DOF locations
if __name__ == "__main__":
    # Initialize the Solano connection
    solano = Solano(host="192.168.16.220", port=23, timeout=1)
    print("Connecting to Solano hexapod...")
    solano.connect()
    if not solano.connection:
        print("Failed to connect to Solano hexapod.")
        exit()
    time.sleep(2)  # Wait for connection to stabilize
    print("Connected to Solano hexapod.")

    
    solano.authenticate()
    solano.init()

    # Define a list of 6-DOF locations (x, y, z, roll, pitch, yaw)
    locations = [
        (0, 0, 0, 0, 0, 0),
        (10, 0, 0, 0, 0, 0),
        (10, 10, 0, 0, 0, 0),
        (0, 10, 0, 0, 0, 0),
        (0, 0, 10, 0, 0, 0)
    ]

    # Control on
    solano.execute_command("ControlOn")

    # Set speed and acceleration if needed
    # solano.execute_command("c_cmd=C_CFG_SPEED c_par(1000,1000,1000,1000,1000,1000)")
    # solano.execute_command("c_cmd=C_CFG_ACCEL c_par(1000,1000,1000,1000,1000,1000)")

    # Move to the initial position
    solano.move_P2P(5, 0, 0, 0, 0, 0)

    # solano.execute_command("ValidPtpMove", parameters=(1,0,0,0,0,0))
    position_response = solano.execute_command("MtpPosition")

    print(f"Initial position: {position_response}")
    #wait for input
    input("Press Enter to start moving...")


    # Iterate through the locations and send move commands
    for location in locations:
        x, y, z, roll, pitch, yaw = location
        
        solano.move_P2P(x, y, z, roll, pitch, yaw)


        # Reas exact position after moving
        position_response = solano.execute_command("MtpPosition")
        print(f"Current position: {position_response}")

        time.sleep(1)

    solano.execute_command("ControlOff")

    # Disconnect from the Solano hexapod
    solano.disconnect()