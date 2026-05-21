#include "SSHDriver.h"

#include <chrono>
#include <iostream>
#include <thread>

#include "Commands.h"

#ifdef __linux__
    #include <arpa/inet.h>
    #include <climits>
    #include <netinet/in.h>
    #include <sys/socket.h>
    #include <unistd.h>
#endif


SSHDriver::SSHDriver() :
  m_session(nullptr),
  m_channel(nullptr),
  m_port(22),
  m_userName("root"),
  m_password("deltatau"),
  m_commandStatusRegex("^c_cmd[\\W]{2}(-?\\d+)\\W+$"),
  m_isSetConfigurationCommand(false),
  m_keepAliveIntervalSeconds(10)
{}

SSHDriver::~SSHDriver()
{
    if(m_keepAliveThreadRunning.load(std::memory_order_acquire))
    {
        stopKeepAliveSending();
    }
}

bool SSHDriver::connect()
{
    int rc = 0;
#ifdef WIN32
    WSADATA wsadata;

    rc = WSAStartup(MAKEWORD(2, 0), &wsadata);
    if(rc)
    {
        std::cout << "WSAStartup failed with error: " << rc << std::endl;
        return EXIT_FAILURE;
    }
#endif

    rc = libssh2_init(0);

    if(rc)
    {
        std::cout << "libssh2 initialization failed. Error code is: " << rc << std::endl;
        return EXIT_FAILURE;
    }

    m_socket = socket(AF_INET, SOCK_STREAM, 0);
    if(m_socket == LIBSSH2_INVALID_SOCKET)
    {
        std::cout << "Failed to create socket." << std::endl;
        libssh2_exit();
        return EXIT_FAILURE;
    }

    struct sockaddr_in sin;
    sin.sin_family = AF_INET;
    sin.sin_port = htons(m_port);
    sin.sin_addr.s_addr = inet_addr(m_ipAddress.c_str());

    std::cout << "Connecting to " << inet_ntoa(sin.sin_addr) << ":" << ntohs(sin.sin_port) << " as user " << m_userName << std::endl;

    if(::connect(m_socket, (struct sockaddr*)(&sin), sizeof(struct sockaddr_in)))
    {
        std::cout << "Failed to connect to " << m_ipAddress << ":" << m_port << std::endl;
        closeSession();
        return EXIT_FAILURE;
    }

    std::cout << "Socket connected" << std::endl;

    m_session = libssh2_session_init();

    if(m_session == nullptr)
    {
        std::cout << "Could not initialize SSH session." << std::endl;
        closeSession();
        return EXIT_FAILURE;
    }

    std::cout << "Session initialized" << std::endl;

    rc = libssh2_session_handshake(m_session, m_socket);

    if(rc != 0)
    {
        std::cout << "Failure establishing SSH session. Error code is: " << rc << std::endl;
        closeSession();
        return EXIT_FAILURE;
    }

    std::cout << "Handshake done." << std::endl;

    // Check what authentication methods are available, but in this example the password method will be chosen
    char* userauthlist = libssh2_userauth_list(m_session, m_userName.c_str(), (unsigned int)strlen(m_userName.c_str()));
    if(userauthlist != nullptr)
    {
        std::cout << "Authentication methods: " << userauthlist << ". Password will be chosen." << std::endl;
        if(strstr(userauthlist, "password"))
        {
            if(libssh2_userauth_password(m_session, m_userName.c_str(), m_password.c_str()))
            {
                std::cout << "Authentication by password failed." << std::endl;
                closeSession();
                return EXIT_FAILURE;
            }
            else
            {
                std::cout << "Authentication by password succeeded." << std::endl;
            }
        }
    }
    else
    {
        std::cout << "There is no authentification method available!" << std::endl;
        closeSession();
        return EXIT_FAILURE;
    }

    // Request a session channel on which to run a shell
    m_channel = libssh2_channel_open_session(m_session);

    if(m_channel == nullptr)
    {
        std::cout << "Unable to open a session." << std::endl;
        closeSession();
        return EXIT_FAILURE;
    }

    std::cout << "Session channel is opened." << std::endl;

    // Request a terminal with 'vanilla' terminal emulation
    rc = libssh2_channel_request_pty(m_channel, "vanilla");
    if(rc != 0)
    {
        std::cout << "Failed requesting pty. Error code is: " << rc << std::endl;
        closeSession();
        return EXIT_FAILURE;
    }

    std::cout << "Requesting pty done." << std::endl;

    rc = libssh2_channel_shell(m_channel);
    if(rc != 0)
    {
        std::cout << "Unable to request shell on allocated pty. Error code is: " << rc << std::endl;
        closeSession();
        return EXIT_FAILURE;
    }

    const int wantReply = 1;
    libssh2_keepalive_config(m_session, wantReply, m_keepAliveIntervalSeconds);
    startKeepAliveSending();

    std::cout << "Shell open." << std::endl;

    // Set the session to non blocking mode. By setting this, the keep alive sending must be handled to avoid closing the connection
    const int blockingSession = 0;
    libssh2_session_set_blocking(m_session, blockingSession);

    // Flush the welcome string in the terminal
    const int retry = 5;
    const int delayBeforeRetryMs = 200;
    for(int count = 0; count < retry; count++)
    {
        flush();
        std::this_thread::sleep_for(std::chrono::milliseconds(delayBeforeRetryMs));
    }

    // Send initial command gpascii -2 and echo7 (see Positioning API for more detail)
    if(!sendInitialCommand())
    {
        return EXIT_FAILURE;
    }

    return EXIT_SUCCESS;
}

