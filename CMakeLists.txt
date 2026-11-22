cmake_minimum_required(VERSION 3.20)
project(OkeLauncher VERSION 1.0.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

add_executable(OkeLauncher WIN32
    src/main.cpp
    resources/app.rc
)

target_compile_definitions(OkeLauncher PRIVATE
    UNICODE _UNICODE NOMINMAX WIN32_LEAN_AND_MEAN
)

if (MSVC)
    target_compile_options(OkeLauncher PRIVATE /W4 /permissive- /MP /utf-8)
    target_link_options(OkeLauncher PRIVATE /ENTRY:wWinMainCRTStartup)
else()
    target_compile_options(OkeLauncher PRIVATE -Wall -Wextra -Wno-unused-parameter)
endif()

target_link_libraries(OkeLauncher PRIVATE
    user32 gdi32 shell32 ole32
    d2d1 dwrite windowscodecs dwmapi
)
