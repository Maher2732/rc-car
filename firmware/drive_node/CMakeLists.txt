cmake_minimum_required(VERSION 3.16)
set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)

# Bluepad32 (Xbox controller over Bluetooth) is a git submodule:
#   git submodule update --init --recursive
set(BLUEPAD32_ROOT ${CMAKE_CURRENT_SOURCE_DIR}/../external/bluepad32)
set(ENV{BTSTACK_ROOT} ${BLUEPAD32_ROOT}/external/btstack)

set(EXTRA_COMPONENT_DIRS
    ${CMAKE_CURRENT_SOURCE_DIR}/../components
    ${BLUEPAD32_ROOT}/src/components
)

include($ENV{IDF_PATH}/tools/cmake/project.cmake)
include($ENV{BTSTACK_ROOT}/port/esp32/components/btstack/cmake/BTstack_project.cmake)

project(drive_node)