void SSHDriver::closeSession()
{
    // Stop the keep alive
    stopKeepAliveSending();

    int rc = 0;
    const int blockingSession = 1;
    libssh2_session_set_blocking(m_session, blockingSession);
    if(m_channel != nullptr)
    {
        rc = libssh2_channel_close(m_channel);

        if(rc != 0)
        {
            std::cout << "Unable to close channel." << std::endl;
        }
        else
        {
            std::cout << "Channel closed." << std::endl;
        }
        libssh2_channel_free(m_channel);
    }

    if(m_session != nullptr)
    {
        rc = libssh2_session_disconnect(m_session, "Normal Shutdown");

        if(rc != 0)
        {
            std::cout << "Cannot disconnect the session." << std::endl;
        }
        else
        {
            std::cout << "Session disconnected" << std::endl;
        }

        libssh2_session_free(m_session);
    }

    if(m_socket != LIBSSH2_INVALID_SOCKET)
    {
#ifdef WIN32
        shutdown(m_socket, SD_BOTH);
        closesocket(m_socket);
#else
        shutdown(m_socket, SHUT_RDWR);
        close(m_socket);
#endif
    }

    std::cout << "Session closed." << std::endl;

    libssh2_exit();
}

void SSHDriver::setIpAddress(const std::string& p_ipAddress)
{
    m_ipAddress = p_ipAddress;
}

bool SSHDriver::sendCommand(const std::string& p_command)
{
    // Before sending a command, flush the communication channel in case there's unwanted content to read later.
    flush();

    // For debug
    // std::cout << "Sending command: " << p_command << std::endl;
    std::string completeCommand = p_command + "\n";

    // Send the command to the ssh server
    ssize_t rc = libssh2_channel_write(m_channel, completeCommand.c_str(), completeCommand.size());

    if(rc > 0)
    {
        // For debug
        // std::cout << rc << " bytes has been written." << std::endl;
    }
    else
    {
        std::cout << "libssh2_channel_write failed with error code: " << rc << std::endl;
        return false;
    }

    return true;
}

bool SSHDriver::handleCommandResponse(const CommandData& p_commandData, const std::string& p_commandSent)
{
    std::string parametersRead;
    bool isReadingDone = false;

    // Try to know if it's a get configuration command to read the parameters later.
    if(p_commandSent.find("c_cfg=1") != std::string::npos)
    {
        m_isSetConfigurationCommand = true;
    }
    else
    {
        m_isSetConfigurationCommand = false;
    }

    // First read the terminal return. It will be the command sent
    isReadingDone = readResponse(p_commandData, parametersRead);

    // Next wait the c_cmd return value to 0 (command is done or < 0 on errors) and read eventual returned parameters
    if(p_commandData.commandType != CommandType::StatusVariable)
    {
        isReadingDone = listenCommandRunning(p_commandData);
    }

    return isReadingDone;
}

