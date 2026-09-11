cmake_minimum_required(VERSION 3.20)
project(FaceKeyProvider LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)

add_library(FaceKeyProvider SHARED
    src/dllmain.cpp
    src/provider.cpp
    src/credential.cpp
    src/pipe_client.cpp
    src/FaceKeyProvider.def
)

target_include_directories(FaceKeyProvider PRIVATE src)

target_link_libraries(FaceKeyProvider PRIVATE
    credui
    secur32
    shlwapi
    advapi32
)

# Output the DLL to a predictable location
set_target_properties(FaceKeyProvider PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin"
    LIBRARY_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin"
)

install(TARGETS FaceKeyProvider RUNTIME DESTINATION bin)
