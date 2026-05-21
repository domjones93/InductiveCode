cmake_minimum_required(VERSION 3.5)

set(PROJECT_NAME "API-cpp-example")

project(${PROJECT_NAME} LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

add_executable(${PROJECT_NAME} main.cpp
    SSHDriver/SSHDriver.h SSHDriver/SSHDriver.cpp
    Commands/Commands.h Commands/Commands.cpp
)

if (WIN32)
target_link_libraries(${PROJECT_NAME} PRIVATE
    ${CMAKE_SOURCE_DIR}/libssh/libssh2.dll
    ws2_32
)
else()
target_link_libraries(${PROJECT_NAME} PRIVATE
    ${CMAKE_SOURCE_DIR}/libssh/libssh2.so.1
)
endif()

include_directories(libssh Commands)

add_custom_command(TARGET ${PROJECT_NAME} POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy ${CMAKE_SOURCE_DIR}/libssh/libssh2.dll ${CMAKE_BINARY_DIR}/libssh2.dll
)