void SSHDriver::flush()
{
    const int bufferSize = 2048;
    char buffer[bufferSize];
    memset(buffer, '\0', bufferSize);

    libssh2_channel_flush_ex(m_channel, LIBSSH2_CHANNEL_FLUSH_ALL);

    ssize_t rc = libssh2_channel_read(m_channel, buffer, bufferSize - 1);

    buffer[bufferSize - 1] = '\0';
    if(rc < 0 && rc != LIBSSH2_ERROR_EAGAIN)
    {
        std::cout << "Cannot flush the channel. Error code is: " << rc << std::endl;
    }
    else if(buffer[0] != '\0')
    {
        //        std::cout << "Flushed buffer is: " << buffer << std::endl << std::endl;
    }
}

void SSHDriver::printReadParameters()
{
    if(!m_readParameters.empty())
    {
        std::cout << "Parameters read are:" << std::endl;
        for(const std::string& parameter : m_readParameters)
        {
            std::cout << parameter << std::endl;
        }
    }

    std::cout << std::endl;
}

bool SSHDriver::sendInitialCommand()
{
    std::string readBuffer;    // Not used
    // Send gpascii command
    CommandData gpascciCommandData = findCommand(CommandId::Gpascii);
    if(!sendCommand(gpascciCommandData.commandName))
    {
        return false;
    }
    if(!readResponse(gpascciCommandData, readBuffer))
    {
        return false;
    }

    // Send echo7 command
    CommandData echoCommandData = findCommand(CommandId::Echo7);
    if(!sendCommand(echoCommandData.commandName))
    {
        return false;
    }
    if(!readResponse(echoCommandData, readBuffer))
    {
        return false;
    }

    return true;
}

bool SSHDriver::readResponse(const CommandData& p_commandDataSent, std::string& p_bufferRead)
{
    ssize_t rc = 0;
    bool readTermMatched = false;
    ssize_t bytesRead = 0;
    ssize_t lastCount = 0;
    const ssize_t bufferSize = 5120;
    char buffer[bufferSize];
    memset(buffer, '\0', bufferSize);
    std::string bufferRead;
    bool readDone = true;
    int readTermCharacter = 0x06;    // It's the ACK symbol
    const auto timeout = std::chrono::steady_clock::now() + std::chrono::seconds(4);
    bool isTimeoutExpired = false;

    m_readParameters.clear();

    if(p_commandDataSent.commandType == CommandType::Initialization)
    {
        readTermCharacter = '\n';
    }

    // Read until the end character is found and the timeout has not expired
    while(!readTermMatched && !isTimeoutExpired)
    {
        rc = libssh2_channel_read(m_channel, &buffer[bytesRead], (bufferSize - bytesRead));

        if(rc > 0)
        {
            bytesRead += rc;

            for(ssize_t i = lastCount; i < bytesRead; i++)
            {
                // Check if the character is the readTermCharacter to stop reading and the buffer returned contains at least the command name
                if(buffer[i] == readTermCharacter /* && bufferRead.size() >= p_commandData.commandName.size()*/)
                {
                    readTermMatched = true;
                    break;
                }
                bufferRead += buffer[i];
            }
            lastCount = bytesRead;
        }
        else if(rc < 0 && rc != LIBSSH2_ERROR_EAGAIN)
        {
            std::cout << "Read error. Code is: " << rc << std::endl;
            readDone = false;
            break;
        }
        isTimeoutExpired = std::chrono::steady_clock::now() > timeout;
    }

    p_bufferRead = bufferRead;

    if(isTimeoutExpired)
    {
        std::cout << "Timeout expired when trying to read response. Buffer read is: " << p_bufferRead << std::endl;
        readDone = false;
    }
    else if(readDone)
    {
        // For status variable like s_hexa, s_uto... there is no need to read returned parameters after sending the command.
        // Parameters are available here unlike configuration command
        if(p_commandDataSent.commandType == CommandType::StatusVariable && p_commandDataSent.commandId != CommandId::CmdStatus)
        {
            // Delimiter
            char delimiter = '\n';
            std::string stringSplitted;
            std::stringstream parametersToSplit(p_bufferRead);

            // Splitting the returned parameter string by the delimiter '\n'
            while(std::getline(parametersToSplit, stringSplitted, delimiter))
            {
                m_readParameters.push_back(stringSplitted);
            }
        }
    }

    return readDone;
}

