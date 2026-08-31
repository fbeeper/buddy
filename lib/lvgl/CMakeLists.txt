file(GLOB_RECURSE SOURCES ${CMAKE_CURRENT_LIST_DIR}/src/*.c)

add_library(LVGL ${SOURCES})

include_directories(${CMAKE_SOURCE_DIR}/firmware/include)
include_directories(${CMAKE_CURRENT_LIST_DIR})
