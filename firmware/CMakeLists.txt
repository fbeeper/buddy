# Search for all firmware source files in the current directory
# and save the names to the FIRMWARE_SOURCES variable
aux_source_directory(./src FIRMWARE_SOURCES)

include_directories(../lib/Config)
include_directories(../lib/LCD)
include_directories(../lib/QMI8658)
include_directories(../lib/lvgl)
include_directories(./include)


# Generate link library
add_library(firmware ${FIRMWARE_SOURCES})
target_link_libraries(firmware PUBLIC Config LCD QMI8658 LVGL hardware_clocks hardware_adc hardware_dma hardware_spi)
