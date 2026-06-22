cmake_minimum_required(VERSION 3.15)
project(AudioRouter CXX)

# 设置C++标准 (ASIO和现代C++最好使用C++17)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# ============ 全局UTF-8编译配置 跨平台修复中文乱码 ============
if(MSVC)
    add_compile_options(/utf-8)
elseif(MINGW)
    add_compile_options(-finput-charset=UTF-8 -fexec-charset=UTF-8)
else()
    # GCC / Clang Linux & macOS
    add_compile_options(-finput-charset=UTF-8 -fexec-charset=UTF-8)
endif()
# ===================================================================

# 包含第三方头文件和自有头文件
include_directories(third_party)
include_directories(include)

# 寻找多线程库
find_package(Threads REQUIRED)

# 添加可执行文件
add_executable(${PROJECT_NAME} 
    src/main.cpp 
    src/AudioApp.cpp
)

# 链接线程库
target_link_libraries(${PROJECT_NAME} PRIVATE Threads::Threads)

# ==========================================
# 【修复重点】针对 Windows 系统，必须链接底层的 Socket 库
# ==========================================
if(WIN32)
    target_link_libraries(${PROJECT_NAME} PRIVATE ws2_32 mswsock)
endif()

# 针对 macOS 的特殊系统库链接 (CoreAudio)
if(APPLE)
    target_link_libraries(${PROJECT_NAME} PRIVATE 
        "-framework CoreAudio" 
        "-framework CoreFoundation" 
        "-framework AudioUnit"
        "-framework AudioToolbox"
    )
endif()

# 针对 Linux 的系统库 (ALSA)
if(UNIX AND NOT APPLE)
    target_link_libraries(${PROJECT_NAME} PRIVATE dl m pthread)
endif()