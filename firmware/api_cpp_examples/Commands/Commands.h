#pragma once

#include <string>
#include <vector>

// In the Positioning API, there is these types of commands.
enum class CommandType : unsigned short
{
    Action,
    StatusCommand,
    StatusVariable,
    Configuration,
    Initialization,
    Invalid
};

// Command available in this example. You can add other commands here and in the COMMANDS_INFO vector defined in the cpp file.
enum class CommandId : unsigned short
{
    ControlOn = 0,
    ControlOff,
    MovePTP,
    ValidPtpMove,
    Home,
    VirtualHome,
    Stop,
    Version,
    CmdStatus,
    AllStatus,
    AxisStatus,
    ErrorNumber,
    UtoPosition,
    MtpPosition,
    Gpascii,
    Echo7,
    SaveConfiguration,
    Speed,
    WorkspaceLimits,
    AccelerationTime,
    KinematicList,
    AxisLimit,
    AxisParam,
    Invalid
};

struct CommandData
{
    CommandId commandId = CommandId::Invalid;
    std::string commandName;
    CommandType commandType = CommandType::Invalid;
    std::string readParameters;
};

extern std::vector<CommandData> COMMANDS_INFO;

/**
 * @brief Allow to find a command by name in the COMMANDS_INFO vector.
 *        If the command is not found, the returned CommandData is invalid.
 * @param p_commandName : name of the command to find
 * @return the command data found, else an empty command data
 */
CommandData findCommand(const std::string& p_commandName);

/**
 * @brief Allow to find a command by ID in the COMMANDS_INFO vector.
 *        If the command is not found an assert is triggered.
 * @param p_commandId : command ID to find
 * @return the command data found, else an empty command data
 */
CommandData findCommand(const CommandId p_commandId);

bool isCommandDataValid(const CommandData& p_commandData);
