#include <iostream>
#include <string>

#include "Commands/Commands.h"
#include "SSHDriver/SSHDriver.h"

int main(int argc, char* argv[])
{
    SSHDriver sshDriver;

    std::string ipAddress;
    std::string userName;
    std::string password;
    std::string command;
    std::string exitString = "exit";
    bool exit = false;

    std::cout << "Please enter the controller ip address:" << std::endl;
    std::getline(std::cin, ipAddress);

    sshDriver.setIpAddress(ipAddress);

    bool isConnected = sshDriver.connect();
    if(isConnected != EXIT_SUCCESS)
    {
        std::cout << "An error occurred during connection steps." << std::endl;
        return EXIT_FAILURE;
    }

    std::cout << std::endl;

    while(!exit)
    {
        std::cout << "Please enter an API command or 'exit' to close the app:" << std::endl;
        std::getline(std::cin, command);

        if(command != exitString)
        {
            CommandData commandData = findCommand(command);

            if(!isCommandDataValid(commandData))
            {
                std::cout << "Command not found" << std::endl;
                continue;
            }

            if(!sshDriver.sendCommand(command))
            {
                std::cout << "Something went wrong during command sending" << std::endl;
            }
            else if(!sshDriver.handleCommandResponse(commandData, command))
            {
                std::cout << "Something went wrong during response reading" << std::endl;
            }
            else
            {
                sshDriver.printReadParameters();
            }
        }
        else
        {
            exit = true;
        }
    }

    sshDriver.closeSession();
}
