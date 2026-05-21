#include "Commands.h"

#include <assert.h>
#include <regex>

// This is a non-exhaustive list. You can add commands here.
std::vector<CommandData> COMMANDS_INFO = {
  // Action commands
  {CommandId::ControlOn, "c_cmd=C_CONTROLON", CommandType::Action, ""},
  {CommandId::ControlOff, "c_cmd=C_CONTROLOFF", CommandType::Action, ""},
  {CommandId::MovePTP, "c_cmd=C_MOVE_PTP", CommandType::Action, ""},
  {CommandId::ValidPtpMove, "c_cmd=C_VALID_PTP", CommandType::Action, "c_par(0)"},
  {CommandId::Home, "c_cmd=C_HOME", CommandType::Action, ""},
  {CommandId::VirtualHome, "c_cmd=C_HOMEVIRTUAL", CommandType::Action, ""},
  {CommandId::Stop, "c_cmd=C_STOP", CommandType::Action, ""},

  // Status commands
  {CommandId::Version, "c_cmd=C_VERSION", CommandType::StatusCommand, "c_par(0),11,1"},

  // Status commands
  {CommandId::CmdStatus, "c_cmd", CommandType::StatusVariable, ""},
  {CommandId::AllStatus, "s_hexa,50,1", CommandType::StatusVariable, ""},
  {CommandId::AxisStatus, "s_ax_1,6,1 s_pos_ax_1,6,1", CommandType::StatusVariable, ""},
  {CommandId::ErrorNumber, "s_err_nr", CommandType::StatusVariable, ""},
  {CommandId::UtoPosition, "s_uto_tx,6,1", CommandType::StatusVariable, ""},
  {CommandId::MtpPosition, "s_mtp_tx,6,1", CommandType::StatusVariable, ""},

  // Init commands
  {CommandId::Gpascii, "gpascii -2", CommandType::Initialization},
  {CommandId::Echo7, "echo7", CommandType::Initialization},

  // Configuration commands
  {CommandId::SaveConfiguration, "c_cmd=C_CFG_SAVE", CommandType::Configuration, "c_par(0)"},
  {CommandId::Speed, "c_cmd=C_CFG_SPEED", CommandType::Configuration, "c_par(0),6,1"},
  {CommandId::WorkspaceLimits, "c_cmd=C_CFG_LIMIT", CommandType::Configuration, "c_par(0),13,1"},
  {CommandId::AccelerationTime, "c_cmd=C_CFG_TA", CommandType::Configuration, "c_par(0),3,1"},
  {CommandId::KinematicList, "c_cmd=C_CFG_KINLIST", CommandType::Configuration, "c_par(0),20,1"},
  {CommandId::AxisLimit, "c_cmd=C_CFG_AXIS_LIMIT", CommandType::Configuration, "c_par(0),4,1"},
  {CommandId::AxisParam, "c_cmd=C_CFG_AXIS_PARAM", CommandType::Configuration, "c_par(0),4,1"}};

CommandData findCommand(const std::string& p_commandName)
{
    CommandData commandDataFound;
    for(const CommandData& cmd : COMMANDS_INFO)
    {
        // Don't search for c_cmd only
        if(cmd.commandId != CommandId::CmdStatus)
        {
            std::regex regexCommand("\\b" + cmd.commandName + "\\b");
            std::smatch match;

            if(std::regex_search(p_commandName, match, regexCommand))
            {
                commandDataFound = cmd;
                break;
            }
        }
    }
    return commandDataFound;
}

CommandData findCommand(const CommandId p_commandId)
{
    CommandData commandDataFound;
    for(const CommandData& cmd : COMMANDS_INFO)
    {
        if(p_commandId == cmd.commandId)
        {
            commandDataFound = cmd;
            break;
        }
    }
    assert(!commandDataFound.commandName.empty());
    return commandDataFound;
}

bool isCommandDataValid(const CommandData& p_commandData)
{
    bool isCommandDataValid = true;
    if(p_commandData.commandId == CommandId::Invalid || p_commandData.commandName.empty() || p_commandData.commandType == CommandType::Invalid)
    {
        isCommandDataValid = false;
    }
    return isCommandDataValid;
}
