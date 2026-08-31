# == DO NOT EDIT THE FOLLOWING LINES for the Raspberry Pi Pico VS Code Extension to work ==
if(WIN32)
    set(USERHOME $ENV{USERPROFILE})
else()
    set(USERHOME $ENV{HOME})
endif()
set(sdkVersion 2.3.0)
set(toolchainVersion RISCV_ZCB_RPI_2_3_0_0)
set(picotoolVersion 2.3.0)
set(picoVscode ${USERHOME}/.pico-sdk/cmake/pico-vscode.cmake)
if (EXISTS ${picoVscode})
    include(${picoVscode})
endif()
# ====================================================================================
# Generated Cmake Pico project file

cmake_minimum_required(VERSION 3.13)

set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)

# Initialise pico_sdk from installed location
# (note this can come from environment, CMake cache etc)
set(PICO_BOARD pico2 CACHE STRING "Board type" FORCE)

# Pull in Raspberry Pi Pico SDK (must be before project)
include(pico_sdk_import.cmake)

if (PICO_SDK_VERSION_STRING VERSION_LESS "1.4.0")
  message(FATAL_ERROR "Raspberry Pi Pico SDK version 1.4.0 (or later) required. Your version is ${PICO_SDK_VERSION_STRING}")
endif()

project(RP2350-LCD-1.28 C CXX ASM)

# Initialise the Raspberry Pi Pico SDK
pico_sdk_init()

# Add executable. Default name is the project name, version 0.1

# Add compilation subdirectory
add_subdirectory(./lib/Config)
add_subdirectory(./lib/LCD)
add_subdirectory(./lib/QMI8658)
add_subdirectory(./lib/lvgl)
add_subdirectory(./firmware)

# Add header file directory
include_directories(./lib/Config)
include_directories(./lib/LCD)
include_directories(./lib/QMI8658)
include_directories(./lib/lvgl)
include_directories(./firmware/include)

# PICO_CONFIG: PICO_XOSC_STARTUP_DELAY_MULTIPLIER, Multiplier to lengthen xosc startup delay to accommodate slow-starting oscillators, type=int, min=1, default=1, group=hardware_xosc
add_compile_definitions(PICO_XOSC_STARTUP_DELAY_MULTIPLIER=128)
add_compile_definitions(PICO_FLASH_SPI_CLKDIV=8)

add_executable(RP2350-LCD-1.28 firmware/src/main.c)

pico_set_program_name(RP2350-LCD-1.28  "RP2350-LCD-1.28")
pico_set_program_version(RP2350-LCD-1.28 "0.1")

pico_enable_stdio_uart(RP2350-LCD-1.28 0)
pico_enable_stdio_usb(RP2350-LCD-1.28  1)
add_compile_definitions(PICO_STDIO_USB_CONNECT_WAIT_TIMEOUT_MS=3000)

# Add the standard library to the build
set(LV_CONF_PATH
  ${CMAKE_CURRENT_SOURCE_DIR}/lib/LVGL/lv_conf.h
    CACHE STRING "" FORCE)
add_compile_options(-O2)


target_link_libraries(RP2350-LCD-1.28
                      LCD
                      QMI8658
                      LVGL
                      Config
                      firmware
                      pico_stdlib
                      hardware_spi
                      hardware_i2c
                      hardware_dma
                      hardware_watchdog
                      )

# Add the standard include files to the build
target_include_directories(RP2350-LCD-1.28   PRIVATE
  ${CMAKE_CURRENT_LIST_DIR}
  # ${CMAKE_CURRENT_LIST_DIR}
  )

pico_add_extra_outputs(RP2350-LCD-1.28)
