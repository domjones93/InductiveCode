#pragma once

#include <atomic>
#include <regex>
#include <string>
#include <thread>
#include <vector>

#include "libssh2.h"

struct CommandData;

class SSHDriver
{
public:
    SSHDriver();
    ~SSHDriver();

    /**
     * @brief Connect to the controller thanks to the SSH protocol by password method. Create the session channel and send the intial command gpascci -2 and echo7.
     *        The session is configured as non blocking and a keep alive is started to keep the connection open.
     * @return true if connected and the session channel has been created else false.
     */
    bool connect();

    /**
     * @brief Close the ssh session and free all libssh2 resources.
     */
    void closeSession();

    /**
     * @brief Set the IP address to connect to the controller. You need to call this method before connect() to define the IP address.
     * @param p_ipAddress : controller IP address.
     */
    void setIpAddress(const std::string& p_ipAddress);

    /**
     * @brief Send an API command thanks to the SSH protocol.
     *        (You can find the list of the available command in this example in the file Commands/Commands.cpp).
     * @param p_command : command to send.
     * @return true if the command has been sent else false.
     */
    bool sendCommand(const std::string& p_command);

    /**
     * @brief Allow to read returned parameters by the command sent if needed.
     * @return true if response has been read else false.
     */
    bool handleCommandResponse(const CommandData& p_commandDataSent, const std::string& p_commandSent);

    /**
     * @brief Flush the channel.
     */
    void flush();

    /**
     * @brief Allow to print the read parameters after a command sending if exists.
     */
    void printReadParameters();

private:
    libssh2_socket_t m_socket;
    LIBSSH2_SESSION* m_session;
    LIBSSH2_CHANNEL* m_channel;

    std::string m_ipAddress;
    const int m_port;
    const std::string m_userName;
    const std::string m_password;

    const std::regex m_commandStatusRegex;

    bool m_isSetConfigurationCommand;

    std::thread m_sendKeepAliveThread;
    std::atomic<bool> m_keepAliveThreadRunning;
    const int m_keepAliveIntervalSeconds;

    std::vector<std::string> m_readParameters;

    /**
     * @brief Allow to send the initial command gpascii -2 and echo7. Mandatory before send command or read response.
     * @return true if the initial command has been sent else false.
     */
    bool sendInitialCommand();

    /**
     * @brief Read the ssh return after sending a command. It must contain the command sent and an acknowledge caracter (0x06 -> ACK).
     * @param p_commandDataSent : the command data sent.
     * @param p_bufferRead : a buffer to save the read content.
     * @return true if the ssh return has been read else false.
     */
    bool readResponse(const CommandData& p_commandDataSent, std::string& p_bufferRead);

    /**
     * @brief Allow to pull on c_cmd variable until the return equal 0 (command success) or inferior to 0 (on error cases).
     *        This command is not call when a status variable command is sent (command starting by s_).
     *        If the status is success,  parameters returned by the command can be read if needed (see readParameters(...)).
     * @param p_commandDataSent : command data sent.
     * @return true if the status has been read else false
     */
    bool listenCommandRunning(const CommandData& p_commandDataSent);

    /**
     * @brief Allow to get the eventual command return values.
     * @param p_commandDataSent : command data sent.
     * @return true if the parameters has been read else false.
     */
    bool readParameters(const CommandData& p_commandDataSent);

    /**
     * @brief Convenient function to extract the read parameters from the buffer.
     * @param p_readParameters : buffer of parameters read.
     */
    void splitReturnedParameters(const std::string& p_readParameters);

    /**
     * @brief Allow to start the keep alive. It's mandatory to send a keep alive to keep the connection open.
     *        The ssh server request a keep alive from the client each 30 seconds at least, otherwise the connection is closed.
     *        In addition, the ssh session is configured as non blocking mode, it's requested by the libbssh2 to send the keep alive in this case.
     *
     */
    void startKeepAliveSending();

    /**
     * @brief Stop the keep alive when closeSession() is called or when the application is closed.
     */
    void stopKeepAliveSending();
};