bool SSHDriver::listenCommandRunning(const CommandData& p_commandDataSent)
{
    bool isProcessDone = false;
    int currentStatus = INT_MAX;
    const CommandData& ccmdCommand = findCommand(CommandId::CmdStatus);
    std::smatch ccmdMatch;
    bool conversionOk = true;
    const auto timeout = std::chrono::steady_clock::now() + std::chrono::seconds(4);
    bool isTimeoutExpired = false;
    std::string readBuffer;
    const int delayBeforeSendCommandStatusMs = 40;    // 40 milliseconds

    // While the command is not successfully interpreted (c_cmd return 0) or error (c_cmd return negative value), a pulling on c_cmd is done
    while(currentStatus > 0 && !isTimeoutExpired)
    {
        isProcessDone = sendCommand(ccmdCommand.commandName);
        if(isProcessDone)
        {
            readBuffer.clear();
            isProcessDone = readResponse(ccmdCommand, readBuffer);
            if(isProcessDone)
            {
                // Try to match the current status
                // Extract the current status from the c_cmd response (ex: c_cmd\r\n0\r\n\u0006)
                if(std::regex_match(readBuffer, ccmdMatch, m_commandStatusRegex))
                {
                    // The first sub_match is the whole string, the next sub_match is the first parenthesized expression.
                    std::ssub_match base_sub_match = ccmdMatch[1];
                    currentStatus = std::stoi(base_sub_match.str());
                }
            }
            else
            {
                std::cout << "An error occurred when trying to read c_cmd command return." << std::endl;
                break;
            }
        }
        else
        {
            std::cout << "An error occurred when trying to send c_cmd command." << std::endl;
            break;
        }

        // To avoid clogging up the controller
        std::this_thread::sleep_for(std::chrono::milliseconds(delayBeforeSendCommandStatusMs));

        isTimeoutExpired = std::chrono::steady_clock::now() > timeout;
    }

    if(isTimeoutExpired)
    {
        std::cout << "Timeout expired when trying to read c_cmd response." << std::endl;
    }
    else if(isProcessDone)
    {
        // If the command status is good, try to read eventual returned parameters
        if(currentStatus == 0)
        {
            isProcessDone = readParameters(p_commandDataSent);
        }
        else
        {
            std::cout << "Current command status is in bad state: " << currentStatus << std::endl;
        }
    }

    return isProcessDone;
}

bool SSHDriver::readParameters(const CommandData& p_commandDataSent)
{
    bool isProcessDone = true;
    // If there is parameters to read and it's not a set config command
    if(!p_commandDataSent.readParameters.empty() && !m_isSetConfigurationCommand)
    {
        std::string response;

        // Send the c_par command (ex: c_par(0),2,1)
        isProcessDone = sendCommand(p_commandDataSent.readParameters);
        if(isProcessDone)
        {
            // Read the response
            response.clear();
            isProcessDone = readResponse(p_commandDataSent, response);
            if(isProcessDone)
            {
                // Extract the returned value from the response
                splitReturnedParameters(response);
            }
            else
            {
                std::cout << "Cannot read parameters " << p_commandDataSent.readParameters << std::endl;
            }
        }
        else
        {
            std::cout << "Cannot send read parameters " << p_commandDataSent.readParameters << std::endl;
        }
    }
    else
    {
        m_readParameters.clear();
    }

    return isProcessDone;
}

void SSHDriver::splitReturnedParameters(const std::string& p_readParameters)
{
    std::stringstream parametersStream(p_readParameters);
    std::string parameter;
    m_readParameters.clear();

    while(std::getline(parametersStream, parameter, '\n'))
    {
        m_readParameters.push_back(parameter);
    }

    if(!m_readParameters.empty())
    {
        m_readParameters.erase(m_readParameters.begin());    // Delete the first string (it's the command name, for ex c_par(0),3,1)
    }
}

void SSHDriver::startKeepAliveSending()
{
    if(m_keepAliveThreadRunning.load(std::memory_order_acquire))
    {
        stopKeepAliveSending();
    }

    m_keepAliveThreadRunning.store(true, std::memory_order_release);

    m_sendKeepAliveThread = std::thread([&]() {
        while(m_keepAliveThreadRunning.load(std::memory_order_acquire))
        {
            libssh2_keepalive_send(m_session, nullptr);
            std::this_thread::sleep_for(std::chrono::seconds(m_keepAliveIntervalSeconds));
        }
    });
}

void SSHDriver::stopKeepAliveSending()
{
    m_keepAliveThreadRunning.store(false, std::memory_order_release);
    if(m_sendKeepAliveThread.joinable())
    {
        m_sendKeepAliveThread.join();
    }
}
